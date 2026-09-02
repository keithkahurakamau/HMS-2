"""The per-row "ask Safaricom" operations reconcile.py's sweep uses.

Split out of reconcile.py purely to keep that file under this project's
~500 line preference (the same reason reservation.py was split out of
stk.py); no behaviour lives here that reconcile.py wouldn't otherwise own
directly. See reconcile.py's module docstring for the full picture: which
of these resolve synchronously, which are asynchronous, and which cases
this job may act on at all versus only surface.

I1 (silent-failure fix): none of these functions catch DarajaError or
HTTPException any more. "We could not even ask Safaricom" (a missing
passkey, a Daraja outage, bad initiator credentials) is a REAL failure,
not the same fact as "Safaricom answered and had no verdict yet", and
must reach ReconcileRunResult.failures, not be logged and silently
swallowed. Every caller in reconcile.py already wraps each row in its own
try/except that does exactly this, so letting these exceptions propagate
is the fix: it costs nothing here and buys the caller the distinction it
needs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import _config_for_source, _notify_refund_needs_review
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
    either as a non-2xx response (query_stk raises HTTPException, which
    propagates: see the module docstring, I1) or as a 200 with no
    ResultCode field at all (Safaricom's "still processing" body carries
    only errorCode/errorMessage/requestId). Both are left exactly as
    Pending: neither is a verdict, so neither is treated as one.
    """
    data = query_stk(session, checkout_request_id=txn.checkout_request_id)

    if "ResultCode" not in data:
        logger.info(
            "Reconciliation: STK query for transaction %s carried no "
            "ResultCode (still being processed); left Pending.", txn.id,
        )
        return

    if str(data.get("ResultCode")) == "0":
        logger.info(
            "Reconciliation: STK query for transaction %s reports success "
            "(ResultCode 0) with no CallbackMetadata; left Pending so the "
            "original callback, carrying the real receipt and amount, can "
            "still settle it if Safaricom retries it.", txn.id,
        )
        return

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

    I2: notifies only the FIRST time a given row is surfaced
    (txn.surfaced_at is None), then records surfaced_at and never notifies
    that row again. Without this, a row stuck for weeks renotifies a
    danger-category channel every 15-minute cron run forever, which trains
    billing staff to dismiss the channel, and the next quarantine, the
    forged-callback one this whole architecture exists to catch, gets
    dismissed along with it.
    """
    logger.error("Reconciliation: %s (transaction %s)", reason, txn.id)
    if txn.surfaced_at is None:
        _notify_quarantine(session, txn, reason=reason)
        txn.surfaced_at = datetime.now(timezone.utc)
        session.commit()


def surface_refund(session: Session, refund: MpesaRefund, *, reason: str) -> None:
    """Tell a human, never resolve locally. Reuses b2c.py's own
    needs-review notification (mpesa:refund). Same once-only discipline as
    surface_transaction; see its docstring (I2)."""
    logger.error("Reconciliation: %s (refund %s)", reason, refund.id)
    if refund.surfaced_at is None:
        _notify_refund_needs_review(session, refund, reason=reason)
        refund.surfaced_at = datetime.now(timezone.utc)
        session.commit()
