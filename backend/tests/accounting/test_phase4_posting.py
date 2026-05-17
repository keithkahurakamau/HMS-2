"""Phase 4 — auto-posting bridge.

Covers the invariants `accounting_posting.post_from_event` advertises:
- balanced 2-line entry per call, accounts come from LedgerMapping
- idempotent on (source_key, source_id)
- skipped silently before go_live_date
- never raises (returns None on misconfiguration)
- payment_method_to_key maps tolerantly
- post_dispense_pair emits two distinct entries (revenue + COGS)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.accounting import (
    AccountingSettings,
    JournalEntry,
    LedgerMapping,
)
from app.services.accounting_posting import (
    payment_method_to_key,
    post_dispense_pair,
    post_from_event,
)
from .conftest import account_id


# ─── Basic post ─────────────────────────────────────────────────────────────

def test_post_from_event_creates_balanced_entry(db):
    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.payment.cash",
        source_id=1001,
        amount=Decimal("2500"),
        memo="Test cash receipt",
    )
    assert entry is not None
    assert entry.status == "posted"
    assert len(entry.lines) == 2
    dr_line = next(l for l in entry.lines if l.debit > 0)
    cr_line = next(l for l in entry.lines if l.credit > 0)
    assert dr_line.account_id == account_id(db, "1110")  # Cash
    assert cr_line.account_id == account_id(db, "1140")  # AR
    assert dr_line.debit == Decimal("2500.0000")
    assert cr_line.credit == Decimal("2500.0000")


# ─── Idempotency ────────────────────────────────────────────────────────────

def test_idempotent_on_source_key_and_id(db):
    a = post_from_event(db, user_id=1, source_key="billing.payment.cash",
                        source_id=42, amount=Decimal("100"))
    b = post_from_event(db, user_id=1, source_key="billing.payment.cash",
                        source_id=42, amount=Decimal("100"))
    assert a is not None and b is not None
    assert a.entry_id == b.entry_id
    # Only one entry should have been created.
    count = db.query(JournalEntry).filter(
        JournalEntry.source_type == "billing.payment.cash",
        JournalEntry.source_id == 42,
    ).count()
    assert count == 1


def test_same_source_id_different_key_creates_distinct_entries(db):
    a = post_from_event(db, user_id=1, source_key="pharmacy.dispense.revenue",
                        source_id=7, amount=Decimal("500"))
    b = post_from_event(db, user_id=1, source_key="pharmacy.dispense.cogs",
                        source_id=7, amount=Decimal("300"))
    assert a.entry_id != b.entry_id


# ─── Go-live gate ───────────────────────────────────────────────────────────

def test_skips_events_before_go_live(db):
    settings = db.query(AccountingSettings).first()
    settings.go_live_date = date.today() + timedelta(days=10)
    db.commit()

    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.payment.cash",
        source_id=999,
        amount=Decimal("100"),
        on_date=date.today(),  # earlier than go-live
    )
    assert entry is None
    # No journal entry was actually created.
    assert db.query(JournalEntry).count() == 0


# ─── Misconfiguration ──────────────────────────────────────────────────────

def test_missing_mapping_returns_none_without_raising(db):
    entry = post_from_event(
        db,
        user_id=1,
        source_key="totally.unknown.event",
        source_id=1,
        amount=Decimal("100"),
    )
    assert entry is None


def test_mapping_with_null_accounts_returns_none(db):
    mapping = db.query(LedgerMapping).filter(
        LedgerMapping.source_key == "billing.payment.cash"
    ).first()
    mapping.debit_account_id = None
    db.commit()

    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.payment.cash",
        source_id=1,
        amount=Decimal("100"),
    )
    assert entry is None


def test_zero_amount_skipped(db):
    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.payment.cash",
        source_id=2,
        amount=Decimal("0"),
    )
    assert entry is None


# ─── Payment method translator ─────────────────────────────────────────────

def test_payment_method_to_key_recognises_variants():
    assert payment_method_to_key("Cash") == "billing.payment.cash"
    assert payment_method_to_key("M-PESA") == "billing.payment.mpesa"
    assert payment_method_to_key("Mobile Money") == "billing.payment.mpesa"
    assert payment_method_to_key("Bank Transfer") == "billing.payment.bank"
    assert payment_method_to_key("Credit Card") == "billing.payment.bank"
    # Unknown defaults to cash but doesn't crash.
    assert payment_method_to_key("Goat Trade") == "billing.payment.cash"
    assert payment_method_to_key(None) == "billing.payment.cash"


# ─── Dispense pair ─────────────────────────────────────────────────────────

def test_post_dispense_pair_creates_two_entries(db):
    rev, cogs = post_dispense_pair(
        db,
        user_id=1,
        dispense_id=5001,
        revenue_amount=Decimal("800"),
        cogs_amount=Decimal("450"),
    )
    db.commit()
    assert rev is not None and cogs is not None
    assert rev.entry_id != cogs.entry_id

    # Revenue: Dr AR / Cr Pharmacy Revenue
    rev_dr = next(l for l in rev.lines if l.debit > 0)
    rev_cr = next(l for l in rev.lines if l.credit > 0)
    assert rev_dr.account_id == account_id(db, "1140")
    assert rev_cr.account_id == account_id(db, "4500")
    assert rev_dr.debit == Decimal("800.0000")

    # COGS: Dr Cost of Drugs / Cr Inventory
    cogs_dr = next(l for l in cogs.lines if l.debit > 0)
    cogs_cr = next(l for l in cogs.lines if l.credit > 0)
    assert cogs_dr.account_id == account_id(db, "5100")
    assert cogs_cr.account_id == account_id(db, "1160")
    assert cogs_dr.debit == Decimal("450.0000")
