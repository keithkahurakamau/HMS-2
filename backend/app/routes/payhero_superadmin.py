"""Superadmin (platform operator) Pay Hero provisioning — cross-tenant.

Only the platform operator is "linked with Pay Hero". This router lets the
superadmin set each hospital's Pay Hero aggregator wiring — the channel id and
(optional) per-tenant API credentials — plus, for onboarding convenience, the
hospital's own Safaricom till + settlement bank.

The Pay Hero config lives in the *tenant* database (``payhero_configs``), so
every endpoint opens a session against the selected tenant's DB, exactly like
the cross-tenant read endpoints in ``public.py``. Everything is gated behind
``require_superadmin``; decrypted credentials are never returned.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.config.database import get_master_db, get_tenant_engine
from app.config.settings import settings
from app.core.dependencies import require_superadmin
from app.core.limiter import limiter
from app.core.payhero_webhook import allowed_networks
from app.models.master import Tenant
from app.models.payhero import PayHeroConfig, PayHeroTransaction
from app.services.payhero_banks import PAYHERO_BANKS, is_supported, name_for
from app.services.payhero_service import initiate_stk_push
from app.utils.encryption import encrypt_data

router = APIRouter(
    prefix="/api/public/superadmin/payhero",
    tags=["Superadmin — Pay Hero"],
    dependencies=[Depends(require_superadmin)],
)


# ─── Tenant session helper ───────────────────────────────────────────────────


@contextmanager
def _tenant_session(tenant_id: int, master_db: Session) -> Iterator[Session]:
    """Open a session against a single tenant's database (validated + active)."""
    t = (
        master_db.query(Tenant)
        .filter(Tenant.tenant_id == tenant_id, Tenant.is_active == True)  # noqa: E712
        .first()
    )
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive.")
    engine = get_tenant_engine(t.db_name)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SuperPayHeroConfigSchema(BaseModel):
    # Hospital till (operator can set during onboarding; hospital can also edit
    # its own from the tenant settings page — both write the same row).
    shortcode: Optional[str] = Field(default=None, max_length=20)
    shortcode_type: Optional[str] = Field(default=None, pattern="^(paybill|till)$")
    # The Pay Hero wiring — operator-only.
    payhero_channel_id: Optional[str] = Field(default=None, max_length=40)
    payhero_username: Optional[str] = None
    payhero_password: Optional[str] = None
    # Each hospital owns its Pay Hero account and signs callbacks with its own
    # secret. Stored encrypted; write-only (never returned).
    payhero_webhook_secret: Optional[str] = None
    # Settlement bank.
    settlement_bank_code: Optional[str] = Field(default=None, max_length=20)
    settlement_account_number: Optional[str] = Field(default=None, max_length=40)
    settlement_account_name: Optional[str] = Field(default=None, max_length=120)
    # Customisation.
    account_reference: Optional[str] = Field(default=None, max_length=50)
    transaction_desc: Optional[str] = Field(default=None, max_length=100)


class SuperTestSTKRequest(BaseModel):
    phone_number: str = Field(min_length=9, max_length=15)


def _operator_view(config: PayHeroConfig | None) -> dict:
    """Operator-facing view: shows the channel id + whether creds are set, but
    never the decrypted credentials themselves."""
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "payhero_channel_id": config.payhero_channel_id,
        "uses_per_tenant_creds": bool(config.payhero_username_encrypted),
        "uses_per_tenant_webhook_secret": bool(config.payhero_webhook_secret_encrypted),
        "settlement_bank_code": config.settlement_bank_code,
        "settlement_bank_name": config.settlement_bank_name,
        "settlement_account_number": config.settlement_account_number,
        "settlement_account_name": config.settlement_account_name,
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "mpesa_active": bool(config.payhero_channel_id),
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/banks")
def list_banks():
    """Supported settlement banks for the operator dropdown."""
    return {"banks": PAYHERO_BANKS}


@router.get("/webhook-health")
def webhook_health():
    """Platform-level webhook readiness check — never exposes secret values.

    Reports which of the four callback env vars are wired so the operator can
    confirm a live deploy at a glance. Mirrors the fail-closed rules in
    ``core/payhero_webhook.verify_payhero``: in production an empty secret or
    empty CIDR allow-list makes every callback 500, so those gaps are flagged
    as blocking. The CIDR list and base URL are not secrets and are returned
    in full; the HMAC secret is reported as a boolean only.
    """
    is_prod = settings.is_production
    base = (settings.PUBLIC_BASE_URL or "").strip()
    nets = [str(n) for n in allowed_networks()]
    secret_set = bool(settings.payhero_webhook_secret)

    base_https = base.startswith("https://")
    base_ok = bool(base) and (base_https or not is_prod)

    # In production all three webhook prerequisites must be satisfied or the
    # callback path is dead; in dev they are advisory.
    blockers: list[str] = []
    if not base:
        blockers.append("PUBLIC_BASE_URL is not set — STK push will 500 before any callback.")
    elif is_prod and not base_https:
        blockers.append("PUBLIC_BASE_URL must be https:// in production.")
    if is_prod and not secret_set:
        blockers.append("PAYHERO_WEBHOOK_SECRET is empty — every callback returns 500 in production.")
    if is_prod and not nets:
        blockers.append("PAYHERO_WEBHOOK_CIDRS is empty — every callback returns 500 in production.")

    callback_template = (
        f"{base.rstrip('/')}/api/payments/payhero/callback/{{tenant_db}}" if base else None
    )

    return {
        "environment": "production" if is_prod else "development",
        "ready": not blockers,
        "blockers": blockers,
        "checks": {
            "public_base_url": {"set": bool(base), "value": base or None, "https": base_https, "ok": base_ok},
            "webhook_secret": {"set": secret_set},
            "webhook_cidrs": {"set": bool(nets), "count": len(nets), "networks": nets},
            "platform_credentials": {
                "username_set": bool(settings.PAYHERO_USERNAME.get_secret_value()),
                "password_set": bool(settings.PAYHERO_PASSWORD.get_secret_value()),
                "channel_id_set": bool(settings.PAYHERO_CHANNEL_ID),
            },
            "payhero_env": settings.PAYHERO_ENV,
        },
        "callback_url_template": callback_template,
    }


