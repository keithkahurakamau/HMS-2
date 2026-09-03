"""Platform-level Daraja STK push: the operator's own subscription charge to
a tenant's billing contact.

Counterpart to app/services/daraja/stk.py, but against PlatformMpesaConfig /
PlatformMpesaTransaction, on the MASTER database, and MediFleet's own
shortcode receives the money, not a hospital's. app/services/daraja/platform.py
holds the callback/settlement side; this module is the push side that Task 9
left unbuilt (see that module's own docstring history).

MediFleet holds no Daraja credentials yet: Safaricom Go-Live for the
MediFleet shortcode has not been completed. A missing or credential-less
platform config is therefore a normal, expected state here, reported with
the same "set it up" message a hospital sees for its own till, never as an
unexpected error.

subscription_invoice_id is set HERE, at push time, when the caller names an
invoice to charge: the superadmin already knows which invoice a charge is
for (the receivables console shows the outstanding balance before a charge
is ever pushed), the same way app/services/daraja/stk.py's caller already
knows invoice_id before reserving a Pending MpesaTransaction. Settlement
(platform.py) only ever reads that column back; it does not, and should
not, have to guess which invoice a bare receipt belongs to.
"""
from __future__ import annotations

import logging
import secrets
from decimal import ROUND_CEILING, Decimal
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.daraja_callback import PLATFORM_HINT
from app.models.master import Tenant
from app.models.platform_mpesa import PlatformMpesaConfig, PlatformMpesaTransaction
from app.models.subscription_billing import SubscriptionInvoice
from app.services.daraja.client import DarajaClient, DarajaError
from app.services.daraja.credentials import daraja_timestamp, normalize_msisdn, stk_password
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

_ACCOUNT_REFERENCE_MAX = 12
_TRANSACTION_DESC_MAX = 13


def platform_config(master_db: Session) -> PlatformMpesaConfig:
    """The singleton platform config, ready to push with.

    Raises a plain 400, not a 500: an unconfigured or credential-less
    platform rail is the expected state until Safaricom Go-Live for the
    MediFleet shortcode completes, not a broken deployment.
    """
    config = master_db.query(PlatformMpesaConfig).first()
    if not config or not config.is_active:
        raise HTTPException(
            status_code=400,
            detail="Platform Daraja is not configured yet. Set it up under "
            "Superadmin -> Subscription Billing.",
        )
    if not (
        config.consumer_key_encrypted
        and config.consumer_secret_encrypted
        and config.passkey_encrypted
    ):
        raise HTTPException(
            status_code=400,
            detail="Platform Daraja has no credentials yet (Safaricom Go-Live "
            "for the MediFleet shortcode is pending).",
        )
    return config


def _decrypted(value: Optional[str], *, field: str) -> str:
    plain = decrypt_data(value) if value else None
    if not plain:
        raise HTTPException(
            status_code=400, detail=f"Platform Daraja {field} is not configured.",
        )
    return plain


def _daraja_client(config: PlatformMpesaConfig) -> DarajaClient:
    creds = SimpleNamespace(
        consumer_key=_decrypted(config.consumer_key_encrypted, field="consumer key"),
        consumer_secret=_decrypted(config.consumer_secret_encrypted, field="consumer secret"),
        environment=config.environment,
        shortcode=config.shortcode,
    )
    return DarajaClient(creds)


def _callback_url(config: PlatformMpesaConfig) -> str:
    """Build the platform CallBackURL, matched exactly against the route
    app/routes/mpesa_payment.py already wires:
    /api/payments/mpesa/platform/stk/callback/{tenant_hint}/{token}, hint
    fixed at the reserved PLATFORM_HINT value.
    """
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured.")
    if settings.is_production and not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL must be HTTPS in production.")
    if not config.callback_token_encrypted:
        raise HTTPException(
            status_code=400,
            detail="Platform Daraja callback token has not been generated yet.",
        )
    token = decrypt_data(config.callback_token_encrypted)
    return f"{base}/api/payments/mpesa/platform/stk/callback/{PLATFORM_HINT}/{quote(token, safe='')}"


