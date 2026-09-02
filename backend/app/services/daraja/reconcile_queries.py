"""The five per-row "ask Safaricom" operations reconcile.py's sweep uses.

Split out of reconcile.py purely to keep that file under this project's
~500 line preference (the same reason reservation.py was split out of
stk.py); no behaviour lives here that reconcile.py wouldn't otherwise own
directly. See reconcile.py's module docstring for the full picture: which
of these resolve synchronously, which are asynchronous, and why refunds are
resolved by re-dispatching rather than by a raw Transaction Status query.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import _notify_refund_needs_review, dispatch_refund
from app.services.daraja.client import DarajaError
from app.services.daraja.settlement import _notify_quarantine, apply_stk_callback
from app.services.daraja.status import query_transaction_status
from app.services.daraja.stk import query_stk
from app.utils.log_redact import safe_repr

logger = logging.getLogger("daraja_reconcile")

# Terminal states apply_stk_callback can write. Reaching one of these is
# what "resolved" means for STK Pending rows; C2B requeries and refund
# re-dispatches never land here synchronously (see reconcile.py's module
# docstring), so they are counted separately by the caller instead of
# being folded into the same number.
TXN_TERMINAL = frozenset({"Success", "Failed", "Quarantined"})


# ─── Case 1: STK Pending (synchronous) ──────────────────────────────────────


def requery_stk(session: Session, txn: MpesaTransaction) -> None:
    """Ask Safaricom for txn's real outcome via STK Query, then route the
    answer through apply_stk_callback exactly as a genuine callback would
    be, so the same cross-checks (amount comparison, receipt requirement,
    replay guard) apply. See reconcile.py's module docstring for why a
    ResultCode 0 response with no receipt is correctly quarantined, not
    settled: STK Query never carries CallbackMetadata.

    A transaction genuinely still being processed comes back from Daraja
    either as a non-2xx response (query_stk raises HTTPException, caught
    here) or as a 200 with no ResultCode field at all (Safaricom's
    "still processing" body carries only errorCode/errorMessage/requestId).
    Both are left exactly as Pending: neither is a verdict, so neither is
    treated as one.
    """
    try:
        data = query_stk(session, checkout_request_id=txn.checkout_request_id)
    except HTTPException as exc:
        logger.info(
            "Reconciliation: STK query for transaction %s returned no verdict "
            "this cycle (%s); left Pending.",
            txn.id, safe_repr(str(exc.detail)),
        )
        return

    if "ResultCode" not in data:
        logger.info(
            "Reconciliation: STK query for transaction %s carried no "
            "ResultCode (still being processed); left Pending.", txn.id,
        )
        return

    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": data.get("CheckoutRequestID") or txn.checkout_request_id,
                "MerchantRequestID": data.get("MerchantRequestID") or txn.merchant_request_id,
                "ResultCode": data.get("ResultCode"),
                "ResultDesc": data.get("ResultDesc"),
            }
        }
    }
    apply_stk_callback(session, payload)


# ─── Case 2: C2B Unverified (asynchronous) ─────────────────────────────────


def requery_c2b(session: Session, txn: MpesaTransaction, *, callback_tenant: str) -> None:
    """Re-fire a Transaction Status query for a C2B receipt still
    Unverified. This only ever gets Safaricom's acknowledgment (a fresh
    ConversationID); the verdict, if one ever arrives, lands later at the
    already-wired /api/payments/mpesa/status/result callback
    (handle_transaction_status_result), the only place that ever settles,
    quarantines, or leaves this row alone. Recording the new
    ConversationID here is exactly what handle_confirmation itself does
    the first time; a fresh id simply supersedes an earlier, unanswered
    query.
    """
    if not txn.receipt_number:
        logger.warning(
            "Reconciliation: Unverified transaction %s has no receipt_number; "
            "cannot ask Safaricom, left as is.", txn.id,
        )
        return
    try:
        ack = query_transaction_status(
            session, receipt=txn.receipt_number, callback_tenant=callback_tenant
        )
    except (DarajaError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.warning(
            "Reconciliation: Transaction Status re-query failed for "
            "transaction %s: %s", txn.id, safe_repr(str(detail)),
        )
        txn.result_desc = str(detail)[:255]
        session.commit()
        return

    if ack is not None:
        txn.conversation_id = ack.get("ConversationID")
        txn.originator_conversation_id = ack.get("OriginatorConversationID")
    session.commit()


# ─── Cases 3 & 4: stuck refunds (asynchronous) ─────────────────────────────


def requery_refund(session: Session, refund: MpesaRefund, *, callback_tenant: str) -> None:
    """Ask Safaricom about a refund stuck Processing, or Approved with a
    dispatch marker already set (first_dispatch_attempted_at is not NULL):
    a prior attempt that may have reached Safaricom but whose outcome was
    never learned, and which retry-dispatch's route deliberately refuses
    to touch (it is gated to Approved WITHOUT a marker).

    See reconcile.py's module docstring for why this calls dispatch_refund
    rather than a raw Transaction Status query. OriginatorConversationID is
    reused unchanged (minted once, at request_refund time), so Safaricom
    recognises this as the SAME instruction, never a second payout, and
    dispatch_refund's own, already-tested branches decide everything from
    here:

      * A fresh synchronous rejection (Safaricom already holds this
        instruction) moves the refund to, or leaves it at, Processing and
        notifies a human; dispatch_refund's ResponseCode handling for an
        already-attempted refund (had_prior_attempt True, which is
        guaranteed here since first_dispatch_attempted_at is already set)
        guarantees this can never resolve to Failed.
      * A genuinely different ConversationID trips the double-dispatch
        alarm in _record_conversation_id, which itself notifies a human
        and stops.
      * The real, asynchronous verdict, if Safaricom ever sends one, still
        only arrives at the existing, already-wired
        /api/payments/mpesa/b2c/result and /b2c/timeout callbacks,
        correlated by OriginatorConversationID: this call never bypasses
        those checks, it only prompts Safaricom to consider the
        instruction live again.

    Nothing here ever writes Completed, Failed, or Reversed directly.
    """
    try:
        dispatch_refund(session, refund=refund, callback_tenant=callback_tenant)
    except (DarajaError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        logger.warning(
            "Reconciliation: refund %s re-dispatch reached no verdict this "
            "cycle: %s", refund.id, safe_repr(str(detail)),
        )


# ─── Surfacing (case 5) ─────────────────────────────────────────────────────


def surface_transaction(session: Session, txn: MpesaTransaction, *, reason: str) -> None:
    """Tell a human, never resolve locally. Reuses settlement.py's own
    quarantine notification (billing:manage) rather than reinventing it:
    the same "not settled, needs review" shape applies whether a row is
    quarantined by a cross-check or stuck long enough that reconciliation
    has given up asking."""
    logger.error("Reconciliation: %s (transaction %s)", reason, txn.id)
    _notify_quarantine(session, txn, reason=reason)
    session.commit()


def surface_refund(session: Session, refund: MpesaRefund, *, reason: str) -> None:
    """Tell a human, never resolve locally. Reuses b2c.py's own
    needs-review notification (mpesa:refund)."""
    logger.error("Reconciliation: %s (refund %s)", reason, refund.id)
    _notify_refund_needs_review(session, refund, reason=reason)
    session.commit()
