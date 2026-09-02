"""Reconciliation: the safety net for the five cases every earlier Daraja
task deferred to it. Mocked at the one seam every other Daraja test uses
(requests.* inside app.services.daraja.client), so a call count assertion
here is a real count of outbound Daraja calls, not a stand-in for one.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.core.circuit import daraja_breaker
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.reconcile import (
    RECONCILE_LOCK_KEY,
    ReconcileRunResult,
    reconcile_lock,
    run_reconciliation,
)
from app.utils.encryption import encrypt_data
from tests.daraja.conftest import make_mpesa_config

TENANT_HINT = "mayoclinic_db"


# ─── Shared fixtures (mirrors test_stk.py / test_refunds.py) ───────────────


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _clear_token_cache():
    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


def _reset_breaker():
    daraja_breaker._state = daraja_breaker.CLOSED
    daraja_breaker._failures = 0
    daraja_breaker._opened_at = 0.0


@pytest.fixture(autouse=True)
def _clear_circuit_breaker():
    _reset_breaker()
    yield
    _reset_breaker()


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    yield


@pytest.fixture(autouse=True)
def _fake_safaricom_public_key(monkeypatch):
    """B2C/Transaction Status sign with SecurityCredential =
    RSA-encrypt(initiator password); stand in for Safaricom's real
    certificate, same as test_refunds.py and test_status.py."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "app.services.daraja.credentials._public_key",
        lambda environment: private_key.public_key(),
    )
    yield


def _fake_oauth(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )


def _counting_post(monkeypatch, response_fn):
    """Install a fake requests.post that counts calls and delegates the
    response to `response_fn(url, **kw)`. Returns the mutable call-count
    holder so a test can assert on it: a status-only assertion has already
    passed against a real bug twice on this branch, so every test below
    that exercises a Daraja call also checks how many times it happened."""
    calls = {"count": 0}

    def fake_post(url, **kw):
        calls["count"] += 1
        return response_fn(url, **kw)

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)
    return calls


def _refund_config(db, **overrides):
    defaults = dict(
        refunds_enabled=True,
        refund_max_amount=Decimal("100000.00"),
        refund_daily_cap=Decimal("100000.00"),
        refund_dual_approval_above=Decimal("100000.00"),
        initiator_name="testapi",
    )
    defaults.update(overrides)
    config = make_mpesa_config(db, **defaults)
    config.initiator_password_encrypted = encrypt_data("initiator-pass")
    db.flush()
    return config


def _make_pending_stk(db, *, config, minutes_old, checkout_request_id=None):
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=Decimal("500.00"),
        checkout_request_id=checkout_request_id or f"ws_CO_{secrets.token_hex(4)}",
        merchant_request_id="mr_1",
        status="Pending",
        transaction_type="STK",
        mpesa_config_id=config.id,
        transaction_date=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
    )
    db.add(txn)
    db.flush()
    return txn


def _make_unverified_c2b(db, *, config, minutes_old, receipt=None):
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=Decimal("300.00"),
        receipt_number=receipt or f"RCPT{secrets.token_hex(4).upper()}",
        status="Unverified",
        transaction_type="C2B",
        mpesa_config_id=config.id,
        transaction_date=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
    )
    db.add(txn)
    db.flush()
    return txn


def _make_settled_txn(db, *, config, amount=Decimal("1000.00")):
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=amount,
        receipt_number=f"RCPT{secrets.token_hex(4).upper()}",
        status="Success",
        transaction_type="STK",
        mpesa_config_id=config.id,
        verified_at=datetime.now(timezone.utc),
        verification_source="stk_callback",
    )
    db.add(txn)
    db.flush()
    return txn


def _make_refund(
    db, *, source_txn, status, minutes_since_dispatch, conversation_id=None,
    amount=Decimal("200.00"),
):
    refund = MpesaRefund(
        source_transaction_id=source_txn.id,
        phone_number=source_txn.phone_number,
        amount=amount,
        reason="reconciliation test",
        status=status,
        originator_conversation_id=f"AG_{secrets.token_hex(8)}",
        conversation_id=conversation_id,
        first_dispatch_attempted_at=(
            datetime.now(timezone.utc) - timedelta(minutes=minutes_since_dispatch)
        ),
        requested_by=1,
        approved_by=1,
    )
    db.add(refund)
    db.flush()
    return refund


def _run(db, _engine, *, now=None):
    """run_reconciliation against a single fake tenant whose "database" is
    the same Postgres test database `db` already uses: this project has no
    per-tenant test database infrastructure (see tests/daraja/conftest.py),
    and the multi-tenant orchestration itself is exercised separately by
    the failure-isolation tests below. A fresh session per call, bound to
    the same engine, so run_reconciliation's own `session.close()` at the
    end of the tenant loop never closes the `db` fixture's own session."""
    tenant = SimpleNamespace(tenant_id=1, db_name=TENANT_HINT)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return run_reconciliation(
        db, now=now, tenants=[tenant], session_for_tenant=lambda name: SessionLocal(),
    )


# ─── The lock ───────────────────────────────────────────────────────────────


