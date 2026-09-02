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
    requesting till's own. The rolling cap is coherently per-TENANT on
    both sides: the total it bounds is every refund the tenant has made in
    the window (not scoped to any one till, and not blind to legacy,
    till-less receipts), and the ceiling it is compared against is the
    hospital DEFAULT till's own refund_daily_cap, never whichever till a
    given refund happens to be filed against (see the comment in
    request_refund for why mixing those two scopes is incoherent, not a
    tradeoff).
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
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterator, Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.circuit import daraja_breaker
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

    # The design's cap is per TENANT, counted across every till: the
    # running total is every refund the tenant has made in the window,
    # full stop, not scoped to any one till. A join on
    # MpesaTransaction.mpesa_config_id would also silently exempt every
    # transaction that predates the per-department-tills migration: that
    # column is nullable and NULL on every such row, and `NULL == id` is
    # NULL, never true in SQL, so a refund against a legacy receipt would
    # neither count toward, nor be bounded by, any till's total at all.
    # Counting across the whole tenant by MpesaRefund alone closes both
    # gaps at once.
    #
    # The CEILING must match that pool: the hospital DEFAULT till's own
    # refund_daily_cap (the department_id IS NULL row, which IS the
    # hospital-level configuration), never the cap configured on whichever
    # till this particular refund happens to be filed against. Comparing a
    # tenant-wide total to a department till's own cap is incoherent, not
    # a tradeoff: a conservative cap set on one till would be void the
    # moment a refund is routed through a different till with more
    # headroom, and which receipt a refund is filed against is something
    # staff can influence. A department that genuinely needs a LOWER limit
    # than the hospital is a separate, additional per-till sub-limit,
    # checked on top of this one, not instead of it; that is not this
    # control and is not implemented here.
    # Deliberately NOT filtered on is_active. This query reads a POLICY
    # NUMBER off the hospital-level configuration record; it is not
    # choosing a till to route a payment through. Requiring is_active
    # here would let deactivating the default till silently promote the
    # ceiling to whichever till the refund happens to be filed against,
    # exactly the higher-headroom bypass this control exists to close: a
    # single toggle could turn a KES 500 tenant ceiling into a KES 50,000
    # one with no error and no log line. The default row's cap value is
    # authoritative regardless of whether that till is currently taking
    # payments.
    hospital_default_config = (
        db.query(MpesaConfig)
        .filter(MpesaConfig.department_id.is_(None))
        .first()
    )
    if hospital_default_config is not None:
        daily_cap = Decimal(str(hospital_default_config.refund_daily_cap))
    else:
        # No hospital-default row exists at all (unusual: every hospital
        # is expected to have one). Falls back to the MINIMUM cap
        # configured on any active till, never the requesting till's own:
        # the whole point of this control is that staff filing a refund
        # cannot move the ceiling by choosing which receipt to file it
        # against, and "whichever till this refund happens to use" is
        # exactly that.
        minimum_active_cap = (
            db.query(func.min(MpesaConfig.refund_daily_cap))
            .filter(MpesaConfig.is_active == True)  # noqa: E712
            .scalar()
        )
        if minimum_active_cap is None:
            # No hospital-default row, and no active till anywhere either.
            # `config` (the requesting till) can itself be inactive, since
            # a refund is filed against the RECEIPT's own till regardless
            # of whether that till is still active (see _config_for_source),
            # so falling back to config.refund_daily_cap here would be
            # exactly the bypass this whole control exists to close.
            # Refuse outright rather than guess at a ceiling.
            raise HTTPException(
                status_code=400,
                detail=(
                    "No active M-Pesa till is configured for this hospital; "
                    "a refund cap cannot be determined safely."
                ),
            )
        daily_cap = Decimal(str(minimum_active_cap))
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

    Also moves `refund` to Processing when the alarm fires, regardless of
    what it was before. A ConversationID exists at all only because
    Safaricom has demonstrably engaged with this refund at least once, so
    Approved (meaning "not yet sent") is never an accurate description of
    it from this point on, including when this call is dispatch_refund's
    own success path (ResponseCode == 0) reporting a SECOND, conflicting
    ConversationID: an operator reading Approved there is exactly the
    person who would file a fresh refund on top of one Safaricom already
    accepted.
    """
    if not reported:
        return True
    if refund.conversation_id and refund.conversation_id != reported:
        refund.status = "Processing"
        refund.result_desc = (
            f"ALARM: a second ConversationID ({reported}) arrived for this "
            f"refund; the recorded ConversationID is {refund.conversation_id}. "
            "Safaricom may hold two distinct instructions for one refund. "
            "Moved to Processing pending manual review."
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
    """Fetch `refund_id` under SELECT ... FOR UPDATE, freshly.

    populate_existing() is not optional here. SQLAlchemy's identity map
    means that if `db` already holds a Python object for this refund_id
    (the caller's own `refund` argument almost always is exactly that
    object), a plain query returns that SAME object WITHOUT overwriting
    its already-loaded attributes from the row this query just fetched,
    even though the FOR UPDATE clause genuinely executed and genuinely
    locked the row at the database level. Confirmed empirically while
    building dispatch_refund's concurrency test: without
    populate_existing(), a caller could read its own stale, pre-lock copy
    of first_dispatch_attempted_at even after this query returned, which
    is exactly the ORM-cache-driven route to the double-refund shape the
    surrounding locking exists to prevent.

    NOTE: populate_existing() also discards any of the caller's own
    UNFLUSHED changes to this same refund object, and the FOR UPDATE
    query below runs inside `db`'s current transaction, so it is subject
    to whatever `db` has pending. dispatch_refund below also commits `db`
    mid-function (to persist the dispatch-attempt marker before calling
    Safaricom), which commits whatever else the caller had pending on
    `db` too. No current caller holds other uncommitted changes on `db`
    at the point it calls dispatch_refund, but both of these are new
    couplings a future caller could trip on if that ever changes.

    This row lock is NOT what serialises two concurrent dispatch attempts
    for the same refund; dispatch_refund's own session-scoped advisory
    lock (_dispatch_lock, below) is what does that, and unlike a row lock,
    it survives dispatch_refund's own mid-function commit. This function
    still adds real value inside that advisory lock: it defends against a
    concurrent WRITER on a different lock path (a B2C result or timeout
    callback, which locks by originator_conversation_id, a different key
    than this refund's id) by blocking until any such writer's own commit
    completes, and populate_existing() then guarantees the fresh values
    are actually read into this object rather than a stale cached copy.
    """
    return (
        db.query(MpesaRefund)
        .filter(MpesaRefund.id == refund_id)
        .populate_existing()
        .with_for_update()
        .first()
    )


# Own namespace via the two-key pg_advisory_lock(int, int) form: Postgres
# treats a single-bigint-key lock and a two-int-key lock as entirely
# separate spaces, so this can never collide with
# subscription_billing.BILLING_LOCK_KEY (a single-key lock) or with this
# module's own pg_advisory_xact_lock calls elsewhere in this file (also
# single-key, and transaction-scoped rather than session-scoped). The
# second key is the refund id itself.
_DISPATCH_LOCK_NAMESPACE = 7825101

# pg_advisory_lock blocks with no timeout of its own, and this project sets
# no lock_timeout or statement_timeout anywhere else either. Without a
# bound, a stranded or genuinely slow dispatch (up to 15s OAuth plus 30s
# POST, doubled by client.py's 401-retry) turns a second caller's request
# into a hang rather than a clear rejection, and a cashier can retry a 409
# but a hung request tells them nothing. Chosen over pg_try_advisory_lock
# plus a manual retry loop: SET LOCAL lock_timeout lets Postgres itself
# enforce the bound on the blocking acquisition statement, no sleep loop
# to get wrong.
_DISPATCH_LOCK_TIMEOUT_MS = 5000


class DispatchLockTimeout(RuntimeError):
    """Another dispatch attempt for the same refund did not finish within
    _DISPATCH_LOCK_TIMEOUT_MS. Converted to a 409 by dispatch_refund."""


@contextmanager
def _dispatch_lock(db: Session, refund_id: int) -> Iterator[None]:
    """Session-scoped advisory lock spanning the WHOLE dispatch attempt for
    `refund_id`: the dispatch-attempt marker read and write, and the
    Safaricom call itself.

    THE PROPERTY A ROW LOCK CANNOT PROVIDE. A first implementation used
    two phases of SELECT ... FOR UPDATE, reasoning that phase 1 commits
    the marker before phase 2 re-locks for the network call. That is
    structurally broken, not merely buggy: the commit that makes the
    marker durable is the SAME commit that releases a row lock, so the
    row lock cannot span both. In practice this let a concurrent caller
    that observed had_prior_attempt=True (because it was unblocked by the
    first caller's marker-commit) skip the marker write entirely and race
    straight to the network call without ever committing, while the
    ORIGINAL caller, still holding only its captured (now stale)
    entry_status and had_prior_attempt, queued behind it. The genuinely
    second dispatch happened FIRST, Safaricom answered the true first
    caller's now-second attempt with a duplicate rejection, and it wrote
    Failed. pg_advisory_lock does not have this problem: it survives a
    commit on the connection that holds it (when that connection is not
    the one being committed, see below), so marker-write order can be
    made to equal dispatch order.

    Deliberately pg_advisory_lock, NOT pg_advisory_xact_lock (the variant
    used elsewhere in this module, for the result/timeout callback
    handlers). The xact variant releases at the next commit or rollback
    on the connection that holds it, which is exactly the mid-function
    commit this lock must survive. pg_advisory_lock only releases on an
    explicit pg_advisory_unlock or the backend disconnecting.

    DEDICATED CONNECTION, not `db`'s. This project already hit the
    failure mode of a session-scoped advisory lock taken on a pooled ORM
    session (see subscription_billing.billing_lock's docstring): a commit
    on that session returns its connection to the pool, and with
    QueuePool the lock then strands on a now-idle pooled connection
    forever, since a later pg_advisory_unlock issued on a DIFFERENT
    connection is a no-op; with PgBouncer transaction pooling the
    underlying server connection is not even pinned to `db` across a
    commit at all, so a lock taken "on db" would not reliably mean
    anything past the first commit either way. dispatch_refund below
    commits `db` more than once (the marker, then the final status
    write), so this lock cannot live on `db`'s connection. It opens its
    OWN connection instead, exactly like billing_lock, and for the
    identical reason: that connection's own transaction is kept open
    (never committed) for the life of this context manager.

    THE EXPLICIT UNLOCK IS THE REAL PROTECTION, NOT `conn.close()`. Under
    the default QueuePool, closing a connection returns it to the pool and
    issues a ROLLBACK; it does NOT disconnect the backend, and a ROLLBACK
    does not drop a session-level pg_advisory_lock (unlike the
    transaction-scoped locks elsewhere in this module, which a rollback
    does drop). A pooled connection can then be handed back out still
    holding this lock. So the explicit pg_advisory_unlock above is not a
    nicety alongside a reliable close, it is the only thing that actually
    releases the lock in the common case. If that explicit unlock itself
    fails, `conn.invalidate()` is called before closing: invalidate marks
    the underlying DBAPI connection as unusable and the pool discards it
    (a real disconnect) rather than returning it to the pool, which is
    what actually drops a lock the explicit unlock could not.

    BOUNDED WAIT. pg_advisory_lock blocks with no timeout of its own, and
    this dedicated connection is a SECOND connection out of the same
    tenant pool the request session already holds, held across the whole
    Safaricom round trip (up to 15s OAuth plus 30s POST, doubled by
    client.py's 401-retry). An unbounded wait would let a double-click, or
    a stranded lock, pin two connections and turn a second caller's
    request into a hang rather than a clear rejection. SET LOCAL
    lock_timeout bounds the acquisition statement itself to
    _DISPATCH_LOCK_TIMEOUT_MS; a caller that cannot acquire the lock in
    time gets DispatchLockTimeout (dispatch_refund converts this to a 409)
    instead of hanging.
    """
    conn = db.get_bind().connect()
    try:
        conn.begin()
        conn.execute(text(f"SET LOCAL lock_timeout = '{_DISPATCH_LOCK_TIMEOUT_MS}ms'"))
        try:
            conn.execute(
                text("SELECT pg_advisory_lock(:ns, :key)"),
                {"ns": _DISPATCH_LOCK_NAMESPACE, "key": refund_id},
            )
        except Exception as exc:
            # lock_timeout aborts the current transaction on this
            # connection; there is nothing to unlock (the lock was never
            # acquired) and nothing usable left to reuse, so discard the
            # connection outright rather than attempt any further
            # statement on it.
            conn.invalidate()
            logger.warning(
                "B2C dispatch lock for refund %s was not acquired within "
                "%sms; another dispatch attempt is likely still in "
                "progress.", refund_id, _DISPATCH_LOCK_TIMEOUT_MS,
            )
            raise DispatchLockTimeout(
                f"Another dispatch attempt for refund {refund_id} is still "
                "in progress; try again shortly."
            ) from exc

        try:
            yield
        finally:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:ns, :key)"),
                    {"ns": _DISPATCH_LOCK_NAMESPACE, "key": refund_id},
                )
            except Exception:
                logger.exception(
                    "Explicit pg_advisory_unlock failed for refund %s; "
                    "invalidating the dedicated dispatch-lock connection so "
                    "it is discarded rather than returned to the pool still "
                    "holding the lock.", refund_id,
                )
                conn.invalidate()
    finally:
        conn.close()


def dispatch_refund(
    db: Session, *, refund: MpesaRefund, callback_tenant: Optional[str] = None
) -> MpesaRefund:
    """Submit `refund` to Safaricom's B2C API.

    Safe to call more than once for the same refund: OriginatorConversationID
    was minted once at request_refund time and is reused unchanged here on
    every call, so a retried dispatch is recognised by Safaricom as the same
    instruction, never a second payout.

    The whole attempt (reading and, if unset, writing
    first_dispatch_attempted_at; resolving credentials and building the
    payload; the Safaricom call; recording the outcome) runs inside
    _dispatch_lock, a session-scoped advisory lock keyed on this refund's
    id (see that function's docstring for why a row lock cannot do this
    job). That is what makes marker-write order match dispatch order: a
    concurrent second caller for the SAME refund genuinely waits for this
    entire call to finish, rather than racing ahead of it the moment this
    call's marker-write commits.

    That lock has a bounded wait (_DISPATCH_LOCK_TIMEOUT_MS): a caller
    that cannot acquire it in time gets a 409 here, deliberately, rather
    than hanging until whatever is holding the lock finishes.
    """
    try:
        return _dispatch_refund_locked(db, refund=refund, callback_tenant=callback_tenant)
    except DispatchLockTimeout as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _dispatch_refund_locked(
    db: Session, *, refund: MpesaRefund, callback_tenant: Optional[str] = None
) -> MpesaRefund:
    """The actual dispatch, run under _dispatch_lock. Split out purely so
    dispatch_refund's own try/except can convert DispatchLockTimeout (raised
    by _dispatch_lock before this function's body ever starts) into a
    clean HTTPException, without wrapping this whole body in a second
    layer of indentation."""
    with _dispatch_lock(db, refund.id):
        refund = _lock_refund(db, refund.id)
        if refund is None:
            raise HTTPException(status_code=404, detail="Refund not found.")
        if refund.status not in ("Approved", "Processing"):
            raise HTTPException(
                status_code=409,
                detail=f"Refund is {refund.status}; nothing to dispatch.",
            )
        entry_status = refund.status
        had_prior_attempt = refund.first_dispatch_attempted_at is not None

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

        # The marker must mean "a request MAY have reached Safaricom", not
        # merely "dispatch_refund was called". Two distinct pre-flight
        # failures must both be excluded from it, and NEITHER opens a
        # socket to the B2C endpoint:
        #
        #   1. The circuit breaker being open. daraja_breaker is a
        #      process-wide singleton shared by every Daraja flow (STK,
        #      C2B, Transaction Status, B2C), so an unrelated STK failure
        #      can trip it. Checking it via client.access_token() alone is
        #      NOT enough: access_token() returns a cached token WITHOUT
        #      consulting the breaker at all when the cache is warm
        #      (tokens live about an hour, so a live process is warm
        #      almost always), meaning the breaker would only be hit for
        #      the first time inside client.post, AFTER the marker below
        #      is committed. So the breaker's own state is read here,
        #      explicitly, independent of whether the token call would
        #      have touched it.
        #   2. Obtaining a fresh access token failing on its own (a cold
        #      cache: bad credentials, or the OAuth endpoint unreachable).
        #
        # Setting the marker before either of these would let a
        # misconfigured hospital's very first attempt, or simply an
        # unrelated STK failure sharing the same breaker, permanently mark
        # had_prior_attempt True for a refund that was NEVER dispatched
        # anywhere: every later dispatch would then read a genuine,
        # definitive rejection as "maybe already accepted" and resolve to
        # Processing forever, holding the balance and the rolling cap
        # hostage with no in-product recovery, since retry-dispatch is
        # gated to Approved and this refund would never be marked Failed
        # to release it. So both checks happen FIRST, outside the
        # marker's scope entirely; only once both pass does a request
        # become imminent.
        if daraja_breaker.state == daraja_breaker.OPEN:
            logger.warning(
                "B2C dispatch for refund %s: Daraja circuit breaker is open; "
                "no request attempted.",
                refund.id,
            )
            raise DarajaError(
                "Daraja temporarily unavailable (circuit open)", status_code=503,
            )

        try:
            client.access_token()
        except DarajaError as exc:
            logger.warning(
                "B2C dispatch for refund %s could not obtain a Daraja access "
                "token; no request was sent: %s",
                refund.id, safe_repr(str(exc)),
            )
            raise

        if not had_prior_attempt:
            refund.first_dispatch_attempted_at = datetime.now(timezone.utc)
            db.commit()

            # Second line of defence, per the coordinator's ruling: re-fetch
            # and re-validate against the row this transaction actually
            # committed, rather than trusting the entry_status captured
            # above to still be current. Under _dispatch_lock this cannot
            # have changed from a concurrent dispatch_refund call (the
            # advisory lock excludes those entirely), but a B2C result or
            # timeout callback locks by a DIFFERENT key
            # (originator_conversation_id) and could in principle still
            # land here.
            refund = _lock_refund(db, refund.id)
            if refund is None:
                raise HTTPException(status_code=404, detail="Refund not found.")
            if refund.status not in ("Approved", "Processing"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Refund is {refund.status}; nothing to dispatch.",
                )
            entry_status = refund.status

        try:
            response = client.post("/mpesa/b2c/v3/paymentrequest", payload)
        except DarajaError as exc:
            # The request never definitively reached Safaricom: a network
            # error, a 5xx, or the circuit breaker open. This is NOT the same
            # fact as Safaricom rejecting it. Nothing is known to be in flight,
            # so the refund is left exactly where it was (Approved, or still
            # Processing on a retry of an already-accepted one) and can be
            # dispatched again safely, because OriginatorConversationID never
            # changes between attempts. The marker (set above, before this
            # call) still correctly records that an attempt was made.
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
        .populate_existing()
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
