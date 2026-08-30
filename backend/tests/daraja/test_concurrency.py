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
from sqlalchemy.orm import sessionmaker

from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.stk import _STALE_PENDING_TIMEOUT, initiate_stk_push
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


def test_a_stale_pending_transaction_does_not_block_a_genuine_retry(db, monkeypatch):
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
    stale.transaction_date = (
        datetime.now(timezone.utc) - _STALE_PENDING_TIMEOUT - timedelta(minutes=5)
    )
    db.commit()

    # A genuine retry for the same invoice must succeed, not be told a
    # prompt is already on its way, and must not raise.
    result = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("500.00"),
        invoice_id=invoice.invoice_id,
        callback_tenant="mayoclinic_db",
    )

    assert result.get("already_pending", False) is False
    assert call_count["n"] == 1

    db.refresh(stale)
    assert stale.status == "Expired"
    # The stale row is never guessed into Success or Failed: its real
    # outcome, if any, is for reconciliation (Task 8) to resolve against
    # Safaricom directly.
    assert stale.status not in ("Success", "Failed")

    new_pending = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.invoice_id == invoice.invoice_id,
            MpesaTransaction.status == "Pending",
        )
        .all()
    )
    assert len(new_pending) == 1
    assert new_pending[0].id == result["transaction_id"]
    assert new_pending[0].id != stale.id


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