def initiate_platform_stk_push(
    master_db: Session,
    *,
    tenant_id: int,
    amount: Decimal,
    phone_number: Optional[str] = None,
    subscription_invoice_id: Optional[int] = None,
    period_label: Optional[str] = None,
    initiated_by: Optional[int] = None,
) -> dict:
    """Push a subscription charge to a tenant's billing MSISDN.

    The phone falls back to the tenant's stored billing_contact_msisdn when
    not supplied, same as the Pay Hero platform rail. When
    subscription_invoice_id is given, it is validated against the tenant
    and stored on the Pending row so a settled callback lands as an
    InvoicePayment against that exact invoice (see platform.py).
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
    try:
        msisdn = normalize_msisdn(raw_phone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    invoice = None
    if subscription_invoice_id is not None:
        invoice = (
            master_db.query(SubscriptionInvoice)
            .filter(
                SubscriptionInvoice.id == subscription_invoice_id,
                SubscriptionInvoice.tenant_id == tenant_id,
            )
            .first()
        )
        if invoice is None:
            raise HTTPException(
                status_code=404, detail="Subscription invoice not found for this tenant.",
            )
        if invoice.status == "void":
            raise HTTPException(status_code=400, detail="Cannot charge against a void invoice.")

    config = platform_config(master_db)

    amount_decimal = Decimal(str(amount))
    if amount_decimal <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    # Round UP to the whole shilling once, here, same discipline and same
    # reason as app/services/daraja/stk.py: Daraja's wire format only takes
    # whole shillings, and this rounded figure is the ONLY one ever quoted
    # to Daraja or persisted, so the two can never diverge.
    charged_amount = amount_decimal.quantize(Decimal("1"), rounding=ROUND_CEILING)

    external_reference = f"SUB-{tenant_id}-{secrets.token_hex(4)}"

    txn = PlatformMpesaTransaction(
        tenant_id=tenant_id,
        subscription_invoice_id=invoice.id if invoice else None,
        phone_number=msisdn,
        amount=charged_amount,
        external_reference=external_reference,
        status="Pending",
        period_label=period_label,
        initiated_by=initiated_by,
    )
    master_db.add(txn)
    # Committed before the Daraja round trip, same reason stk.py's
    # _reserve_pending commits early: a callback that beats this function
    # back finds a real row to settle against.
    master_db.commit()

    try:
        passkey = _decrypted(config.passkey_encrypted, field="passkey")
        timestamp = daraja_timestamp()
        password = stk_password(config.shortcode, passkey, timestamp)
        callback_url = _callback_url(config)
        desc = (config.transaction_desc or "MediFleet Subscription")[:_TRANSACTION_DESC_MAX]
        ref = (config.account_reference or "MEDIFLEET")[:_ACCOUNT_REFERENCE_MAX]

        payload = {
            "BusinessShortCode": config.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": (
                "CustomerBuyGoodsOnline" if config.shortcode_type == "till"
                else "CustomerPayBillOnline"
            ),
            "Amount": int(charged_amount),
            "PartyA": msisdn,
            "PartyB": config.shortcode,
            "PhoneNumber": msisdn,
            "CallBackURL": callback_url,
            "AccountReference": ref,
            "TransactionDesc": desc,
        }
        client = _daraja_client(config)
        data = client.post("/mpesa/stkpush/v1/processrequest", payload)
    except DarajaError as exc:
        logger.warning("Platform Daraja STK push failed: %s", safe_repr(str(exc)))
        txn.status = "Failed"
        txn.result_desc = "Could not reach M-Pesa."
        master_db.commit()
        raise HTTPException(status_code=502, detail="Could not reach M-Pesa. Try again shortly.")
    except HTTPException:
        txn.status = "Failed"
        master_db.commit()
        raise

    checkout_request_id = data.get("CheckoutRequestID")
    merchant_request_id = data.get("MerchantRequestID")
    if not checkout_request_id:
        logger.warning("Platform Daraja STK push returned no CheckoutRequestID: %s", safe_repr(data))
        txn.status = "Failed"
        txn.result_desc = data.get("ResponseDescription") or "M-Pesa did not accept the request."
        master_db.commit()
        raise HTTPException(status_code=502, detail=txn.result_desc)

    txn.checkout_request_id = checkout_request_id
    txn.merchant_request_id = merchant_request_id
    master_db.commit()

    return {
        "message": "Subscription STK push dispatched.",
        "tenant_id": tenant_id,
        "subscription_invoice_id": txn.subscription_invoice_id,
        "transaction_id": txn.id,
        "external_reference": external_reference,
        "checkout_request_id": checkout_request_id,
        "merchant_request_id": merchant_request_id,
        "amount_charged": charged_amount,
    }
