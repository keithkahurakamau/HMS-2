"""
Service layer for the accounting module.

This is where the invariants live (the models only know about the
shape of the data, not the rules). Callers should always go through
these helpers — never set `status = 'posted'` directly on a model.

Invariants enforced here:
  * Posted entries are immutable (edits require a reversal + repost).
  * Sum(debits in base currency) == Sum(credits in base currency).
  * No posting to a closed fiscal period.
  * Postings only allowed against `is_postable=True` accounts.
  * Fiscal period for an entry's date is resolved (and created on
    demand within the requested fiscal year).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.accounting import (
    Account,
    AccountingSettings,
    Currency,
    FiscalPeriod,
    FxRate,
    JournalEntry,
    JournalLine,
)


ZERO = Decimal("0")
ROUND_QUANT = Decimal("0.0001")


# ─── Settings ────────────────────────────────────────────────────────────────

def get_or_create_settings(db: Session) -> AccountingSettings:
    """Return the singleton settings row, creating a default if absent.

    The migration seeds a row on every fresh tenant DB, but defensively
    create one here so test factories and ad-hoc tenants don't blow up.
    """
    row = db.query(AccountingSettings).first()
    if row is not None:
        return row
    row = AccountingSettings(base_currency_code="KES", fiscal_year_start_month=1)
    db.add(row)
    db.flush()
    return row


def get_base_currency_code(db: Session) -> str:
    settings = get_or_create_settings(db)
    return settings.base_currency_code


# ─── Currencies & FX ─────────────────────────────────────────────────────────

def ensure_currency_active(db: Session, code: str) -> Currency:
    cur = db.query(Currency).filter(Currency.code == code).first()
    if not cur:
        raise HTTPException(404, detail=f"Currency '{code}' is not configured.")
    if not cur.is_active:
        raise HTTPException(400, detail=f"Currency '{code}' is inactive.")
    return cur


def resolve_fx_rate(db: Session, from_code: str, to_code: str, as_of: date) -> Decimal:
    """Find the most recent fx rate on or before *as_of*.

    Same-currency conversions short-circuit to 1. Missing rates raise
    a 400 — the caller has to record one before posting.
    """
    if from_code == to_code:
        return Decimal("1")
    rate = (
        db.query(FxRate)
        .filter(
            FxRate.from_currency == from_code,
            FxRate.to_currency == to_code,
            FxRate.effective_date <= as_of,
        )
        .order_by(desc(FxRate.effective_date))
        .first()
    )
    if not rate:
        raise HTTPException(
            400,
            detail=f"No FX rate configured for {from_code}->{to_code} on or before {as_of.isoformat()}.",
        )
    return Decimal(rate.rate)


# ─── Fiscal Periods ──────────────────────────────────────────────────────────

def ensure_fiscal_period(db: Session, on: date) -> FiscalPeriod:
    """Return the FiscalPeriod that covers *on*, creating it on demand.

    Lazy creation lets clients post into a date without first running
    a "seed year" admin action. Closed periods raise.
    """
    period = (
        db.query(FiscalPeriod)
        .filter(FiscalPeriod.year == on.year, FiscalPeriod.month == on.month)
        .first()
    )
    if period is None:
        first = date(on.year, on.month, 1)
        # End-of-month: jump to next month then back one day
        next_month = date(on.year + (1 if on.month == 12 else 0),
                          1 if on.month == 12 else on.month + 1, 1)
        last = next_month - timedelta(days=1)
        period = FiscalPeriod(
            year=on.year, month=on.month, start_date=first, end_date=last, status="open"
        )
        db.add(period)
        db.flush()
    if period.status == "closed":
        raise HTTPException(
            400,
            detail=f"Fiscal period {period.year}-{period.month:02d} is closed.",
        )
    return period


def seed_fiscal_year(db: Session, year: int) -> List[FiscalPeriod]:
    """Pre-create all 12 monthly periods for *year*. Idempotent."""
    created: List[FiscalPeriod] = []
    for month in range(1, 13):
        existing = (
            db.query(FiscalPeriod)
            .filter(FiscalPeriod.year == year, FiscalPeriod.month == month)
            .first()
        )
        if existing:
            created.append(existing)
            continue
        first = date(year, month, 1)
        next_month = date(year + (1 if month == 12 else 0),
                          1 if month == 12 else month + 1, 1)
        last = next_month - timedelta(days=1)
        period = FiscalPeriod(year=year, month=month, start_date=first,
                              end_date=last, status="open")
        db.add(period)
        db.flush()
        created.append(period)
    return created


def close_fiscal_period(db: Session, period_id: int, user_id: int) -> FiscalPeriod:
    period = db.query(FiscalPeriod).filter(FiscalPeriod.period_id == period_id).first()
    if not period:
        raise HTTPException(404, detail="Fiscal period not found.")
    if period.status == "closed":
        return period
    period.status = "closed"
    period.closed_at = datetime.utcnow()
    period.closed_by = user_id
    db.flush()
    return period


# ─── Accounts (CoA) ──────────────────────────────────────────────────────────

def build_account_tree(accounts: Iterable[Account]) -> list:
    """Materialize a tree from a flat list of accounts.

    Returns roots; each node has a `_children` list attached. The route
    layer converts these to Pydantic AccountTreeNode.
    """
    by_id = {a.account_id: a for a in accounts}
    children_map: dict = {a.account_id: [] for a in accounts}
    roots = []
    for a in accounts:
        if a.parent_id and a.parent_id in by_id:
            children_map[a.parent_id].append(a)
        else:
            roots.append(a)
    # Stable ordering by code
    def sort_key(x: Account):
        return x.code or ""
    for k in children_map:
        children_map[k].sort(key=sort_key)
    roots.sort(key=sort_key)
    return [_node_to_dict(r, children_map) for r in roots]


def _node_to_dict(account: Account, children_map: dict) -> dict:
    return {
        "account_id": account.account_id,
        "code": account.code,
        "name": account.name,
        "account_type": account.account_type,
        "parent_id": account.parent_id,
        "currency_code": account.currency_code,
        "is_postable": account.is_postable,
        "is_active": account.is_active,
        "description": account.description,
        "children": [
            _node_to_dict(c, children_map) for c in children_map.get(account.account_id, [])
        ],
    }


# ─── Journal Entries: create, post, reverse ──────────────────────────────────

def _next_entry_number(db: Session, on: date) -> str:
    """Format: JE-YYYYMM-NNNN. Per-month sequence, derived from existing
    count + 1 inside a session — fine for the modest volumes Phase 1 sees.
    For very high volume, swap to a Postgres sequence later.
    """
    prefix = f"JE-{on.year:04d}{on.month:02d}-"
    count = (
        db.query(JournalEntry)
        .filter(JournalEntry.entry_number.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{count + 1:04d}"


def create_draft_entry(
    db: Session,
    *,
    entry_date: date,
    currency_code: str,
    fx_rate: Optional[Decimal],
    lines_in: list,
    user_id: int,
    memo: Optional[str] = None,
    reference: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
) -> JournalEntry:
    """Create a draft entry. Validates lines but does NOT enforce balance —
    balance is checked at post time so users can save partial work."""
    if len(lines_in) < 2:
        raise HTTPException(400, detail="A journal entry needs at least two lines.")

    base_code = get_base_currency_code(db)
    ensure_currency_active(db, currency_code)
    period = ensure_fiscal_period(db, entry_date)

    rate = fx_rate if fx_rate is not None else resolve_fx_rate(db, currency_code, base_code, entry_date)

    # Validate accounts exist and are postable + active.
    account_ids = {l.account_id for l in lines_in}
    accounts = {
        a.account_id: a
        for a in db.query(Account).filter(Account.account_id.in_(account_ids)).all()
    }
    for line in lines_in:
        acc = accounts.get(line.account_id)
        if not acc:
            raise HTTPException(400, detail=f"Account {line.account_id} not found.")
        if not acc.is_active:
            raise HTTPException(400, detail=f"Account {acc.code} is inactive.")
        if not acc.is_postable:
            raise HTTPException(400, detail=f"Account {acc.code} is a roll-up; cannot post directly.")
        if (Decimal(line.debit or 0) > 0) == (Decimal(line.credit or 0) > 0):
            raise HTTPException(
                400, detail="Each line must have exactly one of debit/credit > 0.",
            )

    entry = JournalEntry(
        entry_number=_next_entry_number(db, entry_date),
        entry_date=entry_date,
        fiscal_period_id=period.period_id,
        currency_code=currency_code,
        fx_rate=rate,
        status="draft",
        memo=memo,
        reference=reference,
        source_type=source_type,
        source_id=source_id,
        created_by=user_id,
    )
    db.add(entry)
    db.flush()

    for idx, line in enumerate(lines_in, start=1):
        d = Decimal(line.debit or 0)
        c = Decimal(line.credit or 0)
        db.add(JournalLine(
            entry_id=entry.entry_id,
            line_number=idx,
            account_id=line.account_id,
            debit=d,
            credit=c,
            debit_base=(d * rate).quantize(ROUND_QUANT),
            credit_base=(c * rate).quantize(ROUND_QUANT),
            description=line.description,
        ))
    db.flush()
    db.refresh(entry)
    return entry


def post_entry(db: Session, entry_id: int, user_id: int) -> JournalEntry:
    entry = db.query(JournalEntry).filter(JournalEntry.entry_id == entry_id).first()
    if not entry:
        raise HTTPException(404, detail="Journal entry not found.")
    if entry.status != "draft":
        raise HTTPException(400, detail=f"Cannot post entry in status '{entry.status}'.")

    # Re-check period status; admin may have closed it after draft create.
    period = db.query(FiscalPeriod).filter(FiscalPeriod.period_id == entry.fiscal_period_id).first()
    if not period or period.status == "closed":
        raise HTTPException(400, detail="Fiscal period is closed; cannot post.")

    total_dr = sum((Decimal(l.debit_base) for l in entry.lines), ZERO)
    total_cr = sum((Decimal(l.credit_base) for l in entry.lines), ZERO)
    if total_dr != total_cr:
        raise HTTPException(
            400,
            detail=(
                f"Entry is unbalanced (Dr {total_dr} vs Cr {total_cr} in base currency). "
                f"Fix lines and try again."
            ),
        )
    if total_dr == ZERO:
        raise HTTPException(400, detail="Cannot post a zero-amount entry.")

    entry.status = "posted"
    entry.posted_by = user_id
    entry.posted_at = datetime.utcnow()
    db.flush()
    return entry


def reverse_entry(db: Session, entry_id: int, user_id: int, reason: Optional[str] = None) -> JournalEntry:
    """Create + post a mirror entry; mark the original as reversed."""
    original = db.query(JournalEntry).filter(JournalEntry.entry_id == entry_id).first()
    if not original:
        raise HTTPException(404, detail="Journal entry not found.")
    if original.status != "posted":
        raise HTTPException(400, detail=f"Only posted entries can be reversed (status='{original.status}').")

    period = ensure_fiscal_period(db, date.today())

    mirror = JournalEntry(
        entry_number=_next_entry_number(db, date.today()),
        entry_date=date.today(),
        fiscal_period_id=period.period_id,
        currency_code=original.currency_code,
        fx_rate=original.fx_rate,
        status="posted",
        memo=f"Reversal of {original.entry_number}" + (f" — {reason}" if reason else ""),
        reference=original.reference,
        source_type=original.source_type,
        source_id=original.source_id,
        created_by=user_id,
        posted_by=user_id,
        posted_at=datetime.utcnow(),
        reverses_entry_id=original.entry_id,
    )
    db.add(mirror)
    db.flush()

    for idx, line in enumerate(original.lines, start=1):
        db.add(JournalLine(
            entry_id=mirror.entry_id,
            line_number=idx,
            account_id=line.account_id,
            # Swap debit/credit
            debit=line.credit,
            credit=line.debit,
            debit_base=line.credit_base,
            credit_base=line.debit_base,
            description=f"Reversal of line {line.line_number}",
        ))

    original.status = "reversed"
    original.reversed_by = user_id
    original.reversed_at = datetime.utcnow()
    db.flush()
    db.refresh(mirror)
    return mirror
