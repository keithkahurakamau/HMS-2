"""Recording (never resolving) a reconciliation Transaction Status result
for a B2C refund.

Split out of b2c.py to keep that file from growing further (it already
exceeds this project's ~500 line preference; a new function does not need
to make that worse), and kept separate from status.py to avoid a circular
import: status.py's handle_transaction_status_result lazily imports this
module from inside a function rather than the reverse, since b2c.py already
imports several helpers FROM status.py at module level.

THE RULE THIS FILE EXISTS TO HONOUR. reconcile_queries.py's requery_refund
fires a genuine Transaction Status query against a Processing refund's own
conversation_id (see mpesa_refunds.status_query_conversation_id), because
that is a real question with a real chance of a real answer. But the
answer describes money already dispatched toward a patient's phone: only a
human, having read Safaricom's own verdict, may decide what happens to it
next. This module has exactly two verbs: write down what Safaricom said,
and tell someone. It has no verb for "therefore this refund is Completed"
or "therefore this refund is Failed": those stay handle_b2c_result's and
handle_b2c_timeout's own, separately cross-checked calls to make.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.mpesa import MpesaRefund
from app.services.daraja.b2c import _notify_refund_needs_review
from app.services.daraja.status import _result_parameters

logger = logging.getLogger(__name__)


def handle_transaction_status_result_for_refund(
    db: Session, refund: MpesaRefund, result: dict,
) -> MpesaRefund:
    """Record Safaricom's Transaction Status verdict on `refund` and notify
    a human. Never writes Completed, Failed, or Reversed, and never touches
    conversation_id or originator_conversation_id: those stay
    handle_b2c_result's and handle_b2c_timeout's own decision, correlated
    on originator_conversation_id, which this function does not even read.

    Serialises concurrent deliveries with the same discipline every other
    result handler in this package uses, keyed on
    status_query_conversation_id so this lock can never collide with
    handle_b2c_result/handle_b2c_timeout's own lock (keyed on
    originator_conversation_id, a different id for a different query).

    New-6: a no-op once `refund` has already reached a terminal state
    (Completed, Failed, Reversed). handle_b2c_result/handle_b2c_timeout can
    genuinely resolve a refund BEFORE this status query's own, separately
    fired result arrives; without this check, a late status answer would
    overwrite result_desc that already carries handle_b2c_result's own,
    correct audit text (Safaricom's real ResultDesc for a Completed
    refund), and would fire a danger-category needs-review notification
    for a refund that is already finished, exactly the alarm fatigue I2
    exists to prevent.
    """
    lock_id = int(
        hashlib.sha1(
            (refund.status_query_conversation_id or "").encode("utf-8")
        ).hexdigest()[:15], 16,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        db.refresh(refund)

        if refund.status in ("Completed", "Failed", "Reversed"):
            logger.info(
                "Reconciliation Transaction Status result for refund %s "
                "arrived after it already reached %s; ignored.",
                refund.id, refund.status,
            )
            db.commit()
            return refund

        result_code = result.get("ResultCode")
        params = _result_parameters(result)
        reported_receipt = params.get("TransactionReceipt") or params.get("ReceiptNo")
        raw_amount = params.get("TransactionAmount") or params.get("Amount")
        transaction_status = params.get("TransactionStatus") or params.get("Status")

        amount_desc = "an unreported amount"
        if raw_amount is not None:
            try:
                amount_desc = f"KES {Decimal(str(raw_amount))}"
            except (InvalidOperation, ValueError, TypeError):
                amount_desc = f"an unparseable amount ({raw_amount!r})"

        if str(result_code) != "0":
            summary = (
                f"Reconciliation Transaction Status query for refund {refund.id} "
                f"did not resolve: {result.get('ResultDesc') or result_code}. "
                "Verify against the Safaricom portal."
            )
        else:
            summary = (
                f"Reconciliation Transaction Status query for refund {refund.id} "
                f"reports status {transaction_status!r}, receipt "
                f"{reported_receipt or 'none reported'}, {amount_desc}. Not "
                "applied automatically: verify against the Safaricom portal, "
                "then act deliberately."
            )

        refund.result_desc = summary[:255]
        db.commit()
        logger.info(summary)
        _notify_refund_needs_review(db, refund, reason=summary)
        return refund
    except Exception:
        db.rollback()
        raise
