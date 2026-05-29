"""Superadmin subscription billing — the platform's OWN Pay Hero rail.

This is the single rail where MediFleet receives money: the superadmin
provisions MediFleet's own Pay Hero account here, charges a tenant's
subscription (STK push to the billing contact), and watches it settle live.
The per-hospital rail (payhero_superadmin / payhero_payment) stays custody-free.

Everything is gated behind ``require_superadmin`` and operates on the master DB.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.dependencies import require_superadmin
from app.core.limiter import limiter
from app.config.database import get_master_db
from app.models.platform_payhero import PlatformPayHeroConfig, PlatformPayHeroTransaction
from app.models.master import Tenant
from app.services.payhero_banks import PAYHERO_BANKS, is_supported, name_for
from app.services.platform_payhero_service import initiate_platform_stk_push
from app.utils.encryption import encrypt_data

router = APIRouter(
    prefix="/api/public/superadmin/platform-payhero",
    tags=["Superadmin — Subscription Billing"],
    dependencies=[Depends(require_superadmin)],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────


class PlatformConfigSchema(BaseModel):
    shortcode: Optional[str] = Field(default=None, max_length=20)
    shortcode_type: Optional[str] = Field(default=None, pattern="^(paybill|till)$")
    payhero_channel_id: Optional[str] = Field(default=None, max_length=40)
    payhero_username: Optional[str] = None
    payhero_password: Optional[str] = None
    payhero_webhook_secret: Optional[str] = None
    settlement_bank_code: Optional[str] = Field(default=None, max_length=20)
    settlement_account_number: Optional[str] = Field(default=None, max_length=40)
    settlement_account_name: Optional[str] = Field(default=None, max_length=120)
    account_reference: Optional[str] = Field(default=None, max_length=50)
    transaction_desc: Optional[str] = Field(default=None, max_length=100)


class ChargeRequest(BaseModel):
    tenant_id: int
    amount: float = Field(gt=0)
    phone_number: Optional[str] = Field(default=None, max_length=15)
    period_label: Optional[str] = Field(default=None, max_length=120)


class TestRequest(BaseModel):
    tenant_id: int
    phone_number: str = Field(min_length=9, max_length=15)


class BillingContactSchema(BaseModel):
    billing_contact_msisdn: Optional[str] = Field(default=None, max_length=20)
    billing_contact_name: Optional[str] = Field(default=None, max_length=120)


def _operator_view(config: PlatformPayHeroConfig | None) -> dict:
    """Never exposes the decrypted credentials or webhook secret."""
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "payhero_channel_id": config.payhero_channel_id,
        "uses_credentials": bool(config.payhero_username_encrypted),
        "uses_webhook_secret": bool(config.payhero_webhook_secret_encrypted),
        "settlement_bank_code": config.settlement_bank_code,
        "settlement_bank_name": config.settlement_bank_name,
        "settlement_account_number": config.settlement_account_number,
        "settlement_account_name": config.settlement_account_name,
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/banks")
def list_banks():
    return {"banks": PAYHERO_BANKS}


@router.get("/health")
def platform_health(master_db: Session = Depends(get_master_db)):
    """Is the subscription rail ready to collect money? Never leaks secrets."""
    config = master_db.query(PlatformPayHeroConfig).first()
    base = (settings.PUBLIC_BASE_URL or "").strip()
    is_prod = settings.is_production

    blockers: list[str] = []
    if not base:
        blockers.append("PUBLIC_BASE_URL is not set.")
    elif is_prod and not base.startswith("https://"):
        blockers.append("PUBLIC_BASE_URL must be https:// in production.")
    if not config or not config.is_active:
        blockers.append("Platform Pay Hero config missing or inactive.")
    if not (config and config.payhero_channel_id):
        blockers.append("No channel_id set — STK push will fail.")
    creds_set = bool(
        (config and config.payhero_username_encrypted)
        or (settings.PAYHERO_USERNAME.get_secret_value() and settings.PAYHERO_PASSWORD.get_secret_value())
    )
    if not creds_set:
        blockers.append("No Pay Hero credentials (config has none and platform env creds are blank).")
    secret_set = bool(
        (config and config.payhero_webhook_secret_encrypted) or settings.payhero_webhook_secret
    )
    if is_prod and not secret_set:
        blockers.append("No webhook secret (config has none and PAYHERO_WEBHOOK_SECRET is blank) — callbacks 500.")
    settlement_ok = bool(config and config.settlement_account_number)
    if not settlement_ok:
        blockers.append("No settlement bank account — funds have nowhere to land.")

    return {
        "environment": "production" if is_prod else "development",
        "ready": not blockers,
        "blockers": blockers,
        "callback_url": f"{base.rstrip('/')}/api/payments/payhero/callback/platform" if base else None,
        "config": _operator_view(config),
    }


@router.get("/config")
def get_config(master_db: Session = Depends(get_master_db)):
    return _operator_view(master_db.query(PlatformPayHeroConfig).first())


@router.post("/config")
def set_config(payload: PlatformConfigSchema, master_db: Session = Depends(get_master_db)):
    if payload.settlement_bank_code and not is_supported(payload.settlement_bank_code):
        raise HTTPException(400, detail="Settlement bank not in supported list — see /banks.")

    config = master_db.query(PlatformPayHeroConfig).first()
    if config is None:
        config = PlatformPayHeroConfig()
        master_db.add(config)

    if payload.shortcode is not None:
        config.shortcode = payload.shortcode.strip()
    if payload.shortcode_type is not None:
        config.shortcode_type = payload.shortcode_type
    if payload.payhero_channel_id is not None:
        config.payhero_channel_id = payload.payhero_channel_id.strip() or None
    if payload.settlement_bank_code:
        config.settlement_bank_code = payload.settlement_bank_code
        config.settlement_bank_name = name_for(payload.settlement_bank_code) or payload.settlement_bank_code
    if payload.settlement_account_number is not None:
        config.settlement_account_number = payload.settlement_account_number.strip()
    if payload.settlement_account_name is not None:
        config.settlement_account_name = payload.settlement_account_name.strip() or None
    if payload.account_reference is not None:
        config.account_reference = payload.account_reference
    if payload.transaction_desc is not None:
        config.transaction_desc = payload.transaction_desc
    # Secrets: only overwrite on non-blank, encrypted at rest.
    if payload.payhero_username:
        config.payhero_username_encrypted = encrypt_data(payload.payhero_username)
    if payload.payhero_password:
        config.payhero_password_encrypted = encrypt_data(payload.payhero_password)
    if payload.payhero_webhook_secret:
        config.payhero_webhook_secret_encrypted = encrypt_data(payload.payhero_webhook_secret)
    config.is_active = True

    master_db.commit()
    master_db.refresh(config)
    return {"message": "Platform Pay Hero configuration saved.", **_operator_view(config)}


@router.patch("/tenant/{tenant_id}/billing-contact")
def set_billing_contact(
    tenant_id: int, payload: BillingContactSchema, master_db: Session = Depends(get_master_db)
):
    """Store a tenant's billing MSISDN so subscription charges default to it."""
    tenant = master_db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, detail="Tenant not found.")
    if payload.billing_contact_msisdn is not None:
        tenant.billing_contact_msisdn = payload.billing_contact_msisdn.strip() or None
    if payload.billing_contact_name is not None:
        tenant.billing_contact_name = payload.billing_contact_name.strip() or None
    master_db.commit()
    return {
        "tenant_id": tenant.tenant_id,
        "billing_contact_msisdn": tenant.billing_contact_msisdn,
        "billing_contact_name": tenant.billing_contact_name,
    }


