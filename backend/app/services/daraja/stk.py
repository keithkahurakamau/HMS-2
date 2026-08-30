"""STK Push (Lipa na M-Pesa Online) and STK Query, against a tenant's own
Daraja config.

Everything here goes through DarajaClient, the single seam that speaks HTTP
to Safaricom. This module never calls requests directly.

Money is Decimal end to end. Daraja's wire format only accepts whole
shillings, so the int() cast on Amount happens at the request boundary and
nowhere else.
"""
from __future__ import annotations

import logging
import secrets
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.client import DarajaClient, DarajaError
from app.services.daraja.credentials import daraja_timestamp, normalize_msisdn, stk_password
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

# Daraja enforces these with an opaque error rather than a helpful one, so
# truncate deliberately here instead of discovering the limit in production.
_ACCOUNT_REFERENCE_MAX = 12
_TRANSACTION_DESC_MAX = 13


def config_for(db: Session, *, department_id: Optional[int] = None) -> MpesaConfig:
    """The single lookup point for a tenant's M-Pesa config.

    Every STK/query/settlement path that needs a MpesaConfig must call this,
    not query MpesaConfig directly, so a later change to how a config is
    chosen only has to change here.

    `department_id` is accepted but unused for now: mpesa_configs is
    currently one row per tenant. A planned follow-up makes it a multi-row
    table with a nullable department_id, where the row with NULL is the
    hospital-wide default and a department's own active row overrides it
    when present. That resolution lands here later; today this behaves
    exactly like a plain "the tenant's one active config" lookup regardless
    of what is passed.
    """
    config = db.query(MpesaConfig).filter(MpesaConfig.is_active == True).first()  # noqa: E712
    if not config:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa is not configured for this hospital. Set it up under Settings -> M-Pesa.",
        )
    return config


def _decrypted(value: Optional[str], *, field: str) -> str:
    plain = decrypt_data(value) if value else None
    if not plain:
        raise HTTPException(
            status_code=400,
            detail=f"M-Pesa {field} is not configured for this hospital.",
        )
    return plain


def _daraja_client(config: MpesaConfig) -> DarajaClient:
    """Build the DarajaClient for `config`, decrypting its credentials.

    DarajaClient reads plain .consumer_key / .consumer_secret / .environment
    / .shortcode attributes; MpesaConfig stores the first two encrypted, so a
    lightweight stand-in carries the decrypted values across without adding
    a plaintext-credential attribute to the ORM model itself.
    """
    creds = SimpleNamespace(
        consumer_key=_decrypted(config.consumer_key_encrypted, field="consumer key"),
        consumer_secret=_decrypted(config.consumer_secret_encrypted, field="consumer secret"),
        environment=config.environment,
        shortcode=config.shortcode,
    )
    return DarajaClient(creds)


def _callback_url(config: MpesaConfig, callback_tenant: Optional[str]) -> str:
    """Build the CallBackURL, tenant hint and all.

    The hint is the tenant's db_name, carried alongside the token so an
    inbound callback resolves with one indexed lookup against the one named
    tenant database instead of a scan across every tenant. The token itself
    is decrypted from callback_token_encrypted: that column, not the HMAC
    lookup hash, is the one that can be recovered back to the plaintext
    token an outbound URL needs.
    """
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")
    if settings.is_production and not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL must be HTTPS in production.")
    if not callback_tenant:
        raise HTTPException(
            status_code=500,
            detail="Missing tenant routing hint for the M-Pesa callback URL.",
        )
    if not config.callback_token_encrypted:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa callback token has not been generated yet for this hospital.",
        )
    token = decrypt_data(config.callback_token_encrypted)
    hint = quote(callback_tenant.strip(), safe="")
    return f"{base}/api/payments/mpesa/stk/callback/{hint}/{quote(token, safe='')}"


