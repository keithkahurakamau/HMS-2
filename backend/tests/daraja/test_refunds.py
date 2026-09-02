"""B2C refunds: the only path by which money leaves a hospital.

Every test here targets one of the controls listed in app/services/daraja/
b2c.py's module docstring and docs/superpowers/specs/2026-08-29-daraja-
migration-design.md's "Refunds (B2C)" section. Three of them (over-refund,
concurrent double-request, timeout-not-failure) are the ones this task's
brief calls out as needing revert-evidence: broken deliberately, confirmed
to fail, restored, confirmed to pass again. See task-7-report.md for that
evidence; the tests themselves are unconditional, they do not toggle
anything at runtime.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.core.circuit import daraja_breaker
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import (
    _DISPATCH_LOCK_NAMESPACE,
    approve_refund,
    dispatch_refund,
    handle_b2c_result,
    handle_b2c_timeout,
    refundable_amount,
    request_refund,
)
from app.services.daraja.client import DarajaError, _TOKEN_CACHE
from app.utils.encryption import encrypt_data
from tests.daraja.conftest import make_invoice, make_mpesa_config


@pytest.fixture(scope="module", autouse=True)
def _second_user(_engine):
    """A second real user row, for the dual-approval tests: the requester
    and the approver must be different real users, not just different ids
    that happen to violate no foreign key."""
    with _engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO users (user_id, email, full_name, hashed_password, role_id) "
            "SELECT 2, 'daraja.refund.approver@hms.local', 'Refund Approver', 'x', 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 2)"
        ))
        conn.commit()
    yield


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
    """daraja_breaker is a process-wide singleton shared by every Daraja
    flow (STK, C2B, Transaction Status, B2C), instantiated once at import
    time. A test that trips it (Finding A's warm-cache test does, on
    purpose) must not leak that state into every other test in this
    session, in this file or any other."""
    _reset_breaker()
    yield
    _reset_breaker()


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    yield


@pytest.fixture(autouse=True)
def _fake_safaricom_public_key(monkeypatch):
    """The real Safaricom .cer files are not in this repo (see
    tests/daraja/test_credentials.py). A locally generated RSA keypair
    stands in for the certificate, exercising every line of
    security_credential's real RSA-encryption without needing Safaricom's
    actual public key. Never a fabricated certificate: a different object
    entirely, monkeypatched at the one seam credentials.py exposes for
    exactly this."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "app.services.daraja.credentials._public_key",
        lambda environment: private_key.public_key(),
    )
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


def _make_settled_txn(db, *, amount, receipt="RCPT-REFUND-1", config=None, phone="254712345678"):
    txn = MpesaTransaction(
        phone_number=phone,
        amount=amount,
        receipt_number=receipt,
        status="Success",
        transaction_type="STK",
        mpesa_config_id=config.id if config is not None else None,
        verified_at=datetime.now(timezone.utc),
        verification_source="stk_callback",
    )
    db.add(txn)
    db.flush()
    return txn


# ─── Over-refund guard ──────────────────────────────────────────────────────


def test_refund_cannot_exceed_the_original_receipt(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn.id, amount=Decimal("1001.00"),
            reason="too much", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "exceeds" in exc_info.value.detail

    # The exact receipt amount is fine.
    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("1000.00"),
        reason="full refund", user_id=1,
    )
    assert refund.amount == Decimal("1000.00")


def test_refund_cannot_exceed_the_receipt_minus_refunds_already_in_flight(db, _engine):
    """Two concurrent requests for 60% each of a receipt must not both
    pass. GENUINELY concurrent: two threads, two separate Sessions on two
    separate connections, and a threading.Barrier so both reach
    request_refund's row-locking SELECT at the same moment. A sequential
    test would prove nothing: the bug only exists when the two overlap.
    """
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()  # visible to the two independent connections below

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            r = request_refund(
                session, source_transaction_id=txn.id, amount=Decimal("600.00"),
                reason="60 percent", user_id=1,
            )
            with lock:
                results.append(r)
        except HTTPException as exc:
            with lock:
                errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not (len(results) == 2), "both 60% requests passed: the receipt was over-refunded"
    assert len(results) == 1, f"expected exactly one success, got {len(results)}"
    assert len(errors) == 1, f"expected exactly one rejection, got {len(errors)}"
    assert errors[0].status_code == 400


# ─── Caps ───────────────────────────────────────────────────────────────────


def test_over_per_transaction_cap_is_rejected(db):
    config = _refund_config(db, refund_max_amount=Decimal("200.00"))
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn.id, amount=Decimal("300.00"),
            reason="over cap", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "per-transaction cap" in exc_info.value.detail


def test_over_rolling_24h_cap_is_rejected(db):
    config = _refund_config(db, refund_daily_cap=Decimal("500.00"))
    txn1 = _make_settled_txn(db, amount=Decimal("1000.00"), receipt="R1", config=config)
    txn2 = _make_settled_txn(db, amount=Decimal("1000.00"), receipt="R2", config=config)
    db.commit()

    first = request_refund(
        db, source_transaction_id=txn1.id, amount=Decimal("400.00"),
        reason="first refund today", user_id=1,
    )
    assert first.amount == Decimal("400.00")

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn2.id, amount=Decimal("200.00"),
            reason="second refund today, different receipt", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "24-hour" in exc_info.value.detail


