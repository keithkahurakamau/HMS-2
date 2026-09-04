"""Transaction Status and Account Balance, the two Daraja queries that answer
"what actually happened" rather than initiate something new.

**Both are genuinely asynchronous.** This was gotten wrong in an earlier
version of this module: it treated the synchronous response to
POST /mpesa/transactionstatus/v1/query as the verdict on whether a receipt
was real. It is not. That response only acknowledges the query was queued
and hands back a ConversationID; the actual answer, whether Safaricom knows
the receipt and what amount it reports, arrives later, at a separate
ResultURL callback. Treating the acknowledgment as the verdict verifies
nothing at all: a forged confirmation would sail through it every time,
since nothing in the acknowledgment even mentions the receipt's outcome.

So this module's job is split in two, matching Safaricom's own split:

  - query_transaction_status fires the query and returns the acknowledgment
    (ConversationID, OriginatorConversationID). It decides nothing.
  - handle_transaction_status_result (below) is the actual verdict: it
    receives Safaricom's later callback, correlates it back to the row that
    asked (by ConversationID), and is the ONLY place that decides settle,
    quarantine, or leave unverified. If no result ever arrives, the row
    stays Unverified forever rather than being resolved by a local guess:
    the exact same lesson that removed a local expiry timer from the STK
    reservation path (see reservation.py) for the same reason, silent money
    loss from a guessed outcome.

Account Balance is asynchronous the same way, and this module does not even
attempt the two-step split for it: no result-callback handler exists for
Account Balance in this codebase yet, on either endpoint family. See
account_balance's own docstring for what that means for its return value.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Union
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.services.daraja.c2b_match import match_c2b_invoice
from app.services.daraja.client import DarajaClient, DarajaError
from app.services.daraja.credentials import security_credential
from app.services.daraja.reservation import config_for
from app.services.daraja.settlement import (
    SettlementExceedsBalance, _notify_quarantine, settle_invoice_match,
)
from app.utils.encryption import decrypt_data
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

_IDENTIFIER_TYPE_SHORTCODE = "4"


def _decrypted(value: Optional[str], *, field: str) -> str:
    """Shared with c2b.py: decrypt a config secret, or raise a clear 400
    instead of letting a missing credential surface as an opaque failure
    deep inside a Daraja call."""
    plain = decrypt_data(value) if value else None
    if not plain:
        raise HTTPException(
            status_code=400,
            detail=f"M-Pesa {field} is not configured for this hospital.",
        )
    return plain


def _daraja_client(config: MpesaConfig) -> DarajaClient:
    """Build the DarajaClient for `config`. Ported verbatim from stk.py's
    helper of the same name and purpose (not imported from there: stk.py
    should not become a dependency of every other Daraja module just to
    reuse six lines, and this file needs it for Transaction Status and
    Account Balance the same way stk.py needs it for STK push and query)."""
    creds = SimpleNamespace(
        consumer_key=_decrypted(config.consumer_key_encrypted, field="consumer key"),
        consumer_secret=_decrypted(config.consumer_secret_encrypted, field="consumer secret"),
        environment=config.environment,
        shortcode=config.shortcode,
    )
    return DarajaClient(creds)


def _initiator_credentials(config: MpesaConfig) -> tuple[str, str]:
    """(Initiator, SecurityCredential) for a B2C-style command. Transaction
    Status and Account Balance both authenticate as an API operator the same
    way B2C does, not as the OAuth consumer key/secret alone."""
    if not config.initiator_name:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa initiator name is not configured for this hospital.",
        )
    initiator_password = _decrypted(
        config.initiator_password_encrypted, field="initiator password"
    )
    credential = security_credential(initiator_password, config.environment)
    return config.initiator_name, credential


def _base_hint_token(config: MpesaConfig, callback_tenant: Optional[str]) -> tuple[str, str, str]:
    """(base_url, quoted_tenant_hint, quoted_token) shared by every URL this
    module and c2b.py build. Same validation as stk.py's _callback_url: fail
    loudly on missing configuration rather than send Safaricom a broken URL.
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
    return base, hint, quote(token, safe="")


