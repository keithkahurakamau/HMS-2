"""Per-tenant Pay Hero admin: shortcode + settlement bank CRUD + test STK.

Replaces the legacy ``mpesa_admin`` (Daraja CRUD) surface. Multi-tenants
configure:

  * their existing Safaricom PayBill / Buy-Goods till (``shortcode``,
    ``shortcode_type``),
  * the Pay Hero channel id assigned to that till at onboarding, and
  * the bank account where Pay Hero deposits proceeds.

No consumer key / secret / passkey fields — those are Daraja-only and
unnecessary now that Pay Hero is the aggregator.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.core.limiter import limiter
from app.models.billing import Invoice
from app.models.payhero import PayHeroConfig, PayHeroTransaction
from app.services.payhero_banks import PAYHERO_BANKS, is_supported, name_for
from app.services.payhero_service import (
    initiate_stk_push,
    settle_invoice_match,
)
from app.utils.encryption import encrypt_data

router = APIRouter(prefix="/api/admin/payhero", tags=["Payments — Pay Hero Admin"])


# ─── Schemas ────────────────────────────────────────────────────────────────


class PayHeroConfigSchema(BaseModel):
    shortcode: str = Field(min_length=4, max_length=20)
    shortcode_type: str = Field(default="paybill", pattern="^(paybill|till)$")
    payhero_channel_id: Optional[str] = Field(default=None, max_length=40)
    # Optional per-tenant Pay Hero API creds; blank = use platform default.
    payhero_username: Optional[str] = None
    payhero_password: Optional[str] = None
    # Settlement bank
    settlement_bank_code: str = Field(min_length=2, max_length=20)
    settlement_account_number: str = Field(min_length=4, max_length=40)
    settlement_account_name: Optional[str] = Field(default=None, max_length=120)
    # Customisation
    account_reference: str = Field(default="HMS-BILLING", max_length=50)
    transaction_desc: str = Field(default="Hospital Bill Payment", max_length=100)


class TestSTKRequest(BaseModel):
    phone_number: str = Field(min_length=9, max_length=15)


class AssignReceiptRequest(BaseModel):
    invoice_id: int


# ─── Bank catalogue ─────────────────────────────────────────────────────────


@router.get("/banks")
def list_banks(_user: dict = Depends(get_current_user)):
    """Static list of Pay Hero supported settlement banks for the UI dropdown."""
    return {"banks": PAYHERO_BANKS}


# ─── Config CRUD ────────────────────────────────────────────────────────────


def _public_view(config: PayHeroConfig | None) -> dict:
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "payhero_channel_id": config.payhero_channel_id,
        "settlement_bank_code": config.settlement_bank_code,
        "settlement_bank_name": config.settlement_bank_name,
        "settlement_account_number": config.settlement_account_number,
        "settlement_account_name": config.settlement_account_name,
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "uses_per_tenant_creds": bool(config.payhero_username_encrypted),
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


@router.get("/config")
def get_payhero_config(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
):
    """Public-safe view (no decrypted creds). Returns configured=false when
    nothing is saved yet so the frontend can render the setup card."""
    return _public_view(db.query(PayHeroConfig).first())


@router.post("/config")
def update_payhero_config(
    payload: PayHeroConfigSchema,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
):
    """Create or update the per-tenant Pay Hero configuration."""
    if not is_supported(payload.settlement_bank_code):
        raise HTTPException(400, detail="Settlement bank not in supported list — see /banks.")

    config = db.query(PayHeroConfig).first()
    if config is None:
        config = PayHeroConfig()
        db.add(config)

    config.shortcode = payload.shortcode.strip()
    config.shortcode_type = payload.shortcode_type
    config.payhero_channel_id = (payload.payhero_channel_id or "").strip() or None
    config.settlement_bank_code = payload.settlement_bank_code
    config.settlement_bank_name = name_for(payload.settlement_bank_code) or payload.settlement_bank_code
    config.settlement_account_number = payload.settlement_account_number.strip()
    config.settlement_account_name = (payload.settlement_account_name or "").strip() or None
    config.account_reference = payload.account_reference
    config.transaction_desc = payload.transaction_desc
    # Only overwrite credential fields when the operator supplied non-blank
    # values — submitting an empty string preserves what was already saved.
    if payload.payhero_username:
        config.payhero_username_encrypted = encrypt_data(payload.payhero_username)
    if payload.payhero_password:
        config.payhero_password_encrypted = encrypt_data(payload.payhero_password)
    config.updated_by = user["user_id"]
    config.is_active = True

    db.commit()
    return {"message": "Pay Hero configuration saved.", **_public_view(config)}


# ─── Test STK push ──────────────────────────────────────────────────────────


@router.post("/test-stk")
@limiter.limit("5/minute")
def test_stk(
    request: Request,
    payload: TestSTKRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
):
    """Send a real KES 1 STK push to the supplied phone to verify the
    saved shortcode + Pay Hero credentials work end-to-end."""
    config = db.query(PayHeroConfig).first()
    if not config:
        raise HTTPException(400, detail="Pay Hero is not configured yet.")
    try:
        result = initiate_stk_push(
            db,
            phone_number=payload.phone_number,
            amount=1,
            invoice_id=None,
            account_reference="TEST",
            transaction_desc="MediFleet Pay Hero test",
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


# ─── Unmatched-receipt queue ────────────────────────────────────────────────


@router.get("/unmatched")
def list_unmatched_receipts(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
    limit: int = 100,
):
    rows = (
        db.query(PayHeroTransaction)
        .filter(PayHeroTransaction.match_basis == "unmatched")
        .order_by(PayHeroTransaction.transaction_date.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "id": r.id,
            "phone_number": r.phone_number,
            "amount": float(r.amount or 0),
            "receipt_number": r.receipt_number,
            "external_reference": r.external_reference,
            "bill_ref_number": r.bill_ref_number,
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
    _user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
):
    txn = db.query(PayHeroTransaction).filter(PayHeroTransaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, detail="Receipt not found.")
    if txn.match_basis and txn.match_basis != "unmatched":
        raise HTTPException(400, detail=f"Receipt already in state '{txn.match_basis}'.")

    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(404, detail="Invoice not found.")
    if invoice.status == "Paid":
        raise HTTPException(400, detail="Invoice is already fully paid.")

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


# ─── Transactions audit ────────────────────────────────────────────────────


@router.get("/transactions")
def get_transactions(
    db: Session = Depends(get_db),
    _user: dict = Depends(RequirePermission("payhero:manage", "mpesa:manage")),
):
    transactions = (
        db.query(PayHeroTransaction)
        .order_by(PayHeroTransaction.transaction_date.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": t.id,
            "invoice_id": t.invoice_id,
            "phone_number": t.phone_number,
            "amount": float(t.amount) if t.amount else None,
            "status": t.status,
            "receipt_number": t.receipt_number,
            "payhero_reference": t.payhero_reference,
            "external_reference": t.external_reference,
            "result_desc": t.result_desc,
            "transaction_type": t.transaction_type,
            "bill_ref_number": t.bill_ref_number,
            "match_basis": t.match_basis,
            "created_at": t.transaction_date.isoformat() if t.transaction_date else None,
        }
        for t in transactions
    ]
