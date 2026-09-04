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
from fastapi import HTTPException
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
    calls = {"count": 0, "payloads": []}

    def fake_post(url, **kw):
        calls["count"] += 1
        calls["payloads"].append(kw.get("json"))
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


def _make_unverified_c2b(db, *, config, minutes_old, receipt=None, conversation_id=None):
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=Decimal("300.00"),
        receipt_number=receipt or f"RCPT{secrets.token_hex(4).upper()}",
        status="Unverified",
        transaction_type="C2B",
        mpesa_config_id=config.id,
        conversation_id=conversation_id,
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
    status_query_conversation_id=None, amount=Decimal("200.00"),
):
    refund = MpesaRefund(
        source_transaction_id=source_txn.id,
        phone_number=source_txn.phone_number,
        amount=amount,
        reason="reconciliation test",
        status=status,
        originator_conversation_id=f"AG_{secrets.token_hex(8)}",
        conversation_id=conversation_id,
        status_query_conversation_id=status_query_conversation_id,
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
    assert result.stk_still_pending == 0


def test_stk_pending_over_five_minutes_resolves_via_stk_query_failure(db, _engine, monkeypatch):
    """STK Query answers synchronously: a genuine, non-zero ResultCode
    routes through apply_stk_callback and reaches a terminal status in
    this same run."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "0",
        "ResultCode": "1032",
        "ResultDesc": "Request cancelled by user.",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Failed"
    assert txn.result_desc == "Request cancelled by user."
    assert calls["count"] == 1
    assert result.transactions_resolved == 1


def test_stk_pending_bare_success_is_left_pending_not_settled_or_quarantined(
    db, _engine, monkeypatch,
):
    """C4, and one of the two required revert-evidence proofs.

    STK Query never carries CallbackMetadata (Amount, MpesaReceiptNumber),
    so a bare ResultCode 0 looks IDENTICAL, from this endpoint, whether the
    real callback was merely delayed or was dropped entirely. Routing this
    through apply_stk_callback would quarantine the row (settlement.py's
    own "no MpesaReceiptNumber despite ResultCode 0" step), which moves it
    out of status == "Pending" and means Safaricom's own retry of the REAL
    callback (carrying the actual receipt and amount, the only delivery
    that can safely settle this row) finds no Pending row and settles
    nothing: character-for-character the "Expired" bug reservation.py's
    docstring describes removing, reintroduced through STK Query instead
    of a local timer. So this must leave the row untouched.
    """
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ResponseCode": "0",
        "ResultCode": "0",
        "ResultDesc": "The service request is processed successfully.",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert calls["count"] == 1  # we did ask; a bare "0" is just not a usable verdict
    assert result.transactions_resolved == 0
    assert result.stk_still_pending == 1


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
    assert result.stk_still_pending == 1


def test_stk_query_still_processing_http_error_code_leaves_pending_not_failed(
    db, _engine, monkeypatch,
):
    """New-5. Daraja's stkpushquery is widely documented to return a
    non-2xx response carrying errorCode 500.001.1001 ("The transaction is
    being processed") while a push is genuinely still in flight, not yet
    confirmed against this project's own sandbox. client.py now preserves
    that code on the DarajaError/HTTPException it raises instead of
    flattening every non-2xx response into one generic failure, so
    requery_stk can tell this apart from a real "could not ask" failure:
    this must be treated exactly like the 200-with-no-ResultCode shape
    (left Pending, not a job failure), not like an outage."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(500, {
        "requestId": "16712-79390-1",
        "errorCode": "500.001.1001",
        "errorMessage": "The transaction is being processed",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert calls["count"] == 1
    assert result.ok is True                # not a failure: routine in-flight traffic
    assert result.stk_still_pending == 1


def test_stk_query_other_http_error_code_is_a_real_failure(db, _engine, monkeypatch):
    """The other half of New-5: a non-2xx response carrying a DIFFERENT
    errorCode (or none at all) is a genuine "we could not ask Safaricom"
    failure and must still reach ReconcileRunResult.failures (I1), not be
    silently folded into the same bucket as routine in-flight traffic."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(500, {
        "requestId": "16712-79390-2",
        "errorCode": "404.001.03",
        "errorMessage": "Invalid Access Token",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert calls["count"] == 1
    assert result.ok is False
    assert any(f"transaction {txn.id}" in f for f in result.failures)


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
    assert txn.surfaced_at is not None
    assert calls["count"] == 0  # never retried forever
    assert result.transactions_resolved == 0
    assert any("Pending > 24h" in line for line in result.surfaced)


def test_surfaced_transaction_does_not_renotify_on_a_second_run(db, _engine, monkeypatch):
    """I2. A row stuck past 24 hours is surfaced once; a second cron cycle
    over the same still-stuck row must not renotify a danger-category
    channel again."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=25 * 60)
    db.commit()

    notify_calls = {"count": 0}
    import app.services.daraja.reconcile_queries as reconcile_queries
    real_notify = reconcile_queries._notify_quarantine

    def counting_notify(session, txn_, *, reason):
        notify_calls["count"] += 1
        return real_notify(session, txn_, reason=reason)

    monkeypatch.setattr(reconcile_queries, "_notify_quarantine", counting_notify)

    _run(db, _engine)
    db.refresh(txn)
    assert txn.surfaced_at is not None
    first_surfaced_at = txn.surfaced_at

    _run(db, _engine)
    db.refresh(txn)
    assert txn.surfaced_at == first_surfaced_at
    assert notify_calls["count"] == 1


def test_surfaced_refund_renotifies_when_the_reason_changes(db, _engine, monkeypatch):
    """New-3. surfaced_at alone throttles per ROW, not per REASON. A
    case-4 refund surfaced once, whose status later changes (a human acts)
    and which then becomes stuck again for a COMPLETELY DIFFERENT reason,
    must still notify: throttling on the bare timestamp would silently
    drop that second alarm, which is worse than no throttle, since the
    log would still assert a human was told about money in flight."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Approved",
        minutes_since_dispatch=11, conversation_id=None,
    )
    db.commit()

    import app.services.daraja.reconcile_queries as reconcile_queries
    real_notify = reconcile_queries._notify_refund_needs_review
    notify_calls = []

    def counting_notify(session, refund_, *, reason):
        notify_calls.append(reason)
        return real_notify(session, refund_, reason=reason)

    monkeypatch.setattr(reconcile_queries, "_notify_refund_needs_review", counting_notify)

    _run(db, _engine)
    db.refresh(refund)
    assert len(notify_calls) == 1
    first_reason = refund.surfaced_reason
    assert first_reason is not None
    assert "dispatch attempt already marked" in first_reason

    # A second run with the SAME reason must not renotify.
    _run(db, _engine)
    assert len(notify_calls) == 1

    # Simulate a human running retry-dispatch outside this job: Safaricom
    # accepts it for real this time, moving the refund to Processing with
    # a genuine conversation_id, then it sticks there past 24 hours.
    refund.status = "Processing"
    refund.conversation_id = "AG_REAL_DISPATCH"
    refund.first_dispatch_attempted_at = (
        datetime.now(timezone.utc) - timedelta(hours=25)
    )
    db.commit()

    _run(db, _engine)
    db.refresh(refund)
    assert len(notify_calls) == 2  # a genuinely new reason notified again
    assert refund.surfaced_reason != first_reason


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
    assert result.c2b_requeried == 1
    assert result.transactions_resolved == 0


def test_c2b_unverified_with_an_outstanding_query_is_not_reoverwritten(db, _engine, monkeypatch):
    """C5, and the second required revert-evidence proof.

    txn.conversation_id is the exact key handle_transaction_status_result
    correlates the eventual answer on. If this job overwrote it on every
    15-minute cycle, a genuine answer that takes longer than one cycle to
    arrive could NEVER resolve: each run would invalidate the previous
    query's own correlation id before its result could land. So once a
    query is outstanding (conversation_id already set), this job must ask
    Safaricom nothing further for this row and must not touch the column.
    """
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_unverified_c2b(
        db, config=config, minutes_old=6, conversation_id="AG_OUTSTANDING",
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "OriginatorConversationID": "AG_SHOULD_NOT_BE_SENT",
        "ConversationID": "AG_SHOULD_NOT_OVERWRITE",
        "ResponseCode": "0",
    }))
    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.conversation_id == "AG_OUTSTANDING"  # untouched: the answer is still in flight
    assert calls["count"] == 0
    assert result.c2b_requeried == 0


def test_c2b_requery_never_writes_a_falsy_ack_value(db, _engine, monkeypatch):
    """C5's second half. A 200 response that omits ConversationID (or
    OriginatorConversationID) must never null out the column: that would
    silently orphan the row with no id left for a later result to
    correlate against."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_unverified_c2b(db, config=config, minutes_old=6)
    db.commit()

    _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {"ResponseCode": "0"}))
    _run(db, _engine)

    db.refresh(txn)
    assert txn.conversation_id is None
    assert txn.originator_conversation_id is None


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


