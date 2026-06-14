"""Pay Hero (https://payhero.co.ke) aggregator client — per-tenant routing.

Multi-tenant flow:
  * Each tenant has one ``payhero_configs`` row (see app/models/payhero.py).
  * The row carries the tenant's existing Safaricom shortcode (paybill or
    till), the Pay Hero channel id assigned to that till, and optional
    per-tenant Pay Hero API credentials.
  * Settlement of proceeds is governed by Pay Hero itself; we store the
    bank + account number for receipts and operator reference only.

Public surface:
  * initiate_stk_push(...)        - push an STK prompt to the customer.
  * check_payment_status(...)     - poll Pay Hero for a transaction.
  * settle_invoice_match(...)     - shared invoice-settle helper.
"""
from __future__ import annotations

import base64
import logging
import secrets
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import quote

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.circuit import CircuitBreakerOpen, payhero_breaker
from app.models.billing import Invoice, Payment
from app.models.payhero import PayHeroConfig, PayHeroTransaction
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


# ─── Webhook amount parsing (M-3) ──────────────────────────────────────────


def parse_callback_amount(raw: Any) -> Decimal:
    """Parse an amount from a (signed) webhook body, fail-loud on garbage.

    A missing/blank field is a legitimate "no amount yet" frame → Decimal(0).
    A *present* but non-numeric or negative value is tampering / corruption and
    must NOT silently floor to zero and settle — raise so the caller can
    quarantine the callback (M-3). ``Decimal(str(x))`` previously raised
    ``InvalidOperation`` deep inside the background task where it was swallowed.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Decimal(0)
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"non-numeric callback amount: {raw!r}")
    # Decimal("NaN")/Decimal("Infinity") parse fine but must never reach
    # settlement — NaN comparisons are all False so it would dodge the < 0 gate.
    if not amount.is_finite():
        raise ValueError(f"non-finite callback amount: {raw!r}")
    if amount < 0:
        raise ValueError(f"negative callback amount: {amount}")
    return amount


# ─── Config / auth ─────────────────────────────────────────────────────────


def _tenant_config(db: Session) -> PayHeroConfig:
    config = db.query(PayHeroConfig).first()
    if not config or not config.is_active or not config.payhero_channel_id:
        raise HTTPException(
            status_code=400,
            detail="Pay Hero is not configured for this hospital — set it up under Settings -> Pay Hero.",
        )
    return config


def _credentials(config: PayHeroConfig) -> tuple[str, str]:
    """Per-tenant creds when present, else the platform default from settings."""
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
            detail="No Pay Hero credentials configured (tenant has none and PAYHERO_USERNAME / PAYHERO_PASSWORD are blank).",
        )
    return user, pw


def _auth_header(config: PayHeroConfig) -> dict[str, str]:
    user, pw = _credentials(config)
    token = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


# ─── Helpers ───────────────────────────────────────────────────────────────


def _format_msisdn(phone: str) -> str:
    p = (phone or "").strip().replace(" ", "")
    if p.startswith("0"):
        return "254" + p[1:]
    if p.startswith("+"):
        return p[1:]
    return p


def _callback_url(tenant_db: Optional[str] = None) -> str:
    """Per-push callback URL. The tenant's db_name is baked into the path so
    the webhook can route the callback back to the right tenant database —
    Pay Hero echoes exactly the URL we set here, and (unlike a header) it
    survives the round-trip through Pay Hero's servers. Forgery is still
    blocked by the HMAC signature check in core/payhero_webhook."""
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")
    if settings.is_production and not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL must be HTTPS in production.")
    url = f"{base}/api/payments/payhero/callback"
    if tenant_db:
        url += f"/{quote(tenant_db.strip(), safe='')}"
    return url


# ─── STK push ──────────────────────────────────────────────────────────────


def initiate_stk_push(
    db: Session,
    *,
    phone_number: str,
    amount: Decimal | float | int,
    invoice_id: Optional[int],
    dispense_id: Optional[int] = None,
    account_reference: Optional[str] = None,
    transaction_desc: Optional[str] = None,
    customer_name: Optional[str] = None,
    callback_tenant: Optional[str] = None,
) -> dict:
    """Trigger a Pay Hero STK push and persist a pending PayHeroTransaction.

    ``callback_tenant`` is the tenant's db_name; it is baked into the callback
    URL so the asynchronous webhook lands in this tenant's database.
    """
    config = _tenant_config(db)
    formatted_phone = _format_msisdn(phone_number)

    # External reference is the anchor we match the webhook against. Combine
    # invoice/dispense id with a random nonce so two pushes for the same
    # source (e.g. retry after timeout) don't collide.
    if invoice_id:
        external_reference = f"INV-{invoice_id}-{secrets.token_hex(4)}"
    elif dispense_id:
        external_reference = f"RX-{dispense_id}-{secrets.token_hex(4)}"
    else:
        external_reference = f"TEST-{secrets.token_hex(6)}"

    payload = {
        "amount": int(Decimal(str(amount))),
        "phone_number": formatted_phone,
        "channel_id": config.payhero_channel_id,
        "provider": "m-pesa",
        "external_reference": external_reference,
        "customer_name": customer_name or "HMS Patient",
        "callback_url": _callback_url(callback_tenant),
        "account_reference": account_reference or config.account_reference or "HMS-BILLING",
        "transaction_desc": transaction_desc or config.transaction_desc or "Hospital Bill Payment",
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
        logger.exception("Pay Hero STK request failed")
        raise HTTPException(status_code=502, detail=f"Pay Hero unreachable: {exc}")

    try:
        data = response.json()
    except ValueError:
        data = {}

    logger.info("Pay Hero STK response: status=%s body=%s", response.status_code, safe_repr(data))

    if response.status_code >= 400 or data.get("success") is False:
        raise HTTPException(
            status_code=502,
            detail=data.get("error") or data.get("message") or "Pay Hero rejected request",
        )

    payhero_ref = data.get("reference") or data.get("CheckoutRequestID")
    txn = PayHeroTransaction(
        invoice_id=invoice_id,
        dispense_id=dispense_id,
        phone_number=formatted_phone,
        amount=Decimal(str(amount)),
        payhero_reference=payhero_ref,
        external_reference=external_reference,
        status="Pending",
        transaction_type="STK",
        bill_ref_number=payload["account_reference"],
    )
    db.add(txn)
    db.commit()

    return {
        "message": "Pay Hero STK push dispatched",
        "external_reference": external_reference,
        "reference": payhero_ref,
        "transaction_id": txn.id,
    }


def check_payment_status(db: Session, *, reference: str) -> dict:
    """Poll Pay Hero for the status of a previously-initiated payment."""
    if not reference:
        raise HTTPException(status_code=400, detail="reference is required")
    config = _tenant_config(db)
    url = f"{settings.PAYHERO_BASE_URL.rstrip('/')}/payments/{reference}"
    try:
        response = payhero_breaker.call(
            requests.get, url, headers=_auth_header(config), timeout=10,
        )
    except CircuitBreakerOpen:
        raise HTTPException(status_code=503, detail="Payment aggregator temporarily unavailable")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Pay Hero unreachable: {exc}")
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Pay Hero status lookup failed")
    return response.json()


# ─── Invoice settlement (shared by callback worker + manual assign) ────────


def settle_invoice_match(
    db: Session,
    *,
    invoice: Invoice,
    txn: PayHeroTransaction,
    match_basis: str,
    user_id: Optional[int] = None,
) -> Payment:
    """Apply a Pay Hero receipt to an invoice and post to the ledger.

    Idempotent on ``Payment.transaction_reference == txn.receipt_number``.
    """
    from app.services.accounting_posting import post_from_event

    amount = Decimal(str(txn.amount or 0))
    if amount <= 0:
        raise HTTPException(400, detail="Cannot settle a zero-amount receipt.")

    existing = None
    if txn.receipt_number:
        existing = (
            db.query(Payment)
            .filter(Payment.transaction_reference == txn.receipt_number)
            .first()
        )

    if existing:
        return existing

    payment = Payment(
        invoice_id=invoice.invoice_id,
        amount=amount,
        payment_method="M-Pesa",
        transaction_reference=txn.receipt_number,
    )
    db.add(payment)
    db.flush()

    invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amount
    invoice.status = (
        "Paid" if invoice.amount_paid >= invoice.total_amount else "Partially Paid"
    )
    invoice.payment_method = "M-Pesa"

    txn.invoice_id = invoice.invoice_id
    txn.match_basis = match_basis

    post_from_event(
        db,
        source_key="billing.payment.mpesa",
        source_id=txn.id,
        amount=amount,
        memo=f"Pay Hero receipt {txn.receipt_number or txn.external_reference}",
        reference=f"INV-{invoice.invoice_id}",
        user_id=user_id,
    )

    # M-Pesa settles asynchronously via webhook — the cashier isn't watching
    # the STK screen, so the bell is how they learn the money landed.
    try:
        from app.utils.notify import notify_permission
        fully_paid = invoice.status == "Paid"
        notify_permission(
            db, "billing:manage",
            title="M-Pesa payment received",
            body=(
                f"KES {amount} on Invoice #{invoice.invoice_id} "
                f"({'paid in full' if fully_paid else 'partial'}) · "
                f"receipt {txn.receipt_number or '—'}"
            ),
            link="/app/billing",
            category="success",
        )
    except Exception:  # noqa: BLE001 — notification must never break settlement
        logger.warning("settle_invoice_match: notify failed", exc_info=True)

    return payment