def _flow_urls(
    config: MpesaConfig, callback_tenant: Optional[str], *, flow: str
) -> tuple[str, str]:
    """(ResultURL, QueueTimeOutURL) for an async Daraja command. `flow` is a
    path segment ("status" or "balance"), not a shortcode or receipt, so it
    never needs redaction the way a token does."""
    base, hint, token = _base_hint_token(config, callback_tenant)
    result_url = f"{base}/api/payments/mpesa/{flow}/result/{hint}/{token}"
    timeout_url = f"{base}/api/payments/mpesa/{flow}/timeout/{hint}/{token}"
    return result_url, timeout_url


def _config_for_receipt(db: Session, *, receipt: str) -> MpesaConfig:
    """The till that took `receipt`, so Transaction Status is signed with the
    same shortcode/credentials the payment actually landed on. Falls back to
    config_for's hospital default only when there is no transaction row yet
    to ask (handle_confirmation sets mpesa_config_id and flushes the row
    before firing this query) or it predates mpesa_config_id."""
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.receipt_number == receipt)
        .first()
    )
    if txn is not None and txn.mpesa_config_id is not None:
        config = db.query(MpesaConfig).filter(MpesaConfig.id == txn.mpesa_config_id).first()
        if config is not None:
            return config
    return config_for(db)


def query_transaction_status(
    db: Session,
    *,
    receipt: Optional[str] = None,
    original_conversation_id: Optional[str] = None,
    config: Optional[MpesaConfig] = None,
    callback_tenant: Optional[str] = None,
) -> dict:
    """Fire a Transaction Status query and return Safaricom's acknowledgment
    (OriginatorConversationID, ConversationID, ResponseDescription). This is
    NOT the verdict: see the module docstring. The caller stores the ids so
    the later result callback can be correlated back to whatever it asked
    on behalf of; nothing here decides verified, matched, or settled.

    Two ways to identify the transaction being asked about, exactly one of
    which is required, because Daraja's TransactionStatusQuery accepts
    either:

      * `receipt`: the M-Pesa TransactionID, when one exists (the C2B
        confirmation path: a receipt already arrived, and this asks
        Safaricom to corroborate it). `config` is resolved from the
        receipt via `_config_for_receipt` when not supplied.
      * `original_conversation_id`: Safaricom's own id for an instruction
        it already accepted, for a payment that has NOT produced a receipt
        yet (a Processing B2C refund: see reconcile_queries.py's
        requery_refund). `config` is REQUIRED in this case: there is no
        receipt to resolve one from, so the caller (which already knows
        which till the underlying instruction was signed with) must pass
        it explicitly.
    """
    if not receipt and not original_conversation_id:
        raise HTTPException(
            status_code=400, detail="receipt or original_conversation_id is required",
        )

    if config is None:
        if not receipt:
            raise HTTPException(
                status_code=400,
                detail="config is required when querying by original_conversation_id alone",
            )
        config = _config_for_receipt(db, receipt=receipt)

    initiator, credential = _initiator_credentials(config)
    result_url, timeout_url = _flow_urls(config, callback_tenant, flow="status")

    payload = {
        "Initiator": initiator,
        "SecurityCredential": credential,
        "CommandID": "TransactionStatusQuery",
        # Daraja accepts either identifier; TransactionID is set to "" (not
        # omitted) when only original_conversation_id is known, matching
        # the shape Safaricom's own documentation uses for this case.
        "TransactionID": receipt or "",
        "PartyA": config.shortcode,
        "IdentifierType": _IDENTIFIER_TYPE_SHORTCODE,
        "ResultURL": result_url,
        "QueueTimeOutURL": timeout_url,
        "Remarks": "C2B receipt verification" if receipt else "B2C refund status verification",
        "Occasion": "C2B verification" if receipt else "B2C refund verification",
    }
    if original_conversation_id:
        payload["OriginalConversationID"] = original_conversation_id

    client = _daraja_client(config)
    try:
        return client.post("/mpesa/transactionstatus/v1/query", payload)
    except DarajaError as exc:
        logger.warning("Daraja Transaction Status query failed: %s", safe_repr(str(exc)))
        raise


def _result_parameters(result: dict) -> dict:
    """Flatten Safaricom's Result.ResultParameters.ResultParameter list (the
    same shape B2C and Transaction Status results both use) into a plain
    {Key: Value} dict. Shared here rather than duplicated in c2b.py because
    a future B2C result handler (Task 7) will need the identical shape."""
    items = ((result.get("ResultParameters") or {}).get("ResultParameter")) or []
    return {
        item.get("Key"): item.get("Value")
        for item in items
        if isinstance(item, dict) and item.get("Key")
    }


