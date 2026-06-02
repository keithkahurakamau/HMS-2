"""Budgeting — budget headers, per-account/period lines, budget-vs-actual.

Reads require ``accounting:view``; all mutations require the dedicated
``accounting:budget.manage`` permission (granted to Accountant + Admin).
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.accounting import Budget
from app.services import accounting_budget as svc

router = APIRouter(prefix="/api/accounting/budgets", tags=["Accounting · Budgets"])

VIEW = Depends(RequirePermission("accounting:view"))
MANAGE = Depends(RequirePermission("accounting:budget.manage"))


def _user_id(current_user) -> int:
    return current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", 0)


# ─── Schemas ────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    fiscal_year: int = Field(ge=1900, le=9999)
    notes: Optional[str] = None


class BudgetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    status: Optional[str] = None
    notes: Optional[str] = None


class BudgetLineInput(BaseModel):
    account_id: int
    period_id: int
    amount: Decimal = Field(ge=0)


class BudgetLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_id: int
    budget_id: int
    account_id: int
    period_id: int
    amount: Decimal


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    budget_id: int
    name: str
    fiscal_year: int
    status: str
    notes: Optional[str]
    created_by: int
    lines: List[BudgetLineResponse] = Field(default_factory=list)


class BudgetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    budget_id: int
    name: str
    fiscal_year: int
    status: str
    notes: Optional[str]


class BulkLinesRequest(BaseModel):
    lines: List[BudgetLineInput] = Field(min_length=1)


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[BudgetSummary], dependencies=[VIEW])
def list_budgets(db: Session = Depends(get_db),
                 fiscal_year: Optional[int] = None,
                 status: Optional[str] = None):
    q = db.query(Budget)
    if fiscal_year is not None:
        q = q.filter(Budget.fiscal_year == fiscal_year)
    if status:
        q = q.filter(Budget.status == status)
    return q.order_by(Budget.fiscal_year.desc(), Budget.name).all()


@router.post("", response_model=BudgetResponse, dependencies=[MANAGE])
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    budget = svc.create_budget(db, name=payload.name, fiscal_year=payload.fiscal_year,
                               user_id=_user_id(current_user), notes=payload.notes)
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/{budget_id}", response_model=BudgetResponse, dependencies=[VIEW])
def get_budget(budget_id: int, db: Session = Depends(get_db)):
    budget = db.query(Budget).filter(Budget.budget_id == budget_id).first()
    if not budget:
        raise HTTPException(404, detail="Budget not found.")
    return budget


@router.patch("/{budget_id}", response_model=BudgetResponse, dependencies=[MANAGE])
def update_budget(budget_id: int, payload: BudgetUpdate, db: Session = Depends(get_db)):
    budget = svc.update_budget(db, budget_id=budget_id, name=payload.name,
                               status=payload.status, notes=payload.notes)
    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}", status_code=204, dependencies=[MANAGE])
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    svc.delete_budget(db, budget_id=budget_id)
    db.commit()


@router.put("/{budget_id}/lines", response_model=List[BudgetLineResponse], dependencies=[MANAGE])
def set_budget_lines(budget_id: int, payload: BulkLinesRequest, db: Session = Depends(get_db)):
    lines = svc.bulk_set_lines(db, budget_id=budget_id, lines_in=payload.lines)
    db.commit()
    return lines


@router.delete("/{budget_id}/lines/{line_id}", status_code=204, dependencies=[MANAGE])
def delete_budget_line(budget_id: int, line_id: int, db: Session = Depends(get_db)):
    svc.delete_line(db, budget_id=budget_id, line_id=line_id)
    db.commit()


@router.get("/{budget_id}/vs-actual", dependencies=[VIEW])
def budget_vs_actual(budget_id: int, db: Session = Depends(get_db),
                     period_id: Optional[int] = Query(default=None)):
    return svc.budget_vs_actual(db, budget_id=budget_id, period_id=period_id)
