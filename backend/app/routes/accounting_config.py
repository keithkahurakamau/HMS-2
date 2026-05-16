"""Accounting configuration routes (Phase 3).

Suppliers, insurance providers, medical schemes, master price list, and
the ledger-mapping table that Phase 4 auto-posting reads.

All endpoints require `accounting:settings.manage` for writes and
`accounting:view` for reads.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission
from app.models.accounting import (
    Account,
    InsuranceProvider,
    LedgerMapping,
    MedicalScheme,
    PriceListItem,
    Supplier,
)
from app.schemas.accounting_config import (
    InsuranceProviderCreate,
    InsuranceProviderResponse,
    InsuranceProviderUpdate,
    LedgerMappingResponse,
    LedgerMappingUpdate,
    MedicalSchemeCreate,
    MedicalSchemeResponse,
    MedicalSchemeUpdate,
    PRICE_CATEGORIES,
    PriceListItemCreate,
    PriceListItemResponse,
    PriceListItemUpdate,
    SOURCE_KEY_CATALOGUE,
    SourceKeyCatalogueEntry,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)

router = APIRouter(prefix="/api/accounting/config", tags=["Accounting · Config"])


VIEW = Depends(RequirePermission("accounting:view"))
WRITE = Depends(RequirePermission("accounting:settings.manage"))


def _ensure_account(db: Session, account_id: Optional[int], label: str) -> None:
    if account_id is None:
        return
    if not db.query(Account).filter(Account.account_id == account_id).first():
        raise HTTPException(404, detail=f"{label} account {account_id} not found.")


# ─── Suppliers ───────────────────────────────────────────────────────────────

@router.get("/suppliers", response_model=List[SupplierResponse], dependencies=[VIEW])
def list_suppliers(db: Session = Depends(get_db), include_inactive: bool = False,
                   q: Optional[str] = None):
    query = db.query(Supplier)
    if not include_inactive:
        query = query.filter(Supplier.is_active == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Supplier.name.ilike(like)) | (Supplier.tax_pin.ilike(like))
        )
    return query.order_by(Supplier.name).all()


@router.post("/suppliers", response_model=SupplierResponse, dependencies=[WRITE])
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)):
    _ensure_account(db, payload.default_payable_account_id, "Payable")
    row = Supplier(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse, dependencies=[WRITE])
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db)):
    row = db.query(Supplier).filter(Supplier.supplier_id == supplier_id).first()
    if not row:
        raise HTTPException(404, detail="Supplier not found.")
    data = payload.model_dump(exclude_unset=True)
    if "default_payable_account_id" in data:
        _ensure_account(db, data["default_payable_account_id"], "Payable")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Insurance providers ─────────────────────────────────────────────────────

@router.get("/insurance-providers", response_model=List[InsuranceProviderResponse], dependencies=[VIEW])
def list_providers(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(InsuranceProvider)
    if not include_inactive:
        q = q.filter(InsuranceProvider.is_active == True)  # noqa: E712
    return q.order_by(InsuranceProvider.name).all()


@router.post("/insurance-providers", response_model=InsuranceProviderResponse, dependencies=[WRITE])
def create_provider(payload: InsuranceProviderCreate, db: Session = Depends(get_db)):
    if db.query(InsuranceProvider).filter(InsuranceProvider.name == payload.name).first():
        raise HTTPException(409, detail=f"Provider '{payload.name}' already exists.")
    _ensure_account(db, payload.default_receivable_account_id, "Receivable")
    row = InsuranceProvider(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/insurance-providers/{provider_id}", response_model=InsuranceProviderResponse, dependencies=[WRITE])
def update_provider(provider_id: int, payload: InsuranceProviderUpdate, db: Session = Depends(get_db)):
    row = db.query(InsuranceProvider).filter(InsuranceProvider.provider_id == provider_id).first()
    if not row:
        raise HTTPException(404, detail="Provider not found.")
    data = payload.model_dump(exclude_unset=True)
    if "default_receivable_account_id" in data:
        _ensure_account(db, data["default_receivable_account_id"], "Receivable")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Medical schemes ─────────────────────────────────────────────────────────

@router.get("/medical-schemes", response_model=List[MedicalSchemeResponse], dependencies=[VIEW])
def list_schemes(db: Session = Depends(get_db),
                 provider_id: Optional[int] = None,
                 include_inactive: bool = False):
    q = db.query(MedicalScheme)
    if provider_id is not None:
        q = q.filter(MedicalScheme.provider_id == provider_id)
    if not include_inactive:
        q = q.filter(MedicalScheme.is_active == True)  # noqa: E712
    return q.order_by(MedicalScheme.name).all()


@router.post("/medical-schemes", response_model=MedicalSchemeResponse, dependencies=[WRITE])
def create_scheme(payload: MedicalSchemeCreate, db: Session = Depends(get_db)):
    if not db.query(InsuranceProvider).filter(InsuranceProvider.provider_id == payload.provider_id).first():
        raise HTTPException(404, detail="Provider not found.")
    exists = db.query(MedicalScheme).filter(
        MedicalScheme.provider_id == payload.provider_id,
        MedicalScheme.name == payload.name,
    ).first()
    if exists:
        raise HTTPException(409, detail=f"Scheme '{payload.name}' already exists for this provider.")
    row = MedicalScheme(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/medical-schemes/{scheme_id}", response_model=MedicalSchemeResponse, dependencies=[WRITE])
def update_scheme(scheme_id: int, payload: MedicalSchemeUpdate, db: Session = Depends(get_db)):
    row = db.query(MedicalScheme).filter(MedicalScheme.scheme_id == scheme_id).first()
    if not row:
        raise HTTPException(404, detail="Scheme not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Price list ──────────────────────────────────────────────────────────────

@router.get("/price-list", response_model=List[PriceListItemResponse], dependencies=[VIEW])
def list_prices(db: Session = Depends(get_db),
                category: Optional[str] = None,
                include_inactive: bool = False,
                q: Optional[str] = None):
    query = db.query(PriceListItem)
    if category:
        query = query.filter(PriceListItem.category == category)
    if not include_inactive:
        query = query.filter(PriceListItem.is_active == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter(
            (PriceListItem.name.ilike(like)) | (PriceListItem.service_code.ilike(like))
        )
    return query.order_by(PriceListItem.category, PriceListItem.name).all()


@router.get("/price-list/categories", response_model=List[str], dependencies=[VIEW])
def list_categories():
    return list(PRICE_CATEGORIES)


@router.post("/price-list", response_model=PriceListItemResponse, dependencies=[WRITE])
def create_price(payload: PriceListItemCreate, db: Session = Depends(get_db)):
    if db.query(PriceListItem).filter(PriceListItem.service_code == payload.service_code).first():
        raise HTTPException(409, detail=f"Service code '{payload.service_code}' already exists.")
    if payload.category not in PRICE_CATEGORIES:
        raise HTTPException(400, detail=f"Category must be one of {list(PRICE_CATEGORIES)}.")
    _ensure_account(db, payload.revenue_account_id, "Revenue")
    row = PriceListItem(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/price-list/{price_id}", response_model=PriceListItemResponse, dependencies=[WRITE])
def update_price(price_id: int, payload: PriceListItemUpdate, db: Session = Depends(get_db)):
    row = db.query(PriceListItem).filter(PriceListItem.price_id == price_id).first()
    if not row:
        raise HTTPException(404, detail="Price item not found.")
    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"] not in PRICE_CATEGORIES:
        raise HTTPException(400, detail=f"Category must be one of {list(PRICE_CATEGORIES)}.")
    if "revenue_account_id" in data:
        _ensure_account(db, data["revenue_account_id"], "Revenue")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


# ─── Ledger mappings ─────────────────────────────────────────────────────────

@router.get("/ledger-mappings", response_model=List[LedgerMappingResponse], dependencies=[VIEW])
def list_mappings(db: Session = Depends(get_db), include_inactive: bool = False):
    q = db.query(LedgerMapping)
    if not include_inactive:
        q = q.filter(LedgerMapping.is_active == True)  # noqa: E712
    return q.order_by(LedgerMapping.source_key).all()


@router.get("/ledger-mappings/catalogue", response_model=List[SourceKeyCatalogueEntry], dependencies=[VIEW])
def mapping_catalogue(db: Session = Depends(get_db)):
    """All known source keys + their currently-configured mapping (or null)."""
    existing = {m.source_key: m for m in db.query(LedgerMapping).all()}
    return [
        SourceKeyCatalogueEntry(
            source_key=sk,
            description=desc,
            mapping=LedgerMappingResponse.model_validate(existing[sk]) if sk in existing else None,
        )
        for sk, desc in SOURCE_KEY_CATALOGUE
    ]


@router.patch("/ledger-mappings/{mapping_id}", response_model=LedgerMappingResponse, dependencies=[WRITE])
def update_mapping(mapping_id: int, payload: LedgerMappingUpdate, db: Session = Depends(get_db)):
    row = db.query(LedgerMapping).filter(LedgerMapping.mapping_id == mapping_id).first()
    if not row:
        raise HTTPException(404, detail="Mapping not found.")
    data = payload.model_dump(exclude_unset=True)
    if "debit_account_id" in data:
        _ensure_account(db, data["debit_account_id"], "Debit")
    if "credit_account_id" in data:
        _ensure_account(db, data["credit_account_id"], "Credit")
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.post("/ledger-mappings", response_model=LedgerMappingResponse, dependencies=[WRITE])
def create_mapping(source_key: str = Query(..., min_length=1, max_length=80),
                   debit_account_id: Optional[int] = None,
                   credit_account_id: Optional[int] = None,
                   description: Optional[str] = None,
                   db: Session = Depends(get_db)):
    """Create a mapping for a source_key not yet in the table.

    Used when a future module introduces a new auto-post event. For the
    keys already in SOURCE_KEY_CATALOGUE the migration seeds defaults,
    so this is the escape hatch for custom integrations.
    """
    if db.query(LedgerMapping).filter(LedgerMapping.source_key == source_key).first():
        raise HTTPException(409, detail=f"Mapping for '{source_key}' already exists; use PATCH.")
    _ensure_account(db, debit_account_id, "Debit")
    _ensure_account(db, credit_account_id, "Credit")
    row = LedgerMapping(
        source_key=source_key,
        debit_account_id=debit_account_id,
        credit_account_id=credit_account_id,
        description=description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
