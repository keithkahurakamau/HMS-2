"""Pydantic request/response models for the operator receivables API.

Money crosses the wire as a decimal string, never a float: a stored float
is how rounding bugs enter a billing system. Requests accept a string or a
plain decimal literal (Pydantic coerces both into Decimal); responses are
built by the route handlers, which format every Decimal back to a string
before it leaves the process.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PaymentIn(BaseModel):
    amount_kes: Decimal = Field(gt=0)
    paid_on: date
    method: str = Field(default="mpesa", max_length=20)
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("method")
    @classmethod
    def _method_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("method must not be blank")
        return v


class VoidIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reason must not be blank")
        return v


class RemindersIn(BaseModel):
    paused: bool


class SubscriptionUpdateIn(BaseModel):
    plan: Optional[str] = Field(default=None, max_length=20)
    price_kes: Optional[Decimal] = Field(default=None, gt=0)
    status: Optional[str] = Field(default=None, max_length=20)


class AgeingRow(BaseModel):
    """One row per tenant. All money fields are decimal strings, e.g.
    "15000.00", per the frontend contract this shape was fixed against."""
    tenant_id: int
    tenant_name: str
    current: str
    b1_30: str
    b31_60: str
    b61_90: str
    b90_plus: str
    total: str
    reminders_paused: bool


class SummaryOut(BaseModel):
    billed: str
    received: str
    outstanding: str
    overdue: str


class RunResult(BaseModel):
    ok: bool
    skipped: bool
    invoices_created: int
    reminders_sent: int
    failures: list[str]
    message: str