# ─── Transaction Status result (the actual verdict) ─────────────────────────


def handle_transaction_status_result(
    db: Session, payload: dict,
) -> Optional[Union[MpesaTransaction, MpesaRefund]]:
    """Apply Safaricom's asynchronous Transaction Status result: the real
    verdict on a C2B receipt, arriving separately from (and generally much
    later than) the acknowledgment query_transaction_status received when
    handle_confirmation fired the query. This IS the third defence C2B
    relies on, since the confirmation itself carried no anchor to check
    against; nothing here is guessed.

    Correlated by ConversationID against a row THIS tenant created and is
    still waiting on (status == "Unverified"). A ConversationID matching no
    such row, whether a forged value, one for another deployment, or a
    repeat delivery of a result already applied, is ignored, never acted
    on: Safaricom retries deliveries the same way it does for every other
    callback, and a second delivery of an already-settled result must not
    settle twice or overturn a decision already made.

    Amount comparison is the whole point: matching settles via the existing
    settle_invoice_match, exactly as any other verified receipt would.
    A mismatch quarantines and notifies, and settles nothing: Safaricom's
    own Transaction Status disagreeing with what the confirmation claimed is
    precisely the forged-or-malformed-callback shape this flow exists to
    catch.

    A ConversationID matching no MpesaTransaction is also checked against
    MpesaRefund.status_query_conversation_id before giving up: reconciliation
    (reconcile_queries.py's requery_refund) fires this same query, by the
    same command, for a refund stuck Processing, using its own dedicated
    correlation column so it can never collide with (or overwrite) the B2C
    dispatch's own conversation_id. That branch, handled in
    refund_status.handle_transaction_status_result_for_refund (imported
    lazily here to avoid a circular import: that module imports FROM
    b2c.py, which already imports several helpers FROM this module),
    records what Safaricom reported and notifies a human. It never writes
    Completed, Failed, or Reversed: only a human, reading Safaricom's own
    verdict, may authorise what happens next to money already in flight.
    """
    result = (payload or {}).get("Result") or {}
    conversation_id = result.get("ConversationID")
    if not conversation_id:
        logger.warning("Transaction Status result missing ConversationID; ignored")
        return None

    txn = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.conversation_id == conversation_id,
            MpesaTransaction.status == "Unverified",
        )
        .first()
    )
    if txn is None:
        refund = (
            db.query(MpesaRefund)
            .filter(MpesaRefund.status_query_conversation_id == conversation_id)
            .first()
        )
        if refund is not None:
            from app.services.daraja.refund_status import (
                handle_transaction_status_result_for_refund,
            )
            return handle_transaction_status_result_for_refund(db, refund, result)

        logger.warning(
            "Transaction Status result for an unrecognised or "
            "already-resolved ConversationID; ignored"
        )
        return None

    # Serialise concurrent deliveries of this exact result before acting on
    # it, the same discipline apply_stk_callback and handle_confirmation
    # both use: without it, two near-simultaneous deliveries could both
    # observe status == "Unverified" and both try to settle.
    lock_id = int(hashlib.sha1(conversation_id.encode("utf-8")).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        # Re-check inside the lock: a concurrent delivery could have
        # resolved this row between the query above and the lock being
        # granted.
        db.refresh(txn)
        if txn.status != "Unverified":
            db.commit()
            return txn

        result_code = result.get("ResultCode")
        if str(result_code) != "0":
            # Safaricom itself does not confirm this receipt (not found, or
            # an error on Safaricom's side). This is the same resting state
            # as no result ever arriving: stays Unverified, not a rejection
            # to act on.
            txn.result_desc = str(result.get("ResultDesc") or "")[:255]
            db.commit()
            return txn

        params = _result_parameters(result)

        # C1 (and I3's TransactionStatus, same reasoning): Safaricom's key
        # names for these fields are not settled between documentation
        # sources (Amount vs TransactionAmount, ReceiptNo vs
        # TransactionReceipt); public sources disagree and the authoritative
        # docs need a login this task cannot obtain. Reading only one
        # spelling risks EVERY genuine result missing the field, quarantining
        # every real payment. Read whichever spelling is present for each.
        # No source contradicts "TransactionStatus" the way sources
        # contradict Amount/Receipt, so this is a consistency measure rather
        # than a known defect: a bare "Status" is tolerated as a plausible
        # alternate, not assumed impossible.
        reported_receipt = params.get("TransactionReceipt")
        if reported_receipt is None:
            reported_receipt = params.get("ReceiptNo")
        raw_amount = params.get("TransactionAmount")
        if raw_amount is None:
            raw_amount = params.get("Amount")
        transaction_status = params.get("TransactionStatus")
        if transaction_status is None:
            transaction_status = params.get("Status")

        if reported_receipt is None or raw_amount is None or transaction_status is None:
            # At least one field was not found under any spelling checked.
            # This is not "the value is wrong", it is "we could not find it
            # at all": treating an ABSENT TransactionStatus the same as a
            # genuinely-not-Completed one would produce the identical
            # quarantine message for two different facts (a missing key
            # versus a real Reversed/Failed transaction), which is exactly
            # the kind of thing that misdiagnoses the first real sandbox
            # delivery. Naming the keys that actually arrived turns that
            # into a one-line answer instead of a mystery.
            missing = []
            if reported_receipt is None:
                missing.append("receipt (checked TransactionReceipt, ReceiptNo)")
            if raw_amount is None:
                missing.append("amount (checked TransactionAmount, Amount)")
            if transaction_status is None:
                missing.append("status (checked TransactionStatus, Status)")
            keys_present = sorted(params.keys())
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status result missing {' and '.join(missing)}; "
                f"keys present: {keys_present}"
            )[:255]
            logger.error(
                "C2B Transaction Status result for receipt %s missing expected "
                "field(s) (%s); keys present: %s",
                safe_repr(txn.receipt_number), " and ".join(missing), keys_present,
            )
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        # I2: correlate on the receipt too, not ConversationID alone.
        # conversation_id carries no unique constraint, so if two rows ever
        # shared one, settling purely by ConversationID would apply
        # Safaricom's answer to whichever row Postgres happened to return
        # first, posting real money against a different patient's invoice.
        # The receipt this query answers must be the exact one this row
        # recorded at confirmation time.
        if reported_receipt != txn.receipt_number:
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported receipt {reported_receipt}, "
                f"this row recorded {txn.receipt_number}"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        # I3: ResultCode 0 only means the QUERY succeeded, not that the
        # transaction itself did. The transaction's own outcome lives in
        # TransactionStatus. A receipt Safaricom knows about but marks
        # Failed or Reversed must never settle just because the query
        # worked; anything other than Completed is quarantined, the same
        # as a disagreeing amount, because a "successful-looking" query
        # result for a transaction Safaricom itself did not complete is
        # exactly the kind of thing a human needs to see, not silently
        # leave Unverified. This only runs once the field is known to be
        # PRESENT (see the missing-field check above): an absent
        # TransactionStatus is a different fact from a present one that
        # says something other than Completed, and must never produce this
        # same message.
        if transaction_status != "Completed":
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported status {transaction_status!r}, not Completed"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        try:
            reported_amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            txn.status = "Quarantined"
            txn.result_desc = f"Transaction Status reported an unparseable amount: {raw_amount!r}"[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        expected_amount = Decimal(str(txn.amount or 0))
        if reported_amount != expected_amount:
            # THE cross-check. Safaricom's own Transaction Status disagrees
            # with the amount the confirmation claimed: settle nothing,
            # quarantine, tell a human.
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported KES {reported_amount}, "
                f"confirmation claimed KES {expected_amount}"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        txn.verified_at = datetime.now(timezone.utc)
        txn.verification_source = "transaction_status"

        invoice, match_basis = match_c2b_invoice(
            db, bill_ref_number=txn.bill_ref_number, msisdn=txn.phone_number,
        )
        if invoice is None:
            txn.status = "Unmatched"
            txn.match_basis = "unmatched"
            db.commit()
            return txn

        # populate_existing() is not optional here, for the identical
        # reason it is required in app/services/daraja/b2c.py's
        # _lock_refund: match_c2b_invoice loaded this same Invoice into
        # the session a few statements above with no intervening commit,
        # so a plain query would return that already-identity-mapped
        # object WITHOUT overwriting its attributes from the row this
        # FOR UPDATE query just locked. settle_invoice_match then adds to
        # amount_paid read off that stale, pre-lock value: two
        # verifications settling different receipts against the same
        # invoice concurrently would have the second discard the first's
        # credit, under-crediting a patient for money they already paid.
        invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_id == invoice.invoice_id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        try:
            settle_invoice_match(db, invoice=invoice, txn=txn, match_basis=match_basis)
        except SettlementExceedsBalance as exc:
            txn.status = "Quarantined"
            txn.result_desc = str(exc)[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        txn.status = "Success"
        # ONE commit for the whole verified-and-matched unit, same reasoning
        # as apply_stk_callback: if settle_invoice_match raises, nothing
        # above persists, so the row is retryable rather than stuck
        # half-applied.
        db.commit()
        return txn
    except Exception:
        db.rollback()
        raise


def handle_transaction_status_timeout(
    db: Session, payload: dict,
) -> Optional[Union[MpesaTransaction, MpesaRefund]]:
    """Acknowledge a Transaction Status timeout. Decides NOTHING about
    whether the underlying payment is real: a timeout means Safaricom gave
    up waiting on THIS QUERY, not that the money is not real. Never marks
    a row settled, quarantined, matched, Completed, or Failed here, for
    the same reason a local expiry timer was removed from the STK
    reservation path (reservation.py): a guessed outcome here is how a
    real payment goes missing silently.

    It DOES clear the correlation id this specific query was waiting on
    (MpesaTransaction.conversation_id, or MpesaRefund.status_query_conversation_id),
    which is the one thing a timeout genuinely proves: Safaricom will never
    answer THIS id. Leaving it in place would permanently satisfy
    reconcile_queries.py's own "a query is outstanding, do not re-ask"
    guard (see requery_c2b and requery_refund), silently converting "ask
    again later" into "never ask again", the exact one-way door
    status.py's own module docstring promises reconciliation will not be:
    "A human resolves it from the unmatched queue, or a future
    reconciliation job re-fires the query." Clearing the dead id is what
    makes that second option possible; nothing here decides anything about
    the payment or refund itself.
    """
    result = (payload or {}).get("Result") or {}
    conversation_id = result.get("ConversationID")
    if not conversation_id:
        logger.warning("Transaction Status timeout missing ConversationID; ignored")
        # This function never writes, but the query above still opened a
        # transaction on this session (any SELECT does under Postgres's
        # default isolation), and nothing else here will ever end it.
        # Commit rather than leave the caller holding an idle-in-transaction
        # session.
        db.commit()
        return None

    txn = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.conversation_id == conversation_id,
            MpesaTransaction.status == "Unverified",
        )
        .first()
    )
    if txn is not None:
        logger.info(
            "Transaction Status query timed out for MpesaTransaction %s; left "
            "Unverified, dead conversation_id cleared so reconciliation can "
            "re-ask.", txn.id,
        )
        txn.conversation_id = None
        db.commit()
        return txn

    refund = (
        db.query(MpesaRefund)
        .filter(MpesaRefund.status_query_conversation_id == conversation_id)
        .first()
    )
    if refund is not None:
        logger.info(
            "Transaction Status query timed out for refund %s's status "
            "query; dead status_query_conversation_id cleared so "
            "reconciliation can re-ask.", refund.id,
        )
        refund.status_query_conversation_id = None
        db.commit()
        return refund

    logger.warning(
        "Transaction Status timeout for an unrecognised or "
        "already-resolved ConversationID; ignored"
    )
    db.commit()
    return None


def account_balance(
    db: Session, *, department_id: Optional[int] = None, callback_tenant: Optional[str] = None
) -> dict:
    """Request the shortcode's utility and working balances, for the admin UI
    to show an operator before they promise a refund. Never called on the
    refund hot path.

    NOT WIRED UP YET. This used to build a ResultURL/QueueTimeOutURL pair
    under /api/payments/mpesa/balance/... and submit the AccountBalance
    request to Safaricom, but no route exists to receive that result and
    those paths carry no CSRF exemption (unlike the Transaction Status pair,
    which handle_transaction_status_result, above, now genuinely handles). A
    live request built around URLs nothing can ever answer, and that would
    404 or be blocked outright if Safaricom tried to reach them, is worse
    than not sending it: it looks like progress while accomplishing
    nothing. So this now refuses outright, loudly, rather than making the
    call: build the balance/result and balance/timeout endpoints and their
    CSRF exemptions first (mirroring the status/result and status/timeout
    pair), then restore the request body this docstring used to describe.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Account Balance is not available yet: no result callback handler "
            "exists to receive Safaricom's answer."
        ),
    )
