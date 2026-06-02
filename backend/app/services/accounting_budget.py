"""
Budgeting service — budget headers, per-account/period lines, and the
budget-vs-actual comparison.

A budget is a set of expected amounts, one per (account, fiscal period).
"Actual" comes from the posted ledger: we reuse the same posted-line query
and natural-side sign rules the financial reports use, so a budget line and
its actual are always measured the same way.

Invariants enforced here (the model only knows the shape):
  * Lines may only target postable, active accounts.
  * A line's period must fall inside the budget's fiscal year.
  * Amounts are quantised to the ledger's rounding unit and never negative.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.accounting import (
    Account,
    Budget,
    BudgetLine,
    FiscalPeriod,
    JournalEntry,
)
from app.services.accounting import ROUND_QUANT
from app.services.accounting_reports import _posted_lines_query, _signed_balance

ZERO = Decimal("0")


# ─── Budgets ──────────────────────────────────────────────────────────────────

def create_budget(db: Session, *, name: str, fiscal_year: int, user_id: int,
                  notes: Optional[str] = None) -> Budget:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, detail="Budget name is required.")
    dup = (
        db.query(Budget)
        .filter(Budget.name == name, Budget.fiscal_year == fiscal_year)
        .first()
    )
    if dup:
        raise HTTPException(409, detail=f"A budget named '{name}' already exists for {fiscal_year}.")
    budget = Budget(name=name, fiscal_year=fiscal_year, status="draft",
                    notes=notes, created_by=user_id)
    db.add(budget)
    db.flush()
    db.refresh(budget)
    return budget


def update_budget(db: Session, *, budget_id: int,
                  name: Optional[str] = None,
                  status: Optional[str] = None,
                  notes: Optional[str] = None) -> Budget:
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(400, detail="Budget name cannot be blank.")
        clash = (
            db.query(Budget)
            .filter(Budget.name == name, Budget.fiscal_year == budget.fiscal_year,
                    Budget.budget_id != budget_id)
            .first()
        )
        if clash:
            raise HTTPException(409, detail=f"A budget named '{name}' already exists for {budget.fiscal_year}.")
        budget.name = name
    if status is not None:
        if status not in ("draft", "active", "archived"):
            raise HTTPException(400, detail="Invalid budget status.")
        budget.status = status
    if notes is not None:
        budget.notes = notes
    db.flush()
    db.refresh(budget)
    return budget


def delete_budget(db: Session, *, budget_id: int) -> None:
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")
    if budget.status != "draft":
        raise HTTPException(400, detail="Only draft budgets can be deleted.")
    db.delete(budget)
    db.flush()


# ─── Lines ────────────────────────────────────────────────────────────────────

def _validate_line_target(db: Session, budget: Budget, account_id: int, period_id: int) -> None:
    account = db.query(Account).filter(Account.account_id == account_id).first()
    if not account:
        raise HTTPException(400, detail=f"Account {account_id} not found.")
    if not account.is_active:
        raise HTTPException(400, detail=f"Account {account.code} is inactive.")
    if not account.is_postable:
        raise HTTPException(400, detail=f"Account {account.code} is a roll-up; cannot budget against it.")
    period = db.query(FiscalPeriod).filter(FiscalPeriod.period_id == period_id).first()
    if not period:
        raise HTTPException(400, detail=f"Fiscal period {period_id} not found.")
    if period.year != budget.fiscal_year:
        raise HTTPException(
            400,
            detail=f"Period {period.year}-{period.month:02d} is outside the budget's fiscal year ({budget.fiscal_year}).",
        )


def add_or_update_line(db: Session, *, budget_id: int, account_id: int,
                       period_id: int, amount) -> BudgetLine:
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")
    amt = Decimal(str(amount)).quantize(ROUND_QUANT)
    if amt < ZERO:
        raise HTTPException(400, detail="Budget amount cannot be negative.")
    _validate_line_target(db, budget, account_id, period_id)

    line = (
        db.query(BudgetLine)
        .filter(BudgetLine.budget_id == budget_id,
                BudgetLine.account_id == account_id,
                BudgetLine.period_id == period_id)
        .first()
    )
    if line:
        line.amount = amt
    else:
        line = BudgetLine(budget_id=budget_id, account_id=account_id,
                          period_id=period_id, amount=amt)
        db.add(line)
    db.flush()
    db.refresh(line)
    return line


def bulk_set_lines(db: Session, *, budget_id: int, lines_in: list) -> List[BudgetLine]:
    """Upsert a batch of lines in one shot. Each item carries account_id,
    period_id, amount. Returns the full set of lines after the operation."""
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")
    for item in lines_in:
        amt = Decimal(str(item.amount)).quantize(ROUND_QUANT)
        if amt < ZERO:
            raise HTTPException(400, detail="Budget amount cannot be negative.")
        _validate_line_target(db, budget, item.account_id, item.period_id)
        line = (
            db.query(BudgetLine)
            .filter(BudgetLine.budget_id == budget_id,
                    BudgetLine.account_id == item.account_id,
                    BudgetLine.period_id == item.period_id)
            .first()
        )
        if line:
            line.amount = amt
        else:
            db.add(BudgetLine(budget_id=budget_id, account_id=item.account_id,
                              period_id=item.period_id, amount=amt))
    db.flush()
    return (
        db.query(BudgetLine)
        .filter(BudgetLine.budget_id == budget_id)
        .order_by(BudgetLine.line_id)
        .all()
    )


def delete_line(db: Session, *, budget_id: int, line_id: int) -> None:
    line = (
        db.query(BudgetLine)
        .filter(BudgetLine.line_id == line_id, BudgetLine.budget_id == budget_id)
        .first()
    )
    if not line:
        raise HTTPException(404, detail="Budget line not found.")
    db.delete(line)
    db.flush()


# ─── Budget vs Actual ─────────────────────────────────────────────────────────

def budget_vs_actual(db: Session, *, budget_id: int, period_id: Optional[int] = None) -> dict:
    """Compare budgeted amounts against posted actuals, per account.

    Actuals use the same posted-line query + natural-side sign rules as the
    financial reports, restricted to the same fiscal periods the budget
    lines target. When *period_id* is given, only that period is compared.
    Variance = budget - actual. variance_pct is None when budget is zero.
    """
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")

    lines = db.query(BudgetLine).filter(BudgetLine.budget_id == budget_id)
    if period_id is not None:
        lines = lines.filter(BudgetLine.period_id == period_id)
    lines = lines.all()

    period_ids = sorted({l.period_id for l in lines})

    # Budgeted total per account across the in-scope periods.
    budget_by_account: dict[int, Decimal] = {}
    for l in lines:
        budget_by_account[l.account_id] = budget_by_account.get(l.account_id, ZERO) + Decimal(l.amount)
    budget_account_ids = set(budget_by_account)

    # Actual per account from posted lines within the same periods. Only the
    # budgeted accounts are compared — pulling in every account that happened
    # to post in the period (e.g. the cash/AR contra side) would net the
    # totals to nonsense.
    actual_by_account: dict[int, Decimal] = {}
    account_meta: dict[int, dict] = {}
    if period_ids and budget_account_ids:
        q = _posted_lines_query(db).filter(
            JournalEntry.fiscal_period_id.in_(period_ids),
            Account.account_id.in_(budget_account_ids),
        )
        agg: dict[int, list] = {}
        for line, _entry, acc in q:
            account_meta.setdefault(acc.account_id, {
                "account_id": acc.account_id, "code": acc.code,
                "name": acc.name, "account_type": acc.account_type,
            })
            d, c = agg.setdefault(acc.account_id, [ZERO, ZERO])
            agg[acc.account_id] = [d + Decimal(line.debit_base), c + Decimal(line.credit_base)]
        for aid, (dr, cr) in agg.items():
            actual_by_account[aid] = _signed_balance(account_meta[aid]["account_type"], dr, cr)

    # Make sure every budgeted account has metadata even with zero actuals.
    missing = [aid for aid in budget_account_ids if aid not in account_meta]
    if missing:
        for acc in db.query(Account).filter(Account.account_id.in_(missing)).all():
            account_meta[acc.account_id] = {
                "account_id": acc.account_id, "code": acc.code,
                "name": acc.name, "account_type": acc.account_type,
            }

    rows = []
    total_budget = ZERO
    total_actual = ZERO
    for aid in budget_account_ids:
        meta = account_meta.get(aid, {"account_id": aid, "code": "", "name": "", "account_type": ""})
        b = budget_by_account.get(aid, ZERO)
        a = actual_by_account.get(aid, ZERO)
        variance = b - a
        variance_pct = (variance / b * 100) if b != ZERO else None
        rows.append({
            **meta,
            "budget": b,
            "actual": a,
            "variance": variance,
            "variance_pct": variance_pct,
        })
        total_budget += b
        total_actual += a

    rows.sort(key=lambda r: r["code"] or "")
    return {
        "budget_id": budget.budget_id,
        "name": budget.name,
        "fiscal_year": budget.fiscal_year,
        "status": budget.status,
        "period_id": period_id,
        "rows": rows,
        "totals": {
            "budget": total_budget,
            "actual": total_actual,
            "variance": total_budget - total_actual,
        },
    }
