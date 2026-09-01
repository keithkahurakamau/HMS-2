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
from decimal import ROUND_CEILING, Decimal
from types import SimpleNamespace
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.idempotency import idempotent_guard, persist_and_commit
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

# The endpoint name idempotent_guard scopes the (user, key) cache to. A
# constant, not a parameter, because there is exactly one call site.
_IDEMPOTENCY_ENDPOINT = "daraja.stk-push"

# The two partial unique indexes _reserve_pending is reacting to. Any OTHER
# IntegrityError (an unknown invoice_id violating the FK, a NOT NULL slip,
# a totally unrelated constraint) must never be silently treated as "someone
# else already has this slot": that swallows a real bug behind a 409 that
# can never succeed on retry. See _reserve_pending.
_PENDING_GUARD_CONSTRAINTS = frozenset({
    "uq_mpesa_txn_one_pending_per_invoice",
    "uq_mpesa_txn_one_pending_per_dispense",
})


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

    Caveat this does NOT cover: deactivating a department's config does
    not retroactively help a push already sent from it. Each config's
    callback is authenticated by that config's OWN token, and
    app/core/daraja_callback.py's _lookup_token_in_tenant requires
    is_active=True on the matching row; it never falls back to the
    hospital default the way config_for does. So a prompt already on a
    patient's handset, sent from a till that is deactivated before the
    callback arrives, has its callback rejected as unauthenticated, not
    routed to the default. This function's fallback only ever applies to a
    NEW push, never to settling one already in flight.
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
    unique index this function's caller is reacting to.

    Matches on invoice_id OR dispense_id, not just whichever is checked
    first: a row carrying both is blocked by either partial index, and a
    conflict on one must still be found by a caller that only supplied
    the other.
    """
    conditions = []
    if invoice_id is not None:
        conditions.append(MpesaTransaction.invoice_id == invoice_id)
    if dispense_id is not None:
        conditions.append(MpesaTransaction.dispense_id == dispense_id)
    if not conditions:
        return None
    return (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.status == "Pending")
        .filter(or_(*conditions))
        .first()
    )


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
) -> tuple[Optional[MpesaTransaction], bool]:
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

    There is deliberately NO local staleness timer here any more. An
    earlier version aged a Pending row out to a manufactured "Expired"
    status so a retry was never blocked; that is a guess about the
    original push's outcome, and apply_stk_callback only ever matches
    status == "Pending", so a late genuine success callback for an
    "Expired" row fell into the unrecognised branch and settled nothing:
    money reached the till and the invoice was never credited. A stale
    Pending now correctly BLOCKS a retry (the caller is told a prompt is
    already on its way, which is true) until Task 8's reconciliation job
    resolves it by asking Safaricom via STK Query, never by guessing here.

    CONTRACT the caller must know: when this returns reserved=True, it has
    ALREADY COMMITTED `db` (see the comment at that call site for why:
    responsiveness against a second terminal, not correctness of the guard
    itself), ending whatever transaction was open when this was called,
    including releasing any Postgres advisory lock taken inside it. The
    caller resumes in a new transaction. When it returns reserved=False,
    no commit happens: the only DB effect was an insert attempt rolled
    back to a SAVEPOINT, so the caller's transaction (and any lock it
    holds) is untouched.

    Only the two partial unique indexes this guard owns are treated as
    "someone else already has this slot". Any other IntegrityError (an
    unknown invoice_id violating its FK, for example) is re-raised: a 409
    "try again" for a request that can never succeed is worse than the raw
    error.
    """
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
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint not in _PENDING_GUARD_CONSTRAINTS:
            raise
        existing = _find_pending(db, invoice_id=invoice_id, dispense_id=dispense_id)
        return existing, False
    else:
        # Commit NOW, before the slow Daraja network call, so a second
        # terminal hitting the same invoice/dispense gets an immediate
        # constraint violation instead of blocking on our uncommitted
        # row for however long Safaricom takes to answer.
        db.commit()
        return txn, True


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


