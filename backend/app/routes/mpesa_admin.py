"""Per-tenant M-Pesa administration: config CRUD, test STK, C2B register,
unmatched-receipt review."""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.mpesa_matcher import settle_invoice_from_c2b
from app.services.mpesa_service import (
    get_mpesa_config as _get_config,
    register_c2b_urls as _register_c2b_urls,
    test_stk_push as _test_stk_push,
)
from app.utils.encryption import encrypt_data

router = APIRouter(prefix="/api/admin/mpesa", tags=["M-Pesa Admin Settings"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class MpesaConfigSchema(BaseModel):
    paybill_number: str
    consumer_key: str
    consumer_secret: str
    passkey: str
    environment: str = Field(default="sandbox", pattern="^(sandbox|production)$")
    shortcode_type: str = Field(default="paybill", pattern="^(paybill|till)$")
    c2b_short_code: Optional[str] = None
    c2b_response_type: str = Field(default="Completed", pattern="^(Completed|Cancelled)$")
    account_reference: str = "HMS-BILLING"
    transaction_desc: str = "Hospital Bill Payment"
    kcb_account_number: Optional[str] = None


class TestSTKRequest(BaseModel):
    phone_number: str


class AssignReceiptRequest(BaseModel):
    invoice_id: int


# ─── Config CRUD ────────────────────────────────────────────────────────────

@router.get("/config")
def get_mpesa_config(db: Session = Depends(get_db),
                     user: dict = Depends(RequirePermission("users:manage"))):
    """Public-safe view (no decrypted creds). Returns configured=false
    when nothing is saved yet so the frontend can show a setup card."""
    config = db.query(MpesaConfig).first()
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "paybill_number": config.paybill_number,
        "environment": config.environment,
        "shortcode_type": config.shortcode_type,
        "c2b_short_code": config.c2b_short_code,
        "c2b_response_type": config.c2b_response_type,
        "c2b_registered_at": config.c2b_registered_at.isoformat() if config.c2b_registered_at else None,
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "kcb_account_number": config.kcb_account_number,
        "is_active": config.is_active,
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


@router.post("/config")
def update_mpesa_config(
    payload: MpesaConfigSchema,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("users:manage")),
):
    """Create or update the per-tenant M-Pesa configuration. Secrets are
    encrypted at rest. Saving new credentials clears any prior
    c2b_registered_at — the URLs need re-pushing against the new app."""
    config = db.query(MpesaConfig).first()
    creating = config is None
    if creating:
        config = MpesaConfig()
        db.add(config)

    config.paybill_number = payload.paybill_number
    config.consumer_key_encrypted = encrypt_data(payload.consumer_key)
    config.consumer_secret_encrypted = encrypt_data(payload.consumer_secret)
    config.passkey_encrypted = encrypt_data(payload.passkey)
    config.environment = payload.environment
    config.shortcode_type = payload.shortcode_type
    config.c2b_short_code = payload.c2b_short_code
    config.c2b_response_type = payload.c2b_response_type
    config.account_reference = payload.account_reference
    config.transaction_desc = payload.transaction_desc
    config.kcb_account_number = payload.kcb_account_number
    config.updated_by = user["user_id"]
    if not creating:
        # New creds invalidate the C2B URL registration we did earlier.
        config.c2b_registered_at = None

    db.commit()
    return {"message": "M-Pesa configuration saved.", "configured": True}


# ─── Test STK push ──────────────────────────────────────────────────────────

@router.post("/test-stk")
def test_stk(
    payload: TestSTKRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("users:manage")),
):
    """Send a real KES 1 STK push to the supplied phone to verify the
    saved credentials work. Daraja's response is written back to the
    config so the UI can surface success / failure without polling."""
    config = _get_config(db)
    base = os.environ.get("PUBLIC_BASE_URL") or str(request.base_url).rstrip("/")
    callback_url = f"{base}/api/payments/mpesa/callback"
    if not config.c2b_short_code and config.shortcode_type == "till":
        pass  # No-op; test_stk uses paybill_number which is required.
    return _test_stk_push(db, phone_number=payload.phone_number, callback_url=callback_url)


