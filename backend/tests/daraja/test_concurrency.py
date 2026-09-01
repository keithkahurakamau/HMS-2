"""Many terminals, one till: the partial unique index that stops two
terminals both pushing an STK prompt for the same invoice, and the
idempotency mechanism (existing, reused, not reinvented) that stops one
cashier's double-click or retried request from pushing twice.

The two-terminal test is GENUINELY concurrent: two threads, two separate
Sessions each on their own connection, and a threading.Barrier so both
reach the reservation insert at the same moment. A sequential test would
prove nothing here: the bug only exists when two inserts overlap.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.stk import initiate_stk_push
from app.models.mpesa import MpesaTransaction
from app.config.settings import settings
from tests.daraja.conftest import make_invoice, make_mpesa_config


@pytest.fixture(autouse=True)
def _clear_token_cache():
    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    yield


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def _fake_oauth(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )


def _fake_stk_success(monkeypatch, counter: dict, lock: threading.Lock):
    """Counts every actual Daraja STK request. The count, not just the row
    count in the database, is the real proof that a second terminal never
    causes a second prompt on the patient's handset."""
    def fake_post(url, **kw):
        with lock:
            counter["n"] += 1
            n = counter["n"]
        return FakeResponse(200, {
            "MerchantRequestID": f"mr-{n}",
            "CheckoutRequestID": f"ws_CO_concurrent_{n}",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        })
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)


def test_two_terminals_pushing_the_same_invoice_produce_one_pending_transaction(
    db, _engine, monkeypatch
):
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)

    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()  # visible to the two independent connections below

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=Decimal("500.00"),
                invoice_id=invoice.invoice_id,
                callback_tenant="mayoclinic_db",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"unexpected errors from concurrent pushes: {errors}"
    assert len(results) == 2

    # The proof that matters: Daraja was only ever asked once. Two calls
    # here would mean the patient's handset got two prompts, which is
    # exactly the failure this guard exists to prevent.
    assert call_count["n"] == 1

    pending = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.invoice_id == invoice.invoice_id,
            MpesaTransaction.status == "Pending",
        )
        .all()
    )
    assert len(pending) == 1


def test_the_second_terminal_receives_the_existing_transaction_not_an_error(
    db, _engine, monkeypatch
):
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)

    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=Decimal("500.00"),
                invoice_id=invoice.invoice_id,
                callback_tenant="mayoclinic_db",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors
    assert len(results) == 2
    # Both terminals get a normal dict back: a checkout_request_id and a
    # transaction_id, never a raised error. Exactly one of them reflects
    # the fresh push; the other is told a prompt is already on its way and
    # points at the SAME transaction.
    txn_ids = {r["transaction_id"] for r in results}
    assert len(txn_ids) == 1
    already_pending_flags = [r.get("already_pending", False) for r in results]
    assert sorted(already_pending_flags) == [False, True]


def test_an_unrelated_integrity_error_is_not_mistaken_for_a_pending_conflict(db, monkeypatch):
    """_reserve_pending must treat ONLY the two partial unique indexes as
    "someone else already has this slot". An invoice_id that does not
    exist violates the invoices FK instead, and swallowing that behind
    the generic 409 "try again shortly" would tell the caller to retry a
    request that can never succeed, hiding a real bug (a stale or
    fabricated invoice id) behind a message that looks like ordinary
    contention."""
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)

    with pytest.raises(IntegrityError):
        initiate_stk_push(
            db,
            phone_number="0712345678",
            amount=Decimal("100.00"),
            invoice_id=999999999,  # does not exist: violates the FK, not the pending guard
            callback_tenant="mayoclinic_db",
        )
    assert call_count["n"] == 0