def _finalize(
    db: Session,
    result: dict,
    *,
    persist,
    user_id: Optional[int],
    idempotency_key: Optional[str],
    idempotency_body: Optional[dict],
) -> dict:
    """Persist `result` into the idempotency cache (if `persist` is set)
    and commit.

    _reserve_pending's own commit (see its docstring) ends the transaction
    idempotent_guard took its Postgres advisory lock in, on purpose, so a
    second terminal is not blocked for the whole Daraja round trip. Two
    callers racing on the SAME (user_id, endpoint, key) can therefore both
    reach here; app.core.idempotency.persist_and_commit is what makes that
    survivable (see its own docstring): the loser rolls back its own INSERT
    and replays idempotent_guard for the winner's now-committed response
    instead of surfacing an uncaught IntegrityError, so both terminals see
    the SAME answer.
    """
    if persist is None:
        db.commit()
        return result
    return persist_and_commit(
        db, persist, result, status=200,
        user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT,
        key=idempotency_key, body=idempotency_body,
    )


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
    body raises 409. For a push with NEITHER invoice_id nor dispense_id,
    the guard is checked a SECOND time too, right before the Daraja call:
    see the comment at that call site, below, for why one check is not
    enough there and why the second check must NOT run for an invoice or
    dispense push.

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
    uncommitted row for however long Safaricom takes to answer. That early
    commit also means a stale Pending row (its handset prompt long dead) is
    NOT expired or superseded here: doing that locally would be a guess
    about the original push's outcome, and this module never guesses about
    money. A stale row correctly blocks a retry, and the retrying cashier
    is told a prompt is already on its way, which is true, until Task 8's
    reconciliation job resolves it by asking Safaricom directly.

    `department_id` is forwarded to config_for; see that function's
    docstring for the resolution order.
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
            "phone_number": phone_number,
            "amount": str(amount),
            "invoice_id": invoice_id,
            "dispense_id": dispense_id,
            "department_id": department_id,
            "account_reference": account_reference,
            "transaction_desc": transaction_desc,
        }
        cached, persist = idempotent_guard(
            db, user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT, key=idempotency_key,
            body=idempotency_body,
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
        return _finalize(
            db, result, persist=persist, user_id=user_id,
            idempotency_key=idempotency_key, idempotency_body=idempotency_body,
        )

    # Second idempotency check, right before the network call, ONLY when
    # there is neither an invoice_id nor a dispense_id. The FIRST check
    # (above, before _reserve_pending) cannot protect THIS push:
    # _reserve_pending's own commit already ended that check's transaction
    # and released its advisory lock. With an invoice_id or dispense_id
    # that gap is already closed by the partial unique index (every OTHER
    # caller fails its OWN reservation and never reaches this line), so a
    # second check there would be worse than useless: it would race the
    # `not reserved` branch's own cache write and could wrongly treat the
    # caller that actually holds the reservation as the loser, skipping
    # the real push. Without either id there is no such index, so two
    # callers sharing a key can both reserve their OWN row and both arrive
    # here with reserved=True; re-acquiring the SAME lock here, with no
    # commit before the eventual persist below, closes THAT gap: a
    # concurrent loser blocks until the winner's push and cache write are
    # done, then replays the winner's response instead of its own prompt.
    if idempotency_key is not None and invoice_id is None and dispense_id is None:
        try:
            cached, persist = idempotent_guard(
                db, user_id=user_id, endpoint=_IDEMPOTENCY_ENDPOINT, key=idempotency_key,
                body=idempotency_body,
            )
        except HTTPException:
            # A concurrent caller reused this same key with a genuinely
            # DIFFERENT body: idempotent_guard raises 409 for that, and it
            # must still reach this caller, unswallowed, because a reused
            # key with a different body is a programmer error or an attack.
            # But _reserve_pending already committed THIS row above, so
            # without marking it here it is left status="Pending" with
            # checkout_request_id=None forever: no prompt was ever sent for
            # it, so Task 8's reconciliation job (which needs a
            # checkout_request_id to ask Safaricom via STK Query) has
            # nothing to resolve it with, and it becomes a permanent phantom
            # in the transaction log and every pending-transactions report.
            txn.status = "Failed"
            txn.result_desc = (
                "No prompt was sent from this row: its idempotency key was "
                "reused, concurrently, with a different request body, which "
                "is rejected as a conflict (409) rather than replayed."
            )
            db.commit()
            raise
        if cached is not None:
            # This row was reserved but never pushed: a concurrent request
            # with the same key won the race and its response is being
            # replayed instead. Marking it Failed is a documented fact,
            # not a guess about a push that never happened.
            txn.status = "Failed"
            txn.result_desc = (
                "Superseded by a concurrent request with the same idempotency "
                "key that reached M-Pesa first. No prompt was sent from this row."
            )
            db.commit()
            return cached

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
    return _finalize(
        db, result, persist=persist, user_id=user_id,
        idempotency_key=idempotency_key, idempotency_body=idempotency_body,
    )


def _config_for_query(db: Session, *, checkout_request_id: str) -> MpesaConfig:
    """The exact till a given CheckoutRequestID was pushed from.

    Daraja signs STK Query with the SAME shortcode/passkey the original
    push used. Falling back to config_for's hospital default here (as an
    earlier version did unconditionally) is wrong whenever the push came
    from a department till: the signature Daraja expects is the
    department's, not the default's, and the query fails. The
    transaction's own mpesa_config_id (set at push time) is the source of
    truth for which till that was; config_for's fallback is used only when
    there is no transaction row to ask (or it predates mpesa_config_id
    being recorded), matching this function's pre-existing behaviour for
    that case.
    """
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == checkout_request_id)
        .first()
    )
    if txn is not None and txn.mpesa_config_id is not None:
        config = db.query(MpesaConfig).filter(MpesaConfig.id == txn.mpesa_config_id).first()
        if config is not None:
            return config
    return config_for(db)


def query_stk(db: Session, *, checkout_request_id: str) -> dict:
    """Poll Daraja for the current state of a previously-initiated STK push.

    Returns Daraja's raw response. This does not itself settle anything:
    settlement only ever happens through apply_stk_callback's cross-checked
    path, whether it is reached via the callback or via a reconciliation job
    that calls this and then routes the result through the same checks.
    """
    if not checkout_request_id:
        raise HTTPException(status_code=400, detail="checkout_request_id is required")

    config = _config_for_query(db, checkout_request_id=checkout_request_id)
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
