"""Platform-level Pay Hero — the operator's OWN subscription billing rail.

This is the *only* rail where the platform (MediFleet) receives money: the
superadmin pushes a subscription STK charge to a tenant's billing contact, the
funds land in MediFleet's own Pay Hero account, and Pay Hero settles them to
MediFleet's bank. It is deliberately separate from the per-hospital rail in
``payhero_service`` (which is custody-free — hospital money never touches us).

Everything here operates on the MASTER database:
  * platform_payhero_configs        — singleton: MediFleet's account + bank
  * platform_payhero_transactions   — one row per subscription charge
  * tenants                         — billing_contact_msisdn default

The webhook anchor is ``external_reference = PLAT-<tenant_id>-<nonce>``; the
callback router keys off the ``PLAT-`` prefix to settle here instead of a
tenant DB.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote

import requests
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.circuit import CircuitBreakerOpen, payhero_breaker
from app.models.master import Tenant
from app.models.platform_payhero import PlatformPayHeroConfig, PlatformPayHeroTransaction
from app.services.payhero_service import _format_msisdn, parse_callback_amount
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


# ─── Config / auth ───────────────────────────────────────────────────────────


def platform_config(master_db: Session) -> PlatformPayHeroConfig:
    config = master_db.query(PlatformPayHeroConfig).first()
    if not config or not config.is_active or not config.payhero_channel_id:
        raise HTTPException(
            status_code=400,
            detail="Platform Pay Hero is not configured — set it up under "
            "Superadmin → Subscription Billing.",
        )
    return config


def _credentials(config: PlatformPayHeroConfig) -> tuple[str, str]:
    if config.payhero_username_encrypted and config.payhero_password_encrypted:
        return (
            decrypt_data(config.payhero_username_encrypted),
            decrypt_data(config.payhero_password_encrypted),
        )
    user = settings.PAYHERO_USERNAME.get_secret_value()
    pw = settings.PAYHERO_PASSWORD.get_secret_value()
    if not user or not pw:
        raise HTTPException(
            status_code=500,
            detail="No platform Pay Hero credentials (config has none and "
            "PAYHERO_USERNAME / PAYHERO_PASSWORD are blank).",
        )
    return user, pw


def _auth_header(config: PlatformPayHeroConfig) -> dict[str, str]:
    user, pw = _credentials(config)
    token = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def platform_webhook_secret(master_db: Session) -> Optional[str]:
    """The platform account's own webhook secret (decrypted), or None → the
    callback verifier falls back to the global PAYHERO_WEBHOOK_SECRET."""
    config = master_db.query(PlatformPayHeroConfig).first()
    if config and config.payhero_webhook_secret_encrypted:
        return decrypt_data(config.payhero_webhook_secret_encrypted)
    return None


def _callback_url() -> str:
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")
    if settings.is_production and not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL must be HTTPS in production.")
    return f"{base}/api/payments/payhero/callback/platform"


# ─── STK push (charge a tenant's subscription) ───────────────────────────────


def initiate_platform_stk_push(
    master_db: Session,
    *,
    tenant_id: int,
    amount: Decimal | float | int,
    phone_number: Optional[str] = None,
    period_label: Optional[str] = None,
    initiated_by: Optional[int] = None,
) -> dict:
    """Push a subscription charge to a tenant's billing MSISDN.

    The phone falls back to the tenant's stored ``billing_contact_msisdn`` when
    not supplied. Funds settle to MediFleet's own Pay Hero account.
    """
    tenant = (
        master_db.query(Tenant)
        .filter(Tenant.tenant_id == tenant_id, Tenant.is_active == True)  # noqa: E712
        .first()
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive.")

    raw_phone = (phone_number or tenant.billing_contact_msisdn or "").strip()
    if not raw_phone:
        raise HTTPException(
            status_code=400,
            detail="No phone number: pass one or set the tenant's billing contact MSISDN.",
        )

    config = platform_config(master_db)
    formatted_phone = _format_msisdn(raw_phone)
    external_reference = f"PLAT-{tenant_id}-{secrets.token_hex(4)}"

    payload = {
        "amount": int(Decimal(str(amount))),
        "phone_number": formatted_phone,
        "channel_id": config.payhero_channel_id,
        "provider": "m-pesa",
        "external_reference": external_reference,
        "customer_name": tenant.name or "MediFleet Tenant",
        "callback_url": _callback_url(),
        "account_reference": config.account_reference or "MEDIFLEET",
        "transaction_desc": config.transaction_desc or "MediFleet Subscription",
    }
    url = f"{settings.PAYHERO_BASE_URL.rstrip('/')}/payments"
    try:
        response = payhero_breaker.call(
            requests.post, url, json=payload, headers=_auth_header(config), timeout=15,
        )
    except CircuitBreakerOpen:
        raise HTTPException(
            status_code=503,
            detail="Payment aggregator temporarily unavailable",
            headers={"Retry-After": "30"},
        )
    except requests.RequestException as exc:
        logger.exception("Platform Pay Hero STK request failed")
        raise HTTPException(status_code=502, detail=f"Pay Hero unreachable: {exc}")

    try:
        data = response.json()
    except ValueError:
        data = {}
    logger.info("Platform STK response: status=%s body=%s", response.status_code, safe_repr(data))

    if response.status_code >= 400 or data.get("success") is False:
        raise HTTPException(
            status_code=502,
            detail=data.get("error") or data.get("message") or "Pay Hero rejected request",
        )

    payhero_ref = data.get("reference") or data.get("CheckoutRequestID")
    txn = PlatformPayHeroTransaction(
        tenant_id=tenant_id,
        phone_number=formatted_phone,
        amount=Decimal(str(amount)),
        payhero_reference=payhero_ref,
        external_reference=external_reference,
        status="Pending",
        period_label=period_label,
        initiated_by=initiated_by,
    )
    master_db.add(txn)
    master_db.commit()
    return {
        "message": "Subscription STK push dispatched",
        "tenant_id": tenant_id,
        "external_reference": external_reference,
        "reference": payhero_ref,
        "transaction_id": txn.id,
    }


# ─── Callback settlement (master DB) ─────────────────────────────────────────


def _tenant_id_from_plat_ref(external_ref: str) -> Optional[int]:
    """Pull the tenant id out of a ``PLAT-<tenant_id>-<nonce>`` reference, or
    None if it doesn't have that shape (H-3)."""
    parts = (external_ref or "").split("-")
    if len(parts) >= 3 and parts[0] == "PLAT":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def txn_snapshot(txn: PlatformPayHeroTransaction) -> dict[str, Any]:
    """Plain-value snapshot for the live superadmin feed (taken before the
    session closes)."""
    return {
        "type": "platform_payment_update",
        "transaction_id": txn.id,
        "tenant_id": txn.tenant_id,
        "external_reference": txn.external_reference,
        "status": txn.status,
        "receipt_number": txn.receipt_number,
        "result_desc": txn.result_desc,
        "period_label": txn.period_label,
        "amount": float(txn.amount or 0),
    }