@router.post("/charge")
@limiter.limit("10/minute")
def charge_subscription(
    request: Request,
    payload: ChargeRequest,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    return initiate_platform_stk_push(
        master_db,
        tenant_id=payload.tenant_id,
        amount=payload.amount,
        phone_number=payload.phone_number,
        period_label=payload.period_label,
        initiated_by=admin.get("admin_id"),
    )


@router.post("/test-stk")
@limiter.limit("5/minute")
def test_stk(
    request: Request,
    payload: TestRequest,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    """Send a real KES 1 subscription STK push to verify the platform wiring."""
    config = master_db.query(PlatformPayHeroConfig).first()
    if not config:
        raise HTTPException(400, detail="Platform Pay Hero is not configured yet.")
    try:
        result = initiate_platform_stk_push(
            master_db,
            tenant_id=payload.tenant_id,
            amount=1,
            phone_number=payload.phone_number,
            period_label="TEST",
            initiated_by=admin.get("admin_id"),
        )
        config.last_test_at = datetime.utcnow()
        config.last_test_status = "STK Push Sent"
        config.last_test_message = (
            f"Test KES 1 STK push dispatched to {payload.phone_number}. "
            "Approve on phone to complete the test."
        )
        master_db.commit()
        return result
    except HTTPException as exc:
        config.last_test_at = datetime.utcnow()
        config.last_test_status = f"Failed ({exc.status_code})"
        config.last_test_message = str(exc.detail)[:1000]
        master_db.commit()
        raise


@router.get("/transactions")
def list_transactions(
    master_db: Session = Depends(get_master_db),
    tenant_id: Optional[int] = None,
    limit: int = 50,
):
    q = master_db.query(PlatformPayHeroTransaction)
    if tenant_id is not None:
        q = q.filter(PlatformPayHeroTransaction.tenant_id == tenant_id)
    rows = q.order_by(PlatformPayHeroTransaction.initiated_at.desc()).limit(max(1, min(limit, 200))).all()
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "phone_number": r.phone_number,
            "amount": float(r.amount or 0),
            "status": r.status,
            "receipt_number": r.receipt_number,
            "result_desc": r.result_desc,
            "period_label": r.period_label,
            "external_reference": r.external_reference,
            "initiated_at": r.initiated_at.isoformat() if r.initiated_at else None,
            "settled_at": r.settled_at.isoformat() if r.settled_at else None,
        }
        for r in rows
    ]
