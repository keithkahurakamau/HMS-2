"""STK Push (Lipa na M-Pesa Online) and STK Query, against a tenant's own
Daraja config.

Everything here goes through DarajaClient, the single seam that speaks HTTP
to Safaricom. This module never calls requests directly.

Money is Decimal end to end. Daraja's wire format only accepts whole
shillings, so any fractional amount is rounded UP to the shilling once,
here, at the request boundary, and the SAME rounded figure is what gets
persisted as MpesaTransaction.amount. Rounding up (not down, not truncating)
means the two figures can never diverge: a shortfall would leave every
fractional invoice permanently part-paid, and a mismatch between what we
quote in the payload and what we store would make the settlement
cross-check quarantine a legitimate, matching callback on every invoice
with cents.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.idempotency import idempotent_guard
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

# An STK prompt expires on the handset in about a minute. A Pending
# reservation older than this is treated as dead for the purpose of freeing
# an invoice/dispense slot for a genuine retry (see _reserve_pending). This
# is deliberately longer than the handset expiry so a merely-slow-but-live
# push is never pre-empted, and it never marks the old push Success or
# Failed: that would be settling from a guess. The real outcome, if any, is
# reconciled independently (Task 8) by asking Safaricom, not by asserting one.
_STALE_PENDING_TIMEOUT = timedelta(minutes=2)

# The endpoint name idempotent_guard scopes the (user, key) cache to. A
# constant, not a parameter, because there is exactly one call site.
_IDEMPOTENCY_ENDPOINT = "daraja.stk-push"


def config_for(db: Session, *, department_id: Optional[int] = None) -> MpesaConfig:
    """The till that should take this payment.

    Resolution order: the department's own active row when one exists,
    otherwise the hospital-wide default (department_id IS NULL), otherwise
    the "not configured" error. Every STK/query/settlement path that needs
    a MpesaConfig must call this, not query MpesaConfig directly, so a
    later change to how a config is chosen only has to change here.

    An INACTIVE department row falls back to the default rather than
    raising: a department that switches its till off should keep
    collecting through the hospital till, not stop collecting.
    """
    if department_id is not None:
        dept_config = (
            db.query(MpesaConfig)
            .filter(
                MpesaConfig.department_id == department_id,
                MpesaConfig.is_active == True,  # noqa: E712
            )
            .first()
        )
        if dept_config:
            return dept_config

    default_config = (
        db.query(MpesaConfig)
        .filter(
            MpesaConfig.department_id.is_(None),
            MpesaConfig.is_active == True,  # noqa: E712
        )
        .first()
    )
    if default_config:
        return default_config

    raise HTTPException(
        status_code=400,
        detail="M-Pesa is not configured for this hospital. Set it up under Settings -> M-Pesa.",
    )


def _find_pending(
    db: Session, *, invoice_id: Optional[int], dispense_id: Optional[int]
) -> Optional[MpesaTransaction]:
    """The live Pending row (if any) blocking a reservation for this
    invoice/dispense. At most one can exist by construction of the partial
    unique index this function's caller is reacting to."""
    query = db.query(MpesaTransaction).filter(MpesaTransaction.status == "Pending")
    if invoice_id is not None:
        query = query.filter(MpesaTransaction.invoice_id == invoice_id)
    elif dispense_id is not None:
        query = query.filter(MpesaTransaction.dispense_id == dispense_id)
    else:
        return None
    return query.first()


def _is_stale(txn: MpesaTransaction) -> bool:
    started = txn.transaction_date
    if started is None:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started) > _STALE_PENDING_TIMEOUT


