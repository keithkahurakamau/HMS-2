"""Phase 5 — claim schedules and client deposits.

Lifecycle:
  * Claim schedules: draft -> submitted (auto-posts move from patient AR
    to insurance receivable) -> settled (Dr Bank / Cr Insurance AR)
    or rejected (manual reversal).
  * Client deposits: created (Dr Cash/Bank/MPesa / Cr Patient Deposits)
    then applied to one or more invoices over time (decrements
    amount_applied, bumps invoice.amount_paid).

Auto-posting goes through `accounting_posting.post_from_event` so the
ledger calls share the same idempotency + go-live + non-fatal guarantees
as Phase 4.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.accounting import (
    ClaimSchedule,
    ClaimScheduleItem,
    ClientDeposit,
    DepositApplication,
    InsuranceProvider,
    MedicalScheme,
)
from app.models.billing import Invoice, Payment
from app.services.accounting_posting import post_from_event

router = APIRouter(prefix="/api/accounting/debtors", tags=["Accounting · Debtors"])

VIEW = Depends(RequirePermission("accounting:view"))
WRITE = Depends(RequirePermission("accounting:journal.create"))
POST = Depends(RequirePermission("accounting:journal.post"))


# ─── Schemas ────────────────────────────────────────────────────────────────

class ClaimItemInput(BaseModel):
    invoice_id: Optional[int] = None
    invoice_reference: Optional[str] = Field(default=None, max_length=80)
    patient_name: Optional[str] = Field(default=None, max_length=200)
    member_number: Optional[str] = Field(default=None, max_length=80)
    amount_claimed: Decimal = Field(gt=0)
    notes: Optional[str] = None


class ClaimItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    item_id: int
    invoice_id: Optional[int]
    invoice_reference: Optional[str]
    patient_name: Optional[str]
    member_number: Optional[str]
    amount_claimed: Decimal
    amount_approved: Optional[Decimal]
    notes: Optional[str]


class ClaimCreate(BaseModel):
    provider_id: int
    scheme_id: Optional[int] = None
    period_from: date
    period_to: date
    items: List[ClaimItemInput] = Field(min_length=1)
    notes: Optional[str] = None


class ClaimSettleRequest(BaseModel):
    settled_amount: Decimal = Field(gt=0)
    settlement_reference: Optional[str] = Field(default=None, max_length=120)
    settled_at: Optional[date] = None


class ClaimRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    schedule_id: int
    schedule_number: str
    provider_id: int
    scheme_id: Optional[int]
    period_from: date
    period_to: date
    total_amount: Decimal
    status: str
    submitted_at: Optional[datetime]
    settled_at: Optional[datetime]
    settled_amount: Optional[Decimal]
    settlement_reference: Optional[str]
    rejection_reason: Optional[str]
    notes: Optional[str]
    items: List[ClaimItemResponse]


class DepositCreate(BaseModel):
    patient_id: int
    deposit_date: Optional[date] = None
    amount: Decimal = Field(gt=0)
    method: str = Field(max_length=40)
    reference: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class DepositApplyRequest(BaseModel):
    invoice_id: int
    amount: Decimal = Field(gt=0)
    notes: Optional[str] = None


class DepositApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    application_id: int
    deposit_id: int
    invoice_id: int
    amount: Decimal
    applied_by: int
    applied_at: datetime
    notes: Optional[str]


class DepositResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    deposit_id: int
    deposit_number: str
    patient_id: int
    deposit_date: date
    amount: Decimal
    amount_applied: Decimal
    method: str
    reference: Optional[str]
    status: str
    notes: Optional[str]
    received_by: int
    applications: List[DepositApplicationResponse] = Field(default_factory=list)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _user_id(current_user) -> int:
    return current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", 0)


def _next_claim_number(db: Session, on: date) -> str:
    prefix = f"CLM-{on.year:04d}{on.month:02d}-"
    count = db.query(ClaimSchedule).filter(ClaimSchedule.schedule_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


def _next_deposit_number(db: Session, on: date) -> str:
    prefix = f"DEP-{on.year:04d}{on.month:02d}-"
    count = db.query(ClientDeposit).filter(ClientDeposit.deposit_number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


# ─── Claim schedules ────────────────────────────────────────────────────────

@router.get("/claims", response_model=List[ClaimResponse], dependencies=[VIEW])
def list_claims(db: Session = Depends(get_db),
                provider_id: Optional[int] = None,
                status: Optional[str] = None):
    q = db.query(ClaimSchedule)
    if provider_id is not None:
        q = q.filter(ClaimSchedule.provider_id == provider_id)
    if status:
        q = q.filter(ClaimSchedule.status == status)
    return q.order_by(ClaimSchedule.created_at.desc()).all()


@router.get("/claims/{schedule_id}", response_model=ClaimResponse, dependencies=[VIEW])
def get_claim(schedule_id: int, db: Session = Depends(get_db)):
    row = db.query(ClaimSchedule).filter(ClaimSchedule.schedule_id == schedule_id).first()
    if not row:
        raise HTTPException(404, detail="Claim schedule not found.")
    return row


@router.post("/claims", response_model=ClaimResponse, dependencies=[WRITE])
def create_claim(payload: ClaimCreate, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    if payload.period_from > payload.period_to:
        raise HTTPException(400, detail="period_from must be <= period_to.")
    if not db.query(InsuranceProvider).filter(InsuranceProvider.provider_id == payload.provider_id).first():
        raise HTTPException(404, detail="Provider not found.")
    if payload.scheme_id is not None:
        if not db.query(MedicalScheme).filter(MedicalScheme.scheme_id == payload.scheme_id,
                                              MedicalScheme.provider_id == payload.provider_id).first():
            raise HTTPException(400, detail="Scheme does not belong to that provider.")

    total = sum((Decimal(i.amount_claimed) for i in payload.items), Decimal(0))
    sched = ClaimSchedule(
        schedule_number=_next_claim_number(db, date.today()),
        provider_id=payload.provider_id,
        scheme_id=payload.scheme_id,
        period_from=payload.period_from,
        period_to=payload.period_to,
        total_amount=total,
        status="draft",
        notes=payload.notes,
        created_by=_user_id(current_user),
    )
    db.add(sched)
    db.flush()
    for item in payload.items:
        db.add(ClaimScheduleItem(
            schedule_id=sched.schedule_id,
            invoice_id=item.invoice_id,
            invoice_reference=item.invoice_reference,
            patient_name=item.patient_name,
            member_number=item.member_number,
            amount_claimed=item.amount_claimed,
            notes=item.notes,
        ))
    db.commit()
    db.refresh(sched)
    return sched


@router.post("/claims/{schedule_id}/submit", response_model=ClaimResponse, dependencies=[POST])
def submit_claim(schedule_id: int, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    sched = db.query(ClaimSchedule).filter(ClaimSchedule.schedule_id == schedule_id).first()
    if not sched:
        raise HTTPException(404, detail="Claim schedule not found.")
    if sched.status != "draft":
        raise HTTPException(400, detail=f"Cannot submit a claim in status '{sched.status}'.")

    user_id = _user_id(current_user)
    sched.status = "submitted"
    sched.submitted_at = datetime.utcnow()
    sched.submitted_by = user_id

    # Auto-post: move from patient AR to insurance receivable.
    # Default mapping (Dr 1150 Insurance Receivable / Cr 1140 Accounts Receivable).
    post_from_event(
        db,
        source_key="insurance.claim.submitted",
        source_id=sched.schedule_id,
        amount=sched.total_amount,
        on_date=sched.submitted_at.date(),
        memo=f"Claim schedule {sched.schedule_number} submitted",
        reference=sched.schedule_number,
        user_id=user_id,
    )
    db.commit()
    db.refresh(sched)
    return sched


@router.post("/claims/{schedule_id}/settle", response_model=ClaimResponse, dependencies=[POST])
def settle_claim(schedule_id: int, payload: ClaimSettleRequest, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    sched = db.query(ClaimSchedule).filter(ClaimSchedule.schedule_id == schedule_id).first()
    if not sched:
        raise HTTPException(404, detail="Claim schedule not found.")
    if sched.status != "submitted":
        raise HTTPException(400, detail=f"Cannot settle a claim in status '{sched.status}'.")

    user_id = _user_id(current_user)
    sched.status = "settled"
    sched.settled_amount = payload.settled_amount
    sched.settlement_reference = payload.settlement_reference
    sched.settled_at = datetime.utcnow()
    sched.settled_by = user_id

    # Auto-post the settled amount (insurer paid into bank).
    post_from_event(
        db,
        source_key="insurance.claim.settled",
        source_id=sched.schedule_id,
        amount=payload.settled_amount,
        on_date=payload.settled_at or date.today(),
        memo=f"Claim schedule {sched.schedule_number} settled",
        reference=payload.settlement_reference or sched.schedule_number,
        user_id=user_id,
    )
    db.commit()
    db.refresh(sched)
    return sched


@router.post("/claims/{schedule_id}/reject", response_model=ClaimResponse, dependencies=[POST])
def reject_claim(schedule_id: int, payload: ClaimRejectRequest, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    sched = db.query(ClaimSchedule).filter(ClaimSchedule.schedule_id == schedule_id).first()
    if not sched:
        raise HTTPException(404, detail="Claim schedule not found.")
    if sched.status != "submitted":
        raise HTTPException(400, detail=f"Cannot reject a claim in status '{sched.status}'.")

    sched.status = "rejected"
    sched.rejection_reason = payload.reason
    # NOTE: a true rejection would also reverse the submission journal entry.
    # That's a Phase 5b item — for now the operator must reverse manually
    # from the Journal Entries tab using the original entry's Reverse action.
    db.commit()
    db.refresh(sched)
    return sched


# ─── Client deposits ────────────────────────────────────────────────────────

@router.get("/deposits", response_model=List[DepositResponse], dependencies=[VIEW])
def list_deposits(db: Session = Depends(get_db),
                  patient_id: Optional[int] = None,
                  status: Optional[str] = None):
    q = db.query(ClientDeposit)
    if patient_id is not None:
        q = q.filter(ClientDeposit.patient_id == patient_id)
    if status:
        q = q.filter(ClientDeposit.status == status)
    return q.order_by(ClientDeposit.created_at.desc()).all()


@router.get("/deposits/{deposit_id}", response_model=DepositResponse, dependencies=[VIEW])
def get_deposit(deposit_id: int, db: Session = Depends(get_db)):
    row = db.query(ClientDeposit).filter(ClientDeposit.deposit_id == deposit_id).first()
    if not row:
        raise HTTPException(404, detail="Deposit not found.")
    return row


@router.post("/deposits", response_model=DepositResponse, dependencies=[WRITE])
def create_deposit(payload: DepositCreate, db: Session = Depends(get_db),
                   current_user=Depends(get_current_user)):
    on = payload.deposit_date or date.today()
    user_id = _user_id(current_user)
    row = ClientDeposit(
        deposit_number=_next_deposit_number(db, on),
        patient_id=payload.patient_id,
        deposit_date=on,
        amount=payload.amount,
        amount_applied=Decimal(0),
        method=payload.method,
        reference=payload.reference,
        status="available",
        notes=payload.notes,
        received_by=user_id,
    )
    db.add(row)
    db.flush()

    # Auto-post the deposit receipt.
    post_from_event(
        db,
        source_key="billing.deposit.received",
        source_id=row.deposit_id,
        amount=payload.amount,
        on_date=on,
        memo=f"Patient deposit {row.deposit_number}",
        reference=row.deposit_number,
        user_id=user_id,
    )
    db.commit()
    db.refresh(row)
    return row


@router.post("/deposits/{deposit_id}/apply", response_model=DepositResponse, dependencies=[WRITE])
def apply_deposit(deposit_id: int, payload: DepositApplyRequest, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    dep = db.query(ClientDeposit).with_for_update().filter(
        ClientDeposit.deposit_id == deposit_id).first()
    if not dep:
        raise HTTPException(404, detail="Deposit not found.")
    if dep.status not in ("available", "partially_applied"):
        raise HTTPException(400, detail=f"Deposit status '{dep.status}' cannot be applied.")

    available = Decimal(dep.amount) - Decimal(dep.amount_applied)
    amt = Decimal(payload.amount)
    if amt > available:
        raise HTTPException(400, detail=f"Only {available} available on this deposit.")

    invoice = db.query(Invoice).with_for_update().filter(
        Invoice.invoice_id == payload.invoice_id).first()
    if not invoice:
        raise HTTPException(404, detail="Invoice not found.")
    if invoice.patient_id != dep.patient_id:
        raise HTTPException(400, detail="Invoice belongs to a different patient.")
    if invoice.status == "Paid":
        raise HTTPException(400, detail="Invoice is already fully paid.")

    user_id = _user_id(current_user)

    # Record the deposit application + a Payment row so billing's reporting
    # sees the settlement consistently.
    db.add(DepositApplication(
        deposit_id=dep.deposit_id,
        invoice_id=invoice.invoice_id,
        amount=amt,
        applied_by=user_id,
        notes=payload.notes,
    ))

    pmt = Payment(
        invoice_id=invoice.invoice_id,
        amount=amt,
        payment_method="Deposit",
        transaction_reference=f"DEP-{dep.deposit_number}",
    )
    db.add(pmt)
    db.flush()

    invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amt
    if invoice.amount_paid >= invoice.total_amount:
        invoice.status = "Paid"
    elif invoice.amount_paid > 0:
        invoice.status = "Partially Paid"

    dep.amount_applied = Decimal(dep.amount_applied) + amt
    if dep.amount_applied >= Decimal(dep.amount):
        dep.status = "fully_applied"
    else:
        dep.status = "partially_applied"

    # Ledger: applying a deposit clears the patient deposit liability and
    # records a payment against AR. Dr Patient Deposits (2170) / Cr AR (1140).
    # Reuse a dedicated source_key so it's distinct from cash receipts.
    post_from_event(
        db,
        source_key="billing.deposit.applied",
        source_id=pmt.payment_id,
        amount=amt,
        memo=f"Deposit {dep.deposit_number} applied to Invoice #{invoice.invoice_id}",
        reference=f"INV-{invoice.invoice_id}",
        user_id=user_id,
    )

    db.commit()
    db.refresh(dep)
    return dep
