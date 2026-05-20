"""Phase 6 — bank accounts + statement reconciliation."""
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
    Account,
    BankAccount,
    BankTransaction,
    JournalLine,
)

router = APIRouter(prefix="/api/accounting/bank", tags=["Accounting · Bank"])

VIEW = Depends(RequirePermission("accounting:view"))
WRITE = Depends(RequirePermission("accounting:settings.manage"))
RECON = Depends(RequirePermission("accounting:journal.post"))


# ─── Schemas ────────────────────────────────────────────────────────────────

class BankAccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    bank_name: str = Field(min_length=1, max_length=120)
    branch: Optional[str] = Field(default=None, max_length=120)
    account_number: str = Field(min_length=1, max_length=60)
    swift_code: Optional[str] = Field(default=None, max_length=20)
    currency_code: str = Field(default="KES", min_length=3, max_length=3)
    gl_account_id: Optional[int] = None
    opening_balance: Decimal = Field(default=Decimal("0"))
    notes: Optional[str] = None


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    bank_name: Optional[str] = Field(default=None, max_length=120)
    branch: Optional[str] = Field(default=None, max_length=120)
    account_number: Optional[str] = Field(default=None, max_length=60)
    swift_code: Optional[str] = Field(default=None, max_length=20)
    currency_code: Optional[str] = Field(default=None, min_length=3, max_length=3)
    gl_account_id: Optional[int] = None
    opening_balance: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class BankAccountResponse(BankAccountBase):
    model_config = ConfigDict(from_attributes=True)
    bank_account_id: int
    is_active: bool


class BankTxCreate(BaseModel):
    bank_account_id: int
    transaction_date: date
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal  # signed: positive in / negative out
    running_balance: Optional[Decimal] = None
    reference: Optional[str] = Field(default=None, max_length=120)


class BankTxBulkCreate(BaseModel):
    bank_account_id: int
    transactions: List[BankTxCreate] = Field(min_length=1)


class BankTxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    bank_transaction_id: int
    bank_account_id: int
    transaction_date: date
    description: str
    amount: Decimal
    running_balance: Optional[Decimal]
    reference: Optional[str]
    reconciliation_status: str
    journal_line_id: Optional[int]
    reconciled_at: Optional[datetime]
    ignore_reason: Optional[str]


class CandidateJournalLine(BaseModel):
    line_id: int
    entry_number: str
    entry_date: date
    debit: Decimal
    credit: Decimal
    debit_base: Decimal
    credit_base: Decimal
    description: Optional[str]
    memo: Optional[str]


class ReconcileMatchRequest(BaseModel):
    journal_line_id: int


class ReconcileIgnoreRequest(BaseModel):
    reason: str = Field(min_length=1)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _user_id(current_user) -> int:
    return current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", 0)


