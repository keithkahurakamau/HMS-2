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
     know yet", never failure). Resolved by ASKING (a genuine Transaction
     Status query), never by sending anything.
  4. MpesaRefund stuck Approved with first_dispatch_attempted_at set (a
     crash between the marker commit and the wire, or a breaker trip in a
     narrow window). retry-dispatch's route already covers this shape (it
     is gated on status == "Approved" alone, with no check on the marker),
     so a human already has an in-product recovery for it. This module
     does NOT act automatically here at all: it only surfaces the row so a
     human checks the Safaricom portal and uses that route deliberately.
     See _reconcile_tenant's docstring for why automating a second
     dispatch here specifically would be unsafe.
  5. Anything unresolved after 24 hours, which must surface to a human
     instead of being retried forever.

ACCEPTED ONE-WAY DOOR: once a row is surfaced past 24 hours, this job
never asks Safaricom about it again automatically (the age check's
`continue` in each per-category loop below is permanent: age only grows).
A late, genuine, non-zero verdict arriving after that point is therefore
NOT picked up on its own; a human must resolve it from the surfaced row
(or a fresh manual STK Query / retry-dispatch action). This is a
deliberate consequence of "surface, do not retry forever", written down
here rather than left to be rediscovered: the alternative, resuming
automatic queries on an already-surfaced row, would silently undermine
the "notify once, not every cycle" guarantee (I2) the moment that row's
last verdict finally arrived.

THE RULE. Only Safaricom's own verdict may resolve a payment. Never a local
inference, never a timer, never an assumption from elapsed time, and never
a payment instruction sent in place of a question. Every operation in
reconcile_queries.py either gets a real answer from Safaricom and routes it
through the SAME cross-checked handlers apply_stk_callback already uses (the
amount comparison, the receipt cross-check, the replay guards), or it
leaves the row exactly as it is and, past its threshold, tells a human.
Nothing here ever writes Success, Failed, Quarantined, Completed, or
Reversed directly.