# ─── Case 3: refund stuck Processing (asynchronous, ask, never dispatch) ───


def test_refund_processing_over_ten_minutes_is_asked_via_transaction_status(
    db, _engine, monkeypatch,
):
    """C1. A Processing refund is asked about via a genuine Transaction
    Status query keyed on its OWN conversation_id (the id Safaricom
    accepted this instruction under), never re-dispatched. The query's own
    acknowledgment lands on status_query_conversation_id; conversation_id
    (the B2C dispatch's own correlation id, and the double-dispatch
    alarm's evidence) is never touched."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        minutes_since_dispatch=11, conversation_id="AG_DISPATCH_ORIGINAL",
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "OriginatorConversationID": "AG_STATUS_QUERY_ORIG",
        "ConversationID": "AG_STATUS_QUERY_CONV",
        "ResponseCode": "0",
        "ResponseDescription": "Accept the service request successfully.",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Processing"  # never resolved by this job
    assert refund.conversation_id == "AG_DISPATCH_ORIGINAL"  # B2C correlation untouched
    assert refund.status_query_conversation_id == "AG_STATUS_QUERY_CONV"
    assert calls["count"] == 1
    assert calls["payloads"][0]["OriginalConversationID"] == "AG_DISPATCH_ORIGINAL"
    assert calls["payloads"][0]["TransactionID"] == ""
    assert calls["payloads"][0]["CommandID"] == "TransactionStatusQuery"
    assert result.refunds_requeried == 1


def test_refund_processing_with_an_outstanding_query_is_not_reasked(db, _engine, monkeypatch):
    """Same discipline as C5's C2B fix, applied to refunds: once a status
    query is outstanding, this job must not fire a second one and orphan
    the first one's answer."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        minutes_since_dispatch=11, conversation_id="AG_DISPATCH_ORIGINAL",
        status_query_conversation_id="AG_ALREADY_OUTSTANDING",
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ConversationID": "AG_SHOULD_NOT_OVERWRITE", "ResponseCode": "0",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status_query_conversation_id == "AG_ALREADY_OUTSTANDING"
    assert calls["count"] == 0
    assert result.refunds_requeried == 0