# ─── Two-person rule ────────────────────────────────────────────────────────


def test_requester_cannot_approve_their_own_refund_above_the_threshold(db):
    config = _refund_config(db, refund_dual_approval_above=Decimal("500.00"))
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("600.00"),
        reason="above threshold", user_id=1,
    )

    with pytest.raises(HTTPException) as exc_info:
        approve_refund(db, refund_id=refund.id, user_id=1)
    assert exc_info.value.status_code == 403

    # A DIFFERENT approver may approve the same refund.
    approved = approve_refund(db, refund_id=refund.id, user_id=2)
    assert approved.status == "Approved"
    assert approved.approved_by == 2


def test_self_approval_is_fine_below_the_threshold(db):
    config = _refund_config(db, refund_dual_approval_above=Decimal("500.00"))
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("100.00"),
        reason="small, self-approved", user_id=1,
    )
    approved = approve_refund(db, refund_id=refund.id, user_id=1)
    assert approved.status == "Approved"
    assert approved.approved_by == 1


# ─── Permission separation ──────────────────────────────────────────────────


def test_refund_permission_is_separate_from_billing_manage():
    """Being able to TAKE a payment must not imply being able to SEND one
    back: mpesa:refund is a real, distinct codename, and no role that
    holds billing:manage may also hold it."""
    from app.services.tenant_provisioning import PERMISSIONS, ROLE_GRANTS

    assert "mpesa:refund" in PERMISSIONS
    # Admin is deliberately granted every permission, including this one;
    # it is the one role for which "holds both" is expected and correct.
    for role, grants in ROLE_GRANTS.items():
        if role == "Admin":
            continue
        if "billing:manage" in grants:
            assert "mpesa:refund" not in grants, (
                f"{role} holds both billing:manage and mpesa:refund; "
                "taking a payment must not imply sending one back"
            )
    assert "mpesa:refund" in ROLE_GRANTS["Admin"]


# ─── OriginatorConversationID retry idempotency ─────────────────────────────


def test_retry_reuses_the_originator_conversation_id(db, monkeypatch):
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="retry test", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    minted_id = refund.originator_conversation_id
    assert minted_id

    captured_payloads = []

    def fake_post(url, **kw):
        captured_payloads.append(kw.get("json"))
        return FakeResponse(200, {
            "ConversationID": "AG_20230101_1",
            "OriginatorConversationID": kw["json"]["OriginatorConversationID"],
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    first = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")
    assert first.status == "Processing"

    # Simulate a retried dispatch (e.g. an operator re-triggers it while it
    # is still Processing, or the caller retries after a dropped response).
    second = dispatch_refund(db, refund=first, callback_tenant="mayoclinic_db")
    assert second.status == "Processing"

    assert first.originator_conversation_id == minted_id
    assert second.originator_conversation_id == minted_id
    assert len(captured_payloads) == 2
    assert captured_payloads[0]["OriginatorConversationID"] == minted_id
    assert captured_payloads[1]["OriginatorConversationID"] == minted_id
    assert captured_payloads[0]["CommandID"] == "BusinessPayment"


def test_dispatch_uses_the_till_that_received_the_money(db, monkeypatch):
    _fake_oauth(monkeypatch)
    import secrets
    from app.models.messaging import Department

    dept = Department(name=f"refund-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()

    default_config = _refund_config(db, shortcode="100001", initiator_name="default-api")
    receiving_config = _refund_config(
        db, shortcode="200002", initiator_name="receiving-api",
        department_id=dept.department_id,
    )
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=receiving_config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("100.00"),
        reason="till check", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)

    captured = {}

    def fake_post(url, **kw):
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {
            "ConversationID": "AG_1", "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)
    dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert captured["payload"]["PartyA"] == "200002"
    assert captured["payload"]["InitiatorName"] == "receiving-api"
    assert default_config.shortcode == "100001"  # sanity: the default was never used


# ─── B2C queue timeout: NOT a failure ───────────────────────────────────────


def test_b2c_timeout_moves_to_processing_not_failed(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="timeout test", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_TIMEOUT_1"
    db.commit()

    payload = {
        "Result": {
            "ResultType": 1,
            "ResultCode": 1,
            "ResultDesc": "The service request timed out.",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_TIMEOUT_1",
        }
    }

    result = handle_b2c_timeout(db, payload)
    assert result is not None
    assert result.status == "Processing"

    db.refresh(refund)
    assert refund.status == "Processing"


def test_b2c_timeout_for_an_unknown_originator_id_is_ignored(db):
    result = handle_b2c_timeout(db, {"Result": {"OriginatorConversationID": "does-not-exist"}})
    assert result is None


# ─── B2C result: success completes, both key spellings ──────────────────────


@pytest.mark.parametrize(
    "result_parameters",
    [
        pytest.param(
            [
                {"Key": "TransactionReceipt", "Value": "RBX0000001"},
                {"Key": "TransactionAmount", "Value": 200},
            ],
            id="documented-spelling",
        ),
        pytest.param(
            [
                {"Key": "ReceiptNo", "Value": "RBX0000002"},
                {"Key": "Amount", "Value": 200},
            ],
            id="alternate-spelling",
        ),
    ],
)
def test_b2c_result_success_records_the_receipt_and_completes(db, result_parameters):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="result test", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_1"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_1",
            "ResultParameters": {"ResultParameter": result_parameters},
        }
    }

    result = handle_b2c_result(db, payload)
    assert result is not None
    assert result.status == "Completed"
    assert result.transaction_receipt in ("RBX0000001", "RBX0000002")
    assert result.completed_at is not None


def test_b2c_result_missing_expected_keys_stays_processing_with_a_diagnostic(db):
    """Neither plausible spelling is present. This must not be silently
    treated as a failure: it stays Processing (an ambiguous result is not a
    verdict), and the diagnostic names the keys that actually arrived."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="missing keys", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_1"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "ok",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_1",
            "ResultParameters": {"ResultParameter": [{"Key": "SomeOtherField", "Value": "x"}]},
        }
    }

    result = handle_b2c_result(db, payload)
    assert result.status == "Processing"
    assert "keys present" in result.result_desc
    assert "SomeOtherField" in result.result_desc


def test_b2c_result_failure_code_marks_failed(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="will fail", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_1"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 1,
            "ResultDesc": "Insufficient funds in the organization's account.",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_1",
        }
    }
    result = handle_b2c_result(db, payload)
    assert result.status == "Failed"


def test_b2c_result_cannot_complete_a_different_refund(db):
    """A result must not be able to complete a DIFFERENT refund than the
    one it belongs to. A payload naming the right OriginatorConversationID
    but a DIFFERENT ConversationID than the one recorded at dispatch is
    treated as a double-dispatch alarm (Safaricom may hold two distinct
    instructions for one refund): never overwritten, never used to
    complete the refund, recorded and notified instead."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="cross-check", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_REAL"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "forged or misrouted",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_FORGED",
            "ResultParameters": {"ResultParameter": [
                {"Key": "TransactionReceipt", "Value": "RBXHACK"},
                {"Key": "TransactionAmount", "Value": 200},
            ]},
        }
    }
    result = handle_b2c_result(db, payload)
    assert result is not None
    assert "ALARM" in result.result_desc

    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.transaction_receipt is None
    assert refund.conversation_id == "AG_REAL"  # never overwritten


