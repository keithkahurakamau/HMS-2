"""Reconciliation: the safety net every earlier Daraja task deferred to.

Six times across this migration, a design chose "leave it unresolved and let
reconciliation ask Safaricom" over "guess locally":

  1. MpesaTransaction stuck Pending (reservation.py deleted a local expiry
     timer that guessed a push's outcome; a stale Pending now correctly
     BLOCKS a retry until this module resolves it via STK Query).
  2. MpesaTransaction stuck Unverified (a C2B confirmation posts nothing
     until Safaricom corroborates it; if the Transaction Status result
     never arrives, the row sits Unverified forever unless re-asked).
  3. MpesaRefund stuck Processing (a B2C queue timeout means "we do not
     know yet", never failure).
  4. MpesaRefund stuck Approved with first_dispatch_attempted_at set (a
     crash between the marker commit and the wire, or a breaker trip in a
     narrow window; retry-dispatch's route is deliberately gated away from
     this shape, so today it has no in-product recovery besides this job).
  5. Anything unresolved after 24 hours, which must surface to a human
     instead of being retried forever.

THE RULE. Only Safaricom's own verdict may resolve a payment. Never a local
inference, never a timer, never an assumption from elapsed time. Every
operation in reconcile_queries.py either gets a real answer from Safaricom
and routes it through the SAME cross-checked handlers apply_stk_callback and
dispatch_refund already use (the amount comparison, the receipt
cross-check, the replay guards), or it leaves the row exactly as it is and,
past 24 hours, tells a human. Nothing here ever writes Success, Failed,
Quarantined, or Completed directly.

SYNCHRONOUS VS ASYNCHRONOUS, spelled out because it changes what "resolved"
means for each case:

  * Case 1 (STK Pending) is genuinely synchronous. STK Query answers in the
    same HTTP response, so requery_stk can settle, fail, or quarantine a
    row before this job moves on to the next one. Caveat: Daraja's STK
    Query response never carries CallbackMetadata (Amount,
    MpesaReceiptNumber), only ResultCode/ResultDesc. A ResultCode 0
    response therefore still has no receipt to settle against, and
    apply_stk_callback correctly quarantines it (see settlement.py's
    "no MpesaReceiptNumber despite ResultCode 0" step) rather than
    fabricating one. That is the existing, correct behaviour for
    "Safaricom confirms this succeeded but we cannot safely credit it
    without a receipt", not a defect introduced here.
  * Case 2 (C2B Unverified) is genuinely asynchronous, exactly as
    status.py's own module docstring insists: query_transaction_status
    only ever returns an acknowledgment (a fresh ConversationID). The
    verdict, if Safaricom ever sends one, arrives later at the existing
    /api/payments/mpesa/status/result callback. This job's job is only to
    re-ask and record the new correlation id; it can never itself resolve
    this case.
  * Cases 3 and 4 (refunds) are also asynchronous, and for a reason worth
    stating plainly: Safaricom's TransactionStatusQuery is keyed on a
    receipt (TransactionID) a Processing B2C payout, by definition, does
    not have yet, and this codebase has no result-callback handler that
    could correlate a fresh status query's own ConversationID back to a
    MpesaRefund row without a schema change (handle_transaction_status_result
    is hard-wired to MpesaTransaction). Firing that query anyway, with
    nowhere for its answer to land, is exactly the "looks like progress
    while accomplishing nothing" shape status.py's own account_balance
    refuses outright rather than fake. So this module asks Safaricom the
    one way that both reaches it for real and has a working answer path:
    it calls dispatch_refund again. OriginatorConversationID is minted
    once and reused unchanged, so Safaricom recognises this as the SAME
    instruction, never a second payout, and dispatch_refund's own,
    already-tested branches decide everything from here (see
    reconcile_queries.requery_refund's docstring). The real verdict, if
    one ever arrives, still only lands at the existing, already-wired
    /api/payments/mpesa/b2c/result and /b2c/timeout callbacks.

MULTI-TENANT. Unlike subscription billing (master DB only), Daraja
transactions and refunds live one database per tenant. This job takes a
SINGLE global advisory lock (reconcile_lock, on a dedicated master-DB
connection, same discipline as subscription_billing.billing_lock) purely
to serialise the ORCHESTRATION: only one reconciliation run, cron or a
future "run now" button, proceeds at a time. It does not need a per-tenant
lock in addition: tenants are visited one at a time within that single run.

FAILURES ARE NEVER SILENT. ReconcileRunResult mirrors BillingRunResult: one
line per tenant or row that could not even be attempted, so a run that logs
"0 resolved" while every tenant errored out is visibly different from a
run that genuinely found nothing to do.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config.database import get_tenant_engine
from app.models.master import Tenant
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.reconcile_queries import (
    TXN_TERMINAL,
    requery_c2b,
    requery_refund,
    requery_stk,
    surface_refund,
    surface_transaction,
)

logger = logging.getLogger("daraja_reconcile")

# Arbitrary but fixed, own single-bigint pg_advisory_lock namespace: must
# never collide with subscription_billing.BILLING_LOCK_KEY (7825001) or
# b2c.py's _DISPATCH_LOCK_NAMESPACE (7825101, a two-key lock, a different
# space again).
RECONCILE_LOCK_KEY = 7825201

# "Pending over 5 minutes", "Processing over 10 minutes", and "surface after
# 24 hours" straight from the design doc's Reconciliation section. Unverified
# C2B rows get the same 5-minute grace as Pending: Daraja's own
# QueueTimeOutURL fires well inside that window, so re-asking sooner would
# risk overwriting a still-in-flight query's own conversation_id before its
# answer (or its timeout) has had a chance to arrive.
PENDING_STALE_AFTER = timedelta(minutes=5)
UNVERIFIED_STALE_AFTER = timedelta(minutes=5)
REFUND_STALE_AFTER = timedelta(minutes=10)
SURFACE_AFTER = timedelta(hours=24)


@dataclass
class ReconcileRunResult:
    """What a reconciliation run actually did. Modelled on BillingRunResult
    for the identical reason: "0 resolved" must never be the same shape as
    "everything failed"."""
    transactions_resolved: int = 0     # STK Pending rows settled, failed, or quarantined this run
    transactions_requeried: int = 0    # C2B Unverified rows re-asked; answer, if any, arrives later
    refunds_requeried: int = 0         # Refunds re-dispatched; answer, if any, arrives later
    surfaced: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    # True only when this run did not execute at all because another run
    # already held reconcile_lock. A skipped run is correct, not a failure.
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return not self.failures


@contextmanager
def reconcile_lock(db: Session) -> Iterator[bool]:
    """Serialise reconciliation runs with a Postgres advisory lock.

    Copied from subscription_billing.billing_lock, including the fix
    documented in its own docstring (commit 6560dae): the lock is taken on
    a DEDICATED connection held open (never committed) for the whole run,
    not on `db`. _reconcile_tenant below commits once per row it touches
    (apply_stk_callback's own commit, or reconcile_queries' own commits
    after a requery); a lock taken on `db` would strand on a now-idle
    pooled connection the moment the first row commits, exactly the bug
    that once hit billing_lock. THE EXPLICIT UNLOCK IS THE REAL PROTECTION,
    NOT conn.close(): under the default QueuePool, closing a connection
    returns it to the pool with a ROLLBACK, which does not drop a
    session-level pg_advisory_lock. If the explicit unlock itself fails,
    conn.invalidate() is called before closing, so the pool discards the
    connection instead of handing it back out still holding the lock. A
    stranded lock here disables reconciliation silently and permanently,
    which would re-break every one of the five cases this module exists to
    close.

    Acquisition is non-blocking (pg_try_advisory_lock): a caller that finds
    the lock held skips its run rather than waiting.
    """
    conn = db.get_bind().connect()
    try:
        conn.begin()
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": RECONCILE_LOCK_KEY}
            ).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": RECONCILE_LOCK_KEY}
                    )
                except Exception:
                    logger.exception(
                        "Explicit pg_advisory_unlock failed; invalidating the "
                        "dedicated reconcile_lock connection so it is discarded "
                        "rather than returned to the pool still holding the lock."
                    )
                    conn.invalidate()
    finally:
        conn.close()


def _default_tenant_session(db_name: str) -> Session:
    engine = get_tenant_engine(db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _age(reference: Optional[datetime], now: datetime) -> Optional[timedelta]:
    """now - reference, coercing a naive `reference` to UTC first.

    Postgres returns an aware datetime for a timestamptz column under the
    normal driver path, but a defensive coercion costs nothing and this
    project has hit exactly this naive-vs-aware class of bug before (the
    locked-account 500: see auth.py's lockout comparison)."""
    if reference is None:
        return None
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return now - reference


def _reconcile_tenant(
    session: Session, tenant_db_name: str, *, now: datetime,
) -> tuple[int, int, int, list[str], list[str]]:
    """Run every reconciliation check against one tenant's own Daraja
    tables. Returns (transactions_resolved, transactions_requeried,
    refunds_requeried, surfaced, failures): plain values, not a dataclass,
    so this function stays independent of ReconcileRunResult's shape.

    Every row is wrapped in its own try/except: one bad row (a bug, a
    poisoned session, an unexpected exception) must not stop the rest of
    this tenant's rows or any other tenant's run, the same discipline
    subscription_billing.ensure_invoices uses per-subscription.
    """
    transactions_resolved = 0
    transactions_requeried = 0
    refunds_requeried = 0
    surfaced: list[str] = []
    failures: list[str] = []

    # Case 1: STK Pending.
    pending = (
        session.query(MpesaTransaction)
        .filter(
            MpesaTransaction.status == "Pending",
            MpesaTransaction.transaction_type == "STK",
            MpesaTransaction.checkout_request_id.isnot(None),
        )
        .all()
    )
    for txn in pending:
        try:
            age = _age(txn.transaction_date, now)
            if age is None or age < PENDING_STALE_AFTER:
                continue
            if age >= SURFACE_AFTER:
                surface_transaction(
                    session, txn,
                    reason=(
                        f"STK push stuck Pending for over 24 hours "
                        f"(checkout {txn.checkout_request_id})"
                    ),
                )
                surfaced.append(f"{tenant_db_name}: transaction {txn.id} (Pending > 24h)")
                continue
            before_status = txn.status
            requery_stk(session, txn)
            if txn.status != before_status and txn.status in TXN_TERMINAL:
                transactions_resolved += 1
            else:
                transactions_requeried += 1
        except Exception as exc:  # noqa: BLE001, one bad row must not stop the rest
            logger.exception("Reconciliation: STK Pending row %s failed", txn.id)
            failures.append(f"{tenant_db_name}: transaction {txn.id}: {exc}")

    # Case 2: C2B Unverified.
    unverified = (
        session.query(MpesaTransaction)
        .filter(MpesaTransaction.status == "Unverified")
        .all()
    )
    for txn in unverified:
        try:
            age = _age(txn.transaction_date, now)
            if age is None or age < UNVERIFIED_STALE_AFTER:
                continue
            if age >= SURFACE_AFTER:
                surface_transaction(
                    session, txn,
                    reason=(
                        f"C2B receipt stuck Unverified for over 24 hours "
                        f"(receipt {txn.receipt_number})"
                    ),
                )
                surfaced.append(f"{tenant_db_name}: transaction {txn.id} (Unverified > 24h)")
                continue
            requery_c2b(session, txn, callback_tenant=tenant_db_name)
            transactions_requeried += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation: C2B Unverified row %s failed", txn.id)
            failures.append(f"{tenant_db_name}: transaction {txn.id}: {exc}")

    # Cases 3 & 4: refunds stuck Processing, or Approved with a dispatch
    # marker already set. Both share one clock (first_dispatch_attempted_at)
    # and one recovery mechanism (requery_refund); see its docstring.
    stuck_refunds = (
        session.query(MpesaRefund)
        .filter(
            MpesaRefund.first_dispatch_attempted_at.isnot(None),
            MpesaRefund.status.in_(("Processing", "Approved")),
        )
        .all()
    )
    for refund in stuck_refunds:
        try:
            age = _age(refund.first_dispatch_attempted_at, now)
            if age is None or age < REFUND_STALE_AFTER:
                continue
            if age >= SURFACE_AFTER:
                surface_refund(
                    session, refund,
                    reason=(
                        f"Refund stuck {refund.status} for over 24 hours since "
                        "its first dispatch attempt"
                    ),
                )
                surfaced.append(f"{tenant_db_name}: refund {refund.id} ({refund.status} > 24h)")
                continue
            requery_refund(session, refund, callback_tenant=tenant_db_name)
            refunds_requeried += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation: refund %s failed", refund.id)
            failures.append(f"{tenant_db_name}: refund {refund.id}: {exc}")

    return transactions_resolved, transactions_requeried, refunds_requeried, surfaced, failures


def run_reconciliation(
    master_db: Session,
    *,
    now: Optional[datetime] = None,
    tenants: Optional[list] = None,
    session_for_tenant: Optional[Callable[[str], Session]] = None,
) -> ReconcileRunResult:
    """The one reconciliation entry point the cron (and, eventually, an
    operator console button, the same shape run_billing_cycle already
    offers) should call. Serialises on reconcile_lock, then visits every
    active tenant in turn.

    `tenants` and `session_for_tenant` are injectable purely for tests
    (this project has no per-tenant test database infrastructure; tests
    point a single fake "tenant" at the same Postgres database `master_db`
    already uses). Production leaves both at their defaults: every active
    tenant from the master registry, opened via get_tenant_engine.
    """
    with reconcile_lock(master_db) as acquired:
        if not acquired:
            return ReconcileRunResult(
                failures=["reconciliation run already in progress, skipped"],
                skipped=True,
            )

        run_now = now or datetime.now(timezone.utc)
        open_session = session_for_tenant or _default_tenant_session
        tenant_rows = (
            tenants if tenants is not None else
            master_db.query(Tenant).filter(Tenant.is_active == True)  # noqa: E712
            .order_by(Tenant.tenant_id).all()
        )

        result = ReconcileRunResult()
        for tenant in tenant_rows:
            try:
                session = open_session(tenant.db_name)
            except Exception as exc:  # noqa: BLE001, one bad tenant must not stop the rest
                logger.exception(
                    "Reconciliation: could not open a session for tenant %s", tenant.db_name
                )
                result.failures.append(
                    f"tenant {tenant.tenant_id} ({tenant.db_name}): could not open session: {exc}"
                )
                continue

            try:
                (
                    resolved, requeried, refund_requeried, surfaced, failures,
                ) = _reconcile_tenant(session, tenant.db_name, now=run_now)
                result.transactions_resolved += resolved
                result.transactions_requeried += requeried
                result.refunds_requeried += refund_requeried
                result.surfaced.extend(surfaced)
                result.failures.extend(failures)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Reconciliation failed outright for tenant %s", tenant.db_name)
                result.failures.append(f"tenant {tenant.tenant_id} ({tenant.db_name}): {exc}")
            finally:
                session.close()

        return result
