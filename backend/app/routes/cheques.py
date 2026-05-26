"""Cheque register routes — both incoming and outgoing.

Incoming lifecycle (hospital receives a cheque from someone):
    POST /cheques/                          → Received  (direction='incoming')
    POST /cheques/{id}/deposit              Received  → Deposited
    POST /cheques/{id}/clear                Deposited → Cleared (posts Payment)
    POST /cheques/{id}/bounce               Received/Deposited → Bounced
    POST /cheques/{id}/cancel               (any non-terminal) → Cancelled

Outgoing lifecycle (hospital issues a cheque to a supplier/staff/refund):
    POST /cheques/                          → Issued   (direction='outgoing')
    POST /cheques/{id}/dispatch             Issued    → Dispatched
    POST /cheques/{id}/clear                Dispatched→ Cleared
    POST /cheques/{id}/return               Dispatched→ Returned (by bank)
    POST /cheques/{id}/stop                 Issued/Dispatched → Stopped
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
from app.services.accounting_posting import post_from_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cheques", tags=["Cheques"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_DRAWER_TYPES = {"Insurance", "Employer", "Patient", "Government", "Other"}
ALLOWED_PAYEE_TYPES = {"Supplier", "Staff", "Refund", "Government", "Other"}
ALLOWED_DIRECTIONS = {"incoming", "outgoing"}

# Status sets keyed by direction. The lifecycle guards consult these so the
# action endpoints don't need direction-specific copies of every transition.
NON_TERMINAL_BY_DIR = {
    "incoming": {"Received", "Deposited"},
    "outgoing": {"Issued", "Dispatched"},
}
TERMINAL_BY_DIR = {
    "incoming": {"Cleared", "Bounced", "Cancelled"},
    "outgoing": {"Cleared", "Returned", "Stopped", "Cancelled"},
}
INITIAL_STATUS_BY_DIR = {"incoming": "Received", "outgoing": "Issued"}


class ChequeCreate(BaseModel):
    """Direction-aware payload.

    Incoming cheques require drawer_name + drawer_type; outgoing cheques
    require payee_name + payee_type. Validation enforces the right combo
    so the front-desk never accidentally creates a half-formed row.
    """
    direction: str = "incoming"
    cheque_number: str
    bank_name: str
    bank_branch: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "KES"
    date_on_cheque: Optional[date] = None

    # Incoming-only
    drawer_name: Optional[str] = None
    drawer_type: Optional[str] = None
    # Outgoing-only
    payee_name: Optional[str] = None
    payee_type: Optional[str] = None
    date_issued: Optional[datetime] = None

    invoice_id: Optional[int] = None
    patient_id: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("direction")
    @classmethod
    def direction_in_set(cls, v):
        if v not in ALLOWED_DIRECTIONS:
            raise ValueError(f"direction must be one of {sorted(ALLOWED_DIRECTIONS)}")
        return v


class ChequePatch(BaseModel):
    cheque_number: Optional[str] = None
    drawer_name: Optional[str] = None
    drawer_type: Optional[str] = None
    payee_name: Optional[str] = None
    payee_type: Optional[str] = None
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


class DispatchRequest(BaseModel):
    """Outgoing-only — when the cheque physically leaves the office."""
    dispatch_date: Optional[datetime] = None
    deposit_account: Optional[str] = None  # which of our bank accounts it's drawn on


class ClearRequest(BaseModel):
    clearance_date: Optional[datetime] = None


class BounceRequest(BaseModel):
    reason: str


class ReturnRequest(BaseModel):
    """Outgoing-only — when the receiving bank returns our cheque."""
    reason: str


class StopRequest(BaseModel):
    """Outgoing-only — stop-payment instruction sent to our bank."""
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
        "direction": c.direction,
        "cheque_number": c.cheque_number,
        "drawer_name": c.drawer_name,
        "drawer_type": c.drawer_type,
        "payee_name": c.payee_name,
        "payee_type": c.payee_type,
        "bank_name": c.bank_name,
        "bank_branch": c.bank_branch,
        "amount": float(c.amount),
        "currency": c.currency,
        "status": c.status,
        "date_on_cheque": c.date_on_cheque.isoformat() if c.date_on_cheque else None,
        "date_received": c.date_received.isoformat() if c.date_received else None,
        "date_issued": c.date_issued.isoformat() if c.date_issued else None,
        "dispatch_date": c.dispatch_date.isoformat() if c.dispatch_date else None,
        "deposit_date": c.deposit_date.isoformat() if c.deposit_date else None,
        "deposit_account": c.deposit_account,
        "clearance_date": c.clearance_date.isoformat() if c.clearance_date else None,
        "bounce_reason": c.bounce_reason,
        "return_reason": c.return_reason,
        "stop_reason": c.stop_reason,
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


def _guard_direction(c: Cheque, expected: str, action: str) -> None:
    if c.direction != expected:
        raise HTTPException(
            status_code=400,
            detail=f"`{action}` is an {expected}-only action; this cheque is {c.direction}.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/summary", dependencies=[Depends(RequirePermission("cheques:read"))])
def summary(
    direction: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Counts + sums per status, optionally filtered by direction.

    Returns a dict shaped as `{status: {count, total}}`. Both direction
    flows are folded into the same dict — UI splits them via tabs.
    """
    query = db.query(
        Cheque.status,
        func.count(Cheque.cheque_id),
        func.coalesce(func.sum(Cheque.amount), 0),
    )
    if direction in ALLOWED_DIRECTIONS:
        query = query.filter(Cheque.direction == direction)
    rows = query.group_by(Cheque.status).all()
    # All possible statuses across both directions, pre-seeded with zeros
    # so the UI never has to handle missing keys.
    all_statuses = ("Received", "Deposited", "Issued", "Dispatched",
                    "Cleared", "Bounced", "Returned", "Stopped", "Cancelled")
    out = {status: {"count": 0, "total": 0.0} for status in all_statuses}
    for status, count, total in rows:
        out[status] = {"count": int(count), "total": float(total)}
    return out