SYNCHRONOUS VS ASYNCHRONOUS, spelled out because it changes what "resolved"
means for each case (full reasoning lives in each requery_*/surface_*
function's own docstring in reconcile_queries.py; this is the summary):

  * Case 1 (STK Pending) is SYNCHRONOUS for a genuine, final, non-zero
    ResultCode: requery_stk can settle or fail the row in this same run.
    A bare ResultCode 0 is NOT such a verdict (STK Query never carries
    CallbackMetadata) and is left untouched, so Safaricom's own retry of
    the real callback can still settle it safely later.
  * Case 2 (C2B Unverified) is ASYNCHRONOUS: query_transaction_status only
    returns an acknowledgment. The verdict, if any, lands later at the
    existing status/result callback. This job re-asks at most once per
    outstanding query and never resolves this case itself.
  * Case 3 (refund Processing) is ASYNCHRONOUS, resolved by asking, not by
    sending: Daraja's TransactionStatusQuery accepts an
    OriginalConversationID in place of a receipt, and a Processing refund
    holds conversation_id precisely because Safaricom already accepted and
    named that instruction. The query's own acknowledgment is recorded on
    the dedicated status_query_conversation_id column, never on
    conversation_id itself. The real verdict, when Safaricom sends one,
    is routed to refund_status.handle_transaction_status_result_for_refund,
    which records and notifies a human and never writes Completed or
    Failed.
  * Case 4 (refund Approved with a dispatch marker) is not resolved by
    this job at all. It is surfaced immediately past its threshold and
    left for a human, who already has a real recovery (retry-dispatch).
    Re-dispatching automatically here would be indistinguishable, from
    Safaricom's side, from a genuinely new payout: a case-4 refund has no
    conversation_id yet for _record_conversation_id's double-dispatch
    alarm to compare a fresh acceptance against, so the alarm that
    protects every other retry path in this codebase cannot fire here.

MULTI-TENANT. Unlike subscription billing (master DB only), Daraja
transactions and refunds live one database per tenant. This job takes a
SINGLE global advisory lock (reconcile_lock, on a dedicated master-DB
connection, same discipline as subscription_billing.billing_lock) purely
to serialise the ORCHESTRATION: only one reconciliation run, cron or a
future "run now" button, proceeds at a time. It does not need a per-tenant
lock in addition: tenants are visited one at a time within that single run.

A single run also bounds how much of that time any one tenant, or the run
as a whole, can consume: see _RowBudget and the tenant start-offset
rotation in run_reconciliation, both added so a tenant with many stuck
rows cannot hold RECONCILE_LOCK_KEY for the better part of an hour while
tenants later in the registry are never reached.

FAILURES ARE NEVER SILENT. ReconcileRunResult mirrors BillingRunResult: one
line per tenant or row that could not even be attempted, so a run that logs
"0 resolved" while every tenant errored out is visibly different from a
run that genuinely found nothing to do. "We could not even ask Safaricom"
(a missing credential, a Daraja outage) is exactly such a failure, and is
never the same fact as "Safaricom answered and had no verdict yet": see
reconcile_queries.py's module docstring for how that distinction is kept.
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
# QueueTimeOutURL fires well inside that window, so a query that is still
# genuinely outstanding at 5 minutes almost never is; requery_c2b's own
# outstanding-query guard is what actually prevents an overwrite past that,
# not this threshold.
PENDING_STALE_AFTER = timedelta(minutes=5)
UNVERIFIED_STALE_AFTER = timedelta(minutes=5)
REFUND_STALE_AFTER = timedelta(minutes=10)
SURFACE_AFTER = timedelta(hours=24)

# Bounds how many stuck rows a single run will touch, across every tenant
# combined. Each row is at worst one Daraja network round trip (OAuth plus
# the query itself, each with client.py's own timeout and 401-retry), so an
# unbounded per-run row count turns one tenant with many stuck rows into a
# run that holds RECONCILE_LOCK_KEY, and this process, for the better part
# of an hour. A run that hits the budget simply stops for THIS cycle and
# picks up where it left off 15 minutes later: nothing here is lost, only
# deferred, and the per-row 5/10-minute thresholds mean nothing deferred by
# one cycle becomes newly ineligible by the next.
#
# KNOWN GAP (New-7, not fixed this round): the budget is spent in a fixed
# order WITHIN one tenant, case 1 (STK) before case 2 (C2B) before cases 3
# and 4 (refunds). A tenant with 200+ stuck STK rows can therefore exhaust
# the entire budget before this tenant's own C2B or refund rows are ever
# looked at, every single run, not just once. The cross-tenant rotation
# above does not help here: it only reorders which TENANT goes first, not
# which CASE within a tenant does. A fair fix would interleave the four
# categories (round-robin one row from each in turn) rather than draining
# them in sequence; left as a follow-up.
MAX_ROWS_PER_RUN = 200


class _RowBudget:
    """Shared, mutable row counter threaded through a single run. Not a
    dataclass field on ReconcileRunResult: this is a resource the run
    consumes, not a fact about what it did."""

    def __init__(self, remaining: int):
        self.remaining = remaining

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass
class ReconcileRunResult:
    """What a reconciliation run actually did. Modelled on BillingRunResult
    for the identical reason: "0 resolved" must never be the same shape as
    "everything failed"."""
    transactions_resolved: int = 0     # STK Pending rows reaching a genuine, final verdict this run
    stk_still_pending: int = 0         # STK Pending rows asked again; Safaricom had no verdict yet
    c2b_requeried: int = 0             # C2B Unverified rows re-asked; answer, if any, arrives later
    refunds_requeried: int = 0         # Processing refunds asked again; answer, if any, arrives later
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
    session: Session, tenant_db_name: str, *, now: datetime, budget: _RowBudget,
) -> tuple[int, int, int, int, list[str], list[str]]:
    """Run every reconciliation check against one tenant's own Daraja
    tables. Returns (transactions_resolved, stk_still_pending,
    c2b_requeried, refunds_requeried, surfaced, failures): plain values,
    not a dataclass, so this function stays independent of
    ReconcileRunResult's shape.

    Every row is wrapped in its own try/except: one bad row (a bug, a
    poisoned session, an unexpected exception, OR a genuine "could not ask
    Safaricom" failure now that reconcile_queries.py's requery_* functions
    no longer swallow those, see reconcile_queries.py's module docstring)
    must not stop the rest of this tenant's rows or any other tenant's
    run, the same discipline subscription_billing.ensure_invoices uses
    per-subscription; it must, however, still be recorded, which this
    try/except's own `failures.append` is what actually does.

    Stops early, mid-tenant, once `budget` is exhausted: see
    MAX_ROWS_PER_RUN's own docstring.
    """
    transactions_resolved = 0
    stk_still_pending = 0
    c2b_requeried = 0
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
            if not budget.take():
                break
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
                stk_still_pending += 1
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
            if not budget.take():
                break
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
            if requery_c2b(session, txn, callback_tenant=tenant_db_name):
                c2b_requeried += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation: C2B Unverified row %s failed", txn.id)
            failures.append(f"{tenant_db_name}: transaction {txn.id}: {exc}")

    # Case 3: refunds stuck Processing. Asked via a genuine Transaction
    # Status query (requery_refund), never re-dispatched: see
    # reconcile_queries.requery_refund's docstring and
    # routes/mpesa_refunds.py's retry-dispatch route, which says in
    # writing that a stuck Processing refund is resolved by asking
    # Safaricom directly, not by dispatching again. This module must never
    # contradict that.
    processing_refunds = (
        session.query(MpesaRefund)
        .filter(
            MpesaRefund.status == "Processing",
            MpesaRefund.first_dispatch_attempted_at.isnot(None),
        )
        .all()
    )
    for refund in processing_refunds:
        try:
            age = _age(refund.first_dispatch_attempted_at, now)
            if age is None or age < REFUND_STALE_AFTER:
                continue
            if not budget.take():
                break
            if age >= SURFACE_AFTER:
                surface_refund(
                    session, refund,
                    reason=(
                        "Refund stuck Processing for over 24 hours since its "
                        "first dispatch attempt"
                    ),
                )
                surfaced.append(f"{tenant_db_name}: refund {refund.id} (Processing > 24h)")
                continue
            if not refund.conversation_id:
                # New-4: a Processing refund with no conversation_id at all
                # (a reachable gap in b2c.py's own status transitions, see
                # requery_refund's own guard for the same case) has no id
                # for a Transaction Status query to ask about. Asking
                # anyway would raise on every run, a permanent non-outage
                # failure that would drown out I1's real signal. Surface
                # it immediately rather than waiting out the full 24 hours
                # for a condition that will never resolve on its own.
                surface_refund(
                    session, refund,
                    reason=(
                        "Refund stuck Processing with no ConversationID recorded; "
                        "there is no id to ask Safaricom about. Check the "
                        "Safaricom portal directly."
                    ),
                )
                surfaced.append(f"{tenant_db_name}: refund {refund.id} (Processing, no conversation_id)")
                continue
            if requery_refund(session, refund, callback_tenant=tenant_db_name):
                refunds_requeried += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation: refund %s failed", refund.id)
            failures.append(f"{tenant_db_name}: refund {refund.id}: {exc}")

    # Case 4: refunds stuck Approved with a dispatch marker already set.
    # NOT resolved automatically, at all: see this module's own docstring
    # and reconcile_queries.py's for why a case-4 refund is exactly the
    # shape _record_conversation_id's double-dispatch alarm cannot protect
    # (it has no conversation_id yet to compare a fresh acceptance
    # against), so an automatic re-dispatch here would be indistinguishable
    # from Safaricom's side from a genuinely new payout. retry-dispatch
    # already covers this shape for a human (gated on status == "Approved"
    # alone); this job's only role is to make sure a human notices.
    approved_with_marker = (
        session.query(MpesaRefund)
        .filter(
            MpesaRefund.status == "Approved",
            MpesaRefund.first_dispatch_attempted_at.isnot(None),
        )
        .all()
    )
    for refund in approved_with_marker:
        try:
            age = _age(refund.first_dispatch_attempted_at, now)
            if age is None or age < REFUND_STALE_AFTER:
                continue
            if not budget.take():
                break
            surface_refund(
                session, refund,
                reason=(
                    "Refund stuck Approved with a dispatch attempt already "
                    "marked; check the Safaricom portal, then use "
                    "retry-dispatch deliberately if appropriate"
                ),
            )
            surfaced.append(f"{tenant_db_name}: refund {refund.id} (Approved-with-marker)")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reconciliation: refund %s failed", refund.id)
            failures.append(f"{tenant_db_name}: refund {refund.id}: {exc}")

    return (
        transactions_resolved, stk_still_pending, c2b_requeried, refunds_requeried,
        surfaced, failures,
    )


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
    active tenant in turn, bounded by MAX_ROWS_PER_RUN combined across all
    of them.

    Tenant order is rotated by the current wall-clock minute, not always
    read in the same registry order: without this, a tenant early in the
    master registry that regularly has enough stuck rows to exhaust the
    row budget on its own would starve every tenant that sorts after it,
    forever, since each run would restart from the same first tenant.
    Rotating by the minute is stateless (no cursor to persist between
    cron invocations) and spreads the budget round-robin over time.

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
        if tenant_rows:
            offset = int(run_now.timestamp() // 60) % len(tenant_rows)
            tenant_rows = tenant_rows[offset:] + tenant_rows[:offset]

        budget = _RowBudget(MAX_ROWS_PER_RUN)
        result = ReconcileRunResult()
        for tenant in tenant_rows:
            if budget.remaining <= 0:
                logger.warning(
                    "Reconciliation: row budget (%d) exhausted; stopping this "
                    "run before tenant %s. The next cycle picks up where this "
                    "one left off.", MAX_ROWS_PER_RUN, tenant.db_name,
                )
                break

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
                    resolved, still_pending, c2b_requeried, refund_requeried, surfaced, failures,
                ) = _reconcile_tenant(session, tenant.db_name, now=run_now, budget=budget)
                result.transactions_resolved += resolved
                result.stk_still_pending += still_pending
                result.c2b_requeried += c2b_requeried
                result.refunds_requeried += refund_requeried
                result.surfaced.extend(surfaced)
                result.failures.extend(failures)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Reconciliation failed outright for tenant %s", tenant.db_name)
                result.failures.append(f"tenant {tenant.tenant_id} ({tenant.db_name}): {exc}")
            finally:
                session.close()

        return result
