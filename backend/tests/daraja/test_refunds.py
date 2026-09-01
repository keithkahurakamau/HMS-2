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
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.b2c import (
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


# ─── Fix round 2: FIX 2, the refund row is locked for the whole dispatch ───


def test_concurrent_dispatch_of_the_same_refund_never_double_fails(db, _engine, monkeypatch):
    """FIX 2 (revert-evidence target). Two concurrent dispatch attempts
    against the SAME refund (a double-click, a manual retry racing an
    automated one) with no network fault at all: both would, without the
    row lock, read entry_status == "Approved" with no prior attempt, both
    dispatch, and whichever received the (simulated) duplicate rejection
    would incorrectly hit Failed. With the lock, exactly one of the two
    is the genuine first attempt (and may legitimately fail on its own
    rejection); the other necessarily observes the marker the first one
    committed and can never be marked Failed.

    Two real threads, two separate Sessions on two separate connections,
    a threading.Barrier so both reach dispatch_refund's row lock at the
    same moment, matching the shape of the earlier over-refund concurrency
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

    def fake_post_always_rejects(url, **kw):
        return FakeResponse(200, {
            "ResponseCode": "1", "ResponseDescription": "Duplicate OriginatorConversationID.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post_always_rejects)

    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            r = session.query(MpesaRefund).filter(MpesaRefund.id == refund_id).first()
            barrier.wait(timeout=5)
            outcome = dispatch_refund(session, refund=r, callback_tenant="mayoclinic_db")
            with lock:
                results.append(outcome.status)
        except Exception as exc:  # noqa: BLE001, captured for the assertion below
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

    assert not errors, f"unexpected errors from concurrent dispatch: {errors}"
    assert len(results) == 2
    # The safety property: never both Failed. Exactly one of the two
    # observed no prior attempt (and may legitimately fail on its own
    # rejection); the other is guaranteed to have observed the marker the
    # first one committed, and must resolve to Processing instead.
    assert results.count("Failed") <= 1, (
        f"both concurrent dispatches reached Failed: {results}"
    )
    assert set(results) <= {"Failed", "Processing"}


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