@router.get("/", dependencies=[Depends(RequirePermission("cheques:read"))])
def list_cheques(
    direction: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    drawer_type: Optional[str] = Query(default=None),
    payee_type: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    patient_id: Optional[int] = Query(default=None),
    invoice_id: Optional[int] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Cheque)
    if direction in ALLOWED_DIRECTIONS:
        query = query.filter(Cheque.direction == direction)
    if status:
        query = query.filter(Cheque.status == status)
    if drawer_type:
        query = query.filter(Cheque.drawer_type == drawer_type)
    if payee_type:
        query = query.filter(Cheque.payee_type == payee_type)
    if patient_id:
        query = query.filter(Cheque.patient_id == patient_id)
    if invoice_id:
        query = query.filter(Cheque.invoice_id == invoice_id)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(or_(
            Cheque.cheque_number.ilike(needle),
            Cheque.drawer_name.ilike(needle),
            Cheque.payee_name.ilike(needle),
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
    # Direction-specific required-field check.
    if payload.direction == "incoming":
        if not payload.drawer_name:
            raise HTTPException(status_code=400, detail="drawer_name is required for incoming cheques.")
        drawer_type = payload.drawer_type or "Other"
        if drawer_type not in ALLOWED_DRAWER_TYPES:
            raise HTTPException(status_code=400, detail=f"drawer_type must be one of {sorted(ALLOWED_DRAWER_TYPES)}")
    else:  # outgoing
        if not payload.payee_name:
            raise HTTPException(status_code=400, detail="payee_name is required for outgoing cheques.")
        payee_type = payload.payee_type or "Other"
        if payee_type not in ALLOWED_PAYEE_TYPES:
            raise HTTPException(status_code=400, detail=f"payee_type must be one of {sorted(ALLOWED_PAYEE_TYPES)}")

    # Optional link validation — fail fast rather than store dangling FKs.
    if payload.invoice_id:
        if not db.query(Invoice).filter(Invoice.invoice_id == payload.invoice_id).first():
            raise HTTPException(status_code=400, detail=f"Invoice {payload.invoice_id} not found.")
    if payload.patient_id:
        if not db.query(Patient).filter(Patient.patient_id == payload.patient_id).first():
            raise HTTPException(status_code=400, detail=f"Patient {payload.patient_id} not found.")

    # Duplicate check: same direction + counterparty + bank + cheque number
    # is almost certainly an accidental re-entry.
    counterparty_col = Cheque.drawer_name if payload.direction == "incoming" else Cheque.payee_name
    counterparty_val = payload.drawer_name if payload.direction == "incoming" else payload.payee_name
    dup = db.query(Cheque).filter(
        Cheque.direction == payload.direction,
        Cheque.cheque_number == payload.cheque_number,
        counterparty_col == counterparty_val,
        Cheque.bank_name == payload.bank_name,
        Cheque.status != "Cancelled",
    ).first()
    if dup:
        who = payload.drawer_name if payload.direction == "incoming" else payload.payee_name
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cheque #{payload.cheque_number} {'from' if payload.direction == 'incoming' else 'to'} "
                f"{who} ({payload.bank_name}) is already on file (status: {dup.status})."
            ),
        )

    cheque = Cheque(
        direction=payload.direction,
        cheque_number=payload.cheque_number.strip(),
        drawer_name=payload.drawer_name.strip() if payload.drawer_name else None,
        drawer_type=payload.drawer_type if payload.direction == "incoming" else None,
        payee_name=payload.payee_name.strip() if payload.payee_name else None,
        payee_type=payload.payee_type if payload.direction == "outgoing" else None,
        bank_name=payload.bank_name.strip(),
        bank_branch=payload.bank_branch,
        amount=Decimal(str(payload.amount)),
        currency=payload.currency.upper()[:3],
        date_on_cheque=payload.date_on_cheque,
        date_issued=payload.date_issued if payload.direction == "outgoing" else None,
        invoice_id=payload.invoice_id,
        patient_id=payload.patient_id,
        notes=payload.notes,
        received_by=current_user["user_id"],
        last_updated_by=current_user["user_id"],
        status=INITIAL_STATUS_BY_DIR[payload.direction],
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
    if c.status in TERMINAL_BY_DIR[c.direction]:
        raise HTTPException(
            status_code=400,
            detail=f"Cheque is {c.status} — edits are no longer accepted.",
        )

    data = payload.model_dump(exclude_unset=True)
    if "drawer_type" in data and data["drawer_type"] and data["drawer_type"] not in ALLOWED_DRAWER_TYPES:
        raise HTTPException(status_code=400, detail="Invalid drawer_type.")
    if "payee_type" in data and data["payee_type"] and data["payee_type"] not in ALLOWED_PAYEE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid payee_type.")
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
    """Incoming-only — we deposit the received cheque into our bank."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_direction(c, "incoming", "deposit")
    _guard_transition(c, "Received", "deposit")
    c.status = "Deposited"
    c.deposit_account = payload.deposit_account.strip()
    c.deposit_date = payload.deposit_date or datetime.now()
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/dispatch", dependencies=[Depends(RequirePermission("cheques:manage"))])
def dispatch_cheque(
    cheque_id: int,
    payload: DispatchRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Outgoing-only — the cheque physically leaves the hospital."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_direction(c, "outgoing", "dispatch")
    _guard_transition(c, "Issued", "dispatch")
    c.status = "Dispatched"
    c.dispatch_date = payload.dispatch_date or datetime.now()
    if payload.deposit_account:
        c.deposit_account = payload.deposit_account.strip()
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
    """Mark cheque as cleared by the bank.

    Incoming: clears from 'Deposited'. Posts a Payment against the linked
    invoice (if any) and bumps amount_paid + invoice status.
    Outgoing: clears from 'Dispatched'. No invoice posting (outgoing
    cheques aren't tied to inbound invoices); ledger entry posts the
    bank-credit / AP-debit side via the accounting service.
    """
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    expected_from = "Deposited" if c.direction == "incoming" else "Dispatched"
    _guard_transition(c, expected_from, "clear")

    c.status = "Cleared"
    c.clearance_date = payload.clearance_date or datetime.now()
    c.last_updated_by = current_user["user_id"]

    # Incoming-only: post the inbound payment against the linked invoice.
    if c.direction == "incoming" and c.invoice_id:
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

    # Auto-post to the GL. Source key differs per direction so the
    # ledger mapping (Dr/Cr) is correct: inbound = Bank/AR, outbound =
    # AP/Bank.
    source_key = "cheques.deposit.cleared" if c.direction == "incoming" else "cheques.dispatch.cleared"
    memo_extra = f" against Invoice #{c.invoice_id}" if c.invoice_id else ""
    memo = (
        f"Cheque cleared #{c.cheque_id}{memo_extra}" if c.direction == "incoming"
        else f"Outgoing cheque cleared #{c.cheque_id} (payee: {c.payee_name or 'unknown'})"
    )
    post_from_event(
        db,
        source_key=source_key,
        source_id=c.cheque_id,
        amount=c.amount,
        on_date=c.clearance_date.date() if hasattr(c.clearance_date, "date") else c.clearance_date,
        memo=memo,
        reference=f"CHQ-{c.cheque_id}",
        user_id=current_user["user_id"],
    )

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
    """Incoming-only — the drawer's bank rejected our deposit."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_direction(c, "incoming", "bounce")
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


@router.post("/{cheque_id}/return", dependencies=[Depends(RequirePermission("cheques:manage"))])
def return_cheque(
    cheque_id: int,
    payload: ReturnRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Outgoing-only — the payee's bank returned our cheque (signature
    mismatch, account closed, insufficient funds on our side, etc.).
    Semantically equivalent to an inbound 'bounce' but kept distinct so
    finance can split the two on reconciliation reports."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_direction(c, "outgoing", "return")
    if c.status not in ("Issued", "Dispatched"):
        raise HTTPException(
            status_code=400,
            detail=f"Only Issued or Dispatched outgoing cheques can be returned — current state: {c.status}.",
        )
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Return reason is required.")
    c.status = "Returned"
    c.return_reason = payload.reason.strip()
    c.last_updated_by = current_user["user_id"]
    db.commit()
    db.refresh(c)
    return _serialize(c, db)


@router.post("/{cheque_id}/stop", dependencies=[Depends(RequirePermission("cheques:manage"))])
def stop_cheque(
    cheque_id: int,
    payload: StopRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Outgoing-only — operator sent a stop-payment instruction to our
    bank. Differs from 'cancel' (which is for cheques we've physically
    destroyed before dispatch); a stopped cheque exists in the wild and
    we just instructed the bank to refuse it."""
    c = db.query(Cheque).filter(Cheque.cheque_id == cheque_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cheque not found.")
    _guard_direction(c, "outgoing", "stop")
    if c.status not in ("Issued", "Dispatched"):
        raise HTTPException(
            status_code=400,
            detail=f"Only Issued or Dispatched outgoing cheques can be stopped — current state: {c.status}.",
        )
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Stop-payment reason is required.")
    c.status = "Stopped"
    c.stop_reason = payload.reason.strip()
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
    if c.status not in NON_TERMINAL_BY_DIR[c.direction]:
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
