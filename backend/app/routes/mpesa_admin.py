"""Per-tenant Daraja admin: hospital-wide till config, the unmatched-receipt
queue, and the transaction audit log.

Ported from routes/payhero_admin.py's shape, not reinvented. Scope is
deliberately the hospital-wide default config (MpesaConfig.department_id IS
NULL): per-department till administration already exists at the service
layer (app/services/daraja/reservation.py's config_for,
app/services/daraja/stk.py) and is exercised at that layer by
tests/daraja/test_department_tills.py, but a per-department admin surface is
not part of this task's scope.

Every secret column is Fernet-encrypted at rest and never echoed back: the
config view returns booleans (``has_consumer_key`` etc.), never the value
itself, the same discipline routes/payhero_admin.py already documents.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.settlement import settle_invoice_match
from app.services.daraja.tokens import mint_callback_token, store_callback_token
from app.utils.encryption import encrypt_data

router = APIRouter(prefix="/api/admin/mpesa", tags=["Payments, M-Pesa Admin"])

# Reused from the Pay Hero admin surface: no dedicated write codename exists
# for the Daraja rail (the earlier "mpesa:manage" codename was renamed to
# "payhero:manage" by migration aa2b7c3d8e91, see
# app/core/dependencies.py's RequirePermission docstring), and both
# integrations configure the same underlying capability — collecting M-Pesa
# at the till — until Task 12 removes Pay Hero. Introducing a second,
# parallel write codename here would let a role hold one without the other
# for no operational reason.
_MANAGE = "payhero:manage"
_READ_ANY = ("payhero:manage", "mpesa:read")


# ─── Schemas ────────────────────────────────────────────────────────────────


class MpesaConfigSchema(BaseModel):
    shortcode: str = Field(min_length=4, max_length=20)
    shortcode_type: str = Field(default="paybill", pattern="^(paybill|till)$")
    environment: str = Field(default="sandbox", pattern="^(sandbox|production)$")

    # Secrets: optional on every save. Blank/omitted means "leave the
    # currently stored value alone" — a config update must never be able to
    # wipe a working credential just because the form round-tripped it blank.
    consumer_key: Optional[str] = Field(default=None, max_length=255)
    consumer_secret: Optional[str] = Field(default=None, max_length=255)
    passkey: Optional[str] = Field(default=None, max_length=255)
    initiator_name: Optional[str] = Field(default=None, max_length=80)
    initiator_password: Optional[str] = Field(default=None, max_length=255)

    refunds_enabled: bool = False
    refund_max_amount: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("10000.00")
    refund_daily_cap: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("50000.00")
    refund_dual_approval_above: condecimal(gt=0, max_digits=12, decimal_places=2) = Decimal("5000.00")

    account_reference: str = Field(default="HMS-BILLING", max_length=50)
    transaction_desc: str = Field(default="Hospital Bill Payment", max_length=100)


class AssignReceiptRequest(BaseModel):
    invoice_id: int


# ─── Config CRUD ────────────────────────────────────────────────────────────


def _default_config(db: Session) -> Optional[MpesaConfig]:
    return db.query(MpesaConfig).filter(MpesaConfig.department_id.is_(None)).first()


def _public_view(config: Optional[MpesaConfig]) -> dict:
    if not config:
        return {"configured": False, "mpesa_active": False}
    return {
        "configured": True,
        "mpesa_active": bool(
            config.consumer_key_encrypted
            and config.consumer_secret_encrypted
            and config.passkey_encrypted
            and config.is_active
        ),
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "environment": config.environment,
        "has_consumer_key": bool(config.consumer_key_encrypted),
        "has_consumer_secret": bool(config.consumer_secret_encrypted),
        "has_passkey": bool(config.passkey_encrypted),
        "initiator_name": config.initiator_name,
        "has_initiator_password": bool(config.initiator_password_encrypted),
        "callback_token_configured": bool(config.callback_token_encrypted),
        "refunds_enabled": config.refunds_enabled,
        "refund_max_amount": str(config.refund_max_amount),
        "refund_daily_cap": str(config.refund_daily_cap),
        "refund_dual_approval_above": str(config.refund_dual_approval_above),
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "c2b_urls_registered_at": (
            config.c2b_urls_registered_at.isoformat() if config.c2b_urls_registered_at else None
        ),
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


@router.get("/config")
def get_mpesa_config(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
):
    return _public_view(_default_config(db))


@router.post("/config")
def update_mpesa_config(
    payload: MpesaConfigSchema,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission(_MANAGE)),
):
    config = _default_config(db)
    if config is None:
        config = MpesaConfig(department_id=None)
        db.add(config)

    config.shortcode = payload.shortcode.strip()
    config.shortcode_type = payload.shortcode_type
    config.environment = payload.environment
    if payload.consumer_key:
        config.consumer_key_encrypted = encrypt_data(payload.consumer_key.strip())
    if payload.consumer_secret:
        config.consumer_secret_encrypted = encrypt_data(payload.consumer_secret.strip())
    if payload.passkey:
        config.passkey_encrypted = encrypt_data(payload.passkey.strip())
    if payload.initiator_name:
        config.initiator_name = payload.initiator_name.strip()
    if payload.initiator_password:
        config.initiator_password_encrypted = encrypt_data(payload.initiator_password.strip())

    config.refunds_enabled = payload.refunds_enabled
    config.refund_max_amount = payload.refund_max_amount
    config.refund_daily_cap = payload.refund_daily_cap
    config.refund_dual_approval_above = payload.refund_dual_approval_above
    config.account_reference = payload.account_reference
    config.transaction_desc = payload.transaction_desc
    config.updated_by = user["user_id"]
    config.is_active = True

    # Mint the callback token pair on first save only: rotating it on every
    # unrelated field edit would silently invalidate every STK/C2B/status
    # URL already registered with Safaricom for this till.
    if not config.callback_token_encrypted:
        store_callback_token(config, mint_callback_token())

    db.commit()
    return {"message": "M-Pesa configuration saved.", **_public_view(config)}


# ─── Unmatched-receipt queue ────────────────────────────────────────────────


@router.get("/unmatched")
def list_unmatched_receipts(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
    limit: int = 100,
):
    rows = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.match_basis == "unmatched")
        .order_by(MpesaTransaction.transaction_date.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "id": r.id,
            "phone_number": r.phone_number,
            "amount": str(r.amount or 0),
            "receipt_number": r.receipt_number,
            "bill_ref_number": r.bill_ref_number,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            "transaction_date": r.transaction_date.isoformat() if r.transaction_date else None,
        }
        for r in rows
    ]


@router.post("/unmatched/{txn_id}/assign")
def assign_unmatched_receipt(
    txn_id: int,
    payload: AssignReceiptRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _user: dict = Depends(RequirePermission(_MANAGE)),
):
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if txn.match_basis and txn.match_basis != "unmatched":
        raise HTTPException(status_code=400, detail=f"Receipt already in state '{txn.match_basis}'.")

    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == "Paid":
        raise HTTPException(status_code=400, detail="Invoice is already fully paid.")

    txn.status = "Success"
    settle_invoice_match(
        db,
        invoice=invoice,
        txn=txn,
        match_basis="manual",
        user_id=current_user.get("user_id"),
    )
    db.commit()
    db.refresh(txn)
    return {"status": "assigned", "invoice_id": invoice.invoice_id, "transaction_id": txn.id}


# ─── Transactions audit ─────────────────────────────────────────────────────


@router.get("/transactions")
def get_transactions(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission(*_READ_ANY)),
):
    transactions = (
        db.query(MpesaTransaction)
        .order_by(MpesaTransaction.transaction_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "invoice_id": t.invoice_id,
            "phone_number": t.phone_number,
            "amount": str(t.amount) if t.amount is not None else None,
            "status": t.status,
            "receipt_number": t.receipt_number,
            "external_reference": t.external_reference,
            "result_desc": t.result_desc,
            "transaction_type": t.transaction_type,
            "bill_ref_number": t.bill_ref_number,
            "match_basis": t.match_basis,
            "verified_at": t.verified_at.isoformat() if t.verified_at else None,
            "created_at": t.transaction_date.isoformat() if t.transaction_date else None,
        }
        for t in transactions
    ]
