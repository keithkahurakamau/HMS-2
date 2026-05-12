"""Cheque register routes.

Lifecycle endpoints map onto explicit transitions so the audit trail stays
linear:

    POST /cheques/                          → Received
    POST /cheques/{id}/deposit              Received → Deposited
    POST /cheques/{id}/clear                Deposited → Cleared (posts Payment)
    POST /cheques/{id}/bounce               Deposited → Bounced
    POST /cheques/{id}/cancel               (any non-terminal) → Cancelled
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.billing import Invoice, Payment
from app.models.cheque import Cheque
from app.models.patient import Patient
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cheques", tags=["Cheques"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_DRAWER_TYPES = {"Insurance", "Employer", "Patient", "Government", "Other"}
NON_TERMINAL_STATUSES = {"Received", "Deposited"}
TERMINAL_STATUSES = {"Cleared", "Bounced", "Cancelled"}


class ChequeCreate(BaseModel):
    cheque_number: str
    drawer_name: str
    drawer_type: str = "Other"
    bank_name: str
    bank_branch: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "KES"
    date_on_cheque: Optional[date] = None
    invoice_id: Optional[int] = None
    patient_id: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("drawer_type")
    @classmethod
    def drawer_type_in_set(cls, v):
        if v not in ALLOWED_DRAWER_TYPES:
            raise ValueError(f"drawer_type must be one of {sorted(ALLOWED_DRAWER_TYPES)}")
        return v


class ChequePatch(BaseModel):
    cheque_number: Optional[str] = None
    drawer_name: Optional[str] = None
    drawer_type: Optional[str] = None
    bank_name: Optional[str] = None
    bank_branch: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    date_on_cheque: Optional[date] = None
    invoice_id: Optional[int] = None
    patient_id: Optional[int] = None
    notes: Optional[str] = None


class DepositRequest(BaseModel):
    deposit_account: str
    deposit_date: Optional[datetime] = None


class ClearRequest(BaseModel):
    clearance_date: Optional[datetime] = None


class BounceRequest(BaseModel):
    reason: str


class CancelRequest(BaseModel):
    reason: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _serialize(c: Cheque, db: Session) -> Dict[str, Any]:
    patient = c.patient
    invoice = c.invoice
    return {
        "cheque_id": c.cheque_id,
        "cheque_number": c.cheque_number,
        "drawer_name": c.drawer_name,
        "drawer_type": c.drawer_type,
        "bank_name": c.bank_name,
        "bank_branch": c.bank_branch,
        "amount": float(c.amount),
        "currency": c.currency,
        "status": c.status,
        "date_on_cheque": c.date_on_cheque.isoformat() if c.date_on_cheque else None,
        "date_received": c.date_received.isoformat() if c.date_received else None,
        "deposit_date": c.deposit_date.isoformat() if c.deposit_date else None,
        "deposit_account": c.deposit_account,
        "clearance_date": c.clearance_date.isoformat() if c.clearance_date else None,
        "bounce_reason": c.bounce_reason,
        "cancel_reason": c.cancel_reason,
        "invoice_id": c.invoice_id,
        "invoice_total": float(invoice.total_amount) if invoice else None,
        "patient_id": c.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "received_by": c.received_by,
        "last_updated_by": c.last_updated_by,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _guard_transition(c: Cheque, from_status: str, action: str) -> None:
    if c.status != from_status:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot {action} a cheque in state '{c.status}'. Expected '{from_status}'.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/summary", dependencies=[Depends(RequirePermission("cheques:read"))])
def summary(db: Session = Depends(get_db)):
    """Counts + sums per status. Cheap aggregation for the top-of-page tiles."""
    rows = (
        db.query(
            Cheque.status,
            func.count(Cheque.cheque_id),
            func.coalesce(func.sum(Cheque.amount), 0),
        )
        .group_by(Cheque.status)
        .all()
    )
    out = {status: {"count": 0, "total": 0.0} for status in
           ("Received", "Deposited", "Cleared", "Bounced", "Cancelled")}
    for status, count, total in rows:
        out[status] = {"count": int(count), "total": float(total)}
    return out


@router.get("/", dependencies=[Depends(RequirePermission("cheques:read"))])
def list_cheques(
    status: Optional[str] = Query(default=None),
    drawer_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    patient_id: Optional[int] = Query(default=None),
    invoice_id: Optional[int] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Cheque)
    if status:
        query = query.filter(Cheque.status == status)
    if drawer_type:
        query = query.filter(Cheque.drawer_type == drawer_type)
    if patient_id:
        query = query.filter(Cheque.patient_id == patient_id)
    if invoice_id:
        query = query.filter(Cheque.invoice_id == invoice_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(or_(
            Cheque.cheque_number.ilike(needle),
            Cheque.drawer_name.ilike(needle),
            Cheque.bank_name.ilike(needle),
        ))

    rows = query.order_by(Cheque.date_received.desc()).offset(skip).limit(limit).all()
    return [_serialize(c, db) for c in rows]


@router.get("/{cheque_id}", dependencies=[Depends(RequirePermission("cheques:read"))])
def get_cheque(cheque_id: int, db: Session = Depends(get_db)):
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    return _serialize(c, db)


@router.post("/", dependencies=[Depends(RequirePermission("cheques:manage"))])
def create_cheque(
    payload: ChequeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Optional link validation — fail fast rather than store dangling FKs.
    if payload.invoice_id:
        if not db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first():
            raise HTTPException(status_code=400, detail=f"Invoice {payload.invoice_id} not found.")
    if payload.patient_id:
        if not db.query(Patient).filter(Patient.patient_id == payload.patient_id).first():
            raise HTTPException(status_code=400, detail=f"Patient {payload.patient_id} not found.")

    # Same drawer + bank + number is almost certainly a duplicate entry.
    dup = db.query(Cheque).filter(
        Cheque.cheque_number == payload.cheque_number,
        Cheque.drawer_name == payload.drawer_name,
        Cheque.bank_name == payload.bank_name,
        Cheque.status != "Cancelled",
    ).first()
    if dup:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cheque #{payload.cheque_number} from {payload.drawer_name} ({payload.bank_name}) "
                f"is already on file (status: {dup.status})."
            ),
        )

    cheque = Cheque(
        cheque_number=payload.cheque_number.strip(),
        drawer_name=payload.drawer_name.strip(),
        drawer_type=payload.drawer_type,
        bank_name=payload.bank_name.strip(),
        bank_branch=payload.bank_branch,
        amount=Decimal(str(payload.amount)),
        currency=payload.currency.upper()[:3],
        date_on_cheque=payload.date_on_cheque,
        invoice_id=payload.invoice_id,
        patient_id=payload.patient_id,
        notes=payload.notes,
        received_by=current_user["user_id"],
        last_updated_by=current_user["user_id"],
        status="Received",
    )
    db.add(cheque)
    db.commit()
    db.refresh(cheque)
    return _serialize(cheque, db)


@router.patch("/{cheque_id}", dependencies=[Depends(RequirePermission("cheques:manage"))])
def update_cheque(
    cheque_id: int,
    payload: ChequePatch,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    if c.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cheque is {c.status} — edits are no longer accepted.",
        )

    data = payload.model_dump(exclude_unset=True)
    if "drawer_type" in data and data["drawer_type"] not in ALLOWED_DRAWER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid drawer_type.")
    if "invoice_id" in data and data["invoice_id"]:
        if not db.query(Invoice).filter(Invoice.invoice_id == data["invoice_id"]).first():
            raise HTTPException(status_code=400, detail="Invoice not found.")
    if "patient_id" in data and data["patient_id"]:
        if not db.query(Patient).filter(Patient.patient_id == data["patient_id"]).first():
            raise HTTPException(status_code=400, detail="Patient not found.")

    if "amount" in data and data["amount"] is not None:
        data["amount"] = Decimal(str(data["amount"]))

    for field, value in data.items():
        setattr(c, field, value)
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/deposit", dependencies=[Depends(RequirePermission("cheques:manage"))])
def deposit_cheque(
    cheque_id: int,
    payload: DepositRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_transition(c, "Received", "deposit")
    c.status = "Deposited"
    c.deposit_account = payload.deposit_account.strip()
    c.deposit_date = payload.deposit_date or datetime.now()
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/clear", dependencies=[Depends(RequirePermission("cheques:manage"))])
def clear_cheque(
    cheque_id: int,
    payload: ClearRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark cheque as cleared by the bank. Posts a Payment against the linked
    invoice (if any) and bumps the invoice's amount_paid + status."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_transition(c, "Deposited", "clear")

    c.status = "Cleared"
    c.clearance_date = payload.clearance_date or datetime.now()
    c.last_updated_by = current_user["user_id"]

    if c.invoice_id:
        invoice = db.query(Invoice).filter(Invoice.invoice_id == c.invoice_id).first()
        if invoice:
            # Idempotency: don't double-post if a Payment with this transaction
            # reference already exists (e.g. on retry).
            txn_ref = f"CHQ-{c.cheque_id}"
            existing = db.query(Payment).filter(Payment.transaction_reference == txn_ref).first()
            if not existing:
                db.add(Payment(
                    invoice_id=invoice.invoice_id,
                    amount=c.amount,
                    payment_method="Cheque",
                    transaction_reference=txn_ref,
                    payment_date=c.clearance_date,
                ))
                invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + c.amount
                if invoice.amount_paid >= invoice.total_amount:
                    invoice.status = "Paid"
                elif invoice.amount_paid > 0:
                    invoice.status = "Partially Paid"

    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/bounce", dependencies=[Depends(RequirePermission("cheques:manage"))])
def bounce_cheque(
    cheque_id: int,
    payload: BounceRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    if c.status not in ("Received", "Deposited"):
        raise HTTPException(
            status_code=400,
            detail=f"Only Received or Deposited cheques can bounce — current state: {c.status}.",
        )
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Bounce reason is required.")
    c.status = "Bounced"
    c.bounce_reason = payload.reason.strip()
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/cancel", dependencies=[Depends(RequirePermission("cheques:manage"))])
def cancel_cheque(
    cheque_id: int,
    payload: CancelRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    if c.status not in NON_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel a cheque in state '{c.status}'.",
        )
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Cancellation reason is required.")
    c.status = "Cancelled"
    c.cancel_reason = payload.reason.strip()
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)