# ─── Refunds disabled ───────────────────────────────────────────────────────


def test_disabled_refunds_reject_at_the_service_layer_not_just_the_ui(db):
    config = _refund_config(db, refunds_enabled=False)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn.id, amount=Decimal("100.00"),
            reason="should be blocked", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "not enabled" in exc_info.value.detail


# ─── refundable_amount / misc guards ────────────────────────────────────────


def test_refundable_amount_excludes_failed_and_reversed_refunds(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("300.00"),
        reason="will fail", user_id=1,
    )
    refund.status = "Failed"
    db.commit()

    # A Failed refund never sent money, so the full receipt is still
    # refundable.
    assert refundable_amount(db, txn=txn) == Decimal("1000.00")


def test_request_refund_requires_a_settled_receipt(db):
    config = _refund_config(db)
    pending_txn = MpesaTransaction(
        phone_number="254712345678", amount=Decimal("500.00"),
        status="Pending", transaction_type="STK", mpesa_config_id=config.id,
    )
    db.add(pending_txn)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=pending_txn.id, amount=Decimal("100.00"),
            reason="not settled yet", user_id=1,
        )
    assert exc_info.value.status_code == 400


# ─── Fix round 1: C2, a stranded Approved refund must still be resolvable ───


def test_b2c_result_applies_to_an_approved_refund_whose_dispatch_response_was_lost(db):
    """C2 (revert-evidence target). dispatch_refund's own synchronous
    response can be lost (a read timeout, a dropped connection, a breaker
    trip on the response leg) even though Safaricom already accepted the
    request; the refund is then correctly left Approved, since nothing was
    known at that moment. Safaricom's result callback for that
    already-accepted instruction still arrives later and MUST be applied,
    not discarded as unrecognised: discarding it strands the refund
    Approved forever while the money has already left the till."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="lost dispatch response", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.status == "Approved"
    assert refund.conversation_id is None

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_STRANDED_1",
            "ResultParameters": {"ResultParameter": [
                {"Key": "TransactionReceipt", "Value": "RBXSTRANDED"},
                {"Key": "TransactionAmount", "Value": 200},
            ]},
        }
    }
    result = handle_b2c_result(db, payload)
    assert result is not None
    assert result.status == "Completed"
    assert result.transaction_receipt == "RBXSTRANDED"
    assert result.conversation_id == "AG_STRANDED_1"


def test_b2c_timeout_confirms_an_approved_refund_and_moves_it_to_processing(db):
    """C2's companion case for the timeout handler: a queue timeout can
    also arrive for a refund still at Approved (the synchronous ack was
    lost, but Safaricom queued the request). This confirms Safaricom holds
    it, so the refund moves to Processing, not left stranded at Approved."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="lost dispatch ack, then a timeout", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.status == "Approved"

    payload = {
        "Result": {
            "ResultType": 1,
            "ResultCode": 1,
            "ResultDesc": "The service request timed out.",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_STRANDED_TIMEOUT",
        }
    }
    result = handle_b2c_timeout(db, payload)
    assert result is not None
    assert result.status == "Processing"
    assert result.conversation_id == "AG_STRANDED_TIMEOUT"


