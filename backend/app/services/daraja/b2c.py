"""B2C refunds: the only path by which money leaves a hospital.

Every control here is load-bearing, not a nice-to-have. See docs/superpowers/
specs/2026-08-29-daraja-migration-design.md, section "Refunds (B2C)", for the
design rationale this module implements:

  * ``mpesa:refund`` is a dedicated permission, checked by the route layer,
    separate from ``billing:manage``. Taking a payment must not imply being
    able to send one back.
  * Two-person rule above a configurable threshold (MpesaConfig.
    refund_dual_approval_above), enforced HERE in approve_refund, not only by
    a route or a UI: a UI that hides the approve button is a courtesy, not a
    control.
  * refundable_amount is computed under a row lock (SELECT ... FOR UPDATE on
    the source MpesaTransaction) so two concurrent requests against the same
    receipt serialise instead of both reading a stale balance.
  * A per-transaction cap (refund_max_amount) and a rolling 24-hour cap
    (refund_daily_cap), both enforced here. The per-transaction cap is the
    till's own; the rolling cap's ceiling is also read from the till this
    refund is paid from, but the total it bounds is the whole TENANT's
    refund activity in the window, matching the design's per-tenant cap
    (see the comment in request_refund for why a per-till total would also
    silently exempt every legacy, till-less transaction).
  * OriginatorConversationID is minted once, in request_refund, and reused on
    every dispatch_refund retry: this is the primary double-refund defence,
    since Safaricom recognises a retried request as the same instruction
    rather than a second one.
  * CommandID is BusinessPayment, the correct code for a refund.
  * A B2C queue timeout is NOT a failure (handle_b2c_timeout): it means "we
    do not know yet" and leaves the refund Processing for reconciliation to
    resolve later, the same lesson reservation.py's removed local-expiry
    guess and status.py's Transaction Status split already learned the hard
    way. Treating a timeout as failure is how a system refunds twice.

States: Requested -> Approved -> Processing -> Completed | Failed | Reversed.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.services.daraja.client import DarajaError
from app.services.daraja.credentials import normalize_msisdn
from app.services.daraja.reservation import config_for
# Reused, not reinvented, per the brief: status.py already resolves and
# decrypts initiator credentials, already builds the (ResultURL,
# QueueTimeOutURL) pair for an async Daraja command from a callback_tenant
# hint, already builds a DarajaClient from a MpesaConfig, and already
# flattens Safaricom's ResultParameters list. B2C needs exactly the same
# four things.
from app.services.daraja.status import (
    _daraja_client,
    _flow_urls,
    _initiator_credentials,
    _result_parameters,
)
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

# Refund states that still count against the refundable balance and the
# rolling cap: money already sent, or a request that could still succeed.
# Failed and Reversed are excluded on purpose: neither leaves money out
# against the receipt (Failed never sent it; Reversed means it came back).
_HOLDS_FUNDS = ("Requested", "Approved", "Processing", "Completed")


# ─── Till resolution ─────────────────────────────────────────────────────


def _config_for_source(db: Session, txn: MpesaTransaction) -> MpesaConfig:
    """The till that RECEIVED the money on `txn`, so the refund is paid back
    from the same shortcode/credentials it arrived on, not the hospital's
    unrelated default. Falls back to config_for's default only for a
    transaction that predates mpesa_config_id."""
    if txn.mpesa_config_id is not None:
        config = db.query(MpesaConfig).filter(MpesaConfig.id == txn.mpesa_config_id).first()
        if config is not None:
            return config
    return config_for(db)


# ─── Refundable balance ──────────────────────────────────────────────────


def refundable_amount(db: Session, *, txn: MpesaTransaction) -> Decimal:
    """The balance still refundable against `txn`: the receipt amount minus
    refunds already completed or in flight against it.

    Callers that intend to act on this value (request_refund) must lock
    `txn` with SELECT ... FOR UPDATE before calling this, and must insert
    the new MpesaRefund row and commit inside that same transaction. Only
    then does the lock actually close the race: two concurrent requests
    computing this value against an unlocked row can both see the same
    stale balance and both pass.
    """
    if txn.status != "Success" or not txn.receipt_number:
        return Decimal("0")
    already_committed = (
        db.query(func.coalesce(func.sum(MpesaRefund.amount), 0))
        .filter(
            MpesaRefund.source_transaction_id == txn.id,
            MpesaRefund.status.in_(_HOLDS_FUNDS),
        )
        .scalar()
    )
    balance = Decimal(str(txn.amount)) - Decimal(str(already_committed or 0))
    return balance if balance > 0 else Decimal("0")


# ─── Request ─────────────────────────────────────────────────────────────


def request_refund(
    db: Session, *, source_transaction_id: int, amount, reason: str, user_id: int
) -> MpesaRefund:
    """Create a Requested refund against `source_transaction_id`.

    Every control that can be checked without talking to Safaricom lives
    here: refunds must be enabled for the till, the amount must fit inside
    the receipt's remaining balance (computed under a row lock), the
    per-transaction cap, and the rolling 24-hour cap. All server-side: a
    disabled-refunds hospital, or a cap violation, is rejected here even if
    a caller bypasses the UI entirely.
    """
    try:
        amount = Decimal(str(amount))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid refund amount.") from exc
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Refund amount must be greater than zero.")
    if amount != amount.to_integral_value():
        # dispatch_refund's B2C payload sends Amount as int(refund.amount):
        # Daraja's B2C API pays whole shillings only. Rejecting a
        # fractional amount HERE, at the input boundary, is what keeps the
        # record and the actual payout from ever disagreeing; catching it
        # only at dispatch time would still let a fractional amount sit on
        # the row (and count against caps and the refundable balance) as
        # something the payout can never actually match.
        raise HTTPException(
            status_code=400,
            detail=(
                "Refund amount must be a whole number of shillings: M-Pesa "
                "B2C cannot pay fractional shillings."
            ),
        )
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A refund reason is required.")

    # Lock the source transaction FIRST, before reading anything derived
    # from it. Everything below, the balance check, the cap checks, and the
    # insert, happens inside the transaction this lock opened; only ending
    # it (commit, at the very end) releases it. This is what makes two
    # concurrent 60%-each requests against the same receipt serialise
    # instead of racing: see refundable_amount's docstring.
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.id == source_transaction_id)
        .with_for_update()
        .first()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Source transaction not found.")
    if txn.status != "Success" or not txn.receipt_number:
        raise HTTPException(
            status_code=400, detail="Only a settled, receipted M-Pesa payment can be refunded."
        )

    config = _config_for_source(db, txn)
    if not config.refunds_enabled:
        raise HTTPException(
            status_code=400,
            detail="M-Pesa refunds are not enabled for this hospital's till.",
        )

    available = refundable_amount(db, txn=txn)
    if amount > available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Refund of KES {amount} exceeds the KES {available} still "
                f"refundable on receipt {txn.receipt_number}."
            ),
        )

    max_amount = Decimal(str(config.refund_max_amount))
    if amount > max_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Refund of KES {amount} exceeds the per-transaction cap of KES {max_amount}.",
        )

    # The design's cap is per TENANT, counted across every till, not per
    # till: the ceiling compared against is still the value configured on
    # the till THIS refund would be paid from (there is no separate
    # tenant-wide cap field), but the running total it is compared to is
    # every refund the tenant has made in the window, full stop. A join on
    # MpesaTransaction.mpesa_config_id would also silently exempt every
    # transaction that predates the per-department-tills migration: that
    # column is nullable and NULL on every such row, and `NULL == id` is
    # NULL, never true in SQL, so a refund against a legacy receipt would
    # neither count toward, nor be bounded by, any till's total at all.
    # Counting across the whole tenant by MpesaRefund alone closes both
    # gaps at once.
    window_start = datetime.now(timezone.utc) - timedelta(hours=24)
    rolling_total = (
        db.query(func.coalesce(func.sum(MpesaRefund.amount), 0))
        .filter(
            MpesaRefund.status.in_(_HOLDS_FUNDS),
            MpesaRefund.requested_at >= window_start,
        )
        .scalar()
    )
    rolling_total = Decimal(str(rolling_total or 0))
    daily_cap = Decimal(str(config.refund_daily_cap))
    if rolling_total + amount > daily_cap:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Refund of KES {amount} would push the hospital's rolling "
                f"24-hour refund total past its KES {daily_cap} cap."
            ),
        )

    refund = MpesaRefund(
        source_transaction_id=txn.id,
        invoice_id=txn.invoice_id,
        phone_number=txn.phone_number,
        amount=amount,
        reason=reason[:255],
        status="Requested",
        # Minted ONCE, here, and never regenerated: dispatch_refund reuses
        # this exact value on every retry, which is the primary defence
        # against Safaricom treating a retry as a second instruction.
        originator_conversation_id=str(uuid.uuid4()),
        requested_by=user_id,
    )
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return refund


# ─── Approve ─────────────────────────────────────────────────────────────


def approve_refund(db: Session, *, refund_id: int, user_id: int) -> MpesaRefund:
    """Approve a Requested refund.

    The two-person rule is enforced HERE, not only by a route's permission
    check: a permission check only confirms the caller may approve SOME
    refund, never that they are not the same person who requested THIS one.
    Below the dual-approval threshold, the same user may request and
    approve (e.g. a single admin issuing a small, self-evident refund);
    above it, the requester and approver must differ.
    """
    refund = (
        db.query(MpesaRefund).filter(MpesaRefund.id == refund_id).with_for_update().first()
    )
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found.")
    if refund.status != "Requested":
        raise HTTPException(
            status_code=409,
            detail=f"Refund is {refund.status}, not awaiting approval.",
        )

    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.id == refund.source_transaction_id)
        .first()
    )
    config = _config_for_source(db, txn) if txn is not None else config_for(db)
    threshold = Decimal(str(config.refund_dual_approval_above))

    if refund.amount > threshold and user_id == refund.requested_by:
        raise HTTPException(
            status_code=403,
            detail=(
                "This refund is above the dual-approval threshold: the "
                "requester cannot also approve it."
            ),
        )

    refund.status = "Approved"
    refund.approved_by = user_id
    refund.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(refund)
    return refund


# ─── Dispatch ────────────────────────────────────────────────────────────


def _record_conversation_id(
    db: Session, refund: MpesaRefund, reported: Optional[str]
) -> bool:
    """Record Safaricom's ConversationID on `refund` the first time it is
    learned. A LATER, DIFFERENT value is treated as a double-dispatch
    alarm, never silently overwritten.

    ConversationID is Safaricom's own identifier for the specific
    instruction it accepted. If a second, different value ever arrives for
    the same refund (the same OriginatorConversationID), that is direct
    evidence Safaricom holds TWO distinct instructions for what should be
    one payout, the single most important alarm this flow can raise.
    Overwriting it would erase that evidence and retarget every later
    cross-check at the second instruction, silently disowning the first
    one's own result when it arrives.

    Returns False when an alarm was raised: the caller must stop and must
    not resolve the refund from the response/result that triggered this
    call. Returns True otherwise, including the ordinary case of nothing
    to record yet.
    """
    if not reported:
        return True
    if refund.conversation_id and refund.conversation_id != reported:
        refund.result_desc = (
            f"ALARM: a second ConversationID ({reported}) arrived for this "
            f"refund; the recorded ConversationID is {refund.conversation_id}. "
            "Safaricom may hold two distinct instructions for one refund. "
            "Left untouched pending manual review."
        )[:255]
        logger.error(
            "B2C double-dispatch alarm for refund %s: recorded ConversationID "
            "%s, new arrival %s",
            refund.id, safe_repr(refund.conversation_id), safe_repr(reported),
        )
        db.commit()
        _notify_refund_needs_review(db, refund, reason=refund.result_desc)
        return False
    if not refund.conversation_id:
        refund.conversation_id = reported
    return True


def _lock_refund(db: Session, refund_id: int) -> Optional[MpesaRefund]:
    """Fetch `refund_id` under SELECT ... FOR UPDATE. Shared by every
    dispatch_refund call site: two concurrent attempts against the SAME
    refund (a double-click, a manual retry racing an automated one) must
    serialise on this row, not both read the same entry_status and both
    submit."""
    return (
        db.query(MpesaRefund).filter(MpesaRefund.id == refund_id).with_for_update().first()
    )


def dispatch_refund(
    db: Session, *, refund: MpesaRefund, callback_tenant: Optional[str] = None
) -> MpesaRefund:
    """Submit `refund` to Safaricom's B2C API.

    Safe to call more than once for the same refund: OriginatorConversationID
    was minted once at request_refund time and is reused unchanged here on
    every call, so a retried dispatch is recognised by Safaricom as the same
    instruction, never a second payout.

    Locking, in two phases, both against the refund row itself (the
    caller's `refund` object is only used for its id; every decision below
    reads the freshly locked row):

    Phase 1 locks the row just long enough to read entry_status and decide
    whether this is the FIRST dispatch attempt ever made for this refund
    (first_dispatch_attempted_at IS NULL). If so, that column is set and
    COMMITTED immediately, before any network call: a commit here ends the
    phase-1 transaction and releases its lock, but the marker it wrote is
    now durable, which is the property that matters. Any concurrent caller
    that was blocked on that lock unblocks only after this commit, and so
    is GUARANTEED to see the marker already set: no two concurrent callers
    can ever both observe "no prior attempt" for the same refund.

    Phase 2 re-locks the row and holds that second lock for the rest of
    the function, including the Safaricom call itself: only one dispatch
    attempt for this refund is ever in flight at a time, so a concurrent
    caller that raced in during the brief gap between phase 1's commit and
    phase 2's lock (already guaranteed to see the marker, per the previous
    paragraph) still waits for this attempt's outcome before it can start
    its own.
    """
    refund = _lock_refund(db, refund.id)
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found.")
    if refund.status not in ("Approved", "Processing"):
        raise HTTPException(
            status_code=409,
            detail=f"Refund is {refund.status}; nothing to dispatch.",
        )
    # Captured before anything below can mutate refund.status: the
    # synchronous-rejection branch needs to know what this refund WAS when
    # this specific call started, not what it becomes partway through.
    entry_status = refund.status
    had_prior_attempt = refund.first_dispatch_attempted_at is not None
    if not had_prior_attempt:
        refund.first_dispatch_attempted_at = datetime.now(timezone.utc)
        db.commit()

    refund = _lock_refund(db, refund.id)
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found.")
    if refund.status not in ("Approved", "Processing"):
        # A concurrent call resolved this refund in the gap between phase
        # 1 and phase 2 (e.g. this attempt observed had_prior_attempt via
        # the marker but a genuinely earlier attempt's own response then
        # landed first and completed it). Nothing left to dispatch.
        raise HTTPException(
            status_code=409,
            detail=f"Refund is {refund.status}; nothing to dispatch.",
        )

    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.id == refund.source_transaction_id)
        .first()
    )
    if txn is None:
        raise HTTPException(status_code=404, detail="Source transaction not found.")
    config = _config_for_source(db, txn)
    initiator, credential = _initiator_credentials(config)
    result_url, timeout_url = _flow_urls(config, callback_tenant, flow="b2c")

    payload = {
        "OriginatorConversationID": refund.originator_conversation_id,
        "InitiatorName": initiator,
        "SecurityCredential": credential,
        # BusinessPayment is the correct code for a refund. PromotionPayment
        # and SalaryPayment produce the wrong message on the recipient's
        # handset, so neither is acceptable here even though Daraja would
        # accept either without complaint.
        "CommandID": "BusinessPayment",
        "Amount": int(refund.amount),
        "PartyA": config.shortcode,
        "PartyB": normalize_msisdn(refund.phone_number),
        "Remarks": refund.reason[:100],
        "QueueTimeOutURL": timeout_url,
        "ResultURL": result_url,
        "Occasion": f"REFUND-{refund.id}",
    }

    client = _daraja_client(config)
    try:
        response = client.post("/mpesa/b2c/v3/paymentrequest", payload)
    except DarajaError as exc:
        # The request never definitively reached Safaricom: a network
        # error, a 5xx, or the circuit breaker open. This is NOT the same
        # fact as Safaricom rejecting it. Nothing is known to be in flight,
        # so the refund is left exactly where it was (Approved, or still
        # Processing on a retry of an already-accepted one) and can be
        # dispatched again safely, because OriginatorConversationID never
        # changes between attempts.
        logger.warning(
            "B2C dispatch for refund %s could not reach Daraja: %s",
            refund.id, safe_repr(str(exc)),
        )
        raise

    response_code = str(response.get("ResponseCode", ""))
    if response_code != "0":
        if entry_status == "Processing" or had_prior_attempt:
            # Either this call entered already Processing (an earlier
            # attempt already got a synchronous "0", or a timeout later
            # confirmed Safaricom holds it), or it entered Approved but
            # had_prior_attempt is True, meaning a PREVIOUS dispatch
            # attempt for this same refund was already recorded before
            # this one started, and that earlier attempt's own response
            # never made it back (a lost read timeout, a dropped
            # connection, a breaker trip on the response leg): entry_status
            # stayed "Approved" not because nothing was sent, but because
            # nothing was ever LEARNED about what was sent. Either way,
            # Safaricom already holds an accepted instruction, and a
            # non-zero ResponseCode here is exactly what its own
            # duplicate-OriginatorConversationID rejection looks like:
            # proof it holds that instruction, not evidence the refund
            # failed. Reading this as "the refund failed" is precisely how
            # the loop closes: the operator sees Failed, requests a fresh
            # refund with a fresh originator id, and that second,
            # genuinely distinct instruction pays the patient again on top
            # of the first, already-accepted one. So this must never
            # resolve to Failed; it moves to (or stays at) Processing, the
            # same resting state as an unresolved queue timeout, and a
            # human is told now rather than the record silently
            # disagreeing with reality.
            logger.warning(
                "B2C dispatch for refund %s (entry_status=%s, had_prior_attempt=%s) "
                "got a non-zero synchronous ResponseCode (%s: %s); moved to/left "
                "Processing, not Failed, because Safaricom may already hold the "
                "original instruction.",
                refund.id, entry_status, had_prior_attempt,
                response_code, safe_repr(response.get("ResponseDescription")),
            )
            refund.status = "Processing"
            refund.result_desc = (
                f"Dispatch got ResponseCode {response_code} "
                f"({response.get('ResponseDescription')}); moved to Processing "
                "pending manual review, not Failed, because Safaricom may "
                "already hold a previously accepted instruction."
            )[:255]
            db.commit()
            db.refresh(refund)
            _notify_refund_needs_review(db, refund, reason=refund.result_desc)
            return refund

        # entry_status == "Approved" and had_prior_attempt is False: this
        # IS the first dispatch attempt ever made for this refund, and
        # this IS its own synchronous verdict, a definitive rejection
        # Safaricom gave for an instruction it never accepted into its
        # queue. No asynchronous result will ever follow for it, so
        # Failed is genuinely correct here. This is a different fact from
        # a queue timeout on a request Safaricom DID accept (see
        # handle_b2c_timeout, below), which must never be marked Failed,
        # and a different fact from either case just above.
        refund.status = "Failed"
        refund.result_desc = str(
            response.get("ResponseDescription") or "Daraja rejected the B2C request"
        )[:255]
        db.commit()
        db.refresh(refund)
        return refund

    if not _record_conversation_id(db, refund, response.get("ConversationID")):
        db.refresh(refund)
        return refund

    refund.status = "Processing"
    db.commit()
    db.refresh(refund)
    return refund


# ─── Result callback ─────────────────────────────────────────────────────


def _notify_refund_needs_review(db: Session, refund: MpesaRefund, *, reason: str) -> None:
    """Notify mpesa:refund holders that a refund needs manual review.

    Best-effort: a notification failure must never be mistaken for, or
    turned into, a failure of the refund state change itself.
    """
    try:
        from app.utils.notify import notify_permission
        notify_permission(
            db, "mpesa:refund",
            title="M-Pesa refund needs review",
            body=f"Refund #{refund.id} (KES {refund.amount}): {reason}",
            link="/app/billing",
            category="danger",
            # mpesa:refund is Admin-only (see PERMISSION_CATALOG); the
            # default exclude_roles=("Admin",) on notify_permission would
            # otherwise notify nobody at all.
            exclude_roles=(),
        )
    except Exception:  # noqa: BLE001
        logger.warning("_notify_refund_needs_review: notification failed", exc_info=True)


def _apply_completed_refund_to_invoice(db: Session, refund: MpesaRefund) -> None:
    """Decrement the invoice's amount_paid by the refunded amount and
    recalculate its status. Called only once a refund is genuinely
    Completed (Safaricom's own result confirmed the money moved).

    Without this, a Completed refund updates no invoice: the books would
    still say the invoice is fully paid after part of that payment went
    back out to the patient, an accounting hole, not a missing nicety.

    TODO(ledger): this does not post a ledger entry for the refund.
    settle_invoice_match posts through post_from_event, and that path has
    a known, separately-tracked defect: JournalEntry.created_by is
    NOT NULL while post_from_event defaults user_id=None, so a call with
    no human actor (exactly what an unattended B2C result callback is)
    poisons the session on its own INSERT. Do not add a ledger post here
    until that is fixed, or every unattended completion fails here
    instead of merely failing to post. The invoice adjustment above is
    unaffected by that defect and must not wait on it.
    """
    if not refund.invoice_id:
        return
    invoice = (
        db.query(Invoice)
        .filter(Invoice.invoice_id == refund.invoice_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        return
    invoice.amount_paid = max(
        Decimal("0"),
        Decimal(str(invoice.amount_paid or 0)) - Decimal(str(refund.amount)),
    )
    total_amount = Decimal(str(invoice.total_amount or 0))
    if invoice.amount_paid <= 0:
        invoice.status = "Pending"
    elif invoice.amount_paid >= total_amount:
        invoice.status = "Paid"
    else:
        invoice.status = "Partially Paid"


def handle_b2c_result(db: Session, payload: dict) -> Optional[MpesaRefund]:
    """Apply Safaricom's asynchronous B2C result.

    Correlated by OriginatorConversationID ALONE (the id WE minted, unique
    per refund by a real database constraint). Earlier versions of this
    handler additionally required status == "Processing", which discards
    the single most important delivery this flow can receive: if
    dispatch_refund's own synchronous response was lost (a read timeout, a
    dropped connection, a breaker trip on the response leg) after
    Safaricom had already accepted the request, the refund is correctly
    left Approved (nothing was known at the time), but Safaricom's result
    callback for that already-accepted instruction still arrives. A
    status == "Processing" filter would call that "unrecognised" and
    discard Safaricom's only definitive statement about money that has
    already left the till, stranding the refund Approved forever: money
    out, record says not yet sent. So the row is found by
    OriginatorConversationID alone, and the STATUS FOUND decides what
    happens next:
      - Approved or Processing: apply the result below.
      - Completed, Failed, or Reversed: already resolved, a repeat
        delivery; no-op.
      - anything else (e.g. Requested): should not happen, ignored.

    ConversationID (Safaricom's own id for the accepted instruction) is
    recorded the first time it is learned and cross-checked on every
    later arrival via _record_conversation_id: a result must not be able
    to complete a DIFFERENT refund than the one it belongs to, the same
    discipline status.py's Transaction Status result handler applies via
    its receipt cross-check, and a genuinely different ConversationID is
    itself an alarm (see _record_conversation_id), not a discard.
    """
    result = (payload or {}).get("Result") or {}
    originator_id = result.get("OriginatorConversationID")
    if not originator_id:
        logger.warning("B2C result missing OriginatorConversationID; ignored")
        return None

    refund = (
        db.query(MpesaRefund)
        .filter(MpesaRefund.originator_conversation_id == originator_id)
        .first()
    )
    if refund is None:
        logger.warning(
            "B2C result for an unrecognised OriginatorConversationID; ignored"
        )
        return None

    # Serialise concurrent deliveries of this exact result, the same
    # discipline apply_stk_callback and handle_transaction_status_result
    # both use, before acting on it.
    lock_id = int(hashlib.sha1(originator_id.encode("utf-8")).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        db.refresh(refund)

        if refund.status in ("Completed", "Failed", "Reversed"):
            logger.info(
                "B2C result for refund %s already %s; repeat delivery, no-op",
                refund.id, refund.status,
            )
            db.commit()
            return refund

        if refund.status not in ("Approved", "Processing"):
            logger.warning(
                "B2C result for refund %s in unexpected status %s; ignored",
                refund.id, refund.status,
            )
            db.commit()
            return None

        if not _record_conversation_id(db, refund, result.get("ConversationID")):
            db.refresh(refund)
            return refund

        result_code = result.get("ResultCode")
        if str(result_code) != "0":
            refund.status = "Failed"
            refund.result_desc = str(result.get("ResultDesc") or "")[:255]
            db.commit()
            return refund

        # Safaricom's documented B2C result keys are TransactionReceipt and
        # TransactionAmount; as with C2B's Transaction Status result (see
        # status.py), a bare ReceiptNo/Amount is tolerated as a plausible
        # alternate spelling rather than assumed impossible. Reading only
        # one spelling risks every genuine result missing the field.
        params = _result_parameters(result)
        reported_receipt = params.get("TransactionReceipt")
        if reported_receipt is None:
            reported_receipt = params.get("ReceiptNo")
        raw_amount = params.get("TransactionAmount")
        if raw_amount is None:
            raw_amount = params.get("Amount")

        if reported_receipt is None or raw_amount is None:
            # At least one field was not found under any spelling checked.
            # This is "we could not find it", not "the refund failed": an
            # ambiguous result is never treated as a verdict, so the refund
            # stays Processing and a human is told exactly what arrived.
            missing = []
            if reported_receipt is None:
                missing.append("receipt (checked TransactionReceipt, ReceiptNo)")
            if raw_amount is None:
                missing.append("amount (checked TransactionAmount, Amount)")
            keys_present = sorted(params.keys())
            refund.result_desc = (
                f"B2C result missing {' and '.join(missing)}; keys present: {keys_present}"
            )[:255]
            logger.error(
                "B2C result for refund %s missing expected field(s) (%s); "
                "keys present: %s",
                refund.id, " and ".join(missing), keys_present,
            )
            db.commit()
            _notify_refund_needs_review(db, refund, reason=refund.result_desc)
            return refund

        try:
            reported_amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            refund.result_desc = f"B2C result reported an unparseable amount: {raw_amount!r}"[:255]
            logger.error(
                "B2C result for refund %s reported an unparseable amount: %r",
                refund.id, raw_amount,
            )
            db.commit()
            _notify_refund_needs_review(db, refund, reason=refund.result_desc)
            return refund

        # THE amount cross-check. Without this, a result reporting KES 200
        # against a refund of KES 2,000 would complete the full KES 2,000
        # on the strength of a result that never actually confirmed it;
        # requiring the field to be PRESENT (above) is not the same as
        # requiring it to AGREE. Mirrors status.py's Transaction Status
        # cross-check: a mismatch settles nothing, quarantines to a human.
        if reported_amount != Decimal(str(refund.amount)):
            refund.result_desc = (
                f"B2C result reported KES {reported_amount}, this refund "
                f"requested KES {refund.amount}. Not completed, pending review."
            )[:255]
            logger.error(
                "B2C result amount mismatch for refund %s: reported KES %s, "
                "requested KES %s",
                refund.id, reported_amount, refund.amount,
            )
            db.commit()
            _notify_refund_needs_review(db, refund, reason=refund.result_desc)
            return refund

        refund.transaction_receipt = str(reported_receipt)
        refund.result_desc = str(result.get("ResultDesc") or "")[:255]
        refund.status = "Completed"
        refund.completed_at = datetime.now(timezone.utc)
        _apply_completed_refund_to_invoice(db, refund)
        db.commit()
        return refund
    except Exception:
        db.rollback()
        raise


def handle_b2c_timeout(db: Session, payload: dict) -> Optional[MpesaRefund]:
    """Apply a Daraja B2C queue timeout.

    THE rule that matters most: a queue timeout is NOT a failure. It means
    Safaricom has not told us the outcome yet, exactly the same resting
    state as if no result had arrived at all. The refund stays (or moves
    to) Processing; reconciliation resolves it later by asking Safaricom
    directly. Marking it Failed here is how a refund goes out twice: an
    operator sees Failed, retries with a fresh request, and the original
    payout may still land, or already has.

    Correlated by OriginatorConversationID ALONE, the same reasoning as
    handle_b2c_result: a timeout callback can arrive for a refund still
    sitting at Approved (dispatch_refund's own synchronous response was
    lost, but Safaricom had already queued the request), and a
    status == "Processing" filter would discard that arrival as
    "unrecognised" instead of learning from it that Safaricom does hold
    the instruction. An Approved refund that receives a timeout moves to
    Processing: the timeout itself is confirmation Safaricom has it, even
    though the outcome is still unknown.
    """
    result = (payload or {}).get("Result") or {}
    originator_id = result.get("OriginatorConversationID")
    if not originator_id:
        logger.warning("B2C timeout missing OriginatorConversationID; ignored")
        db.commit()
        return None

    refund = (
        db.query(MpesaRefund)
        .filter(MpesaRefund.originator_conversation_id == originator_id)
        .first()
    )
    if refund is None:
        logger.warning("B2C timeout for an unrecognised OriginatorConversationID; ignored")
        db.commit()
        return None

    # Serialise concurrent deliveries the same way handle_b2c_result does:
    # this handler now performs real state changes (a possible
    # Approved -> Processing transition, a ConversationID write), not just
    # a confirmation, so it needs the same protection against a race with
    # another delivery of the same or a related callback.
    lock_id = int(hashlib.sha1(originator_id.encode("utf-8")).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        db.refresh(refund)

        if refund.status in ("Completed", "Failed", "Reversed"):
            logger.info(
                "B2C timeout for refund %s already %s; repeat/late delivery, no-op",
                refund.id, refund.status,
            )
            db.commit()
            return refund

        if refund.status not in ("Approved", "Processing"):
            logger.warning(
                "B2C timeout for refund %s in unexpected status %s; ignored",
                refund.id, refund.status,
            )
            db.commit()
            return None

        if not _record_conversation_id(db, refund, result.get("ConversationID")):
            db.refresh(refund)
            return refund

        was_approved = refund.status == "Approved"
        refund.status = "Processing"
        if was_approved:
            refund.result_desc = (
                "Daraja queue timeout confirms Safaricom accepted this refund "
                "(an earlier dispatch attempt's own synchronous response was "
                "lost); outcome not yet known, awaiting reconciliation."
            )[:255]
        else:
            refund.result_desc = (
                "Daraja queue timeout: outcome not yet known, awaiting reconciliation."
            )[:255]
        logger.info("B2C queue timeout for refund %s; left Processing", refund.id)
        db.commit()
        return refund
    except Exception:
        db.rollback()
        raise