def test_a_stale_pending_transaction_does_not_block_a_genuine_retry(db, monkeypatch):
    """Name kept from the original spec list; the CONTRACT changed after a
    reviewed regression. An earlier version aged a stale Pending row out to
    a local "Expired" status so a retry was never blocked. That is a guess
    about the original push's outcome, and apply_stk_callback only ever
    matches status == "Pending": a late genuine success callback for the
    "Expired" row fell into the unrecognised branch and settled nothing,
    reproduced end to end as PAYMENT ROWS: 0, invoice still Pending, while
    money had actually reached the till.

    The correct contract, per the design doc: a stale Pending BLOCKS a
    retry (the second cashier is told a prompt is already on its way,
    which is true) until Task 8's reconciliation job resolves it by asking
    Safaricom via STK Query, never by guessing locally. This test asserts
    that: the retry does NOT push a second prompt, is NOT treated as an
    error, and the stale row is left exactly as it was, still Pending,
    for reconciliation to resolve later.
    """
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)

    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))

    # A Pending row from a push whose handset prompt has long since expired.
    stale = MpesaTransaction(
        invoice_id=invoice.invoice_id,
        phone_number="254712345678",
        amount=Decimal("500.00"),
        checkout_request_id="ws_CO_dead_prompt",
        merchant_request_id="mr_dead",
        status="Pending",
        transaction_type="STK",
    )
    db.add(stale)
    db.flush()
    stale.transaction_date = datetime.now(timezone.utc) - timedelta(hours=6)
    db.commit()

    result = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("500.00"),
        invoice_id=invoice.invoice_id,
        callback_tenant="mayoclinic_db",
    )

    # Blocked, correctly: no second prompt was sent, and the caller is told
    # a prompt is already on its way (true) rather than handed an error or
    # a silent duplicate push.
    assert result["already_pending"] is True
    assert result["transaction_id"] == stale.id
    assert call_count["n"] == 0

    db.refresh(stale)
    assert stale.status == "Pending"

    pending = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.invoice_id == invoice.invoice_id,
            MpesaTransaction.status == "Pending",
        )
        .all()
    )
    assert len(pending) == 1
    assert pending[0].id == stale.id


# ─── Problem A: idempotency, the EXISTING mechanism ────────────────────────


def test_repeated_submit_with_the_same_idempotency_key_pushes_once(db, monkeypatch):
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)

    kwargs = dict(
        phone_number="0712345678",
        amount=Decimal("250.00"),
        callback_tenant="mayoclinic_db",
        user_id=1,
        idempotency_key="cashier-1-double-click",
    )
    first = initiate_stk_push(db, **kwargs)
    second = initiate_stk_push(db, **kwargs)

    assert call_count["n"] == 1
    assert first["checkout_request_id"] == second["checkout_request_id"]
    assert first["transaction_id"] == second["transaction_id"]


def test_same_idempotency_key_with_a_different_body_returns_409(db, monkeypatch):
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)

    initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("250.00"),
        callback_tenant="mayoclinic_db",
        user_id=1,
        idempotency_key="cashier-1-reused-key",
    )

    with pytest.raises(HTTPException) as exc_info:
        initiate_stk_push(
            db,
            phone_number="0712345678",
            amount=Decimal("999.00"),  # different body, same key
            callback_tenant="mayoclinic_db",
            user_id=1,
            idempotency_key="cashier-1-reused-key",
        )
    assert exc_info.value.status_code == 409
    assert call_count["n"] == 1


def test_two_different_cashiers_are_separate_idempotency_scopes(db, monkeypatch):
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)

    shared_key = "shared-key-different-users"
    first = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("250.00"),
        callback_tenant="mayoclinic_db",
        user_id=1,
        idempotency_key=shared_key,
    )
    second = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("250.00"),
        callback_tenant="mayoclinic_db",
        user_id=2,
        idempotency_key=shared_key,
    )

    # Two genuine, distinct actions by two different cashiers: both push,
    # neither is treated as a replay of the other.
    assert call_count["n"] == 2
    assert first["transaction_id"] != second["transaction_id"]