def test_refund_stuck_processing_over_24_hours_surfaces_without_further_query(
    db, _engine, monkeypatch,
):
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
    assert refund.status_query_conversation_id is None
    assert refund.surfaced_at is not None
    assert calls["count"] == 0
    assert any("Processing > 24h" in line for line in result.surfaced)


def test_refund_processing_with_no_conversation_id_is_surfaced_not_asked(
    db, _engine, monkeypatch,
):
    """New-4. b2c.py's own dispatch_refund and handle_b2c_timeout both move
    a refund to Processing unconditionally once _record_conversation_id
    returns True, which it also does, as a documented no-op, when
    Safaricom's response carried no ConversationID at all. So Processing
    with conversation_id IS NULL is reachable. There is no id to ask
    Safaricom about (TransactionStatusQuery needs either a receipt, which a
    Processing refund never has, or this exact id), so asking would raise
    on every run forever, a permanent non-outage failure that would drown
    out I1's real signal. This must surface instead, immediately, not wait
    out the full 24 hours for a condition that time cannot fix."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        minutes_since_dispatch=11, conversation_id=None,
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ConversationID": "AG_SHOULD_NOT_BE_SENT", "ResponseCode": "0",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.conversation_id is None
    assert refund.status_query_conversation_id is None
    assert refund.surfaced_at is not None
    assert calls["count"] == 0                    # Safaricom was never contacted
    assert result.refunds_requeried == 0
    assert result.ok is True                       # surfaced, not a job failure
    assert any("no conversation_id" in line for line in result.surfaced)


# ─── Case 4: refund Approved with a dispatch marker (surfaced, never acted) ─


def test_refund_approved_with_marker_is_surfaced_never_dispatched(db, _engine, monkeypatch):
    """C2/C3. retry-dispatch's own route already covers this shape for a
    human (gated on status == "Approved" alone, with no check on the
    marker). Automating a second dispatch here would be indistinguishable,
    from Safaricom's side, from a genuinely new payout: a case-4 refund by
    definition has no conversation_id yet, so _record_conversation_id's
    double-dispatch alarm has nothing to compare a fresh acceptance
    against and cannot catch it. So this job must never contact Safaricom
    for this case: it only surfaces the row for a human."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Approved",
        minutes_since_dispatch=11, conversation_id=None,
    )
    db.commit()

    calls = _counting_post(monkeypatch, lambda url, **kw: FakeResponse(200, {
        "ConversationID": "AG_WOULD_BE_A_SECOND_PAYOUT", "ResponseCode": "0",
    }))
    result = _run(db, _engine)

    db.refresh(refund)
    assert refund.status == "Approved"          # never touched
    assert refund.conversation_id is None        # never acquired one from this job
    assert refund.surfaced_at is not None
    assert calls["count"] == 0                   # Safaricom was never contacted
    assert result.refunds_requeried == 0
    assert any("Approved-with-marker" in line for line in result.surfaced)


# ─── I1: "could not ask" is a failure, not a silent still-pending ──────────


def test_could_not_ask_safaricom_is_recorded_as_a_failure(db, _engine, monkeypatch):
    """I1. "We could not even ask Safaricom" (a Daraja outage, a missing
    credential) must never look like "Safaricom answered with no verdict
    yet": the former is a real failure that belongs in
    ReconcileRunResult.failures, or a total outage silently looks like a
    quiet, healthy run forever."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_pending_stk(db, config=config, minutes_old=6)
    db.commit()

    def raise_could_not_ask(session, txn_):
        raise HTTPException(status_code=502, detail="Could not reach M-Pesa. Try again shortly.")

    monkeypatch.setattr("app.services.daraja.reconcile.requery_stk", raise_could_not_ask)

    result = _run(db, _engine)

    db.refresh(txn)
    assert txn.status == "Pending"
    assert result.stk_still_pending == 0
    assert result.ok is False
    assert any(
        f"transaction {txn.id}" in f and "Could not reach M-Pesa" in f
        for f in result.failures
    )


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
