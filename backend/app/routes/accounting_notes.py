"""Debit / credit notes — post-invoice receivable adjustments.

Reads require ``accounting:view``. Creating/deleting a draft needs
``accounting:notes.manage``; posting or voiding additionally needs
``accounting:journal.post`` so the note pipeline respects the same
separation-of-duties as manual journals.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.accounting import AdjustmentNote
from app.services import accounting_notes as svc

router = APIRouter(prefix="/api/accounting/notes", tags=["Accounting · Notes"])

VIEW = Depends(RequirePermission("accounting:view"))
MANAGE = Depends(RequirePermission("accounting:notes.manage"))
POST = Depends(RequirePermission("accounting:journal.post"))


def _user_id(current_user) -> int:
    return current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", 0)


# ─── Schemas ────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    note_type: str = Field(pattern="^(debit|credit)$")
    note_date: Optional[date] = None
    amount: Decimal = Field(gt=0)
    debit_account_id: int
    credit_account_id: int
    currency_code: str = Field(default="KES", max_length=3)
    invoice_id: Optional[int] = None
    target_entry_id: Optional[int] = None
    reason: Optional[str] = None


class NoteVoidRequest(BaseModel):
    reason: Optional[str] = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    note_id: int
    note_number: str
    note_type: str
    note_date: date
    amount: Decimal
    invoice_id: Optional[int]
    target_entry_id: Optional[int]
    debit_account_id: int
    credit_account_id: int
    currency_code: str
    reason: Optional[str]
    status: str
    journal_entry_id: Optional[int]
    created_by: int
    posted_by: Optional[int]
    posted_at: Optional[datetime]
    voided_by: Optional[int]
    voided_at: Optional[datetime]


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[NoteResponse], dependencies=[VIEW])
def list_notes(db: Session = Depends(get_db),
               note_type: Optional[str] = None,
               status: Optional[str] = None):
    q = db.query(AdjustmentNote)
    if note_type:
        q = q.filter(AdjustmentNote.note_type == note_type)
    if status:
        q = q.filter(AdjustmentNote.status == status)
    return q.order_by(AdjustmentNote.created_at.desc()).all()


@router.get("/{note_id}", response_model=NoteResponse, dependencies=[VIEW])
def get_note(note_id: int, db: Session = Depends(get_db)):
    row = db.query(AdjustmentNote).filter(AdjustmentNote.note_id == note_id).first()
    if not row:
        raise HTTPException(404, detail="Note not found.")
    return row


@router.post("", response_model=NoteResponse, dependencies=[MANAGE])
def create_note(payload: NoteCreate, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)):
    note = svc.create_note(
        db,
        note_type=payload.note_type,
        note_date=payload.note_date or date.today(),
        amount=payload.amount,
        debit_account_id=payload.debit_account_id,
        credit_account_id=payload.credit_account_id,
        user_id=_user_id(current_user),
        currency_code=payload.currency_code,
        invoice_id=payload.invoice_id,
        target_entry_id=payload.target_entry_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(note)
    return note


@router.post("/{note_id}/post", response_model=NoteResponse, dependencies=[MANAGE, POST])
def post_note(note_id: int, db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    note = svc.post_note(db, note_id=note_id, user_id=_user_id(current_user))
    db.commit()
    db.refresh(note)
    return note


@router.post("/{note_id}/void", response_model=NoteResponse, dependencies=[MANAGE, POST])
def void_note(note_id: int, payload: NoteVoidRequest, db: Session = Depends(get_db),
              current_user=Depends(get_current_user)):
    note = svc.void_note(db, note_id=note_id, user_id=_user_id(current_user),
                         reason=payload.reason)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204, dependencies=[MANAGE])
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(AdjustmentNote).filter(AdjustmentNote.note_id == note_id).first()
    if not note:
        raise HTTPException(404, detail="Note not found.")
    if note.status != "draft":
        raise HTTPException(400, detail="Only draft notes can be deleted.")
    db.delete(note)
    db.commit()
