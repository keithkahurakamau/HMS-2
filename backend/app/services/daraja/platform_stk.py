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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.daraja_callback import PLATFORM_HINT
from app.core.idempotency import idempotent_guard, persist_and_commit
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

# The endpoint name idempotent_guard scopes the (user, key) cache to, same
# convention as app/services/daraja/stk.py's _IDEMPOTENCY_ENDPOINT.
_IDEMPOTENCY_ENDPOINT = "daraja.platform-stk-push"

# The one partial unique index this module reacts to (never checks for
# ahead of time): app/models/platform_mpesa.py's __table_args__, applied to
# the real master DB via MASTER_DB_PATCHES in scripts/migrate_all_tenants.py.
_PENDING_GUARD_CONSTRAINTS = frozenset({"uq_platform_mpesa_txn_one_pending_per_invoice"})


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


def _find_pending_for_invoice(
    master_db: Session, *, subscription_invoice_id: Optional[int]
) -> Optional[PlatformMpesaTransaction]:
    """The live Pending row (if any) blocking a reservation for this
    invoice. At most one can exist by construction of the partial unique
    index this function's caller is reacting to. Mirrors
    app/services/daraja/reservation.py's _find_pending exactly, scoped to
    subscription_invoice_id instead of invoice_id/dispense_id."""
    if subscription_invoice_id is None:
        return None
    return (
        master_db.query(PlatformMpesaTransaction)
        .filter(
            PlatformMpesaTransaction.status == "Pending",
            PlatformMpesaTransaction.subscription_invoice_id == subscription_invoice_id,
        )
        .first()
    )


def _reserve_pending(
    master_db: Session,
    *,
    tenant_id: int,
    subscription_invoice_id: Optional[int],
    phone_number: str,
    charged_amount: Decimal,
    external_reference: str,
    period_label: Optional[str],
    initiated_by: Optional[int],
) -> tuple[Optional[PlatformMpesaTransaction], bool]:
    """Reserve the one Pending slot for this subscription invoice.

    CRITICAL fix, round 1 review: insert-and-catch, never check-then-insert,
    the exact discipline app/services/daraja/reservation.py's
    _reserve_pending documents for the tenant rail and for the same reason:
    a check-then-insert has a gap between the check and the insert, and
    that gap is precisely how a superadmin double-click used to reach
    settlement twice (two genuine Safaricom receipts, so the receipt-keyed
    replay check in platform.py never caught either one). The partial
    unique index (uq_platform_mpesa_txn_one_pending_per_invoice) is what
    actually enforces "at most one Pending row per subscription invoice"
    across every worker; this function only reacts to it.

    Returns (txn, reserved). reserved=True means the caller owns a fresh
    Pending row and should push to Daraja. reserved=False means a
    DIFFERENT, still-live Pending transaction already exists for this
    invoice: txn is that transaction, and the caller must not send a
    second prompt to the billing contact's handset.

    A charge with no subscription_invoice_id (a bare connectivity test)
    has no uniqueness to enforce, matching the index's WHERE clause: it
    always reserves.

    CONTRACT the caller must know, same as the tenant rail's version:
    reserved=True means `master_db` has ALREADY BEEN COMMITTED (before the
    slow Daraja round trip, so a callback that beats this function back
    still finds a row). reserved=False means no commit happened.
    """
    txn = PlatformMpesaTransaction(
        tenant_id=tenant_id,
        subscription_invoice_id=subscription_invoice_id,
        phone_number=phone_number,
        amount=charged_amount,
        external_reference=external_reference,
        status="Pending",
        period_label=period_label,
        initiated_by=initiated_by,
    )
    try:
        with master_db.begin_nested():
            master_db.add(txn)
            master_db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint not in _PENDING_GUARD_CONSTRAINTS:
            raise
        existing = _find_pending_for_invoice(
            master_db, subscription_invoice_id=subscription_invoice_id
        )
        return existing, False
    else:
        master_db.commit()
        return txn, True


