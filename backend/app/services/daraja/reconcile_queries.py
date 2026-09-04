"""The per-row "ask Safaricom" operations reconcile.py's sweep uses.

Split out of reconcile.py purely to keep that file under this project's
~500 line preference (the same reason reservation.py was split out of
stk.py); no behaviour lives here that reconcile.py wouldn't otherwise own
directly. See reconcile.py's module docstring for the full picture: which
of these resolve synchronously, which are asynchronous, and which cases
this job may act on at all versus only surface.

I1 (silent-failure fix): these functions do not catch DarajaError or
HTTPException to swallow them. "We could not even ask Safaricom" (a
missing passkey, a Daraja outage, bad initiator credentials) is a REAL
failure, not the same fact as "Safaricom answered and had no verdict
yet", and must reach ReconcileRunResult.failures, not be logged and
silently discarded. Every caller in reconcile.py already wraps each row
in its own try/except that does exactly this, so letting these exceptions
propagate is the fix. The one exception, literally: requery_stk catches
HTTPException for exactly one purpose (New-5, telling Daraja's
"still processing" errorCode apart from every other rejection) and
re-raises anything that is not that one specific code, so the I1
guarantee holds for everything else unchanged.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from typing import Optional

from app.models.mpesa_events import MpesaEvent

from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import _config_for_source, _notify_refund_needs_review
from app.services.daraja.events import record_event
from app.services.daraja.settlement import _notify_quarantine, apply_stk_callback
from app.services.daraja.status import query_transaction_status
from app.services.daraja.stk import query_stk

logger = logging.getLogger("daraja_reconcile")

# Terminal states apply_stk_callback can write. Reaching one of these is
# what "resolved" means for STK Pending rows. C2B requeries and refund
# status queries never land here synchronously (see reconcile.py's module
# docstring), so they are counted separately by the caller instead of
# being folded into the same number.
TXN_TERMINAL = frozenset({"Success", "Failed", "Quarantined"})

# New-5: Daraja's own code for "the transaction is still being processed",
# widely documented for stkpushquery on an in-flight push. NOT YET
# CONFIRMED against this project's own sandbox credentials (none are in
# this repo); implemented defensively regardless, because the alternative,
# client.py flattening every non-2xx response into one generic
# HTTPException, is exactly what makes the question unanswerable. If
# sandbox testing shows a different code (or none at all, a bare non-2xx
# with no body), update this constant; nothing else here needs to change.
STILL_PROCESSING_ERROR_CODE = "500.001.1001"


# ─── Case 1: STK Pending (synchronous) ──────────────────────────────────────


def requery_stk(session: Session, txn: MpesaTransaction) -> None:
    """Ask Safaricom for txn's real outcome via STK Query.

    A GENUINE, FINAL verdict (any ResultCode other than 0: 1032 cancelled,
    1037 timeout, 1 insufficient funds, ...) is routed through
    apply_stk_callback exactly as a real callback would be, so the same
    cross-checks (amount comparison, receipt requirement, replay guard)
    apply. Nothing further can ever arrive for this CheckoutRequestID once
    Safaricom has given a non-zero ResultCode, so settling the row here is
    safe.

    C4: a bare ResultCode 0 is NOT routed through apply_stk_callback, and
    is NOT a verdict this job may act on. STK Query never carries
    CallbackMetadata (Amount, MpesaReceiptNumber): a genuine successful
    payment whose real callback was simply dropped looks IDENTICAL, from
    this endpoint, to one whose callback merely has not arrived yet. If
    this were routed through apply_stk_callback, settlement.py's own "no
    MpesaReceiptNumber despite ResultCode 0" step would mark it
    Quarantined. That is not a safe resting state here: apply_stk_callback
    only ever matches status == "Pending", so Safaricom's own retry of the
    ORIGINAL callback (which DOES carry the real receipt and amount, and
    is the ONLY delivery that can safely settle this row) would then find
    "no Pending row" and settle nothing, silently, forever. That is
    character-for-character the "Expired" bug reservation.py's docstring
    describes removing, reintroduced through a different door. A bare
    ResultCode 0 therefore leaves the row exactly as Pending, changing
    nothing, so the real callback's retry still has a Pending row to find;
    the 24-hour surface path is the backstop if that retry never comes.

    A transaction genuinely still being processed comes back from Daraja
    either as a 200 with no ResultCode field at all (Safaricom's "still
    processing" body carries only errorCode/errorMessage/requestId) or,
    per widely documented Daraja behaviour not yet confirmed against this
    project's own sandbox (New-5, flagged for the operator to verify), as
    a non-2xx response carrying errorCode STILL_PROCESSING_ERROR_CODE.
    Both are left exactly as Pending: neither is a verdict, so neither is
    treated as one. Any OTHER non-2xx response (query_stk raises
    HTTPException with a different or missing error_code) is a genuine
    "we could not ask Safaricom" failure and propagates: see the module
    docstring, I1.
    """
    _t0 = time.monotonic()
    try:
        data = query_stk(session, checkout_request_id=txn.checkout_request_id)
    except HTTPException as exc:
        duration_ms = int((time.monotonic() - _t0) * 1000)
        if getattr(exc, "error_code", None) == STILL_PROCESSING_ERROR_CODE:
            logger.info(
                "Reconciliation: STK query for transaction %s reports still "
                "processing (errorCode %s); left Pending.",
                txn.id, STILL_PROCESSING_ERROR_CODE,
            )
            record_event(
                session, flow="stk_query", direction="outbound", outcome="success",
                daraja_result_code=exc.error_code, daraja_result_desc="Still processing",
                duration_ms=duration_ms, mpesa_transaction_id=txn.id,
                mpesa_config_id=txn.mpesa_config_id,
                checkout_request_id=txn.checkout_request_id,
            )
            return
        record_event(
            session, flow="stk_query", direction="outbound", outcome="error",
            http_status=getattr(exc, "status_code", None),
            daraja_result_code=getattr(exc, "error_code", None),
            error_detail=str(exc.detail) if hasattr(exc, "detail") else str(exc),
            duration_ms=duration_ms, mpesa_transaction_id=txn.id,
            mpesa_config_id=txn.mpesa_config_id,
            checkout_request_id=txn.checkout_request_id,
        )
        raise

    duration_ms = int((time.monotonic() - _t0) * 1000)

    if "ResultCode" not in data:
        logger.info(
            "Reconciliation: STK query for transaction %s carried no "
            "ResultCode (still being processed); left Pending.", txn.id,
        )
        record_event(
            session, flow="stk_query", direction="outbound", outcome="success",
            daraja_result_desc="No ResultCode yet; still being processed",
            duration_ms=duration_ms, mpesa_transaction_id=txn.id,
            mpesa_config_id=txn.mpesa_config_id,
            checkout_request_id=txn.checkout_request_id, response_payload=data,
        )
        return

    if str(data.get("ResultCode")) == "0":
        logger.info(
            "Reconciliation: STK query for transaction %s reports success "
            "(ResultCode 0) with no CallbackMetadata; left Pending so the "
            "original callback, carrying the real receipt and amount, can "
            "still settle it if Safaricom retries it.", txn.id,
        )
        record_event(
            session, flow="stk_query", direction="outbound", outcome="success",
            daraja_result_code="0",
            daraja_result_desc=data.get("ResultDesc"),
            duration_ms=duration_ms, mpesa_transaction_id=txn.id,
            mpesa_config_id=txn.mpesa_config_id,
            checkout_request_id=txn.checkout_request_id, response_payload=data,
        )
        return

    record_event(
        session, flow="stk_query", direction="outbound", outcome="success",
        daraja_result_code=str(data.get("ResultCode")),
        daraja_result_desc=data.get("ResultDesc"),
        duration_ms=duration_ms, mpesa_transaction_id=txn.id,
        mpesa_config_id=txn.mpesa_config_id,
        checkout_request_id=txn.checkout_request_id, response_payload=data,
    )

    # A genuine, final, non-zero verdict. Pinned to txn's own
    # CheckoutRequestID/MerchantRequestID, never Daraja's echo of them: this
    # payload exists purely to drive apply_stk_callback's own lookup and
    # logging, and trusting an echo over the value this job already knows
    # is true invites exactly the kind of drift status.py's own receipt
    # cross-check (see its module docstring) exists to catch elsewhere.
    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": txn.checkout_request_id,
                "MerchantRequestID": txn.merchant_request_id,
                "ResultCode": data.get("ResultCode"),
                "ResultDesc": data.get("ResultDesc"),
            }
        }
    }
    apply_stk_callback(session, payload)


# ─── Case 2: C2B Unverified (asynchronous) ─────────────────────────────────


def requery_c2b(session: Session, txn: MpesaTransaction, *, callback_tenant: str) -> bool:
    """Re-fire a Transaction Status query for a C2B receipt still
    Unverified, UNLESS a query is already outstanding.

    C5: txn.conversation_id is the exact key handle_transaction_status_result
    correlates the eventual answer on. Overwriting it with a fresh id every
    time this job runs (every 15 minutes) would invalidate whatever answer
    the PREVIOUS query is still waiting to deliver, every single cycle,
    which means a result that takes longer than one cron interval to
    arrive can never resolve: this job would perpetually re-ask a new
    question before the last one's answer could ever land. So this fires
    at most once per outstanding query: once txn.conversation_id is set, a
    query is outstanding and this function does nothing until either the
    result callback clears it (by settling, quarantining, or matching the
    row, all of which move it out of "Unverified") or the row is old
    enough to be surfaced instead (reconcile.py's 24-hour path).

    Only a truthy id from the acknowledgment is ever written: Daraja
    omitting ConversationID/OriginatorConversationID on a 200 must never
    overwrite a real, still-live value (or a not-yet-set NULL) with NULL,
    which would silently orphan the row with no way to ever match a later
    result.

    Returns True iff a query was actually fired this call, so the caller's
    "requeried" count reflects rows genuinely asked about this cycle, not
    rows that were merely inspected and left waiting.
    """
    if not txn.receipt_number:
        logger.warning(
            "Reconciliation: Unverified transaction %s has no receipt_number; "
            "cannot ask Safaricom, left as is.", txn.id,
        )
        return False
    if txn.conversation_id:
        logger.info(
            "Reconciliation: transaction %s already has a Transaction Status "
            "query outstanding; left waiting for its result.", txn.id,
        )
        return False

    ack = query_transaction_status(
        session, receipt=txn.receipt_number, callback_tenant=callback_tenant
    )
    if ack is not None:
        new_conversation_id = ack.get("ConversationID")
        new_originator_id = ack.get("OriginatorConversationID")
        if new_conversation_id:
            txn.conversation_id = new_conversation_id
        if new_originator_id:
            txn.originator_conversation_id = new_originator_id
        if new_conversation_id or new_originator_id:
            session.commit()
    return True


# ─── Case 3: refund stuck Processing (asynchronous) ────────────────────────


def requery_refund(session: Session, refund: MpesaRefund, *, callback_tenant: str) -> bool:
    """Ask Safaricom about a refund stuck Processing, via a GENUINE
    Transaction Status query keyed on the refund's own conversation_id:
    the id Safaricom handed back when it accepted this exact B2C
    instruction (see b2c.py's _record_conversation_id). This is C1's fix:
    Daraja's TransactionStatusQuery accepts an OriginalConversationID as an
    alternative to a receipt-based TransactionID, and a Processing refund
    holds exactly that id, precisely because Safaricom already accepted
    and named the instruction. This asks; it does not send anything.

    Deliberately NOT a re-dispatch. routes/mpesa_refunds.py's
    retry-dispatch route says, in writing: "A stuck Processing refund is
    resolved by asking Safaricom directly (reconciliation), not by
    dispatching again." This function is that asking.

    The acknowledgment here is only a fresh ConversationID for THIS query,
    recorded on refund.status_query_conversation_id: a column dedicated to
    this query's own correlation, NEVER refund.conversation_id, which is
    the B2C dispatch's own id and the evidence _record_conversation_id's
    double-dispatch alarm depends on. The real verdict, when Safaricom
    sends one, arrives later at the existing status/result callback and is
    routed by handle_transaction_status_result to
    refund_status.handle_transaction_status_result_for_refund, which
    records and notifies a human. It never writes Completed or Failed:
    only a human, reading Safaricom's own answer, may authorise what
    happens to money already in flight.

    Fires at most once per outstanding query, the same discipline
    requery_c2b uses and for the identical reason: if
    status_query_conversation_id is already set, a previous query is still
    awaiting its answer, and overwriting it here would orphan that answer
    before it can land.

    Returns True iff a query was actually fired this call, so the
    caller's "requeried" count reflects rows genuinely asked about this
    cycle, not rows that were merely inspected and left waiting.
    """
    if refund.status_query_conversation_id:
        logger.info(
            "Reconciliation: refund %s already has a Transaction Status "
            "query outstanding; left waiting for its result.", refund.id,
        )
        return False

    if not refund.conversation_id:
        # New-4: b2c.py's own dispatch_refund and handle_b2c_timeout both
        # move a refund to Processing unconditionally once
        # _record_conversation_id returns True, which it also does (as a
        # documented no-op) when Safaricom's response carried no
        # ConversationID at all. So status == "Processing" with
        # conversation_id IS NULL is reachable, and there is nothing here
        # to ask Safaricom ABOUT: TransactionStatusQuery needs either a
        # receipt (which a Processing refund never has) or this exact id.
        # Calling query_transaction_status anyway would raise on every
        # 15-minute run forever, a permanent non-outage failure that would
        # drown out I1's real signal. The caller (reconcile.py) surfaces
        # this row instead of asking.
        logger.warning(
            "Reconciliation: refund %s is Processing with no conversation_id "
            "recorded; there is no id to ask Safaricom about.", refund.id,
        )
        return False

    source_txn = (
        session.query(MpesaTransaction)
        .filter(MpesaTransaction.id == refund.source_transaction_id)
        .first()
    )
    if source_txn is None:
        logger.warning(
            "Reconciliation: refund %s has no source transaction on record; "
            "cannot resolve which till to sign the query with.", refund.id,
        )
        return False
    config = _config_for_source(session, source_txn)

    ack = query_transaction_status(
        session,
        original_conversation_id=refund.conversation_id,
        config=config,
        callback_tenant=callback_tenant,
    )
    new_id = ack.get("ConversationID") if ack else None
    if new_id:
        refund.status_query_conversation_id = new_id
        session.commit()
    return True


# ─── Surfacing (case 5, and case 4's only handling) ────────────────────────


def surface_transaction(session: Session, txn: MpesaTransaction, *, reason: str) -> None:
    """Tell a human, never resolve locally. Reuses settlement.py's own
    quarantine notification (billing:manage) rather than reinventing it.

    I2/New-3: notifies only the FIRST time a given row is surfaced for a
    GIVEN reason (txn.surfaced_reason != reason, including the initial
    None), then records surfaced_at and surfaced_reason together and does
    not notify again for that SAME reason. Without this throttle, a row
    stuck for weeks renotifies a danger-category channel every 15-minute
    cron run forever, which trains billing staff to dismiss the channel,
    and the next quarantine, the forged-callback one this whole
    architecture exists to catch, gets dismissed along with it.

    Keyed on the reason text, not the row alone, because a row can be
    surfaced, have its status change under it (a human acts, or a callback
    lands), and later become stuck again for a COMPLETELY DIFFERENT
    reason: throttling on surfaced_at alone would then notify nobody the
    second time, which is worse than no throttle, since the log still
    records that a human was told about money in flight.
    """
    logger.error("Reconciliation: %s (transaction %s)", reason, txn.id)
    truncated_reason = reason[:255]
    if txn.surfaced_reason != truncated_reason:
        _notify_quarantine(session, txn, reason=reason)
        txn.surfaced_at = datetime.now(timezone.utc)
        txn.surfaced_reason = truncated_reason
        session.commit()


def surface_refund(session: Session, refund: MpesaRefund, *, reason: str) -> None:
    """Tell a human, never resolve locally. Reuses b2c.py's own
    needs-review notification (mpesa:refund). Same reason-keyed throttle as
    surface_transaction; see its docstring (I2/New-3)."""
    logger.error("Reconciliation: %s (refund %s)", reason, refund.id)
    truncated_reason = reason[:255]
    if refund.surfaced_reason != truncated_reason:
        _notify_refund_needs_review(session, refund, reason=reason)
        refund.surfaced_at = datetime.now(timezone.utc)
        refund.surfaced_reason = truncated_reason
        session.commit()


def replay_unapplied_callbacks(
    session: Session, *, older_than: timedelta, now: Optional[datetime] = None
) -> int:
    """Re-apply callbacks Safaricom delivered that we accepted but never acted on.

    The gap this closes: a handler that raises rolls its own session back, so
    before the inbound journal existed there was no record left that Safaricom
    had ever called. Safaricom does not retry an STK callback, and STK Query's
    bare ResultCode 0 carries neither receipt nor amount, so requery_stk
    correctly refuses to settle from it. The row therefore waited forever on a
    retry that was never coming. That is not hypothetical: it stranded two
    confirmed sandbox payments.

    A journalled row still at `received` past `older_than` is precisely "a
    response reached us and was not applied". Replaying it is not an inference
    and not a timer-driven guess: it is the real callback, run back through
    apply_stk_callback, which keeps every amount check, receipt cross-check and
    replay guard that a first-time callback goes through. Settlement is already
    idempotent on the receipt, so replaying one that did in fact apply is a
    no-op rather than a double credit.

    The grace period matters: a callback handled normally is marked `applied`
    within milliseconds, so anything older is genuinely stuck, and waiting
    lets the ordinary path win whenever it can.
    """
    from app.services.daraja.events import INBOUND_APPLIED, INBOUND_RECEIVED

    now = now or datetime.now(timezone.utc)
    cutoff = now - older_than

    stuck = (
        session.query(MpesaEvent)
        .filter(
            MpesaEvent.direction == "inbound",
            MpesaEvent.outcome == INBOUND_RECEIVED,
            MpesaEvent.flow == "stk_callback",
            MpesaEvent.created_at < cutoff,
        )
        .order_by(MpesaEvent.id.asc())
        .limit(100)
        .all()
    )

    replayed = 0
    for event in stuck:
        payload = _loads(event.request_payload)
        if payload is None:
            # Nothing to replay. Leave it at `received` rather than marking it
            # applied: a row we could not act on must stay visible.
            logger.warning(
                "Reconciliation: journalled callback %s has no replayable payload", event.id
            )
            continue
        try:
            apply_stk_callback(session, payload)
            session.commit()
        except Exception:  # noqa: BLE001, one poisoned row must not stop the rest
            session.rollback()
            logger.exception(
                "Reconciliation: replay of journalled callback %s failed", event.id
            )
            continue
        event.outcome = INBOUND_APPLIED
        session.commit()
        replayed += 1
        logger.info(
            "Reconciliation: replayed callback %s that had been accepted but never applied",
            event.id,
        )
    return replayed


def _loads(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None