def initiate_stk_push(
    db: Session,
    *,
    phone_number: str,
    amount: Decimal | float | int,
    invoice_id: Optional[int] = None,
    dispense_id: Optional[int] = None,
    account_reference: Optional[str] = None,
    transaction_desc: Optional[str] = None,
    callback_tenant: Optional[str] = None,
    department_id: Optional[int] = None,
) -> dict:
    """Push an STK prompt to `phone_number` and persist a Pending transaction.

    The MpesaTransaction row is written and committed before this function
    returns, with the CheckoutRequestID Daraja just handed back, so a
    callback arriving before our own commit still finds a row (Daraja
    callbacks can be fast).

    `department_id` is forwarded to config_for and otherwise unused today;
    see that function's docstring.
    """
    config = config_for(db, department_id=department_id)
    msisdn = normalize_msisdn(phone_number)

    amount_decimal = Decimal(str(amount))
    if amount_decimal <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    passkey = _decrypted(config.passkey_encrypted, field="passkey")
    timestamp = daraja_timestamp()
    password = stk_password(config.shortcode, passkey, timestamp)
    callback_url = _callback_url(config, callback_tenant)

    ref = (account_reference or config.account_reference or "HMS-BILLING")
    ref = ref[:_ACCOUNT_REFERENCE_MAX]
    desc = (transaction_desc or config.transaction_desc or "Payment")
    desc = desc[:_TRANSACTION_DESC_MAX]

    payload = {
        "BusinessShortCode": config.shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": (
            "CustomerBuyGoodsOnline" if config.shortcode_type == "till"
            else "CustomerPayBillOnline"
        ),
        "Amount": int(amount_decimal),  # Daraja takes whole shillings only
        "PartyA": msisdn,
        "PartyB": config.shortcode,
        "PhoneNumber": msisdn,
        "CallBackURL": callback_url,
        "AccountReference": ref,
        "TransactionDesc": desc,
    }

    client = _daraja_client(config)
    try:
        data = client.post("/mpesa/stkpush/v1/processrequest", payload)
    except DarajaError as exc:
        logger.warning("Daraja STK push failed: %s", safe_repr(str(exc)))
        raise HTTPException(status_code=502, detail="Could not reach M-Pesa. Try again shortly.")

    checkout_request_id = data.get("CheckoutRequestID")
    merchant_request_id = data.get("MerchantRequestID")
    if not checkout_request_id:
        logger.warning("Daraja STK push returned no CheckoutRequestID: %s", safe_repr(data))
        raise HTTPException(
            status_code=502,
            detail=data.get("ResponseDescription") or "M-Pesa did not accept the request.",
        )

    if invoice_id:
        external_reference = f"INV-{invoice_id}-{secrets.token_hex(4)}"
    elif dispense_id:
        external_reference = f"RX-{dispense_id}-{secrets.token_hex(4)}"
    else:
        external_reference = f"TEST-{secrets.token_hex(6)}"

    txn = MpesaTransaction(
        invoice_id=invoice_id,
        dispense_id=dispense_id,
        phone_number=msisdn,
        amount=amount_decimal,
        checkout_request_id=checkout_request_id,
        merchant_request_id=merchant_request_id,
        external_reference=external_reference,
        status="Pending",
        transaction_type="STK",
        bill_ref_number=ref,
    )
    db.add(txn)
    db.commit()

    return {
        "checkout_request_id": checkout_request_id,
        "merchant_request_id": merchant_request_id,
        "external_reference": external_reference,
        "transaction_id": txn.id,
    }


def query_stk(db: Session, *, checkout_request_id: str) -> dict:
    """Poll Daraja for the current state of a previously-initiated STK push.

    Returns Daraja's raw response. This does not itself settle anything:
    settlement only ever happens through apply_stk_callback's cross-checked
    path, whether it is reached via the callback or via a reconciliation job
    that calls this and then routes the result through the same checks.
    """
    if not checkout_request_id:
        raise HTTPException(status_code=400, detail="checkout_request_id is required")

    config = config_for(db)
    passkey = _decrypted(config.passkey_encrypted, field="passkey")
    timestamp = daraja_timestamp()
    password = stk_password(config.shortcode, passkey, timestamp)

    payload = {
        "BusinessShortCode": config.shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    client = _daraja_client(config)
    try:
        return client.post("/mpesa/stkpushquery/v1/query", payload)
    except DarajaError as exc:
        logger.warning("Daraja STK query failed: %s", safe_repr(str(exc)))
        raise HTTPException(status_code=502, detail="Could not reach M-Pesa. Try again shortly.")