# ─── Fix round 1: C1, a retry's own duplicate-rejection must not be Failed ──


def test_dispatch_retry_nonzero_response_code_does_not_fail_a_processing_refund(db, monkeypatch):
    """C1 (revert-evidence target). A refund that entered dispatch_refund
    already Processing (a retry) and gets a non-zero synchronous
    ResponseCode must NOT be marked Failed: that is exactly the shape of
    Safaricom recognising the retry as a duplicate of the instruction it
    already holds, i.e. the OriginatorConversationID reuse defence working
    as intended. Marking it Failed here is how the next operator action (a
    brand new refund, a brand new originator id) pays the patient twice."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="retry duplicate rejection", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)

    def fake_post_first_accept(url, **kw):
        return FakeResponse(200, {
            "ConversationID": "AG_FIRST", "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_first_accept)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")
    assert refund.status == "Processing"

    def fake_post_duplicate_rejection(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "1",
            "ResponseDescription": "Duplicate OriginatorConversationID.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_duplicate_rejection)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.status == "Processing"
    assert refund.result_desc is not None
    assert "manual review" in refund.result_desc


def test_dispatch_first_attempt_nonzero_response_code_fails_an_approved_refund(db, monkeypatch):
    """The counterpart to the test above: a non-zero synchronous
    ResponseCode on the FIRST attempt (entered as Approved) is a genuine,
    definitive rejection; no async result will ever follow it, so Failed
    is correct here."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="first attempt rejected", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)

    def fake_post_reject(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "2001", "ResponseDescription": "Invalid initiator credentials.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_reject)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.status == "Failed"


# ─── Fix round 1: I2, ConversationID is written once, never overwritten ────


def test_dispatch_never_overwrites_an_already_recorded_conversation_id(db, monkeypatch):
    """A second, DIFFERENT ConversationID arriving on a later dispatch call
    is direct evidence Safaricom may hold two distinct instructions for one
    refund. It must be recorded as an alarm, never silently overwritten:
    overwriting it would erase that evidence and retarget every later
    cross-check at the second instruction."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="conversation id integrity", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)

    def fake_post_one(url, **kw):
        return FakeResponse(200, {"ConversationID": "AG_ONE", "ResponseCode": "0", "ResponseDescription": "ok"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_one)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")
    assert refund.conversation_id == "AG_ONE"

    def fake_post_two(url, **kw):
        return FakeResponse(200, {"ConversationID": "AG_TWO", "ResponseCode": "0", "ResponseDescription": "ok"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_two)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.conversation_id == "AG_ONE"
    assert refund.result_desc is not None
    assert "ALARM" in refund.result_desc


def test_double_dispatch_alarm_from_an_approved_entry_moves_to_processing(db, monkeypatch):
    """Fix round 4 minor. When the double-dispatch alarm fires on
    dispatch_refund's own success path (ResponseCode == 0) for a refund
    that entered as Approved, the refund must move to Processing, not
    stay Approved. Approved means "not yet sent", which stops being an
    accurate description the moment Safaricom reports ANY ConversationID
    for this refund; an operator reading Approved is exactly the person
    who would file a fresh refund on top of one Safaricom already
    accepted."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="alarm from an approved entry", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    # A ConversationID already recorded while the row is still, for
    # whatever reason, at Approved.
    refund.conversation_id = "AG_EXISTING"
    db.commit()

    def fake_post_conflicting(url, **kw):
        return FakeResponse(200, {
            "ConversationID": "AG_DIFFERENT", "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_conflicting)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.status == "Processing"
    assert refund.conversation_id == "AG_EXISTING"
    assert refund.result_desc is not None
    assert "ALARM" in refund.result_desc


# ─── Fix round 1: I3, the result's amount is actually compared ─────────────


def test_b2c_result_amount_mismatch_does_not_complete(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="amount cross-check", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_AMOUNT_1"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "ok",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_AMOUNT_1",
            "ResultParameters": {"ResultParameter": [
                {"Key": "TransactionReceipt", "Value": "RBXMISMATCH"},
                {"Key": "TransactionAmount", "Value": 50},
            ]},
        }
    }
    result = handle_b2c_result(db, payload)
    assert result.status == "Processing"
    assert "KES" in result.result_desc
    assert result.transaction_receipt is None


# ─── Fix round 1: I1, the rolling cap is tenant-wide, not per-till ─────────


def test_rolling_24h_cap_applies_to_legacy_transactions_with_no_till(db):
    """I1 (also proves the tenant-wide scope). mpesa_config_id is nullable
    and NULL on every transaction written before per-department tills
    existed. A cap query joined to mpesa_config_id == config.id would
    never see a refund against such a receipt (NULL == id is NULL, never
    true in SQL), silently exempting that whole class of receipts from one
    of four load-bearing controls. It must count toward the same
    tenant-wide rolling total as every other refund."""
    config = _refund_config(db, refund_daily_cap=Decimal("500.00"))
    legacy_txn = _make_settled_txn(db, amount=Decimal("1000.00"), receipt="LEGACY1", config=None)
    normal_txn = _make_settled_txn(db, amount=Decimal("1000.00"), receipt="NORMAL1", config=config)
    db.commit()

    first = request_refund(
        db, source_transaction_id=legacy_txn.id, amount=Decimal("400.00"),
        reason="refund against a legacy, till-less receipt", user_id=1,
    )
    assert first.amount == Decimal("400.00")

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=normal_txn.id, amount=Decimal("200.00"),
            reason="pushes the tenant-wide total past the cap", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "24-hour" in exc_info.value.detail


# ─── Fix round 1: I4, a non-integral amount is rejected up front ───────────


def test_request_refund_rejects_a_non_integral_amount(db):
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn.id, amount=Decimal("250.75"),
            reason="fractional shillings", user_id=1,
        )
    assert exc_info.value.status_code == 400


# ─── Fix round 1: M4, a completed refund adjusts the invoice ───────────────


def test_completed_refund_decrements_invoice_amount_paid_and_recalculates_status(db):
    """A Completed refund must update no fewer books than the payment it
    reverses did. Without this, the invoice still says fully paid after
    part of that payment went back out to the patient: an accounting
    hole, not a missing nicety. (The ledger half is tracked separately,
    blocked on a known post_from_event/created_by defect; see the TODO
    at _apply_completed_refund_to_invoice's call site.)"""
    config = _refund_config(db)
    invoice = make_invoice(db, total_amount=Decimal("1000.00"))
    invoice.amount_paid = Decimal("1000.00")
    invoice.status = "Paid"
    db.flush()

    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    txn.invoice_id = invoice.invoice_id
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("300.00"),
        reason="partial refund, invoice adjustment", user_id=1,
    )
    refund.status = "Processing"
    refund.conversation_id = "AG_INVOICE_1"
    db.commit()

    payload = {
        "Result": {
            "ResultCode": 0,
            "ResultDesc": "ok",
            "OriginatorConversationID": refund.originator_conversation_id,
            "ConversationID": "AG_INVOICE_1",
            "ResultParameters": {"ResultParameter": [
                {"Key": "TransactionReceipt", "Value": "RBXINVOICE"},
                {"Key": "TransactionAmount", "Value": 300},
            ]},
        }
    }
    result = handle_b2c_result(db, payload)
    assert result.status == "Completed"

    db.refresh(invoice)
    assert invoice.amount_paid == Decimal("700.00")
    assert invoice.status == "Partially Paid"