def _reserve_pending(
    db: Session,
    *,
    invoice_id: Optional[int],
    dispense_id: Optional[int],
    phone_number: str,
    charged_amount: Decimal,
    external_reference: str,
    bill_ref_number: str,
    config: MpesaConfig,
) -> tuple[MpesaTransaction, bool]:
    """Reserve the one Pending slot for this invoice/dispense.

    Insert-and-catch, never check-then-insert: a check-then-insert has a gap
    between the check and the insert, which is the precise race this exists
    to close. The partial unique index on mpesa_transactions is what
    actually enforces "at most one Pending row per invoice/dispense" across
    every worker and every terminal; this function only reacts to it.

    Returns (txn, reserved). reserved=True means the caller owns a fresh
    Pending row and should go ahead and push to Daraja. reserved=False means
    a DIFFERENT, still-live Pending transaction already exists for this
    invoice/dispense: txn is that transaction, and the caller must not push
    a second prompt to the patient's handset.

    A stale existing Pending row (older than _STALE_PENDING_TIMEOUT) is
    marked Expired, in the same transaction as the new reservation, so a
    genuine retry of a dead prompt is not blocked forever. Expired is not
    Success or Failed: this function never guesses at the old push's real
    outcome, it only frees the slot. Both changes commit together, or not
    at all.
    """
    for _ in range(2):
        txn = MpesaTransaction(
            invoice_id=invoice_id,
            dispense_id=dispense_id,
            phone_number=phone_number,
            amount=charged_amount,
            external_reference=external_reference,
            status="Pending",
            transaction_type="STK",
            bill_ref_number=bill_ref_number,
            mpesa_config_id=config.id,
        )
        try:
            with db.begin_nested():
                db.add(txn)
                db.flush()
        except IntegrityError:
            existing = _find_pending(db, invoice_id=invoice_id, dispense_id=dispense_id)
            if existing is not None and _is_stale(existing):
                existing.status = "Expired"
                existing.result_desc = (
                    "Superseded by a retry after the on-handset window elapsed. "
                    "The original push's outcome, if any, is reconciled "
                    "independently against Safaricom, not assumed here."
                )
                db.flush()
                continue
            return existing, False
        else:
            # Commit NOW, before the slow Daraja network call, so a second
            # terminal hitting the same invoice/dispense gets an immediate
            # constraint violation instead of blocking on our uncommitted
            # row for however long Safaricom takes to answer.
            db.commit()
            return txn, True

    # Pathological: contention outlasted the retry budget. Surface whatever
    # is there rather than raising a bare 500.
    existing = _find_pending(db, invoice_id=invoice_id, dispense_id=dispense_id)
    return existing, False


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


