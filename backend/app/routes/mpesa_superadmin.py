"""Superadmin Daraja config: the platform's OWN subscription billing rail.

Counterpart to app/routes/mpesa_admin.py (per-tenant Daraja config), and
sibling to app/routes/platform_payhero.py (the same job for the older Pay
Hero rail). Config CRUD and readiness live here; the money-moving surface
(charge a tenant, list transactions) lives in app/routes/platform_mpesa.py,
the same split mpesa_admin.py / mpesa_payment.py already draws for the
tenant rail.

MediFleet holds no Daraja credentials yet: Safaricom Go-Live for the
MediFleet shortcode has not been completed. An unconfigured or
credential-less platform config is therefore a normal, expected state,
reported here as "not ready" with a plain blocker list, never as an error.
Configuring it later is a form submission (POST /config), not a deploy.

Everything is gated behind require_superadmin and operates on the master DB.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_master_db
from app.config.settings import settings
from app.core.dependencies import require_superadmin
from app.models.platform_mpesa import PlatformMpesaConfig
from app.services.daraja.tokens import mint_callback_token, store_callback_token
from app.services.daraja.platform_stk import _callback_url
from app.utils.encryption import encrypt_data

router = APIRouter(
    prefix="/api/public/superadmin/platform-mpesa",
    tags=["Superadmin — Subscription Billing (Daraja)"],
    dependencies=[Depends(require_superadmin)],
)

# The placeholder that stands in for the token segment on a masked (not
# revealed) callback URL, matching app/routes/mpesa_admin.py's own
# convention and app/utils/log_redact.py's "<redacted>" word for the same
# concept everywhere a Daraja callback token is withheld.
_MASKED_TOKEN = "<redacted>"


# ─── Schemas ─────────────────────────────────────────────────────────────────


class PlatformMpesaConfigSchema(BaseModel):
    shortcode: Optional[str] = Field(default=None, max_length=20)
    shortcode_type: Optional[str] = Field(default=None, pattern="^(paybill|till)$")
    environment: Optional[str] = Field(default=None, pattern="^(sandbox|production)$")

    # Secrets: optional on every save, same as mpesa_admin.py's
    # MpesaConfigSchema. Blank/omitted means "leave the currently stored
    # value alone": a config update must never wipe a working credential
    # just because the form round-tripped it blank.
    consumer_key: Optional[str] = Field(default=None, max_length=255)
    consumer_secret: Optional[str] = Field(default=None, max_length=255)
    passkey: Optional[str] = Field(default=None, max_length=255)

    account_reference: Optional[str] = Field(default=None, max_length=50)
    transaction_desc: Optional[str] = Field(default=None, max_length=100)


# ─── Views ───────────────────────────────────────────────────────────────────


def _operator_view(config: Optional[PlatformMpesaConfig]) -> dict:
    """Never exposes decrypted credentials or the callback token."""
    if not config:
        return {"configured": False, "has_credentials": False}
    return {
        "configured": True,
        "has_credentials": bool(
            config.consumer_key_encrypted
            and config.consumer_secret_encrypted
            and config.passkey_encrypted
        ),
        "shortcode": config.shortcode,
        "shortcode_type": config.shortcode_type,
        "environment": config.environment,
        "callback_token_configured": bool(config.callback_token_encrypted),
        # Identifies WHICH token is live without revealing any part of it,
        # same reasoning as mpesa_admin.py's own field of this name.
        "callback_token_rotated_at": (
            config.callback_token_rotated_at.isoformat()
            if config.callback_token_rotated_at else None
        ),
        "account_reference": config.account_reference,
        "transaction_desc": config.transaction_desc,
        "is_active": config.is_active,
        "last_test_at": config.last_test_at.isoformat() if config.last_test_at else None,
        "last_test_status": config.last_test_status,
        "last_test_message": config.last_test_message,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/health")
def platform_health(master_db: Session = Depends(get_master_db)):
    """Is the Daraja subscription rail ready to collect money?

    Reports "not configured"/"no credentials" as plain blockers, not an
    error: MediFleet has not completed Safaricom Go-Live for its own
    shortcode yet, so this is the expected state today. Never leaks secrets.
    """
    config = master_db.query(PlatformMpesaConfig).first()
    base = (settings.PUBLIC_BASE_URL or "").strip()
    is_prod = settings.is_production

    blockers: list[str] = []
    if not base:
        blockers.append("PUBLIC_BASE_URL is not set.")
    elif is_prod and not base.startswith("https://"):
        blockers.append("PUBLIC_BASE_URL must be https:// in production.")
    if not config or not config.is_active:
        blockers.append("Platform Daraja config missing or inactive.")
    if not (config and config.shortcode):
        blockers.append("No MediFleet shortcode set.")
    has_creds = bool(
        config
        and config.consumer_key_encrypted
        and config.consumer_secret_encrypted
        and config.passkey_encrypted
    )
    if not has_creds:
        blockers.append(
            "No Daraja credentials yet (Safaricom Go-Live for the MediFleet "
            "shortcode is pending)."
        )
    if not (config and config.callback_token_encrypted):
        blockers.append("No callback token minted yet — save the config first.")

    callback_url = None
    if config and config.callback_token_encrypted and base:
        try:
            callback_url = _callback_url(config)
        except HTTPException:
            callback_url = None

    return {
        "environment": (config.environment if config else "sandbox"),
        "ready": not blockers,
        "blockers": blockers,
        "callback_url": callback_url,
        "config": _operator_view(config),
    }


@router.get("/config")
def get_config(master_db: Session = Depends(get_master_db)):
    return _operator_view(master_db.query(PlatformMpesaConfig).first())


@router.post("/config")
def set_config(payload: PlatformMpesaConfigSchema, master_db: Session = Depends(get_master_db)):
    config = master_db.query(PlatformMpesaConfig).first()
    if config is None:
        # Ships defaulted to sandbox with no credentials: MediFleet has not
        # completed Safaricom Go-Live yet. Not an error state, see the
        # module docstring.
        config = PlatformMpesaConfig(environment="sandbox")
        master_db.add(config)

    if payload.shortcode is not None:
        config.shortcode = payload.shortcode.strip()
    if payload.shortcode_type is not None:
        config.shortcode_type = payload.shortcode_type
    if payload.environment is not None:
        config.environment = payload.environment
    if payload.consumer_key:
        config.consumer_key_encrypted = encrypt_data(payload.consumer_key.strip())
    if payload.consumer_secret:
        config.consumer_secret_encrypted = encrypt_data(payload.consumer_secret.strip())
    if payload.passkey:
        config.passkey_encrypted = encrypt_data(payload.passkey.strip())
    if payload.account_reference is not None:
        config.account_reference = payload.account_reference
    if payload.transaction_desc is not None:
        config.transaction_desc = payload.transaction_desc
    config.is_active = True

    # Mint the callback token pair on first save only: rotating it on every
    # unrelated field edit would silently invalidate a URL already
    # registered with Safaricom, same discipline as mpesa_admin.py.
    if not config.callback_token_encrypted:
        store_callback_token(config, mint_callback_token())

    master_db.commit()
    master_db.refresh(config)
    return {"message": "Platform Daraja configuration saved.", **_operator_view(config)}


@router.post("/rotate-token")
def rotate_callback_token(master_db: Session = Depends(get_master_db)):
    """Mint a fresh callback token, and reveal it exactly once in the URL
    this response carries: the same reveal-once pattern every API key UI
    (and mpesa_admin.py's own rotate-token) uses. The standing GET
    (/health, /config) never shows the plaintext token again.
    """
    config = master_db.query(PlatformMpesaConfig).first()
    if config is None:
        raise HTTPException(status_code=400, detail="Platform Daraja is not configured yet.")
    store_callback_token(config, mint_callback_token())
    master_db.commit()
    master_db.refresh(config)

    base = (settings.PUBLIC_BASE_URL or "").strip()
    url = None
    if base:
        try:
            url = _callback_url(config)
        except HTTPException:
            url = None

    return {
        "message": (
            "Callback token rotated. This is the only time the new token is "
            "shown: copy the URL below into the Safaricom developer portal. "
            "Any URL registered with the old token is now dead."
        ),
        "stk_callback_url": url,
        **_operator_view(config),
    }
