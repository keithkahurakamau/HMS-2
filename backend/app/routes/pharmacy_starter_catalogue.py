"""Starter pharmacy catalogue: browse and adopt a ready-made product list.

Split out of pharmacy.py to keep that file focused on dispensing. This
feature has three moving parts:

  1. A static, repo-shipped catalogue of product names (see
     app.services.pharmacy_starter_catalogue), read from
     docs/seed/pharmacy-catalogue.csv and cached in process.
  2. An operator-controlled per-hospital toggle: the
     ``pharmacy_starter_catalogue`` key on Tenant.feature_flags (master
     DB), set from the superadmin Tenants Manager. Every route here checks
     it and returns 403 when it's off, the same way the module gate
     middleware blocks a whole module the tenant hasn't purchased. The
     ``/status`` endpoint is the one exception: it exists specifically so
     the frontend can ask "should I show this at all" without tripping a
     403 on first paint.
  3. Adoption, which writes zero-quantity, zero-price InventoryItem rows
     into the tenant's own database (see adopt_into_inventory for the
     idempotency and non-overwrite guarantees).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import RequirePermission
from app.core.modules import get_tenant_flags_cached, is_feature_flag_enabled
from app.schemas.pharmacy_starter_catalogue import (
    StarterCatalogueAdoptRequest,
    StarterCatalogueAdoptResponse,
    StarterCatalogueResponse,
    StarterCatalogueStatus,
)
from app.services.pharmacy_starter_catalogue import adopt_into_inventory, load_catalogue

router = APIRouter(prefix="/api/pharmacy/starter-catalogue", tags=["Pharmacy Starter Catalogue"])

FEATURE_FLAG_KEY = "pharmacy_starter_catalogue"


def _flag_enabled(request: Request) -> bool:
    tenant_db = request.headers.get("X-Tenant-ID") or ""
    if not tenant_db:
        return False
    return is_feature_flag_enabled(get_tenant_flags_cached(tenant_db), FEATURE_FLAG_KEY)


def _require_flag(request: Request) -> None:
    if not _flag_enabled(request):
        raise HTTPException(
            status_code=403,
            detail="The starter pharmacy catalogue is not enabled for this hospital.",
        )


@router.get("/status", response_model=StarterCatalogueStatus, dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_starter_catalogue_status(request: Request):
    """Whether the operator has switched this feature on for this hospital.

    Unlike the other routes here this never 403s: the Pharmacy page calls
    it up front to decide whether to render the "starter catalogue" entry
    point at all, so a disabled hospital never even sees the option.
    """
    return {"enabled": _flag_enabled(request)}


@router.get("", response_model=StarterCatalogueResponse, dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_starter_catalogue(request: Request):
    """List the starter catalogue's product names.

    ``available: false`` (with an empty list) means the operator hasn't
    loaded a real catalogue into docs/seed/pharmacy-catalogue.csv yet.
    That's a normal state, not an error.
    """
    _require_flag(request)
    products = load_catalogue()
    return {"available": len(products) > 0, "products": products}


@router.post("/adopt", response_model=StarterCatalogueAdoptResponse, dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def adopt_starter_catalogue(
    payload: StarterCatalogueAdoptRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Adopt some or all of the starter catalogue into this hospital's
    inventory as zero-quantity, zero-price items.

    Send ``names`` to adopt a selected subset, or omit it (or send an
    empty list) to adopt everything. Idempotent: items that already exist
    (matched by normalised name) are reported as skipped and left
    untouched, never overwritten.
    """
    _require_flag(request)
    result = adopt_into_inventory(db, payload.names)
    return result
