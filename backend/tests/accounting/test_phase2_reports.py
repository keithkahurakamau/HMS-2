"""Phase 2 — financial reports.

Each report is a pure aggregation over posted journal lines. Tests post a
known set of entries and assert the report numbers match.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.accounting_reports import (
    balance_sheet,
    cash_flow,
    daily_collections,
    income_statement,
    trial_balance,
)
from .conftest import post_simple_entry


# ─── Trial Balance ──────────────────────────────────────────────────────────

def test_trial_balance_reconciles(db):
    # Three entries; every Dr matched by a Cr on the other side.
    post_simple_entry(db, "1110", "4100", 500)
    post_simple_entry(db, "1120", "4500", 1500)
    post_simple_entry(db, "6300", "1120", 200)

    tb = trial_balance(db, as_of=date.today())
    # Sanity: 4 unique accounts touched (1110, 1120, 4100, 4500, 6300)
    codes = {r["code"] for r in tb["rows"]}
    assert codes == {"1110", "1120", "4100", "4500", "6300"}
    assert tb["totals"]["debit"] == tb["totals"]["credit"]
    assert tb["totals"]["difference"] == Decimal("0")


def test_trial_balance_excludes_reversed_pair(db):
    """A reversed entry + its mirror cancel out — neither contributes to
    the trial balance. Accounts touched only by the reversed pair don't
    appear at all (rather than showing as zero-balance rows)."""
    from app.services.accounting import reverse_entry

    original = post_simple_entry(db, "1110", "4100", 1000)
    reverse_entry(db, original.entry_id, user_id=1)
    db.commit()

    tb = trial_balance(db, as_of=date.today())
    # Neither account should be in the report — the pair nets to zero,
    # there are no other postings, so the trial balance is empty.
    codes = [r["code"] for r in tb["rows"]]
    assert "1110" not in codes
    assert "4100" not in codes
    assert tb["totals"]["debit"] == Decimal("0")
    assert tb["totals"]["credit"] == Decimal("0")
    assert tb["totals"]["difference"] == Decimal("0")


def test_trial_balance_with_one_reversed_and_one_active(db):
    """When a pair is reversed but another entry remains, only the
    remaining entry's effect shows up in the trial balance."""
    from app.services.accounting import reverse_entry

    # Reversed pair: nets to zero.
    bad = post_simple_entry(db, "1110", "4100", 500)
    reverse_entry(db, bad.entry_id, user_id=1)
    # Surviving entry.
    post_simple_entry(db, "1110", "4500", 200)
    db.commit()

    tb = trial_balance(db, as_of=date.today())
    row_1110 = next(r for r in tb["rows"] if r["code"] == "1110")
    row_4500 = next(r for r in tb["rows"] if r["code"] == "4500")
    assert row_1110["balance"] == Decimal("200")
    assert row_4500["balance"] == Decimal("200")
    # 4100 not touched by anything that survived.
    codes = [r["code"] for r in tb["rows"]]
    assert "4100" not in codes


# ─── Income Statement (P&L) ─────────────────────────────────────────────────

def test_income_statement_net_income_is_revenue_minus_expenses(db):
    # Revenue: 5000. COGS: 1200. Opex: 800.
    post_simple_entry(db, "1110", "4100", 5000)
    post_simple_entry(db, "5100", "1160", 1200)  # COGS
    post_simple_entry(db, "6300", "1120", 800)   # opex (utilities)

    today = date.today()
    pl = income_statement(db, from_date=today, to_date=today)
    assert pl["total_revenue"] == Decimal("5000")
    assert pl["total_cogs"] == Decimal("1200")
    assert pl["gross_profit"] == Decimal("3800")
    assert pl["total_operating_expenses"] == Decimal("800")
    assert pl["net_income"] == Decimal("3000")  # 5000 - 1200 - 800


def test_income_statement_filters_to_window(db):
    from datetime import timedelta
    today = date.today()
    old = today - timedelta(days=30)

    post_simple_entry(db, "1110", "4100", 1000, on_date=old)
    post_simple_entry(db, "1110", "4100", 500, on_date=today)

    pl = income_statement(db, from_date=today, to_date=today)
    assert pl["total_revenue"] == Decimal("500")


# ─── Balance Sheet ──────────────────────────────────────────────────────────

def test_balance_sheet_balances(db):
    # Owner contributes capital: Dr Cash, Cr Owner's Capital.
    post_simple_entry(db, "1110", "3100", 10000)
    # Receive revenue: Dr Cash, Cr Revenue.
    post_simple_entry(db, "1110", "4100", 2500)
    # Pay an expense: Dr Utilities, Cr Cash.
    post_simple_entry(db, "6300", "1110", 300)

    bs = balance_sheet(db, as_of=date.today())
    # Assets = Liab + Equity. Net Income (rev − exp) rolls into equity.
    assert bs["balanced"] is True
    assert bs["total_assets"] == bs["total_liabilities_and_equity"]
    # Specifically: assets = 10000 + 2500 - 300 = 12200
    assert bs["total_assets"] == Decimal("12200")
    # Owner's capital 10000 + current-year earnings (2500 − 300) = 12200
    assert bs["total_equity"] == Decimal("12200")
    assert bs["current_year_earnings"] == Decimal("2200")


# ─── Cash Flow ──────────────────────────────────────────────────────────────

def test_cash_flow_categorizes_by_counterparty_type(db):
    # Operating (other side is Revenue/Expense)
    post_simple_entry(db, "1110", "4100", 1000)  # +1000 operating
    post_simple_entry(db, "6300", "1110", 200)   # -200 operating
    # Financing (other side is Equity)
    post_simple_entry(db, "1110", "3100", 5000)  # +5000 financing

    cf = cash_flow(db, from_date=date.today(), to_date=date.today())
    assert cf["operating"] == Decimal("800")     # 1000 - 200
    assert cf["financing"] == Decimal("5000")
    assert cf["investing"] == Decimal("0")
    assert cf["net_change"] == Decimal("5800")
    assert cf["cash_in"] == Decimal("6000")      # 1000 + 5000
    assert cf["cash_out"] == Decimal("200")


# ─── Daily Collections ──────────────────────────────────────────────────────

def test_daily_collections_sums_cash_inflows_only(db):
    today = date.today()
    post_simple_entry(db, "1110", "4100", 300, on_date=today)   # cash in
    post_simple_entry(db, "1120", "4500", 700, on_date=today)   # bank in
    post_simple_entry(db, "6300", "1110", 50,  on_date=today)   # cash OUT — should NOT count

    dc = daily_collections(db, from_date=today, to_date=today)
    # Three rows expected? Actually two: 1110 nets to 300−50=250 in this
    # implementation — but the report only counts debits (cash IN), so
    # the 50 outflow doesn't subtract from the 300 inflow.
    total_in = sum(r["amount"] for r in dc["rows"])
    assert total_in == Decimal("1000")
    assert dc["total"] == Decimal("1000")