def test_two_terminals_with_the_same_idempotency_key_and_no_invoice_push_once(
    db, _engine, monkeypatch
):
    """The one case with no partial-unique-index backstop: a push with
    neither invoice_id nor dispense_id reserves a slot that never
    conflicts with anything, so _reserve_pending's own commit ends the
    FIRST idempotency check's transaction on BOTH threads before either has
    written the idempotency cache row. The reservation guard alone cannot
    save this case, and never claimed to.

    What closes it is initiate_stk_push's SECOND idempotent_guard check,
    taken again right before the Daraja call with no commit in between it
    and the eventual cache write: whichever thread gets there first holds
    the advisory lock across its own Daraja call and cache write, so the
    other blocks until that is done, then replays the winner's response
    instead of pushing its own prompt. This is genuinely concurrent: two
    threads, two separate Sessions on separate connections, and a
    threading.Barrier so both reach the guard together. A sequential test
    would prove nothing here.
    """
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)
    db.commit()  # visible to the two independent connections below

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=Decimal("250.00"),
                callback_tenant="mayoclinic_db",
                user_id=1,
                idempotency_key="no-invoice-race-key",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"unexpected errors from concurrent pushes: {errors}"
    assert len(results) == 2
    # The proof that matters: Daraja was only ever asked once, even with no
    # invoice/dispense to fall back on. Two calls here would mean the
    # patient's handset got two prompts from one double-click.
    assert call_count["n"] == 1
    assert results[0]["checkout_request_id"] == results[1]["checkout_request_id"]
    assert results[0]["transaction_id"] == results[1]["transaction_id"]


def test_two_terminals_with_the_same_idempotency_key_and_invoice_push_once(
    db, _engine, monkeypatch
):
    """The WITH-invoice counterpart: here the partial unique index already
    stops a second reservation, so the loser takes the "not reserved"
    branch straight to _finalize. What this test guards is the OTHER half
    of I3: that loser's own persist attempt races the winner's on
    pk_idempotency_keys (both used the same idempotency key), and before
    persist_and_commit existed that surfaced as an uncaught IntegrityError,
    a 500 on the exact double-click path idempotency exists to serve. Only
    one Daraja call, and neither terminal raises.
    """
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)

    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()  # visible to the two independent connections below

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=Decimal("500.00"),
                invoice_id=invoice.invoice_id,
                callback_tenant="mayoclinic_db",
                user_id=1,
                idempotency_key="invoice-race-key",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"unexpected errors from concurrent pushes: {errors}"
    assert len(results) == 2
    assert call_count["n"] == 1
    assert results[0]["checkout_request_id"] == results[1]["checkout_request_id"]
    assert results[0]["transaction_id"] == results[1]["transaction_id"]


def test_concurrent_reuse_of_the_same_key_with_a_different_body_returns_409(
    db, _engine, monkeypatch
):
    """A DIFFERENT body under the same key is a programmer error or an
    attack whether or not it arrives concurrently: the racing terminal must
    still get 409, never the other terminal's unrelated cached answer.

    This exercises the lock's OWN post-acquisition re-check, not just the
    unlocked pre-check: both threads reach idempotent_guard with nothing
    cached yet, so neither is rejected before taking the lock. Whichever
    is second only discovers the mismatch after it is granted the lock,
    which is exactly the path that must still raise 409 rather than
    silently return the winner's response.
    """
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)
    db.commit()

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker(amount: Decimal):
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=amount,
                callback_tenant="mayoclinic_db",
                user_id=1,
                idempotency_key="same-key-different-bodies",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=(Decimal("250.00"),))
    t2 = threading.Thread(target=worker, args=(Decimal("999.00"),))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    # Exactly one of the two genuinely different requests succeeds; the
    # other is rejected as a key reuse with a different body, not silently
    # handed the first one's answer and not left to crash.
    assert len(results) == 1
    assert len(errors) == 1
    http_errors = [e for e in errors if isinstance(e, HTTPException)]
    assert len(http_errors) == 1, f"expected an HTTPException, got: {errors}"
    assert http_errors[0].status_code == 409
    # The winner's own push happened; the loser's rejection must not have
    # triggered a second, wasted call.
    assert call_count["n"] == 1