def test_second_acquisition_fails_while_the_first_is_held(_engine):
    Session = sessionmaker(bind=_engine)
    first = Session()
    second = Session()
    try:
        with reconcile_lock(first) as first_acquired:
            assert first_acquired is True
            with reconcile_lock(second) as second_acquired:
                assert second_acquired is False
    finally:
        first.close()
        second.close()


def test_lock_is_released_once_the_holder_exits(_engine):
    Session = sessionmaker(bind=_engine)
    first = Session()
    second = Session()
    try:
        with reconcile_lock(first) as acquired:
            assert acquired is True
        with reconcile_lock(second) as acquired:
            assert acquired is True
    finally:
        first.close()
        second.close()


def test_a_run_that_finds_the_lock_held_is_skipped_not_failed(db, _engine):
    """skipped=True is the correct outcome for a concurrent run, and must
    never be reported the same way as a genuine failure."""
    Session = sessionmaker(bind=_engine)
    holder = Session()
    try:
        with reconcile_lock(holder) as acquired:
            assert acquired is True
            result = _run(db, _engine)
            assert result.skipped is True
            assert result.ok is False  # visible in logs, but distinct from a real failure
            assert result.transactions_resolved == 0
    finally:
        holder.close()
    holder2 = Session()
    holder2.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": RECONCILE_LOCK_KEY})
    holder2.commit()
    holder2.close()


# ─── Case 1: STK Pending (synchronous) ──────────────────────────────────────


def test_stk_pending_under_five_minutes_is_left_alone(db, _engine, monkeypatch):
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=1)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {}))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert calls["count"] == 0
    assert result.transactions_resolved == 0
    assert result.transactions_requeried == 0


def test_stk_pending_over_five_minutes_resolves_via_stk_query_failure(db, _engine, monkeypatch):
    """STK Query answers synchronously: a genuine ResultCode routes through
    apply_stk_callback and reaches a terminal status in this same run."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "0",
        "MerchantRequestID": "mr_1",
        "CheckoutRequestID": txn.checkout_request_id,
        "ResultCode": "1032",
        "ResultDesc": "Request cancelled by user.",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Failed"
    assert txn.result_desc == "Request cancelled by user."
    assert calls["count"] == 1
    assert result.transactions_resolved == 1


def test_stk_pending_success_with_no_receipt_is_quarantined_not_settled(db, _engine, monkeypatch):
    """STK Query never carries CallbackMetadata (Amount, MpesaReceiptNumber);
    a bare ResultCode 0 must never be read as enough to settle. This is the
    existing settlement.py cross-check doing its job through reconciliation,
    not a new rule."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "0",
        "MerchantRequestID": "mr_1",
        "CheckoutRequestID": txn.checkout_request_id,
        "ResultCode": "0",
        "ResultDesc": "The service request is processed successfully.",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    # Whichever cross-check trips first (settlement.py checks the amount
    # before the receipt), the outcome that matters here is: quarantined,
    # never silently settled with no receipt to anchor it to.
    assert txn.status == "Quarantined"
    assert txn.result_desc  # a human-readable reason was recorded
    assert result.transactions_resolved == 1


def test_stk_query_no_verdict_yet_leaves_pending(db, _engine, monkeypatch):
    """THE inference guard. Safaricom's genuine "still processing" body
    carries no ResultCode at all. This must never be read as a verdict of
    any kind: the row is left exactly as Pending, not resolved by
    inference. See task-8-report.md for the break/restore evidence this
    test produced."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "requestId": "16712-79390-1",
        "errorCode": "500.001.1001",
        "errorMessage": "The transaction is being processed",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert calls["count"] == 1  # we did ask; Safaricom just had no verdict yet
    assert result.transactions_resolved == 0
    assert result.transactions_requeried == 1


def test_stk_pending_over_24_hours_surfaces_without_further_query(db, _engine, monkeypatch):
    """THE no-retry-forever guard. Once a row is 24+ hours stuck, it must
    stop being asked about (call count 0 for this row) and instead be
    surfaced. See task-8-report.md for the break/restore evidence this
    test produced."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=25 * 60)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResultCode": "0", "CheckoutRequestID": txn.checkout_request_id,
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"  # never resolved, just because it is old
    assert calls["count"] == 0  # never retried forever
    assert result.transactions_resolved == 0
    assert any("Pending > 24h" in line for line in result.surfaced)


# ─── Case 2: C2B Unverified (asynchronous) ─────────────────────────────────


