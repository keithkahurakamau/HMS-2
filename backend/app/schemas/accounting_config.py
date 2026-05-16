"""Pydantic schemas for the accounting config layer (Phase 3)."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Suppliers ───────────────────────────────────────────────────────────────

class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_person: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = None
    tax_pin: Optional[str] = Field(default=None, max_length=40)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    default_payable_account_id: Optional[int] = None
    notes: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    contact_person: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = None
    tax_pin: Optional[str] = Field(default=None, max_length=40)
    payment_terms_days: Optional[int] = Field(default=None, ge=0, le=365)
    default_payable_account_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierResponse(SupplierBase):
    model_config = ConfigDict(from_attributes=True)
    supplier_id: int
    is_active: bool


# ─── Insurance providers ─────────────────────────────────────────────────────

class InsuranceProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_person: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = None
    default_receivable_account_id: Optional[int] = None
    notes: Optional[str] = None


class InsuranceProviderCreate(InsuranceProviderBase):
    pass


class InsuranceProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    contact_person: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=160)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = None
    default_receivable_account_id: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class InsuranceProviderResponse(InsuranceProviderBase):
    model_config = ConfigDict(from_attributes=True)
    provider_id: int
    is_active: bool


# ─── Medical schemes ─────────────────────────────────────────────────────────

class MedicalSchemeBase(BaseModel):
    provider_id: int
    name: str = Field(min_length=1, max_length=160)
    scheme_code: Optional[str] = Field(default=None, max_length=60)
    coverage_limit: Optional[Decimal] = None
    notes: Optional[str] = None


class MedicalSchemeCreate(MedicalSchemeBase):
    pass


class MedicalSchemeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    scheme_code: Optional[str] = Field(default=None, max_length=60)
    coverage_limit: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class MedicalSchemeResponse(MedicalSchemeBase):
    model_config = ConfigDict(from_attributes=True)
    scheme_id: int
    is_active: bool


# ─── Price list ──────────────────────────────────────────────────────────────

PRICE_CATEGORIES = ("Consultation", "Lab", "Radiology", "Pharmacy", "Ward", "Procedure", "Other")


class PriceListItemBase(BaseModel):
    service_code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(max_length=60)
    unit_price: Decimal = Field(ge=0)
    revenue_account_id: Optional[int] = None
    tax_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    description: Optional[str] = None


class PriceListItemCreate(PriceListItemBase):
    pass


class PriceListItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=60)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    revenue_account_id: Optional[int] = None
    tax_rate_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PriceListItemResponse(PriceListItemBase):
    model_config = ConfigDict(from_attributes=True)
    price_id: int
    is_active: bool


# ─── Ledger mappings ─────────────────────────────────────────────────────────

# The catalogue of all source keys the Phase 4 auto-posting service knows
# about. Surface this to the UI so admins can see what's wired even if a
# mapping row hasn't been created yet.
SOURCE_KEY_CATALOGUE = [
    ("billing.invoice.created",      "Invoice raised against a patient"),
    ("billing.payment.cash",         "Patient pays an invoice with cash"),
    ("billing.payment.bank",         "Patient pays via bank transfer/card"),
    ("billing.payment.mpesa",        "Patient pays via M-Pesa"),
    ("billing.deposit.received",     "Patient pre-payment / deposit received"),
    ("pharmacy.dispense.revenue",    "Pharmacy dispensation revenue side"),
    ("pharmacy.dispense.cogs",       "Pharmacy dispensation cost of goods sold"),
    ("cheques.deposit.cleared",      "Cheque has cleared into the bank"),
    ("mpesa.receipt.direct",         "Direct M-Pesa receipt with no prior invoice"),
    ("insurance.claim.submitted",    "Claim moved from patient to insurance receivable"),
    ("insurance.claim.settled",      "Insurer paid; clear insurance receivable"),
]


class LedgerMappingUpdate(BaseModel):
    debit_account_id: Optional[int] = None
    credit_account_id: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class LedgerMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    mapping_id: int
    source_key: str
    debit_account_id: Optional[int]
    credit_account_id: Optional[int]
    description: Optional[str]
    is_active: bool


class SourceKeyCatalogueEntry(BaseModel):
    source_key: str
    description: str
    mapping: Optional[LedgerMappingResponse]