# ─── Fix round 1: I6, a route-protection regression net ───────────────────


def test_every_state_changing_refund_route_requires_exactly_mpesa_refund():
    """A one-time reading that mpesa:refund gates the refund routes is not
    a net: a future edit that drops the dependency, or widens it to an
    any-of with billing:manage or another permission, would silently hand
    every holder of that other permission the ability to send money out.
    This iterates the app's actual registered routes so it fails the
    moment that happens, rather than relying on someone noticing.
    """
    import app.main as app_module
    from app.core.dependencies import RequirePermission

    refund_routes = [
        route for route in app_module.app.routes
        if "/api/payments/mpesa/refunds" in getattr(route, "path", "")
    ]
    assert refund_routes, "no refund routes found; the router may not be mounted"

    checked = 0
    for route in refund_routes:
        methods = getattr(route, "methods", None) or set()
        if "GET" in methods:
            continue  # read endpoints may reasonably allow billing:read too
        checked += 1
        required = [
            dep.call.required_permissions
            for dep in route.dependant.dependencies
            if isinstance(dep.call, RequirePermission)
        ]
        assert required, (
            f"{methods} {route.path} carries no RequirePermission dependency at all"
        )
        assert required == [("mpesa:refund",)], (
            f"{methods} {route.path} must require exactly ('mpesa:refund',), "
            f"found {required}"
        )
    assert checked >= 3, "expected at least the request/approve/retry-dispatch routes"


# ─── Fix round 2: FIX 1, Approved is ambiguous, the marker resolves it ─────


