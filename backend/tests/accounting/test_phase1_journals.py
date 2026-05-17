"""Phase 1 — journal entry lifecycle + invariants.

Covers:
- Balanced entries post cleanly; unbalanced ones raise on post.
- Posted entries become immutable.
- Reversal creates a mirror entry and marks the original as reversed.
- Fiscal period auto-created on demand; closed periods reject new posts.
- FX rate resolution for non-base currency entries.
- Zero-amount and roll-up account postings are refused.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.accounting import FiscalPeriod, JournalEntry
from app.services.accounting import (
    close_fiscal_period,
    create_draft_entry,
    ensure_fiscal_period,
    post_entry,
    resolve_fx_rate,
    reverse_entry,
    seed_fiscal_year,
)
from .conftest import account_id, post_simple_entry


class _LineIn:
    def __init__(self, account_id, debit=Decimal(0), credit=Decimal(0), description=None):
        self.account_id = account_id
        self.debit = debit
        self.credit = credit
        self.description = description


# ─── Balance invariant ───────────────────────────────────────────────────────

def test_balanced_entry_posts(db):
    entry = post_simple_entry(db, "1110", "4100", 1000)
    assert entry.status == "posted"
    assert entry.posted_at is not None


def test_unbalanced_entry_blocks_post(db):
    dr = _LineIn(account_id(db, "1110"), debit=Decimal("100"))
    cr = _LineIn(account_id(db, "4100"), credit=Decimal("75"))  # mismatched
    entry = create_draft_entry(
        db,
        entry_date=date.today(),
        currency_code="KES",
        fx_rate=None,
        lines_in=[dr, cr],
        user_id=1,
    )
    db.commit()
    with pytest.raises(HTTPException) as exc:
        post_entry(db, entry.entry_id, user_id=1)
    assert exc.value.status_code == 400
    assert "unbalanced" in exc.value.detail.lower()


def test_zero_total_entry_blocks_post(db):
    dr = _LineIn(account_id(db, "1110"), debit=Decimal("0"))
    cr = _LineIn(account_id(db, "4100"), credit=Decimal("0"))
    with pytest.raises(HTTPException) as exc:
        create_draft_entry(
            db, entry_date=date.today(), currency_code="KES",
            fx_rate=None, lines_in=[dr, cr], user_id=1,
        )
    # Either the per-line invariant or the < 2 lines guard catches this;
    # both surface as 400.
    assert exc.value.status_code == 400


# ─── Immutability + reversal ────────────────────────────────────────────────

def test_posted_entry_cannot_be_reposted(db):
    entry = post_simple_entry(db, "1110", "4100", 500)
    with pytest.raises(HTTPException) as exc:
        post_entry(db, entry.entry_id, user_id=1)
    assert exc.value.status_code == 400


def test_reversal_creates_mirror_and_marks_original(db):
    original = post_simple_entry(db, "1110", "4100", 200,
                                 memo="Original sale")
    mirror = reverse_entry(db, original.entry_id, user_id=1, reason="duplicate")
    db.commit()
    db.refresh(original)
    db.refresh(mirror)

    assert original.status == "reversed"
    assert original.reversed_at is not None
    assert mirror.status == "posted"
    assert mirror.reverses_entry_id == original.entry_id

    # Mirror's debit side mirrors original's credit side (and vice versa).
    orig_lines = sorted(original.lines, key=lambda l: l.line_number)
    mir_lines = sorted(mirror.lines, key=lambda l: l.line_number)
    for orig, mir in zip(orig_lines, mir_lines):
        assert mir.debit == orig.credit
        assert mir.credit == orig.debit


def test_cannot_reverse_a_draft_or_already_reversed_entry(db):
    # Cannot reverse a draft.
    dr = _LineIn(account_id(db, "1110"), debit=Decimal("10"))
    cr = _LineIn(account_id(db, "4100"), credit=Decimal("10"))
    draft = create_draft_entry(
        db, entry_date=date.today(), currency_code="KES",
        fx_rate=None, lines_in=[dr, cr], user_id=1,
    )
    db.commit()
    with pytest.raises(HTTPException):
        reverse_entry(db, draft.entry_id, user_id=1)

    # Cannot reverse an already-reversed entry.
    posted = post_simple_entry(db, "1110", "4100", 50)
    reverse_entry(db, posted.entry_id, user_id=1)
    db.commit()
    with pytest.raises(HTTPException):
        reverse_entry(db, posted.entry_id, user_id=1)


# ─── Fiscal period gating ───────────────────────────────────────────────────

def test_period_auto_created_on_post(db):
    on = date.today()
    period = ensure_fiscal_period(db, on)
    db.commit()
    assert period.year == on.year
    assert period.month == on.month
    assert period.status == "open"


def test_seed_fiscal_year_is_idempotent(db):
    seed_fiscal_year(db, 2099)
    seed_fiscal_year(db, 2099)
    db.commit()
    count = db.query(FiscalPeriod).filter(FiscalPeriod.year == 2099).count()
    assert count == 12


def test_closed_period_blocks_posting(db):
    on = date.today()
    period = ensure_fiscal_period(db, on)
    db.commit()
    close_fiscal_period(db, period.period_id, user_id=1)
    db.commit()

    dr = _LineIn(account_id(db, "1110"), debit=Decimal("10"))
    cr = _LineIn(account_id(db, "4100"), credit=Decimal("10"))
    # ensure_fiscal_period raises during draft creation.
    with pytest.raises(HTTPException) as exc:
        create_draft_entry(
            db, entry_date=on, currency_code="KES",
            fx_rate=None, lines_in=[dr, cr], user_id=1,
        )
    assert exc.value.status_code == 400


# ─── Non-postable account guard ─────────────────────────────────────────────

def test_cannot_post_to_rollup_account(db):
    # 1000 'Assets' is a roll-up — not postable.
    dr = _LineIn(account_id(db, "1000"), debit=Decimal("10"))
    cr = _LineIn(account_id(db, "4100"), credit=Decimal("10"))
    with pytest.raises(HTTPException) as exc:
        create_draft_entry(
            db, entry_date=date.today(), currency_code="KES",
            fx_rate=None, lines_in=[dr, cr], user_id=1,
        )
    assert exc.value.status_code == 400


# ─── FX rate resolution ─────────────────────────────────────────────────────

def test_same_currency_fx_rate_is_one(db):
    rate = resolve_fx_rate(db, "KES", "KES", date.today())
    assert rate == Decimal("1")


def test_missing_fx_rate_raises(db):
    with pytest.raises(HTTPException) as exc:
        resolve_fx_rate(db, "USD", "KES", date.today())
    assert exc.value.status_code == 400


def test_picks_most_recent_fx_rate(db):
    from app.models.accounting import Currency, FxRate
    db.add(Currency(code="USD", name="US Dollar", decimals=2, is_active=True))
    db.flush()
    db.add(FxRate(from_currency="USD", to_currency="KES",
                  rate=Decimal("140"), effective_date=date.today() - timedelta(days=5)))
    db.add(FxRate(from_currency="USD", to_currency="KES",
                  rate=Decimal("145"), effective_date=date.today()))
    db.commit()

    rate = resolve_fx_rate(db, "USD", "KES", date.today())
    assert rate == Decimal("145")

    # Asking for an earlier date returns the older rate.
    older = resolve_fx_rate(db, "USD", "KES", date.today() - timedelta(days=2))
    assert older == Decimal("140")
