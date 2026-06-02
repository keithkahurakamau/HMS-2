"""
Debit / credit note service.

A note is an adjustment to a receivable that posts through the *normal*
journal pipeline — `create_draft_entry` + `post_entry` — so it inherits
every ledger invariant (balanced, postable accounts only, no closed
periods). We never flip a note (or its entry) to 'posted' by hand.

  * credit note → reduces the customer's balance (Dr Revenue / Cr AR)
  * debit  note → increases it                (Dr AR / Cr Revenue)

The two accounts are chosen by the caller (debit_account_id /
credit_account_id) so the same machinery covers supplier-side notes too.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.accounting import AdjustmentNote, JournalEntry
from app.services.accounting import create_draft_entry, post_entry, reverse_entry


@dataclass
class _Line:
    """Minimal shape `create_draft_entry` expects from a line input."""
    account_id: int
    debit: Decimal
    credit: Decimal
    description: Optional[str] = None


def _next_note_number(db: Session, note_type: str, on: date) -> str:
    prefix = f"{'DN' if note_type == 'debit' else 'CN'}-{on.year:04d}{on.month:02d}-"
    count = (
        db.query(AdjustmentNote)
        .filter(AdjustmentNote.note_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


def create_note(db: Session, *, note_type: str, note_date: date, amount,
                debit_account_id: int, credit_account_id: int,
                user_id: int,
                currency_code: str = "KES",
                invoice_id: Optional[int] = None,
                target_entry_id: Optional[int] = None,
                reason: Optional[str] = None) -> AdjustmentNote:
    if note_type not in ("debit", "credit"):
        raise HTTPException(400, detail="note_type must be 'debit' or 'credit'.")
    amt = Decimal(str(amount))
    if amt <= Decimal("0"):
        raise HTTPException(400, detail="Note amount must be positive.")
    if debit_account_id == credit_account_id:
        raise HTTPException(400, detail="Debit and credit accounts must differ.")

    note = AdjustmentNote(
        note_number=_next_note_number(db, note_type, note_date),
        note_type=note_type,
        note_date=note_date,
        amount=amt,
        invoice_id=invoice_id,
        target_entry_id=target_entry_id,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        currency_code=currency_code,
        reason=reason,
        status="draft",
        created_by=user_id,
    )
    db.add(note)
    db.flush()
    db.refresh(note)
    return note


def post_note(db: Session, *, note_id: int, user_id: int) -> AdjustmentNote:
    note = db.query(AdjustmentNote).filter(AdjustmentNote.note_id == note_id).first()
    if not note:
        raise HTTPException(404, detail="Note not found.")
    if note.status != "draft":
        raise HTTPException(400, detail=f"Cannot post a note in status '{note.status}'.")

    amt = Decimal(note.amount)
    lines = [
        _Line(account_id=note.debit_account_id, debit=amt, credit=Decimal("0"),
              description=f"{note.note_number}: {note.reason or note.note_type + ' note'}"),
        _Line(account_id=note.credit_account_id, debit=Decimal("0"), credit=amt,
              description=f"{note.note_number}: {note.reason or note.note_type + ' note'}"),
    ]
    entry = create_draft_entry(
        db,
        entry_date=note.note_date,
        currency_code=note.currency_code,
        fx_rate=None,
        lines_in=lines,
        user_id=user_id,
        memo=f"{note.note_type.capitalize()} note {note.note_number}"
             + (f" — {note.reason}" if note.reason else ""),
        reference=note.note_number,
        source_type=f"accounting.{note.note_type}_note",
        source_id=note.note_id,
    )
    post_entry(db, entry.entry_id, user_id)

    note.journal_entry_id = entry.entry_id
    note.status = "posted"
    note.posted_by = user_id
    note.posted_at = datetime.utcnow()
    db.flush()
    db.refresh(note)
    return note


def void_note(db: Session, *, note_id: int, user_id: int,
              reason: Optional[str] = None) -> AdjustmentNote:
    note = db.query(AdjustmentNote).filter(AdjustmentNote.note_id == note_id).first()
    if not note:
        raise HTTPException(404, detail="Note not found.")
    if note.status != "posted":
        raise HTTPException(400, detail=f"Only posted notes can be voided (status='{note.status}').")
    if note.journal_entry_id:
        reverse_entry(db, note.journal_entry_id, user_id,
                      reason=reason or f"Void of {note.note_number}")
    note.status = "void"
    note.voided_by = user_id
    note.voided_at = datetime.utcnow()
    db.flush()
    db.refresh(note)
    return note