# ─── Accounts ───────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=List[BankAccountResponse], dependencies=[VIEW])
def list_bank_accounts(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(BankAccount)
    if not include_inactive:
        q = q.filter(BankAccount.is_active == True)  # noqa: E712
    return q.order_by(BankAccount.name).all()


@router.post("/accounts", response_model=BankAccountResponse, dependencies=[WRITE])
def create_bank_account(payload: BankAccountCreate, db: Session = Depends(get_db)):
    if payload.gl_account_id is not None:
        gl = db.query(Account).filter(Account.account_id == payload.gl_account_id).first()
        if not gl:
            raise HTTPException(404, detail="GL account not found.")
        if gl.account_type != "Asset":
            raise HTTPException(400, detail="GL account must be an Asset.")
    row = BankAccount(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/accounts/{bank_account_id}", response_model=BankAccountResponse, dependencies=[WRITE])
def update_bank_account(bank_account_id: int, payload: BankAccountUpdate, db: Session = Depends(get_db)):
    row = db.query(BankAccount).filter(BankAccount.bank_account_id == bank_account_id).first()
    if not row:
        raise HTTPException(404, detail="Bank account not found.")
    data = payload.model_dump(exclude_unset=True)
    if data.get("gl_account_id") is not None:
        gl = db.query(Account).filter(Account.account_id == data["gl_account_id"]).first()
        if not gl:
            raise HTTPException(404, detail="GL account not found.")
        if gl.account_type != "Asset":
            raise HTTPException(400, detail="GL account must be an Asset.")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Transactions ───────────────────────────────────────────────────────────

@router.get("/transactions", response_model=List[BankTxResponse], dependencies=[VIEW])
def list_transactions(
    db: Session = Depends(get_db),
    bank_account_id: Optional[int] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    limit: int = Query(200, ge=1, le=1000),
):
    q = db.query(BankTransaction)
    if bank_account_id is not None:
        q = q.filter(BankTransaction.bank_account_id == bank_account_id)
    if status:
        q = q.filter(BankTransaction.reconciliation_status == status)
    if from_date:
        q = q.filter(BankTransaction.transaction_date >= from_date)
    if to_date:
        q = q.filter(BankTransaction.transaction_date <= to_date)
    return q.order_by(BankTransaction.transaction_date.desc(),
                      BankTransaction.bank_transaction_id.desc()).limit(limit).all()


@router.post("/transactions", response_model=BankTxResponse, dependencies=[WRITE])
def create_transaction(payload: BankTxCreate, db: Session = Depends(get_db),
                       current_user=Depends(get_current_user)):
    if not db.query(BankAccount).filter(BankAccount.bank_account_id == payload.bank_account_id).first():
        raise HTTPException(404, detail="Bank account not found.")
    row = BankTransaction(
        bank_account_id=payload.bank_account_id,
        transaction_date=payload.transaction_date,
        description=payload.description,
        amount=payload.amount,
        running_balance=payload.running_balance,
        reference=payload.reference,
        reconciliation_status="unreconciled",
        created_by=_user_id(current_user),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/transactions/bulk", response_model=List[BankTxResponse], dependencies=[WRITE])
def bulk_create(payload: BankTxBulkCreate, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    """Bulk import — typically called after parsing a bank statement CSV
    client-side. Skips duplicates on (bank_account_id, transaction_date,
    amount, reference) so re-imports are idempotent."""
    if not db.query(BankAccount).filter(BankAccount.bank_account_id == payload.bank_account_id).first():
        raise HTTPException(404, detail="Bank account not found.")

    inserted: List[BankTransaction] = []
    user_id = _user_id(current_user)
    for tx in payload.transactions:
        if tx.bank_account_id != payload.bank_account_id:
            continue
        existing = db.query(BankTransaction).filter(
            BankTransaction.bank_account_id == tx.bank_account_id,
            BankTransaction.transaction_date == tx.transaction_date,
            BankTransaction.amount == tx.amount,
            BankTransaction.reference == tx.reference,
        ).first()
        if existing:
            continue
        row = BankTransaction(
            bank_account_id=tx.bank_account_id,
            transaction_date=tx.transaction_date,
            description=tx.description,
            amount=tx.amount,
            running_balance=tx.running_balance,
            reference=tx.reference,
            reconciliation_status="unreconciled",
            created_by=user_id,
        )
        db.add(row)
        inserted.append(row)
    db.commit()
    for r in inserted:
        db.refresh(r)
    return inserted


# ─── Reconciliation ─────────────────────────────────────────────────────────

@router.get(
    "/transactions/{bank_transaction_id}/candidates",
    response_model=List[CandidateJournalLine],
    dependencies=[VIEW],
)
def reconcile_candidates(bank_transaction_id: int, db: Session = Depends(get_db),
                         window_days: int = Query(7, ge=0, le=90)):
    """Suggest journal_lines that *might* match this bank transaction.

    Same-day to N days around the bank transaction, posted to the bank
    account's linked GL account, and with the same amount-magnitude on the
    matching side (Dr if money out, Cr if money in).
    """
    tx = db.query(BankTransaction).filter(BankTransaction.bank_transaction_id == bank_transaction_id).first()
    if not tx:
        raise HTTPException(404, detail="Bank transaction not found.")
    bank = db.query(BankAccount).filter(BankAccount.bank_account_id == tx.bank_account_id).first()
    if not bank or not bank.gl_account_id:
        return []
    from datetime import timedelta
    lo = tx.transaction_date - timedelta(days=window_days)
    hi = tx.transaction_date + timedelta(days=window_days)
    amt = abs(Decimal(tx.amount))

    from app.models.accounting import JournalEntry
    q = (
        db.query(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .filter(
            JournalLine.account_id == bank.gl_account_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= lo,
            JournalEntry.entry_date <= hi,
        )
    )
    if tx.amount >= 0:
        # Money in to bank — GL Dr to bank account
        q = q.filter(JournalLine.debit_base == amt)
    else:
        q = q.filter(JournalLine.credit_base == amt)

    out = []
    for line, entry in q.order_by(JournalEntry.entry_date).all():
        out.append(CandidateJournalLine(
            line_id=line.line_id,
            entry_number=entry.entry_number,
            entry_date=entry.entry_date,
            debit=line.debit,
            credit=line.credit,
            debit_base=line.debit_base,
            credit_base=line.credit_base,
            description=line.description,
            memo=entry.memo,
        ))
    return out


@router.post(
    "/transactions/{bank_transaction_id}/match",
    response_model=BankTxResponse,
    dependencies=[RECON],
)
def match_transaction(bank_transaction_id: int, payload: ReconcileMatchRequest,
                      db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    tx = db.query(BankTransaction).filter(BankTransaction.bank_transaction_id == bank_transaction_id).first()
    if not tx:
        raise HTTPException(404, detail="Bank transaction not found.")
    if tx.reconciliation_status == "matched":
        raise HTTPException(400, detail="Already reconciled.")
    line = db.query(JournalLine).filter(JournalLine.line_id == payload.journal_line_id).first()
    if not line:
        raise HTTPException(404, detail="Journal line not found.")
    bank = db.query(BankAccount).filter(BankAccount.bank_account_id == tx.bank_account_id).first()
    if bank and bank.gl_account_id and line.account_id != bank.gl_account_id:
        raise HTTPException(
            400,
            detail=f"Journal line is on a different GL account than this bank account's link.",
        )
    tx.reconciliation_status = "matched"
    tx.journal_line_id = line.line_id
    tx.reconciled_at = datetime.utcnow()
    tx.reconciled_by = _user_id(current_user)
    tx.ignore_reason = None
    db.commit()
    db.refresh(tx)
    return tx


@router.post(
    "/transactions/{bank_transaction_id}/ignore",
    response_model=BankTxResponse,
    dependencies=[RECON],
)
def ignore_transaction(bank_transaction_id: int, payload: ReconcileIgnoreRequest,
                       db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    tx = db.query(BankTransaction).filter(BankTransaction.bank_transaction_id == bank_transaction_id).first()
    if not tx:
        raise HTTPException(404, detail="Bank transaction not found.")
    tx.reconciliation_status = "ignored"
    tx.ignore_reason = payload.reason
    tx.reconciled_at = datetime.utcnow()
    tx.reconciled_by = _user_id(current_user)
    tx.journal_line_id = None
    db.commit()
    db.refresh(tx)
    return tx


@router.post(
    "/transactions/{bank_transaction_id}/unmatch",
    response_model=BankTxResponse,
    dependencies=[RECON],
)
def unmatch_transaction(bank_transaction_id: int, db: Session = Depends(get_db)):
    """Revert a transaction back to unreconciled."""
    tx = db.query(BankTransaction).filter(BankTransaction.bank_transaction_id == bank_transaction_id).first()
    if not tx:
        raise HTTPException(404, detail="Bank transaction not found.")
    tx.reconciliation_status = "unreconciled"
    tx.journal_line_id = None
    tx.reconciled_at = None
    tx.reconciled_by = None
    tx.ignore_reason = None
    db.commit()
    db.refresh(tx)
    return tx