def _finalize(
    master_db: Session,
    result: dict,
    *,
    persist,
    user_id: Optional[int],
    idempotency_key: Optional[str],
    idempotency_body: Optional[dict],
) -> dict:
    """Persist `result` into the idempotency cache (if `persist` is set)
    and commit. Mirrors app/services/daraja/stk.py's _finalize exactly,
    including its reasoning for persist_and_commit over a plain commit: a
    caller racing this one can reach persist() too, after _reserve_pending's
    own early commit released the advisory lock idempotent_guard took, and
    persist_and_commit is what makes that race replay the winner's answer
    instead of surfacing an uncaught IntegrityError.
    """
    if persist is None:
        master_db.commit()
        return result
    return persist_and_commit(
        master_db, persist, result, status=200,
        user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT,
        key=idempotency_key, body=idempotency_body,
    )


def initiate_platform_stk_push(
    master_db: Session,
    *,
    tenant_id: int,
    amount: Decimal,
    phone_number: Optional[str] = None,
    subscription_invoice_id: Optional[int] = None,
    period_label: Optional[str] = None,
    initiated_by: Optional[int] = None,
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Push a subscription charge to a tenant's billing MSISDN.

    The phone falls back to the tenant's stored billing_contact_msisdn when
    not supplied, same as the Pay Hero platform rail. When
    subscription_invoice_id is given, it is validated against the tenant,
    reserved via the partial unique index (see _reserve_pending), and
    stored on the Pending row so a settled callback lands as an
    InvoicePayment against that exact invoice (see platform.py).

    `idempotency_key` (with `user_id`, the superadmin's admin_id) is real
    idempotency via app/core/idempotency.py's idempotent_guard, the same
    mechanism app/services/daraja/stk.py's tenant STK route requires: a
    repeated key with the same body replays the first response instead of
    pushing a second prompt. This protects the "same admin double-clicked
    the same button" case; _reserve_pending's partial unique index is what
    protects the ledger regardless of whether a key was ever supplied.
    """
    persist = None
    idempotency_body = None
    if idempotency_key:
        if user_id is None:
            raise HTTPException(
                status_code=400,
                detail="user_id is required when using an idempotency key.",
            )
        idempotency_body = {
            "tenant_id": tenant_id,
            "amount": str(amount),
            "phone_number": phone_number,
            "subscription_invoice_id": subscription_invoice_id,
            "period_label": period_label,
        }
        cached, persist = idempotent_guard(
            master_db, user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT, key=idempotency_key,
            body=idempotency_body,
        )
        if cached is not None:
            return cached

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

    # CRITICAL fix, round 1 review: reserve via insert-and-catch against the
    # partial unique index, not a bare add()+commit(). A bare commit here
    # let two genuine STK approvals against the same invoice both reach
    # settlement (see _reserve_pending's own docstring for the full story).
    txn, reserved = _reserve_pending(
        master_db,
        tenant_id=tenant_id,
        subscription_invoice_id=invoice.id if invoice else None,
        phone_number=msisdn,
        charged_amount=charged_amount,
        external_reference=external_reference,
        period_label=period_label,
        initiated_by=initiated_by,
    )
    if not reserved:
        if txn is None:
            raise HTTPException(
                status_code=409,
                detail="Could not reserve a charge slot for this invoice. Try again shortly.",
            )
        result = {
            "message": "A charge is already pending for this invoice.",
            "tenant_id": tenant_id,
            "subscription_invoice_id": txn.subscription_invoice_id,
            "transaction_id": txn.id,
            "external_reference": txn.external_reference,
            "checkout_request_id": txn.checkout_request_id,
            "amount_charged": txn.amount,
            "already_pending": True,
        }
        return _finalize(
            master_db, result, persist=persist, user_id=user_id,
            idempotency_key=idempotency_key, idempotency_body=idempotency_body,
        )

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

    result = {
        "message": "Subscription STK push dispatched.",
        "tenant_id": tenant_id,
        "subscription_invoice_id": txn.subscription_invoice_id,
        "transaction_id": txn.id,
        "external_reference": external_reference,
        "checkout_request_id": checkout_request_id,
        "merchant_request_id": merchant_request_id,
        "amount_charged": charged_amount,
    }
    return _finalize(
        master_db, result, persist=persist, user_id=user_id,
        idempotency_key=idempotency_key, idempotency_body=idempotency_body,
    )