def apply_platform_callback(master_db: Session, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Settle a PLAT- callback against platform_payhero_transactions.

    Idempotent via a Postgres advisory lock on the receipt/reference and the
    UNIQUE(receipt_number) / UNIQUE(external_reference) constraints. Returns a
    snapshot to broadcast on the superadmin feed, or None when nothing changed.
    """
    resp = payload.get("response") or payload
    external_ref = resp.get("ExternalReference") or resp.get("external_reference") or ""
    receipt_no = resp.get("MpesaReceiptNumber") or resp.get("receipt_number")
    result_code = resp.get("ResultCode")
    result_desc = resp.get("ResultDesc") or resp.get("status") or ""

    if not external_ref:
        logger.error("Platform callback with no external_reference: %s", safe_repr(resp))
        return None

    # M-3: a present-but-non-numeric Amount is corruption/tampering, not a
    # zero payment — quarantine rather than floor-to-zero and mis-settle.
    try:
        amount = parse_callback_amount(resp.get("Amount") if resp.get("Amount") is not None else resp.get("amount"))
    except ValueError as exc:
        logger.error("Platform callback amount rejected for %s: %s", external_ref, exc)
        return None

    lock_id = int(hashlib.sha1((receipt_no or external_ref).encode()).hexdigest()[:15], 16)
    master_db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    if receipt_no:
        existing = (
            master_db.query(PlatformPayHeroTransaction)
            .filter(PlatformPayHeroTransaction.receipt_number == receipt_no)
            .first()
        )
        if existing:
            master_db.commit()
            return None

    txn = (
        master_db.query(PlatformPayHeroTransaction)
        .filter(PlatformPayHeroTransaction.external_reference == external_ref)
        .first()
    )
    if not txn:
        logger.error("Platform callback for unknown external_reference=%s", external_ref)
        return None

    # H-3: this is the operator's only money-receiving rail. The reference is
    # PLAT-<tenant_id>-<nonce>; re-derive the tenant from it and confirm it
    # matches the pending row, so a (validly-signed) callback that reuses or
    # manipulates another tenant's reference shape can't settle here.
    ref_tenant_id = _tenant_id_from_plat_ref(external_ref)
    if ref_tenant_id is not None and txn.tenant_id is not None and ref_tenant_id != txn.tenant_id:
        txn.status = "Tenant Mismatch"
        txn.result_desc = (
            f"reference tenant {ref_tenant_id} != pending tenant {txn.tenant_id}"
        )[:255]
        logger.warning(
            "Platform callback tenant mismatch on %s: ref=%s pending=%s (refused)",
            external_ref, ref_tenant_id, txn.tenant_id,
        )
        master_db.commit()
        return None

    # M-4: never transition out of a terminal Success. A settled charge must
    # not be regressed to Failed (or re-settled) by a later/replayed frame.
    if txn.status == "Success":
        master_db.commit()
        return None

    # C-1: the pending row already stored the amount we pushed — that is the
    # authoritative figure. A callback claiming MORE than we initiated is
    # tampering; refuse to settle and never adopt the body amount.
    initiated_amount = Decimal(str(txn.amount or 0))
    succeeded = result_code in (0, "0")
    if succeeded and initiated_amount > 0 and amount > initiated_amount:
        txn.status = "Amount Mismatch"
        txn.result_desc = (
            f"callback amount {amount} exceeds initiated {initiated_amount}"
        )[:255]
        logger.warning(
            "Platform callback amount tampering on %s: initiated=%s callback=%s (refused)",
            external_ref, initiated_amount, amount,
        )
        master_db.commit()
        return None

    txn.status = "Success" if succeeded else "Failed"
    txn.result_desc = str(result_desc)[:255]
    if receipt_no:
        txn.receipt_number = receipt_no
    # Keep the authoritative initiated amount; only adopt the callback figure
    # for older/unmatched rows that never recorded one.
    if initiated_amount <= 0 and amount > 0:
        txn.amount = amount
    if succeeded:
        from datetime import datetime, timezone

        txn.settled_at = datetime.now(timezone.utc)

    snapshot = txn_snapshot(txn)
    try:
        master_db.commit()
    except IntegrityError:
        master_db.rollback()
        return None
    return snapshot