def test_concurrent_reuse_with_a_different_body_leaves_no_stranded_pending_row(
    db, _engine, monkeypatch
):
    """The loser in the race above still owns a Pending row: _reserve_pending
    committed it before either thread ever reached the second idempotent_guard
    check that raises the 409. Without marking that row Failed before
    re-raising, it is left status="Pending" with checkout_request_id=None
    forever: Daraja was never called for it, so Task 8's reconciliation job
    (which needs a checkout_request_id to ask Safaricom via STK Query) can
    never resolve it, and it becomes a permanent phantom in the transaction
    log and every pending-transactions report.

    No money is at risk here (Daraja was never called for the loser's row);
    this guards log integrity, not fund safety. This is the no-invoice path
    (no invoice_id/dispense_id), since that is the one case where
    _reserve_pending's partial unique index never blocks the loser's own
    reservation: both threads reserve their OWN separate row before either
    reaches the guard that rejects one of them.

    A plain start-of-function barrier does not reliably reproduce this: with
    everything mocked, one thread can run start-to-finish (including writing
    the idempotency cache row) before the other even leaves its FIRST
    idempotent_guard check, in which case the loser is rejected there,
    before ever reserving a row, and nothing is stranded. The race this test
    targets needs BOTH threads to have already reserved (and committed)
    their own row before either reaches its SECOND, gated call. A second
    barrier, tripped from inside a wrapped idempotent_guard on each thread's
    second call, forces exactly that interleaving.
    """
    _fake_oauth(monkeypatch)
    call_count = {"n": 0}
    lock = threading.Lock()
    _fake_stk_success(monkeypatch, call_count, lock)
    make_mpesa_config(db)
    db.commit()

    import app.services.daraja.stk as stk_module

    real_idempotent_guard = stk_module.idempotent_guard
    second_call_barrier = threading.Barrier(2)
    call_counts: dict = {}
    call_counts_lock = threading.Lock()

    def wrapped_idempotent_guard(session, **kwargs):
        tid = threading.get_ident()
        with call_counts_lock:
            call_counts[tid] = call_counts.get(tid, 0) + 1
            n = call_counts[tid]
        if n == 2:
            # Both threads' reservations (_reserve_pending) are already
            # committed by the time either gets here: this is the SECOND
            # call per thread, made only after _reserve_pending returned.
            # Holding both here until both arrive is what forces the race
            # onto the "already reserved, now racing the guard" path.
            second_call_barrier.wait(timeout=5)
        return real_idempotent_guard(session, **kwargs)

    monkeypatch.setattr(stk_module, "idempotent_guard", wrapped_idempotent_guard)

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    start_barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker(amount: Decimal):
        session = SessionLocal()
        try:
            start_barrier.wait(timeout=5)
            r = initiate_stk_push(
                session,
                phone_number="0712345678",
                amount=amount,
                callback_tenant="mayoclinic_db",
                user_id=1,
                idempotency_key="stranded-row-different-bodies",
            )
            with results_lock:
                results.append(r)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
            with results_lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=(Decimal("250.00"),))
    t2 = threading.Thread(target=worker, args=(Decimal("999.00"),))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    # The 409 must still reach the loser: a reused key with a genuinely
    # different body is a programmer error or an attack and must surface,
    # never be silently absorbed just to keep the row tidy.
    assert len(results) == 1
    assert len(errors) == 1
    http_errors = [e for e in errors if isinstance(e, HTTPException)]
    assert len(http_errors) == 1, f"expected an HTTPException, got: {errors}"
    assert http_errors[0].status_code == 409

    # Both threads did reserve their own row (proof this exercised the
    # intended race, not the FIRST-check rejection that never reserves).
    all_rows = db.query(MpesaTransaction).all()
    assert len(all_rows) == 2

    # The winner's own row legitimately STAYS "Pending" after a successful
    # push (it is not settled until the callback arrives): that is correct
    # and must not be mistaken for a stranded row. The bug this guards is
    # specifically a Pending row with NO checkout_request_id: Daraja was
    # never called for it, so no callback and no STK Query can ever settle
    # it, and it is that combination, not "Pending" alone, that never
    # resolves.
    orphaned = [
        t for t in all_rows if t.status == "Pending" and t.checkout_request_id is None
    ]
    assert orphaned == [], (
        "a stranded Pending row survived the concurrent 409: it has no "
        "checkout_request_id, so reconciliation can never resolve it"
    )

    failed = [t for t in all_rows if t.status == "Failed"]
    assert len(failed) == 1
    assert failed[0].checkout_request_id is None
    assert failed[0].result_desc
