"""HTTP API for the Managerial Accounting module.

Routes are intentionally thin — they parse input, check the appropriate
permission, and hand off to `app.services.accounting`. All validation /
balance enforcement lives in the service layer.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.accounting import (
    Account,
    AccountingSettings,
    Currency,
    FiscalPeriod,
    FxRate,
    JournalEntry,
)
from app.schemas.accounting import (
    AccountCreate,
    AccountingSettingsResponse,
    AccountingSettingsUpdate,
    AccountResponse,
    AccountTreeNode,
    AccountUpdate,
    CurrencyCreate,
    CurrencyResponse,
    CurrencyUpdate,
    FiscalPeriodResponse,
    FiscalPeriodSeedRequest,
    FxRateCreate,
    FxRateResponse,
    JournalEntryCreate,
    JournalEntryResponse,
)
from app.services import accounting as svc

router = APIRouter(prefix="/api/accounting", tags=["Accounting"])


# ─── Settings ────────────────────────────────────────────────────────────────

@router.get(
    "/settings",
    response_model=AccountingSettingsResponse,
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def get_settings(db: Session = Depends(get_db)):
    return svc.get_or_create_settings(db)


@router.patch(
    "/settings",
    response_model=AccountingSettingsResponse,
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def update_settings(payload: AccountingSettingsUpdate, db: Session = Depends(get_db)):
    row = svc.get_or_create_settings(db)
    data = payload.model_dump(exclude_unset=True)

    if "base_currency_code" in data:
        # Switching base is a heavy change — block if posted entries exist.
        # Phase 1: refuse outright with a hint to use a migration script.
        posted = db.query(JournalEntry).filter(JournalEntry.status == "posted").count()
        if posted > 0:
            raise HTTPException(
                400,
                detail=(
                    "Base currency cannot be changed once posted entries exist. "
                    "Contact support for a controlled migration."
                ),
            )
        code = data["base_currency_code"].upper()
        cur = db.query(Currency).filter(Currency.code == code).first()
        if not cur or not cur.is_active:
            raise HTTPException(400, detail=f"Currency '{code}' must exist and be active.")
        # Flip is_base flags.
        for c in db.query(Currency).filter(Currency.is_base == True).all():  # noqa: E712
            c.is_base = False
        cur.is_base = True
        row.base_currency_code = code

    if "go_live_date" in data:
        row.go_live_date = data["go_live_date"]
    if "fiscal_year_start_month" in data:
        row.fiscal_year_start_month = data["fiscal_year_start_month"]

    db.commit()
    db.refresh(row)
    return row


# ─── Currencies ──────────────────────────────────────────────────────────────

@router.get(
    "/currencies",
    response_model=List[CurrencyResponse],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_currencies(db: Session = Depends(get_db)):
    return db.query(Currency).order_by(Currency.code).all()


@router.post(
    "/currencies",
    response_model=CurrencyResponse,
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def create_currency(payload: CurrencyCreate, db: Session = Depends(get_db)):
    if db.query(Currency).filter(Currency.code == payload.code).first():
        raise HTTPException(409, detail=f"Currency '{payload.code}' already exists.")
    cur = Currency(**payload.model_dump())
    if cur.is_base:
        # Demote any existing base — only one base at a time.
        for c in db.query(Currency).filter(Currency.is_base == True).all():  # noqa: E712
            c.is_base = False
    db.add(cur)
    db.commit()
    db.refresh(cur)
    if cur.is_base:
        # Mirror onto settings so reports/reads have a single source of truth.
        settings = svc.get_or_create_settings(db)
        settings.base_currency_code = cur.code
        db.commit()
    return cur


@router.patch(
    "/currencies/{currency_id}",
    response_model=CurrencyResponse,
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def update_currency(currency_id: int, payload: CurrencyUpdate, db: Session = Depends(get_db)):
    cur = db.query(Currency).filter(Currency.currency_id == currency_id).first()
    if not cur:
        raise HTTPException(404, detail="Currency not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cur, k, v)
    db.commit()
    db.refresh(cur)
    return cur


# ─── FX Rates ────────────────────────────────────────────────────────────────

@router.get(
    "/fx-rates",
    response_model=List[FxRateResponse],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_fx_rates(
    db: Session = Depends(get_db),
    from_currency: Optional[str] = Query(None, min_length=3, max_length=3),
    to_currency: Optional[str] = Query(None, min_length=3, max_length=3),
):
    q = db.query(FxRate)
    if from_currency:
        q = q.filter(FxRate.from_currency == from_currency.upper())
    if to_currency:
        q = q.filter(FxRate.to_currency == to_currency.upper())
    return q.order_by(FxRate.effective_date.desc()).limit(500).all()


@router.post(
    "/fx-rates",
    response_model=FxRateResponse,
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def create_fx_rate(payload: FxRateCreate, db: Session = Depends(get_db)):
    if payload.from_currency == payload.to_currency:
        raise HTTPException(400, detail="from_currency and to_currency must differ.")
    # Confirm both currencies exist.
    for code in (payload.from_currency, payload.to_currency):
        if not db.query(Currency).filter(Currency.code == code).first():
            raise HTTPException(404, detail=f"Currency '{code}' not configured.")
    existing = (
        db.query(FxRate)
        .filter(
            FxRate.from_currency == payload.from_currency,
            FxRate.to_currency == payload.to_currency,
            FxRate.effective_date == payload.effective_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(409, detail="A rate already exists for this date/pair.")
    row = FxRate(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Chart of Accounts ───────────────────────────────────────────────────────

@router.get(
    "/accounts",
    response_model=List[AccountResponse],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_accounts(
    db: Session = Depends(get_db),
    account_type: Optional[str] = Query(None),
    include_inactive: bool = False,
):
    q = db.query(Account)
    if account_type:
        q = q.filter(Account.account_type == account_type)
    if not include_inactive:
        q = q.filter(Account.is_active == True)  # noqa: E712
    return q.order_by(Account.code).all()


@router.get(
    "/accounts/tree",
    response_model=List[AccountTreeNode],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_accounts_tree(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(Account)
    if not include_inactive:
        q = q.filter(Account.is_active == True)  # noqa: E712
    return svc.build_account_tree(q.all())


@router.post(
    "/accounts",
    response_model=AccountResponse,
    dependencies=[Depends(RequirePermission("accounting:coa.manage"))],
)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    if db.query(Account).filter(Account.code == payload.code).first():
        raise HTTPException(409, detail=f"Account code '{payload.code}' already exists.")
    if payload.parent_id is not None:
        parent = db.query(Account).filter(Account.account_id == payload.parent_id).first()
        if not parent:
            raise HTTPException(404, detail="Parent account not found.")
        if parent.account_type != payload.account_type:
            raise HTTPException(
                400,
                detail=(
                    f"Account type must match parent ({parent.account_type})."
                ),
            )
    row = Account(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountResponse,
    dependencies=[Depends(RequirePermission("accounting:coa.manage"))],
)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)):
    row = db.query(Account).filter(Account.account_id == account_id).first()
    if not row:
        raise HTTPException(404, detail="Account not found.")
    data = payload.model_dump(exclude_unset=True)
    # Block toggling is_postable=False once lines exist against it.
    if data.get("is_postable") is False:
        from app.models.accounting import JournalLine
        used = db.query(JournalLine).filter(JournalLine.account_id == account_id).count()
        if used:
            raise HTTPException(
                400,
                detail=f"Cannot mark account non-postable — it has {used} journal line(s).",
            )
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Fiscal Periods ──────────────────────────────────────────────────────────

@router.get(
    "/fiscal-periods",
    response_model=List[FiscalPeriodResponse],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_periods(db: Session = Depends(get_db), year: Optional[int] = None):
    q = db.query(FiscalPeriod)
    if year is not None:
        q = q.filter(FiscalPeriod.year == year)
    return q.order_by(FiscalPeriod.year, FiscalPeriod.month).all()


@router.post(
    "/fiscal-periods/seed-year",
    response_model=List[FiscalPeriodResponse],
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def seed_year(payload: FiscalPeriodSeedRequest, db: Session = Depends(get_db)):
    rows = svc.seed_fiscal_year(db, payload.year)
    db.commit()
    return rows


@router.post(
    "/fiscal-periods/{period_id}/close",
    response_model=FiscalPeriodResponse,
    dependencies=[Depends(RequirePermission("accounting:settings.manage"))],
)
def close_period(period_id: int, db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    row = svc.close_fiscal_period(db, period_id, user_id)
    db.commit()
    return row


# ─── Journal Entries ─────────────────────────────────────────────────────────

@router.get(
    "/journal-entries",
    response_model=List[JournalEntryResponse],
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def list_entries(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    reference: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    q = db.query(JournalEntry)
    if status:
        q = q.filter(JournalEntry.status == status)
    if from_date:
        q = q.filter(JournalEntry.entry_date >= from_date)
    if to_date:
        q = q.filter(JournalEntry.entry_date <= to_date)
    if reference:
        q = q.filter(JournalEntry.reference == reference)
    return q.order_by(JournalEntry.entry_date.desc(), JournalEntry.entry_id.desc()).limit(limit).all()


@router.get(
    "/journal-entries/{entry_id}",
    response_model=JournalEntryResponse,
    dependencies=[Depends(RequirePermission("accounting:view"))],
)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(JournalEntry).filter(JournalEntry.entry_id == entry_id).first()
    if not row:
        raise HTTPException(404, detail="Journal entry not found.")
    return row


@router.post(
    "/journal-entries",
    response_model=JournalEntryResponse,
    dependencies=[Depends(RequirePermission("accounting:journal.create"))],
)
def create_entry(payload: JournalEntryCreate, db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    entry = svc.create_draft_entry(
        db,
        entry_date=payload.entry_date,
        currency_code=payload.currency_code.upper(),
        fx_rate=payload.fx_rate,
        lines_in=payload.lines,
        user_id=user_id,
        memo=payload.memo,
        reference=payload.reference,
    )
    db.commit()
    db.refresh(entry)
    return entry


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryResponse,
    dependencies=[Depends(RequirePermission("accounting:journal.post"))],
)
def post_entry(entry_id: int, db: Session = Depends(get_db),
               current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    row = svc.post_entry(db, entry_id, user_id)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryResponse,
    dependencies=[Depends(RequirePermission("accounting:journal.post"))],
)
def reverse_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    reason: Optional[str] = Query(None, max_length=200),
):
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    mirror = svc.reverse_entry(db, entry_id, user_id, reason)
    db.commit()
    db.refresh(mirror)
    return mirror