def test_c2b_unverified_over_five_minutes_is_requeried_and_stays_unverified(db, _engine, monkeypatch):
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_unverified_c2b(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "OriginatorConversationID": "AG_ORIG_NEW",
        "ConversationID": "AG_CONV_NEW",
        "ResponseCode": "0",
        "ResponseDescription": "Accept the service request successfully.",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Unverified"  # the verdict, if any, lands later at a callback
    assert txn.conversation_id == "AG_CONV_NEW"
    assert txn.originator_conversation_id == "AG_ORIG_NEW"
    assert calls["count"] == 1
    assert result.transactions_requeried == 1
    assert result.transactions_resolved == 0


def test_c2b_unverified_over_24_hours_surfaces_without_further_query(db, _engine, monkeypatch):
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_unverified_c2b(db, config=config, minutes_old=25 * 60)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "OriginatorConversationID": "AG_X", "ConversationID": "AG_Y", "ResponseCode": "0",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Unverified"
    assert txn.conversation_id is None  # never touched once past 24h
    assert calls["count"] == 0
    assert any("Unverified > 24h" in line for line in result.surfaced)


# ─── Cases 3 & 4: stuck refunds (asynchronous) ─────────────────────────────


def test_refund_processing_over_ten_minutes_is_redispatched_and_stays_processing(
    db, _engine, monkeypatch,
):
    """Case 3. A duplicate-instruction rejection from Safaricom confirms it
    already holds this refund; dispatch_refund's own existing logic (not
    reconciliation) is what keeps this from ever reading as Failed."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        minutes_since_dispatch=11, conversation_id="AG_FIRST",
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "1", "ResponseDescription": "Duplicate OriginatorConversationID.",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.result_desc is not None and "manual review" in refund.result_desc
    assert calls["count"] == 1
    assert result.refunds_requeried == 1


def test_refund_approved_with_dispatch_marker_over_ten_minutes_is_redispatched(
    db, _engine, monkeypatch,
):
    """Case 4. Approved with first_dispatch_attempted_at already set has NO
    other in-product recovery (retry-dispatch's route refuses it). A fresh
    acceptance moves it forward to Processing with a real ConversationID."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Approved",
        minutes_since_dispatch=11, conversation_id=None,
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ConversationID": "AG_RECOVERED", "ResponseCode": "0",
        "ResponseDescription": "Accept the service request successfully.",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.conversation_id == "AG_RECOVERED"
    assert calls["count"] == 1
    assert result.refunds_requeried == 1


def test_refund_stuck_over_24_hours_surfaces_without_further_dispatch(db, _engine, monkeypatch):
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        minutes_since_dispatch=25 * 60, conversation_id="AG_OLD",
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "0", "ConversationID": "AG_SHOULD_NOT_BE_SENT",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.conversation_id == "AG_OLD"  # never touched once past 24h
    assert calls["count"] == 0
    assert any("Processing > 24h" in line for line in result.surfaced)


# ─── Failure visibility ─────────────────────────────────────────────────────


def test_one_bad_row_is_recorded_as_a_failure_and_does_not_stop_the_others(
    db, _engine, monkeypatch,
):
    """Mirrors tests/receivables/test_failures.py: "0 resolved" must never
    look identical to "every row failed"."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    good_txn = _make_pending_stk(db, config=config, minutes_old=6)
    bad_txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    import app.services.daraja.reconcile_queries as reconcile_queries

    real_requery_stk = reconcile_queries.requery_stk

    def flaky_requery_stk(session, txn):
        if txn.id == bad_txn.id:
            raise RuntimeError("simulated failure")
        return real_requery_stk(session, txn)

    monkeypatch.setattr("app.services.daraja.reconcile.requery_stk", flaky_requery_stk)
    _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResultCode": "1032", "ResultDesc": "Request cancelled by user.",
        "CheckoutRequestID": good_txn.checkout_request_id,
    }))

    result = _run(db, _engine)

    db.refresh(good_txn)
    db.refresh(bad_txn)
    assert good_txn.status == "Failed"       # the good row still got resolved
    assert bad_txn.status == "Pending"       # the bad row is untouched, not silently lost
    assert result.transactions_resolved == 1
    assert result.ok is False
    assert any(f"transaction {bad_txn.id}" in f and "simulated failure" in f for f in result.failures)


def test_a_tenant_whose_session_cannot_be_opened_does_not_stop_other_tenants(db, _engine):
    """The multi-tenant orchestration itself: one tenant's database being
    unreachable must not silently swallow the whole run, and must not stop
    a different tenant's own rows from being reconciled."""
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=1)  # too fresh to touch either way
    db.commit()

    good_tenant = SimpleNamespace(tenant_id=1, db_name="good_tenant")
    bad_tenant = SimpleNamespace(tenant_id=2, db_name="bad_tenant")

    # A fresh session per call, bound to the same engine, exactly as _run
    # does: run_reconciliation closes whatever session_for_tenant hands it,
    # so returning the `db` fixture's own session directly would close it
    # out from under this test's own later assertions.
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    def session_for_tenant(name):
        if name == "bad_tenant":
            raise RuntimeError("connection refused")
        return SessionLocal()

    result = run_reconciliation(
        db, tenants=[bad_tenant, good_tenant], session_for_tenant=session_for_tenant,
    )

    assert result.ok is False
    assert any("bad_tenant" in f and "connection refused" in f for f in result.failures)
    # The good tenant's own sweep still ran (found nothing stale, which is
    # correct here since txn is only 1 minute old): no exception propagated
    # past the bad tenant.
    assert result.transactions_resolved == 0
    db.refresh(txn)
    assert txn.status == "Pending"


def test_reconcile_run_result_ok_reflects_failures():
    assert ReconcileRunResult().ok is True
    assert ReconcileRunResult(failures=["x"]).ok is False
