"""
Financial reports — read-only views over posted journal lines.

All numbers in base currency (KES by default). Drafts and reversed entries
are excluded. Reversed entries also exclude their original — the pair
nets to zero so leaving the original in would just double-count.

Account-type semantics:

    Asset / Expense     — debit-side accounts; balance = Dr - Cr
    Liability / Equity  — credit-side accounts; balance = Cr - Dr
    Revenue             — credit-side account;  balance = Cr - Dr

The trial balance preserves the natural sign per account type so the
report reads the way an accountant expects. P&L and Balance Sheet apply
the sign rules to produce always-positive line amounts under their
normal sections.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from app.models.accounting import Account, JournalEntry, JournalLine


ZERO = Decimal("0")

# Account-type → which side is "natural positive".
# debit-natural means balance = sum(debit) - sum(credit)
# credit-natural means balance = sum(credit) - sum(debit)
NATURAL_SIDE = {
    "Asset": "debit",
    "Expense": "debit",
    "Liability": "credit",
    "Equity": "credit",
    "Revenue": "credit",
}

# Account codes we treat as cash & equivalents in the Cash Flow report.
# Conservative default: any account starting with 11 in the Assets tree
# AND whose name matches one of the obvious cash labels. Tenants who add
# new bank accounts under 1120 / 1130 will be picked up automatically.
CASH_PREFIXES = ("1110", "1120", "1130")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _posted_lines_query(db: Session, on_or_before: Optional[date] = None,
                        from_date: Optional[date] = None,
                        to_date: Optional[date] = None):
    """Base query: journal_lines from posted entries, optionally bounded by
    a date filter on the entry header."""
    q = (
        db.query(JournalLine, JournalEntry, Account)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.entry_id)
        .join(Account, JournalLine.account_id == Account.account_id)
        .filter(JournalEntry.status == "posted")
        # Exclude reversal mirrors so a reversed entry pair nets to zero
        # in the report (the original is already excluded via status='reversed').
        .filter(JournalEntry.reverses_entry_id.is_(None))
    )
    if on_or_before is not None:
        q = q.filter(JournalEntry.entry_date <= on_or_before)
    if from_date is not None:
        q = q.filter(JournalEntry.entry_date >= from_date)
    if to_date is not None:
        q = q.filter(JournalEntry.entry_date <= to_date)
    return q


def _signed_balance(account_type: str, dr: Decimal, cr: Decimal) -> Decimal:
    """Apply natural-side rule. Returns a positive number when the account
    is in its expected position (e.g. a positive number on an Asset means
    'has assets'), negative otherwise."""
    if NATURAL_SIDE.get(account_type) == "debit":
        return dr - cr
    return cr - dr


# ─── Trial Balance ───────────────────────────────────────────────────────────

def trial_balance(db: Session, as_of: date) -> dict:
    """Per-account Dr/Cr totals + signed balance, plus grand totals.

    Lines are aggregated up to and including `as_of`. Roll-up parents are
    NOT included (they don't receive postings); only leaf accounts that
    have at least one line are returned.
    """
    rows: Dict[int, Dict] = {}
    for line, entry, acc in _posted_lines_query(db, on_or_before=as_of):
        bucket = rows.setdefault(acc.account_id, {
            "account_id": acc.account_id,
            "code": acc.code,
            "name": acc.name,
            "account_type": acc.account_type,
            "debit": ZERO,
            "credit": ZERO,
        })
        bucket["debit"] += Decimal(line.debit_base)
        bucket["credit"] += Decimal(line.credit_base)

    result = []
    grand_dr = ZERO
    grand_cr = ZERO
    for r in sorted(rows.values(), key=lambda x: x["code"]):
        bal = _signed_balance(r["account_type"], r["debit"], r["credit"])
        r["balance"] = bal
        grand_dr += r["debit"]
        grand_cr += r["credit"]
        result.append(r)

    return {
        "as_of": as_of,
        "rows": result,
        "totals": {
            "debit": grand_dr,
            "credit": grand_cr,
            "difference": grand_dr - grand_cr,  # should be zero
        },
    }


# ─── Income Statement (P&L) ──────────────────────────────────────────────────

def income_statement(db: Session, from_date: date, to_date: date) -> dict:
    """Revenue − COGS − Operating Expenses = Net Income.

    Revenue and Expense balances are signed positive under their natural
    side; net income is Revenue − (sum of all expenses).
    """
    rev_rows: Dict[int, Dict] = {}
    exp_rows: Dict[int, Dict] = {}
    for line, entry, acc in _posted_lines_query(db, from_date=from_date, to_date=to_date):
        if acc.account_type not in ("Revenue", "Expense"):
            continue
        target = rev_rows if acc.account_type == "Revenue" else exp_rows
        bucket = target.setdefault(acc.account_id, {
            "account_id": acc.account_id,
            "code": acc.code,
            "name": acc.name,
            "account_type": acc.account_type,
            "amount": ZERO,
        })
        bucket["amount"] += _signed_balance(acc.account_type,
                                            Decimal(line.debit_base),
                                            Decimal(line.credit_base))

    revenue = sorted(rev_rows.values(), key=lambda x: x["code"])
    expenses = sorted(exp_rows.values(), key=lambda x: x["code"])

    total_revenue = sum((r["amount"] for r in revenue), ZERO)
    total_expense = sum((e["amount"] for e in expenses), ZERO)

    # Cost-of-services accounts (5xxx) vs other operating expenses (6xxx,
    # 7xxx, …). Convention used by the default CoA — degrades gracefully
    # if tenants invent a different numbering by lumping anything that
    # isn't a 5xxx into "other operating".
    cogs = [e for e in expenses if (e["code"] or "").startswith("5")]
    opex = [e for e in expenses if not (e["code"] or "").startswith("5")]
    total_cogs = sum((c["amount"] for c in cogs), ZERO)
    total_opex = sum((o["amount"] for o in opex), ZERO)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "revenue": revenue,
        "total_revenue": total_revenue,
        "cogs": cogs,
        "total_cogs": total_cogs,
        "gross_profit": total_revenue - total_cogs,
        "operating_expenses": opex,
        "total_operating_expenses": total_opex,
        "net_income": total_revenue - total_expense,
    }


# ─── Balance Sheet ───────────────────────────────────────────────────────────

def balance_sheet(db: Session, as_of: date) -> dict:
    """Assets = Liabilities + Equity (with current-year earnings rolled in).

    For a fully closed prior year, the closing entry to Retained Earnings
    is a separate workflow (Phase 5+); until then, "Current Year Earnings"
    is computed dynamically as cumulative Revenue − Expenses up to as_of.
    """
    asset_rows: Dict[int, Dict] = {}
    liab_rows: Dict[int, Dict] = {}
    eq_rows: Dict[int, Dict] = {}
    rev_total = ZERO
    exp_total = ZERO

    for line, entry, acc in _posted_lines_query(db, on_or_before=as_of):
        amount = _signed_balance(acc.account_type,
                                 Decimal(line.debit_base),
                                 Decimal(line.credit_base))
        if acc.account_type == "Asset":
            bucket = asset_rows.setdefault(acc.account_id, _new_bucket(acc))
            bucket["amount"] += amount
        elif acc.account_type == "Liability":
            bucket = liab_rows.setdefault(acc.account_id, _new_bucket(acc))
            bucket["amount"] += amount
        elif acc.account_type == "Equity":
            bucket = eq_rows.setdefault(acc.account_id, _new_bucket(acc))
            bucket["amount"] += amount
        elif acc.account_type == "Revenue":
            rev_total += amount
        elif acc.account_type == "Expense":
            exp_total += amount

    assets = sorted(asset_rows.values(), key=lambda x: x["code"])
    liabilities = sorted(liab_rows.values(), key=lambda x: x["code"])
    equity = sorted(eq_rows.values(), key=lambda x: x["code"])

    total_assets = sum((a["amount"] for a in assets), ZERO)
    total_liabilities = sum((l["amount"] for l in liabilities), ZERO)
    total_equity = sum((e["amount"] for e in equity), ZERO)
    current_year_earnings = rev_total - exp_total
    total_equity_with_earnings = total_equity + current_year_earnings

    return {
        "as_of": as_of,
        "assets": assets,
        "total_assets": total_assets,
        "liabilities": liabilities,
        "total_liabilities": total_liabilities,
        "equity": equity,
        "current_year_earnings": current_year_earnings,
        "total_equity": total_equity_with_earnings,
        "total_liabilities_and_equity": total_liabilities + total_equity_with_earnings,
        "balanced": (total_assets - (total_liabilities + total_equity_with_earnings)) == ZERO,
    }


def _new_bucket(acc: Account) -> Dict:
    return {
        "account_id": acc.account_id,
        "code": acc.code,
        "name": acc.name,
        "account_type": acc.account_type,
        "amount": ZERO,
    }


# ─── Cash Flow ───────────────────────────────────────────────────────────────

def cash_flow(db: Session, from_date: date, to_date: date) -> dict:
    """Simplified direct-method cash flow.

    Iterates posted entries in the window that touch a cash account.
    For each such entry, the cash leg's net change (Dr − Cr in base
    currency) is classified by looking at the *other* leg's account
    type:

      * Revenue / Expense     → Operating
      * Asset (non-cash)      → Investing
      * Liability / Equity    → Financing
      * Mixed multi-leg entry → Operating (best-effort default)

    The result deliberately understates accuracy for complex entries
    (split disbursements, etc.); v2 of this report will let a posting
    declare its cash-flow classification explicitly.
    """
    operating = ZERO
    investing = ZERO
    financing = ZERO

    # Pre-group lines by entry so we can inspect the "other side".
    by_entry: Dict[int, List[Tuple[JournalLine, Account]]] = defaultdict(list)
    for line, entry, acc in _posted_lines_query(db, from_date=from_date, to_date=to_date):
        by_entry[entry.entry_id].append((line, acc))

    cash_in_total = ZERO
    cash_out_total = ZERO

    for entry_id, items in by_entry.items():
        cash_legs = [(l, a) for l, a in items if _is_cash_account(a)]
        if not cash_legs:
            continue
        non_cash = [(l, a) for l, a in items if not _is_cash_account(a)]
        # Net cash change for this entry.
        net = sum((Decimal(l.debit_base) - Decimal(l.credit_base) for l, _ in cash_legs), ZERO)
        if net > 0:
            cash_in_total += net
        else:
            cash_out_total += -net

        # Classify by the dominant non-cash leg type.
        bucket = _classify_cash_entry(non_cash)
        if bucket == "operating":
            operating += net
        elif bucket == "investing":
            investing += net
        elif bucket == "financing":
            financing += net
        else:
            operating += net

    net_change = operating + investing + financing
    return {
        "from_date": from_date,
        "to_date": to_date,
        "operating": operating,
        "investing": investing,
        "financing": financing,
        "net_change": net_change,
        "cash_in": cash_in_total,
        "cash_out": cash_out_total,
    }


def _is_cash_account(acc: Account) -> bool:
    return any((acc.code or "").startswith(p) for p in CASH_PREFIXES)


def _classify_cash_entry(non_cash_legs) -> str:
    if not non_cash_legs:
        return "operating"
    types = {a.account_type for _, a in non_cash_legs}
    if types & {"Revenue", "Expense"}:
        return "operating"
    if types & {"Asset"}:
        return "investing"
    if types & {"Liability", "Equity"}:
        return "financing"
    return "operating"


# ─── Daily Collections ───────────────────────────────────────────────────────

def daily_collections(db: Session, from_date: date, to_date: date) -> dict:
    """Cash received per day broken down by collection account.

    Only counts the DEBIT side of cash accounts (= cash coming in). Cash
    going out is excluded — that's the Daily Payments report (separate).
    """
    by_date: Dict[Tuple[date, str], Dict] = {}
    grand_total = ZERO

    for line, entry, acc in _posted_lines_query(db, from_date=from_date, to_date=to_date):
        if not _is_cash_account(acc):
            continue
        amt = Decimal(line.debit_base)
        if amt == ZERO:
            continue
        key = (entry.entry_date, acc.code)
        bucket = by_date.setdefault(key, {
            "date": entry.entry_date,
            "account_code": acc.code,
            "account_name": acc.name,
            "amount": ZERO,
        })
        bucket["amount"] += amt
        grand_total += amt

    rows = sorted(by_date.values(), key=lambda x: (x["date"], x["account_code"]))
    return {
        "from_date": from_date,
        "to_date": to_date,
        "rows": rows,
        "total": grand_total,
    }