# ─── C2B URL registration ───────────────────────────────────────────────────

@router.post("/register-c2b")
def register_c2b(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("users:manage")),
):
    """Tell Safaricom where to send direct-to-till payments. After this
    call succeeds, any customer who pays the till directly (without an
    STK prompt from us) will trigger our /c2b/confirmation webhook."""
    base = os.environ.get("PUBLIC_BASE_URL") or str(request.base_url).rstrip("/")
    if base.startswith("http://") and "localhost" in base:
        raise HTTPException(
            400,
            detail=(
                "PUBLIC_BASE_URL must be a public HTTPS URL — Safaricom "
                "won't accept localhost/private addresses."
            ),
        )
    confirmation = f"{base}/api/payments/mpesa/c2b/confirmation"
    validation = f"{base}/api/payments/mpesa/c2b/validation"
    return _register_c2b_urls(db, confirmation_url=confirmation, validation_url=validation)


# ─── Unmatched-receipt queue ────────────────────────────────────────────────

@router.get("/unmatched")
def list_unmatched_receipts(
    db: Session = Depends(get_db),
    user: dict = Depends(RequirePermission("users:manage")),
    limit: int = 100,
):
    """Direct-to-till payments that didn't auto-match to an invoice.
    Cashier reviews and assigns them via /unmatched/{id}/assign."""
    rows = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.transaction_type == "C2B",
                MpesaTransaction.match_basis == "unmatched")
        .order_by(MpesaTransaction.transaction_date.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [
        {
            "id": r.id,
            "phone_number": r.phone_number,
            "amount": float(r.amount or 0),
            "receipt_number": r.receipt_number,
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
    user: dict = Depends(RequirePermission("users:manage")),
):
    """Cashier manually links an unmatched C2B receipt to an invoice.
    Creates the Payment row, flips invoice status, posts to the ledger
    (via the existing M-Pesa callback flow — billing.payment.mpesa key)."""
    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == txn_id).first()
    if not txn:
        raise HTTPException(404, detail="Receipt not found.")
    if txn.match_basis != "unmatched":
        raise HTTPException(400, detail=f"Receipt already in state '{txn.match_basis}'.")

    invoice = db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(404, detail="Invoice not found.")
    if invoice.status == "Paid":
        raise HTTPException(400, detail="Invoice is already fully paid.")

    settle_invoice_from_c2b(
        db, invoice=invoice, amount=Decimal(str(txn.amount or 0)),
        mpesa_receipt=txn.receipt_number,
    )
    txn.invoice_id = invoice.invoice_id
    txn.match_basis = "manual"

    # Ledger post via the same source key the auto-match flow uses.
    from app.services.accounting_posting import post_from_event
    post_from_event(
        db,
        source_key="billing.payment.mpesa",
        source_id=txn.id,
        amount=Decimal(str(txn.amount or 0)),
        memo=f"M-Pesa receipt {txn.receipt_number} (manually assigned)",
        reference=f"INV-{invoice.invoice_id}",
        user_id=current_user.get("user_id") if isinstance(current_user, dict) else None,
    )
    db.commit()
    db.refresh(txn)
    return {"status": "assigned", "invoice_id": invoice.invoice_id, "transaction_id": txn.id}


# ─── Transactions audit (kept from prior version) ──────────────────────────

@router.get("/transactions")
def get_mpesa_transactions(db: Session = Depends(get_db),
                           user: dict = Depends(RequirePermission("users:manage"))):
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
            "amount": float(t.amount) if t.amount else None,
            "status": t.status,
            "receipt_number": t.receipt_number,
            "result_desc": t.result_desc,
            "transaction_type": t.transaction_type,
            "bill_ref_number": t.bill_ref_number,
            "match_basis": t.match_basis,
            "created_at": t.transaction_date.isoformat() if t.transaction_date else None,
        }
        for t in transactions
    ]