def test_retry_dispatch_after_a_lost_first_response_does_not_fail(db, monkeypatch):
    """FIX 1 (revert-evidence target). The first dispatch attempt reaches
    Safaricom, which accepts it, but the response is lost before we learn
    the outcome (a read timeout, a dropped connection). The refund is left
    Approved with no conversation_id, exactly indistinguishable, by status
    and conversation_id alone, from a refund that was never dispatched at
    all. first_dispatch_attempted_at is what tells them apart. A
    subsequent retry-dispatch that gets a non-zero ResponseCode, exactly
    what Safaricom's own duplicate-instruction rejection looks like, must
    move the refund to Processing and must NEVER reach Failed: Failed
    would release the balance and let a fresh refund pay out on top of the
    one Safaricom already accepted.
    """
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="lost first response", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.first_dispatch_attempted_at is None

    def fake_post_response_lost(url, **kw):
        raise requests.exceptions.ReadTimeout(
            "simulated: Safaricom may have already processed this request"
        )

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_response_lost)
    with pytest.raises(DarajaError):
        dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    db.refresh(refund)
    assert refund.status == "Approved"  # unchanged: nothing was learned
    assert refund.conversation_id is None
    # But the fact that an attempt was made IS now durably recorded, which
    # is the entire point: this is what a genuinely never-dispatched
    # refund would NOT have.
    assert refund.first_dispatch_attempted_at is not None

    def fake_post_duplicate_rejection(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "1",
            "ResponseDescription": "Duplicate OriginatorConversationID.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_duplicate_rejection)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.status == "Processing"
    assert refund.status != "Failed"


def test_first_ever_attempt_rejection_still_fails_correctly(db, monkeypatch):
    """The counterpart to the test above, so FIX 1 is not a one-way door:
    a refund with NO prior recorded attempt that gets a non-zero
    ResponseCode on its actual first try is a genuine, definitive
    rejection. Failed is still correct in that case."""
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="genuine first rejection", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.first_dispatch_attempted_at is None

    def fake_post_reject(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "2001", "ResponseDescription": "Invalid initiator credentials.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_reject)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert refund.status == "Failed"
    assert refund.first_dispatch_attempted_at is not None


# ─── Fix round 3: FIX 3, the marker means "a request may have reached ─────
# ─── Safaricom", not merely "dispatch_refund was called" ──────────────────


def test_marker_is_not_set_on_a_pre_flight_credential_failure(db, monkeypatch):
    """FIX 3. Obtaining a Daraja access token (a cache hit, or a fresh
    OAuth fetch) can fail before any request is ever sent to the B2C
    endpoint, on a circuit breaker trip or on Daraja rejecting the OAuth
    credentials themselves. Setting the dispatch-attempt marker before
    this check would let a misconfigured hospital's very first attempt
    permanently mark had_prior_attempt True: every later dispatch,
    including a genuine, definitive rejection, would then resolve to
    Processing forever, holding the balance and the rolling cap hostage
    with no in-product recovery (retry-dispatch is gated to Approved, and
    this refund could never be marked Failed to release it). The marker
    must stay unset when nothing was ever sent."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="bad initiator credentials", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.first_dispatch_attempted_at is None

    def fake_oauth_rejects(url, **kw):
        return FakeResponse(400, {"errorMessage": "invalid consumer key"})

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth_rejects)

    with pytest.raises(DarajaError):
        dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    db.refresh(refund)
    assert refund.status == "Approved"
    assert refund.first_dispatch_attempted_at is None

    # And once credentials are fixed, this refund is still a genuine FIRST
    # attempt: a definitive rejection now correctly fails it, rather than
    # being permanently stuck reading as "maybe already sent".
    _fake_oauth(monkeypatch)

    def fake_post_reject(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "2001", "ResponseDescription": "Invalid initiator credentials.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_reject)
    refund = dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")
    assert refund.status == "Failed"


def test_marker_is_not_set_on_an_open_breaker_with_a_warm_token_cache(db, monkeypatch):
    """Finding A (revert-evidence target). client.access_token() returns a
    cached token WITHOUT consulting the circuit breaker at all when the
    cache is warm (tokens live about an hour, so a live process is warm
    almost always). Every other test in this file runs with a cold cache
    (_clear_token_cache is autouse), which always takes the OAuth network
    path and therefore always would have hit the breaker check inside
    that path anyway, masking this gap entirely. This test warms the
    cache directly and trips the breaker, proving zero requests reach
    Safaricom's OAuth or B2C endpoints and the marker stays unset."""
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="warm cache, open breaker", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    assert refund.first_dispatch_attempted_at is None

    # Warm the cache for the exact consumer key make_mpesa_config uses.
    _TOKEN_CACHE["test-consumer-key"] = ("warm-cached-token", time.monotonic() + 3600)

    # Trip the breaker directly, the same way a completely unrelated STK
    # failure sharing this process-wide singleton would.
    daraja_breaker._state = daraja_breaker.OPEN
    daraja_breaker._opened_at = time.monotonic()

    request_count = {"n": 0}

    def fail_if_called(*args, **kwargs):
        request_count["n"] += 1
        raise AssertionError("no request should reach Daraja with the breaker open")

    monkeypatch.setattr("app.services.daraja.client.requests.get", fail_if_called)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fail_if_called)

    with pytest.raises(DarajaError):
        dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")

    assert request_count["n"] == 0, "a request reached Daraja despite the open breaker"

    db.refresh(refund)
    assert refund.status == "Approved"
    assert refund.first_dispatch_attempted_at is None


# ─── Fix round 2: FIX 2, the refund row is locked for the whole dispatch ───


def test_concurrent_dispatch_of_the_same_refund_never_double_fails(db, _engine, monkeypatch):
    """FIX 1 (revert-evidence target; supersedes the round-2 version of
    this test, which asserted only on each call's own return value and
    was satisfied by the exact broken outcome it was meant to catch).

    Two concurrent dispatch attempts against the SAME refund (a
    double-click, a manual retry racing an automated one), with no
    network fault at all. Under the two-phase ROW lock this project tried
    first, the caller that observes had_prior_attempt=True (because it
    was unblocked by the other's marker-commit) never itself commits, so
    it keeps holding the row lock and dispatches to Safaricom FIRST; the
    genuinely-first caller queues behind it, dispatches SECOND still
    carrying its own now-stale had_prior_attempt=False, and writes Failed
    on Safaricom's duplicate rejection. Critically, in that broken
    version BOTH calls actually reach Safaricom, and the LAST one to
    commit wins regardless of which is more "correct": with a mock that
    always rejects, the buggy sequence ends with the same "Failed" status
    a correct single dispatch would also produce (Processing, from the
    genuinely-first call, gets silently overwritten by Failed from the
    illegitimate second one). A status-only assertion on the final row
    cannot tell these apart. The one fact that DOES distinguish them is
    how many times Safaricom was actually asked: exactly once if the
    session-scoped advisory lock genuinely serialises the whole attempt
    (the second caller finds the refund already resolved and is refused
    before it ever builds a request), twice if it does not.

    Two real threads, two separate Sessions on two separate connections,
    a threading.Barrier so both reach dispatch_refund's lock at the same
    moment, matching the shape of the earlier over-refund concurrency
    test.
    """
    _fake_oauth(monkeypatch)
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="concurrent dispatch", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)
    refund_id = refund.id
    db.commit()

    call_count = {"n": 0}
    post_call_lock = threading.Lock()

    def fake_post_always_rejects(url, **kw):
        with post_call_lock:
            call_count["n"] += 1
        return FakeResponse(200, {
            "ResponseCode": "1", "ResponseDescription": "Duplicate OriginatorConversationID.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_always_rejects)

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    results_lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            r = session.query(MpesaRefund).filter(MpesaRefund.id == refund_id).first()
            barrier.wait(timeout=5)
            outcome = dispatch_refund(session, refund=r, callback_tenant="mayoclinic_db")
            with results_lock:
                results.append(outcome.status)
        except HTTPException as exc:
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

    # Neither thread should raise anything OTHER than the expected refusal.
    assert len(results) + len(errors) == 2

    # THE decisive proof: Safaricom was only ever asked once. A prior,
    # broken two-phase row-lock version let both calls reach Safaricom,
    # which a status-only check on the final row would not have caught
    # (see the docstring above for why).
    assert call_count["n"] == 1, (
        f"Safaricom was contacted {call_count['n']} times for one refund; "
        "expected exactly 1"
    )

    # The genuinely-first caller gets the real (rejected) outcome; the
    # second, unblocked only after the first fully resolved the refund,
    # finds it already Failed and is refused via the ordinary status
    # guard rather than ever building a second request.
    assert results == ["Failed"], f"expected exactly one real outcome, Failed; got {results}"
    assert len(errors) == 1
    assert errors[0].status_code == 409
    assert "Failed" in errors[0].detail

    # THE assertion the coordinator asked for explicitly: on the FINAL
    # PERSISTED ROW, queried fresh and independent of either worker's own
    # session, not on any call's return value.
    final_refund = (
        db.query(MpesaRefund)
        .filter(MpesaRefund.id == refund_id)
        .populate_existing()
        .first()
    )
    assert final_refund.status == "Failed"


# ─── Fix round 2: FIX 3, the rolling cap ceiling is the hospital default ───


def test_rolling_cap_ceiling_is_the_hospital_default_not_the_departments_own(db):
    """A department till configured with a HIGHER cap than the hospital
    default must not let a refund through past the hospital's own
    tenant-wide ceiling: the ceiling compared against the tenant-wide
    total is always the hospital default's refund_daily_cap, never the
    requesting till's own value."""
    import secrets
    from app.models.messaging import Department

    hospital_default = _refund_config(db, refund_daily_cap=Decimal("500.00"))

    dept = Department(name=f"high-cap-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()
    dept_config = _refund_config(
        db, shortcode="300003", initiator_name="dept-api",
        department_id=dept.department_id, refund_daily_cap=Decimal("50000.00"),
    )

    hospital_txn = _make_settled_txn(
        db, amount=Decimal("1000.00"), receipt="HOSP1", config=hospital_default,
    )
    dept_txn = _make_settled_txn(
        db, amount=Decimal("1000.00"), receipt="DEPT1", config=dept_config,
    )
    db.commit()

    first = request_refund(
        db, source_transaction_id=hospital_txn.id, amount=Decimal("400.00"),
        reason="against the hospital default till", user_id=1,
    )
    assert first.amount == Decimal("400.00")

    # Filed against the department's OWN higher-cap till, but the running
    # tenant-wide total (400 already spent) plus this 200 would push past
    # the HOSPITAL's 500 cap, not the department's 50,000 one.
    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=dept_txn.id, amount=Decimal("200.00"),
            reason="filed against the high-cap department till", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "24-hour" in exc_info.value.detail
    assert "500" in exc_info.value.detail
    assert dept_config.refund_daily_cap == Decimal("50000.00")  # untouched, just not used


def test_rolling_cap_ceiling_survives_deactivating_the_hospital_default(db):
    """FIX 4. The hospital-default cap lookup reads a policy number off
    the hospital-level configuration record; it does not choose a routing
    target. Deactivating that till (it stopped taking payments, for
    example) must not silently promote the ceiling to whichever
    higher-cap department till a refund happens to be filed against: that
    is a single boolean turning a KES 500 tenant ceiling into a KES 50,000
    one with no error and no log line.
    """
    import secrets
    from app.models.messaging import Department

    hospital_default = _refund_config(db, refund_daily_cap=Decimal("500.00"))
    hospital_default.is_active = False

    dept = Department(name=f"high-cap-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()
    dept_config = _refund_config(
        db, shortcode="400004", initiator_name="dept-api",
        department_id=dept.department_id, refund_daily_cap=Decimal("50000.00"),
    )

    hospital_txn = _make_settled_txn(
        db, amount=Decimal("1000.00"), receipt="DEACT1", config=hospital_default,
    )
    dept_txn = _make_settled_txn(
        db, amount=Decimal("1000.00"), receipt="DEACT2", config=dept_config,
    )
    db.commit()

    first = request_refund(
        db, source_transaction_id=hospital_txn.id, amount=Decimal("400.00"),
        reason="against the now-inactive hospital default's own receipt", user_id=1,
    )
    assert first.amount == Decimal("400.00")

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=dept_txn.id, amount=Decimal("200.00"),
            reason="filed against the high-cap department till", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "500" in exc_info.value.detail
    assert "50000" not in exc_info.value.detail


def test_rolling_cap_raises_a_clear_error_when_no_active_till_exists_anywhere(db):
    """Fix round 4 minor. With no hospital-default row (no department_id
    IS NULL config exists at all) and no active till anywhere, the cap
    fallback must be a hard 400, never the requesting till's own cap:
    that is exactly the bypass this whole control exists to close, and a
    refund can legitimately be filed against an inactive till (see
    _config_for_source, which does not filter on is_active)."""
    import secrets
    from app.models.messaging import Department

    dept = Department(name=f"inactive-only-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()
    config = _refund_config(
        db, shortcode="500005", initiator_name="inactive-api",
        department_id=dept.department_id,
    )
    config.is_active = False
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        request_refund(
            db, source_transaction_id=txn.id, amount=Decimal("100.00"),
            reason="no active till anywhere", user_id=1,
        )
    assert exc_info.value.status_code == 400
    assert "active M-Pesa till" in exc_info.value.detail


def test_dispatch_lock_timeout_returns_a_clean_409_not_a_hang(db, _engine):
    """Finding C. pg_advisory_lock blocks with no timeout of its own, and
    dispatch_refund's dedicated lock connection is a second connection
    from the same tenant pool the request session already holds, held
    across the whole Safaricom round trip. Without a bound, a stranded or
    genuinely slow dispatch turns a second caller's request into a hang
    rather than a clear rejection: a cashier can retry a 409, a hung
    request tells them nothing. Holds the SAME advisory lock directly, on
    a separate raw connection standing in for "another dispatch attempt
    already in progress", and confirms dispatch_refund raises a clean 409
    within the configured lock_timeout rather than hanging.
    """
    config = _refund_config(db)
    txn = _make_settled_txn(db, amount=Decimal("1000.00"), config=config)
    db.commit()

    refund = request_refund(
        db, source_transaction_id=txn.id, amount=Decimal("200.00"),
        reason="lock timeout", user_id=1,
    )
    refund = approve_refund(db, refund_id=refund.id, user_id=2)

    holder_conn = _engine.connect()
    holder_conn.begin()
    holder_conn.execute(
        text("SELECT pg_advisory_lock(:ns, :key)"),
        {"ns": _DISPATCH_LOCK_NAMESPACE, "key": refund.id},
    )
    try:
        started = time.monotonic()
        with pytest.raises(HTTPException) as exc_info:
            dispatch_refund(db, refund=refund, callback_tenant="mayoclinic_db")
        elapsed = time.monotonic() - started
        assert exc_info.value.status_code == 409
        assert "still in progress" in exc_info.value.detail
        # Bounded well under a hang. Not asserting a tight lower bound:
        # the point is "does not wait forever", not the exact millisecond.
        assert elapsed < 15.0
    finally:
        holder_conn.execute(
            text("SELECT pg_advisory_unlock(:ns, :key)"),
            {"ns": _DISPATCH_LOCK_NAMESPACE, "key": refund.id},
        )
        holder_conn.close()
