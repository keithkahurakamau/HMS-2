"""Pydantic request/response models for the accounting module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


AccountType = Literal["Asset", "Liability", "Equity", "Revenue", "Expense"]
EntryStatus = Literal["draft", "posted", "reversed"]
PeriodStatus = Literal["open", "closed"]


# ─── Currencies ──────────────────────────────────────────────────────────────

class CurrencyCreate(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    name: str = Field(min_length=1, max_length=80)
    symbol: Optional[str] = Field(default=None, max_length=8)
    decimals: int = Field(default=2, ge=0, le=6)
    is_base: bool = False

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        return v.upper()


class CurrencyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    symbol: Optional[str] = Field(default=None, max_length=8)
    decimals: Optional[int] = Field(default=None, ge=0, le=6)
    is_active: Optional[bool] = None


class CurrencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency_id: int
    code: str
    name: str
    symbol: Optional[str]
    decimals: int
    is_base: bool
    is_active: bool


# ─── FX Rates ────────────────────────────────────────────────────────────────

class FxRateCreate(BaseModel):
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: Decimal = Field(gt=0)
    effective_date: date

    @field_validator("from_currency", "to_currency")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        return v.upper()


class FxRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fx_rate_id: int
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_date: date
    created_at: datetime


# ─── Accounts ────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=160)
    account_type: AccountType
    parent_id: Optional[int] = None
    currency_code: Optional[str] = Field(default=None, max_length=3)
    is_postable: bool = True
    description: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    parent_id: Optional[int] = None
    currency_code: Optional[str] = Field(default=None, max_length=3)
    is_postable: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    code: str
    name: str
    account_type: AccountType
    parent_id: Optional[int]
    currency_code: Optional[str]
    is_postable: bool
    is_active: bool
    description: Optional[str]


class AccountTreeNode(AccountResponse):
    """Used by the CoA tree endpoint — children populated server-side."""
    children: List["AccountTreeNode"] = Field(default_factory=list)


AccountTreeNode.model_rebuild()


# ─── Fiscal Periods ──────────────────────────────────────────────────────────

class FiscalPeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_id: int
    year: int
    month: int
    start_date: date
    end_date: date
    status: PeriodStatus


class FiscalPeriodSeedRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)


# ─── Journal Entries ─────────────────────────────────────────────────────────

class JournalLineInput(BaseModel):
    account_id: int
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    description: Optional[str] = None


class JournalLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_id: int
    line_number: int
    account_id: int
    debit: Decimal
    credit: Decimal
    debit_base: Decimal
    credit_base: Decimal
    description: Optional[str]


class JournalEntryCreate(BaseModel):
    entry_date: date
    currency_code: str = Field(min_length=3, max_length=3)
    fx_rate: Optional[Decimal] = Field(default=None, gt=0)  # auto-resolved if omitted
    memo: Optional[str] = None
    reference: Optional[str] = Field(default=None, max_length=120)
    lines: List[JournalLineInput] = Field(min_length=2)


class JournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: int
    entry_number: str
    entry_date: date
    fiscal_period_id: int
    currency_code: str
    fx_rate: Decimal
    status: EntryStatus
    memo: Optional[str]
    reference: Optional[str]
    source_type: Optional[str]
    source_id: Optional[int]
    created_by: int
    created_at: datetime
    posted_by: Optional[int]
    posted_at: Optional[datetime]
    reversed_by: Optional[int]
    reversed_at: Optional[datetime]
    reverses_entry_id: Optional[int]
    lines: List[JournalLineResponse]


# ─── Settings ────────────────────────────────────────────────────────────────

class AccountingSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    settings_id: int
    base_currency_code: str
    go_live_date: Optional[date]
    fiscal_year_start_month: int


class AccountingSettingsUpdate(BaseModel):
    base_currency_code: Optional[str] = Field(default=None, min_length=3, max_length=3)
    go_live_date: Optional[date] = None
    fiscal_year_start_month: Optional[int] = Field(default=None, ge=1, le=12)
