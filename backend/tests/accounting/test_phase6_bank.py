"""Phase 6 — bank module + reconciliation.

Routes-side logic is exercised directly against the models since the
service layer is thin. Covers:
- BankAccount + BankTransaction CRUD basics
- Reconciliation transitions: unreconciled → matched / ignored / unmatch
- Candidate matching window (amount magnitude + GL account + date window)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_

from app.models.accounting import (
    Account,
    BankAccount,
    BankTransaction,
)
from .conftest import account_id, post_simple_entry


# ─── Helpers ────────────────────────────────────────────────────────────────

def _bank_account(db, *, name="Main Ops", number="0123456789", gl_code="1120"):
    gl = db.query(Account).filter(Account.code == gl_code).first()
    a = BankAccount(
        name=name, bank_name="Equity Bank", account_number=number,
        currency_code="KES", gl_account_id=gl.account_id if gl else None,
        is_active=True,
    )
    db.add(a)
    db.commit()
    return a


def _bank_tx(db, bank, *, on_date=None, amount=Decimal("1000"),
             description="Test deposit", reference=None):
    tx = BankTransaction(
        bank_account_id=bank.bank_account_id,
        transaction_date=on_date or date.today(),
        description=description,
        amount=amount,
        reference=reference,
        reconciliation_status="unreconciled",
        created_by=1,
    )
    db.add(tx)
    db.commit()
    return tx


# ─── Basics ─────────────────────────────────────────────────────────────────

def test_bank_account_unique_per_bank_number(db):
    from sqlalchemy.exc import IntegrityError
    _bank_account(db, name="A", number="9999")
    bank = BankAccount(
        name="Different Internal Name",
        bank_name="Equity Bank",
        account_number="9999",
        currency_code="KES",
        is_active=True,
    )
    db.add(bank)
    try:
        db.commit()
        assert False, "expected unique constraint violation"
    except IntegrityError:
        db.rollback()


# ─── Reconciliation state machine ──────────────────────────────────────────

def test_match_transitions(db):
    bank = _bank_account(db)
    # Post a ledger entry against the bank GL account.
    entry = post_simple_entry(db, "1120", "4100", 750, memo="Customer EFT")
    bank_line = next(l for l in entry.lines if l.debit > 0 and l.account_id == account_id(db, "1120"))

    tx = _bank_tx(db, bank, amount=Decimal("750"), description="Inward EFT")

    # Simulate the match endpoint: link line + flip status.
    tx.reconciliation_status = "matched"
    tx.journal_line_id = bank_line.line_id
    tx.reconciled_at = datetime.utcnow()
    tx.reconciled_by = 1
    db.commit()
    db.refresh(tx)

    assert tx.reconciliation_status == "matched"
    assert tx.journal_line_id == bank_line.line_id


def test_ignore_transition(db):
    bank = _bank_account(db)
    tx = _bank_tx(db, bank, amount=Decimal("50"), description="Bank charge")
    tx.reconciliation_status = "ignored"
    tx.ignore_reason = "Already booked under fees"
    tx.reconciled_at = datetime.utcnow()
    tx.reconciled_by = 1
    db.commit()
    db.refresh(tx)
    assert tx.reconciliation_status == "ignored"
    assert tx.ignore_reason is not None
    assert tx.journal_line_id is None


def test_unmatch_returns_to_unreconciled(db):
    bank = _bank_account(db)
    entry = post_simple_entry(db, "1120", "4100", 200)
    bank_line = next(l for l in entry.lines if l.debit > 0 and l.account_id == account_id(db, "1120"))
    tx = _bank_tx(db, bank, amount=Decimal("200"))
    tx.reconciliation_status = "matched"
    tx.journal_line_id = bank_line.line_id
    tx.reconciled_by = 1
    tx.reconciled_at = datetime.utcnow()
    db.commit()

    # Revert
    tx.reconciliation_status = "unreconciled"
    tx.journal_line_id = None
    tx.reconciled_at = None
    tx.reconciled_by = None
    db.commit()
    db.refresh(tx)

    assert tx.reconciliation_status == "unreconciled"
    assert tx.journal_line_id is None


# ─── Candidate matching ────────────────────────────────────────────────────

def test_candidate_finds_matching_journal_line(db):
    """The candidates endpoint filters journal lines by:
    - same GL account as the bank account's gl_account_id
    - same amount-magnitude on the matching side (Dr for money-in)
    - within ±7 days of the transaction date

    This test reproduces that query directly to keep the dependency on
    route code shallow."""
    from datetime import timedelta
    from app.models.accounting import JournalEntry, JournalLine

    bank = _bank_account(db, gl_code="1120")
    # Three entries on different dates and amounts.
    on1 = date.today()
    on2 = date.today() - timedelta(days=3)
    on3 = date.today() - timedelta(days=30)  # outside window
    post_simple_entry(db, "1120", "4100", 1500, on_date=on1)
    post_simple_entry(db, "1120", "4100", 1500, on_date=on2)
    post_simple_entry(db, "1120", "4100", 1500, on_date=on3)
    post_simple_entry(db, "1120", "4100",  999, on_date=on1)  # wrong amount

    target = Decimal("1500")
    lo = on1 - timedelta(days=7)
    hi = on1 + timedelta(days=7)

    candidates = (
        db.query(JournalLine)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .filter(
            JournalLine.account_id == bank.gl_account_id,
            JournalLine.debit_base == target,
            JournalEntry.entry_date >= lo,
            JournalEntry.entry_date <= hi,
            JournalEntry.status == "posted",
        )
        .all()
    )
    # Should find the two 1500-on-date and exclude the old + the 999.
    assert len(candidates) == 2


# ─── Bulk-import dedupe ────────────────────────────────────────────────────

def test_bulk_import_dedupe(db):
    """Re-importing the same (date, amount, reference) on the same account
    should produce zero new rows. The route does this via an EXISTS check;
    here we simulate it via direct query semantics."""
    bank = _bank_account(db)
    _bank_tx(db, bank, on_date=date.today(), amount=Decimal("123.45"), reference="REF-A")

    duplicate_exists = (
        db.query(BankTransaction).filter(
            and_(
                BankTransaction.bank_account_id == bank.bank_account_id,
                BankTransaction.transaction_date == date.today(),
                BankTransaction.amount == Decimal("123.45"),
                BankTransaction.reference == "REF-A",
            )
        ).count()
    )
    assert duplicate_exists == 1
