"""Superadmin Daraja payments: charge a tenant's subscription, and see what
happened.

Counterpart to app/routes/mpesa_payment.py's authenticated STK-push surface,
and sibling to app/routes/platform_payhero.py's /charge and /transactions
(the same job for the older Pay Hero rail). Config CRUD lives in
app/routes/mpesa_superadmin.py; this file is the money-moving half of that
same split.

GET /transactions is also the fix for a defect a review found in
app/services/daraja/platform.py: a quarantined subscription charge used to
have no route listing it at all, so it sat in platform_mpesa_transactions
invisible to everyone. This route lists every status, quarantined included.

Everything is gated behind require_superadmin and operates on the master DB.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, condecimal
from sqlalchemy.orm import Session

from app.config.database import get_master_db
from app.core.dependencies import require_superadmin
from app.core.limiter import limiter
from app.models.platform_mpesa import PlatformMpesaTransaction
from app.services.daraja.platform_stk import initiate_platform_stk_push

router = APIRouter(
    prefix="/api/public/superadmin/platform-mpesa",
    tags=["Superadmin — Subscription Billing (Daraja)"],
    dependencies=[Depends(require_superadmin)],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ChargeRequest(BaseModel):
    tenant_id: int
    # Money is Decimal end to end, never float: see
    # app/services/daraja/platform_stk.py's own rounding discipline for why
    # this is the figure that must round-trip exactly.
    amount: condecimal(gt=0, max_digits=12, decimal_places=2)
    phone_number: Optional[str] = Field(default=None, max_length=15)
    subscription_invoice_id: Optional[int] = None
    period_label: Optional[str] = Field(default=None, max_length=120)


# ─── Endpoints ───────────────────────────────────────────────────────────────


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
        amount=Decimal(payload.amount),
        phone_number=payload.phone_number,
        subscription_invoice_id=payload.subscription_invoice_id,
        period_label=payload.period_label,
        initiated_by=admin.get("admin_id"),
    )


@router.get("/transactions")
def list_transactions(
    master_db: Session = Depends(get_master_db),
    tenant_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """Every platform Daraja charge, whatever its status: Pending, Success,
    Failed, or Quarantined. A quarantined row surfaces here even though it
    was never settled to the ledger, so a superadmin can find and resolve
    it manually instead of it sitting unseen.
    """
    q = master_db.query(PlatformMpesaTransaction)
    if tenant_id is not None:
        q = q.filter(PlatformMpesaTransaction.tenant_id == tenant_id)
    if status is not None:
        q = q.filter(PlatformMpesaTransaction.status == status)
    rows = (
        q.order_by(PlatformMpesaTransaction.initiated_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "subscription_invoice_id": r.subscription_invoice_id,
            "phone_number": r.phone_number,
            "amount": str(r.amount or 0),
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


@router.get("/transactions/{transaction_id}")
def get_transaction(
    transaction_id: int,
    master_db: Session = Depends(get_master_db),
):
    r = (
        master_db.query(PlatformMpesaTransaction)
        .filter(PlatformMpesaTransaction.id == transaction_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "subscription_invoice_id": r.subscription_invoice_id,
        "phone_number": r.phone_number,
        "amount": str(r.amount or 0),
        "status": r.status,
        "receipt_number": r.receipt_number,
        "result_desc": r.result_desc,
        "period_label": r.period_label,
        "external_reference": r.external_reference,
        "checkout_request_id": r.checkout_request_id,
        "merchant_request_id": r.merchant_request_id,
        "initiated_at": r.initiated_at.isoformat() if r.initiated_at else None,
        "settled_at": r.settled_at.isoformat() if r.settled_at else None,
    }