@router.get("/{tenant_id}/config")
def get_tenant_payhero(tenant_id: int, master_db: Session = Depends(get_master_db)):
    with _tenant_session(tenant_id, master_db) as db:
        return _operator_view(db.query(PayHeroConfig).first())


@router.post("/{tenant_id}/config")
def set_tenant_payhero(
    tenant_id: int,
    payload: SuperPayHeroConfigSchema,
    master_db: Session = Depends(get_master_db),
):
    """Provision a tenant's Pay Hero wiring. Every field is optional — only the
    supplied ones are written, so the operator can set the channel id without
    disturbing the till the hospital entered, and credentials are preserved
    when left blank."""
    if payload.settlement_bank_code and not is_supported(payload.settlement_bank_code):
        raise HTTPException(400, detail="Settlement bank not in supported list — see /banks.")

    with _tenant_session(tenant_id, master_db) as db:
        config = db.query(PayHeroConfig).first()
        if config is None:
            config = PayHeroConfig()
            db.add(config)

        if payload.shortcode is not None:
            config.shortcode = payload.shortcode.strip()
        if payload.shortcode_type is not None:
            config.shortcode_type = payload.shortcode_type
        if payload.payhero_channel_id is not None:
            config.payhero_channel_id = payload.payhero_channel_id.strip() or None
        if payload.settlement_bank_code:
            config.settlement_bank_code = payload.settlement_bank_code
            config.settlement_bank_name = (
                name_for(payload.settlement_bank_code) or payload.settlement_bank_code
            )
        if payload.settlement_account_number is not None:
            config.settlement_account_number = payload.settlement_account_number.strip()
        if payload.settlement_account_name is not None:
            config.settlement_account_name = payload.settlement_account_name.strip() or None
        if payload.account_reference is not None:
            config.account_reference = payload.account_reference
        if payload.transaction_desc is not None:
            config.transaction_desc = payload.transaction_desc
        # Credentials: only overwrite on non-blank, encrypted at rest.
        if payload.payhero_username:
            config.payhero_username_encrypted = encrypt_data(payload.payhero_username)
        if payload.payhero_password:
            config.payhero_password_encrypted = encrypt_data(payload.payhero_password)
        if payload.payhero_webhook_secret:
            config.payhero_webhook_secret_encrypted = encrypt_data(payload.payhero_webhook_secret)
        config.is_active = True
        # NB: updated_by is a FK to the tenant's users table — leave it untouched
        # here since the actor is a platform superadmin, not a tenant user.

        db.commit()
        db.refresh(config)
        return {"message": "Pay Hero configuration saved.", **_operator_view(config)}


@router.post("/{tenant_id}/test-stk")
@limiter.limit("5/minute")
def test_tenant_stk(
    tenant_id: int,
    payload: SuperTestSTKRequest,
    request: Request,
    master_db: Session = Depends(get_master_db),
):
    """Send a real KES 1 STK push using the tenant's saved wiring to verify it
    end-to-end. Records the outcome on the tenant's config."""
    tenant = (
        master_db.query(Tenant)
        .filter(Tenant.tenant_id == tenant_id, Tenant.is_active == True)  # noqa: E712
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive.")
    with _tenant_session(tenant_id, master_db) as db:
        config = db.query(PayHeroConfig).first()
        if not config:
            raise HTTPException(400, detail="This tenant has no Pay Hero config yet.")
        try:
            result = initiate_stk_push(
                db,
                phone_number=payload.phone_number,
                amount=1,
                invoice_id=None,
                account_reference="TEST",
                transaction_desc="MediFleet Pay Hero test",
                callback_tenant=tenant.db_name,
            )
            config.last_test_at = datetime.utcnow()
            config.last_test_status = "STK Push Sent"
            config.last_test_message = (
                f"Test KES 1 STK push dispatched to {payload.phone_number}. "
                "Customer must approve on phone to complete the test."
            )
            db.commit()
            return result
        except HTTPException as exc:
            config.last_test_at = datetime.utcnow()
            config.last_test_status = f"Failed ({exc.status_code})"
            config.last_test_message = str(exc.detail)[:1000]
            db.commit()
            raise


@router.get("/{tenant_id}/transactions")
def tenant_transactions(
    tenant_id: int,
    master_db: Session = Depends(get_master_db),
    limit: int = 50,
):
    """Recent M-Pesa transactions for operator oversight of one tenant."""
    with _tenant_session(tenant_id, master_db) as db:
        rows = (
            db.query(PayHeroTransaction)
            .order_by(PayHeroTransaction.transaction_date.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return [
            {
                "id": r.id,
                "invoice_id": r.invoice_id,
                "phone_number": r.phone_number,
                "amount": float(r.amount) if r.amount else None,
                "status": r.status,
                "receipt_number": r.receipt_number,
                "result_desc": r.result_desc,
                "transaction_type": r.transaction_type,
                "created_at": r.transaction_date.isoformat() if r.transaction_date else None,
            }
            for r in rows
        ]
