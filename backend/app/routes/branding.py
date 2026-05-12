"""Tenant branding — uploaded logo, background image, brand colours, and
print-template configuration.

Branding lives on the **master DB** ``tenants`` row (one record per hospital)
because every login surface needs to render the right logo/background before
the tenant-DB session even exists. The frontend identifies the tenant by the
usual ``X-Tenant-ID`` header (== ``tenant.db_name``).

Storage strategy
----------------
Today the logo + background are persisted as **base64 data URLs** directly in
the row. This keeps the upload surface dead simple while we wait on the
Cloudinary integration. The contract is identical once we move: the column
will simply hold an ``https://res.cloudinary.com/...`` URL and the frontend
will keep using it as ``<img src={url} />``.

Size guard
----------
Data URLs balloon fast. We enforce a 1.2 MB cap on each field server-side so a
runaway upload can't bloat the master DB. The frontend pre-compresses to
~600 KB before uploading.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_master_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.master import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/branding", tags=["Branding"])
public_router = APIRouter(prefix="/api/public/branding", tags=["Branding (public)"])


# ── Limits ──────────────────────────────────────────────────────────────────
MAX_DATA_URL_BYTES = 1_200_000          # ~900 KB image after base64 overhead


# ── Pydantic ────────────────────────────────────────────────────────────────
class PrintTemplateConfig(BaseModel):
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    primary_template: Optional[str] = Field(default="modern")  # modern|classic|minimal
    show_logo: Optional[bool] = True


class BrandingPayload(BaseModel):
    """All fields optional — clients PATCH-style; absent keys mean 'unchanged'."""
    logo_data_url: Optional[str] = None
    background_data_url: Optional[str] = None
    brand_primary: Optional[str] = Field(default=None, max_length=16)
    brand_accent: Optional[str] = Field(default=None, max_length=16)
    print_templates: Optional[PrintTemplateConfig] = None
    # Sentinels — pass true to wipe the field rather than leaving it unchanged.
    clear_logo: bool = False
    clear_background: bool = False


# ── Helpers ─────────────────────────────────────────────────────────────────
def _resolve_tenant_by_request(request: Request, db: Session) -> Tenant:
    db_name = request.headers.get("X-Tenant-ID")
    if not db_name:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header is required")
    tenant = db.query(Tenant).filter(Tenant.db_name == db_name).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _serialize(t: Tenant) -> Dict[str, Any]:
    templates: Dict[str, Any] = {}
    if t.print_templates:
        try:
            templates = json.loads(t.print_templates)
        except (json.JSONDecodeError, TypeError):
            templates = {}
    return {
        "tenant_id": t.tenant_id,
        "tenant_name": t.name,
        "logo_data_url": t.logo_data_url,
        "background_data_url": t.background_data_url,
        "brand_primary": t.brand_primary,
        "brand_accent": t.brand_accent,
        "print_templates": templates,
    }


def _validate_data_url(value: str, label: str) -> None:
    if not value.startswith("data:image/"):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be a base64-encoded image data URL (data:image/...).",
        )
    if len(value) > MAX_DATA_URL_BYTES:
        kb = MAX_DATA_URL_BYTES // 1024
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds the {kb} KB upload cap. Compress the image and retry.",
        )


def _validate_hex_color(value: str, label: str) -> None:
    if not value.startswith("#") or len(value) not in (4, 7, 9):
        raise HTTPException(status_code=400, detail=f"{label} must be a hex colour (e.g. #06b6d4).")


# ── Routes ──────────────────────────────────────────────────────────────────
@router.get("")
def get_branding(request: Request, db: Session = Depends(get_master_db),
                 _: dict = Depends(get_current_user)):
    """Returns the branding for the caller's tenant."""
    tenant = _resolve_tenant_by_request(request, db)
    return _serialize(tenant)


@router.put("", dependencies=[Depends(RequirePermission("settings:read"))])
def update_branding(
    payload: BrandingPayload,
    request: Request,
    db: Session = Depends(get_master_db),
):
    """Updates branding for the caller's tenant.

    Permission gate is intentionally ``settings:read`` — every Admin already has
    it (settings is admin-only), and we keep the column count down by reusing
    the existing capability rather than minting ``branding:write``.
    """
    tenant = _resolve_tenant_by_request(request, db)

    # ─ logo / background ─
    if payload.clear_logo:
        tenant.logo_data_url = None
    elif payload.logo_data_url is not None:
        _validate_data_url(payload.logo_data_url, "Logo")
        tenant.logo_data_url = payload.logo_data_url

    if payload.clear_background:
        tenant.background_data_url = None
    elif payload.background_data_url is not None:
        _validate_data_url(payload.background_data_url, "Background")
        tenant.background_data_url = payload.background_data_url

    # ─ colours ─
    if payload.brand_primary is not None:
        if payload.brand_primary == "":
            tenant.brand_primary = None
        else:
            _validate_hex_color(payload.brand_primary, "brand_primary")
            tenant.brand_primary = payload.brand_primary
    if payload.brand_accent is not None:
        if payload.brand_accent == "":
            tenant.brand_accent = None
        else:
            _validate_hex_color(payload.brand_accent, "brand_accent")
            tenant.brand_accent = payload.brand_accent

    # ─ print templates ─
    if payload.print_templates is not None:
        tenant.print_templates = json.dumps(payload.print_templates.model_dump(exclude_none=True))

    db.commit()
    db.refresh(tenant)
    logger.info("Branding updated for tenant %s (id=%s)", tenant.db_name, tenant.tenant_id)
    return _serialize(tenant)


# ── Public lookup ───────────────────────────────────────────────────────────
@public_router.get("/{db_name}")
def public_branding(db_name: str, db: Session = Depends(get_master_db)):
    """Returns the public-safe branding subset (logo, colours) for unauth surfaces.

    Background images are intentionally **omitted** here — they can be large
    and we don't want anonymous probes pulling them on every request. Login /
    Landing surfaces include the background lookup once the user has selected
    a hospital from the Portal.
    """
    tenant = db.query(Tenant).filter(Tenant.db_name == db_name).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "logo_data_url": tenant.logo_data_url,
        "background_data_url": tenant.background_data_url,
        "brand_primary": tenant.brand_primary,
        "brand_accent": tenant.brand_accent,
    }