def _pending_conflict_response(txn: MpesaTransaction) -> dict:
    """The response handed to a second terminal that lost the reservation
    race: the existing prompt's details, not an error, and no new prompt is
    sent to the patient's handset."""
    return {
        "checkout_request_id": txn.checkout_request_id,
        "merchant_request_id": txn.merchant_request_id,
        "external_reference": txn.external_reference,
        "transaction_id": txn.id,
        "amount_charged": txn.amount,
        "already_pending": True,
    }


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
    user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """Push an STK prompt to `phone_number` and persist a Pending transaction.

    Two different races are guarded here, and they are not the same problem:

    Problem A, the same action submitted twice by one cashier (a double
    click, a retried request after a dropped response): guarded by the
    EXISTING idempotency mechanism (app/core/idempotency.py), scoped to
    (user_id, endpoint, key). Pass `user_id` and `idempotency_key` to use
    it; a repeated key with the same body returns the first response
    without pushing a second prompt, and the same key with a different
    body raises 409.

    Problem B, two different cashiers on two different terminals both
    pushing for the same invoice or dispense: no per-user key catches
    this. Guarded by a partial unique index in Postgres (at most one
    Pending row per invoice, and per dispense) via _reserve_pending, which
    inserts and catches the conflict rather than checking then inserting.
    A second terminal that loses this race gets the existing prompt back,
    not an error, and never causes a second prompt on the patient's handset.

    The Pending row for a fresh push is committed before the Daraja call is
    made (see _reserve_pending), so a callback arriving before this
    function returns still finds a row, and so a concurrent second terminal
    gets an immediate constraint violation instead of blocking on our
    uncommitted row for however long Safaricom takes to answer.

    `department_id` is forwarded to config_for; see that function's
    docstring for the resolution order.
    """
    persist = None
    if idempotency_key:
        if user_id is None:
            raise HTTPException(
                status_code=400,
                detail="user_id is required when using an idempotency key.",
            )
        body = {
            "phone_number": phone_number,
            "amount": str(amount),
            "invoice_id": invoice_id,
            "dispense_id": dispense_id,
            "department_id": department_id,
            "account_reference": account_reference,
            "transaction_desc": transaction_desc,
        }
        cached, persist = idempotent_guard(
            db, user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT, key=idempotency_key, body=body,
        )
        if cached is not None:
            return cached

    config = config_for(db, department_id=department_id)
    try:
        msisdn = normalize_msisdn(phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    amount_decimal = Decimal(str(amount))
    if amount_decimal <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    # Round UP to the whole shilling once, here. This is the ONLY figure
    # that ever gets quoted to Daraja or persisted: see the module
    # docstring for why rounding up, and why the two must never diverge.
    charged_amount = amount_decimal.quantize(Decimal("1"), rounding=ROUND_CEILING)

    ref = (account_reference or config.account_reference or "HMS-BILLING")
    ref = ref[:_ACCOUNT_REFERENCE_MAX]

    if invoice_id:
        external_reference = f"INV-{invoice_id}-{secrets.token_hex(4)}"
    elif dispense_id:
        external_reference = f"RX-{dispense_id}-{secrets.token_hex(4)}"
    else:
        external_reference = f"TEST-{secrets.token_hex(6)}"

    # Problem B: reserve the slot BEFORE calling Daraja. If this is a
    # duplicate, stop here, no second prompt is ever sent.
    txn, reserved = _reserve_pending(
        db,
        invoice_id=invoice_id,
        dispense_id=dispense_id,
        phone_number=msisdn,
        charged_amount=charged_amount,
        external_reference=external_reference,
        bill_ref_number=ref,
        config=config,
    )
    if not reserved:
        if txn is None:
            raise HTTPException(
                status_code=409,
                detail="Could not reserve a payment slot for this invoice. Try again shortly.",
            )
        result = _pending_conflict_response(txn)
        if persist:
            persist(result, status=200)
        db.commit()
        return result

    # From here on this call owns the reserved Pending row. Any failure
    # below marks it Failed (a real, known outcome) rather than leaving it
    # Pending forever for a push that never even reached Daraja.
    try:
        passkey = _decrypted(config.passkey_encrypted, field="passkey")
        timestamp = daraja_timestamp()
        password = stk_password(config.shortcode, passkey, timestamp)
        callback_url = _callback_url(config, callback_tenant)
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
            "Amount": int(charged_amount),  # already whole shillings, rounded up above
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
        logger.warning("Daraja STK push failed: %s", safe_repr(str(exc)))
        txn.status = "Failed"
        txn.result_desc = "Could not reach M-Pesa."
        db.commit()
        raise HTTPException(status_code=502, detail="Could not reach M-Pesa. Try again shortly.")
    except HTTPException:
        txn.status = "Failed"
        db.commit()
        raise

    checkout_request_id = data.get("CheckoutRequestID")
    merchant_request_id = data.get("MerchantRequestID")
    if not checkout_request_id:
        logger.warning("Daraja STK push returned no CheckoutRequestID: %s", safe_repr(data))
        txn.status = "Failed"
        txn.result_desc = data.get("ResponseDescription") or "M-Pesa did not accept the request."
        db.commit()
        raise HTTPException(status_code=502, detail=txn.result_desc)

    txn.checkout_request_id = checkout_request_id
    txn.merchant_request_id = merchant_request_id

    result = {
        "checkout_request_id": checkout_request_id,
        "merchant_request_id": merchant_request_id,
        "external_reference": external_reference,
        "transaction_id": txn.id,
        # The actually-charged, rounded-up figure, so a caller (the cashier's
        # UI) can show the patient what will really be prompted rather than
        # the pre-rounding amount it asked for.
        "amount_charged": charged_amount,
    }
    if persist:
        persist(result, status=200)
    db.commit()
    return result


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
