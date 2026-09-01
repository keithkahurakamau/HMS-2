"""Transaction Status and Account Balance. Both are genuinely asynchronous
Daraja commands: their synchronous response is only an acknowledgment
(ConversationID/OriginatorConversationID), never a verdict. This file only
covers that acknowledgment step, query_transaction_status. The actual
Transaction Status verdict, and the settle/quarantine decision it drives, is
covered in test_c2b.py against
app.services.daraja.c2b.handle_transaction_status_result, since that is
where the real cross-check now lives (see status.py's module docstring for
why an earlier version wrongly put it here instead).
"""
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.models.mpesa import MpesaTransaction
from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.status import account_balance, query_transaction_status
from app.config.settings import settings
from tests.daraja.conftest import make_mpesa_config


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
    """Transaction Status and Account Balance both sign with
    SecurityCredential = RSA-encrypt(initiator password), the same as B2C.
    The real Safaricom .cer files are not checked into this repo (see
    tests/daraja/test_credentials.py); a locally generated keypair stands in
    for it, exercising the real encryption code in
    credentials.security_credential without needing Safaricom's actual
    certificate."""
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


def _make_txn(db, *, amount, receipt="RCPT001", mpesa_config_id=None) -> MpesaTransaction:
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=amount,
        receipt_number=receipt,
        status="Unverified",
        transaction_type="C2B",
        mpesa_config_id=mpesa_config_id,
    )
    db.add(txn)
    db.flush()
    return txn


# ─── query_transaction_status ───────────────────────────────────────────────


def test_query_transaction_status_sends_the_receipt_and_returns_darajas_response(db, monkeypatch):
    _fake_oauth(monkeypatch)
    config = make_mpesa_config(
        db,
        shortcode="174379",
        initiator_name="testapi",
    )
    from app.utils.encryption import encrypt_data
    config.initiator_password_encrypted = encrypt_data("initiator-pass")
    db.commit()

    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {
            "OriginatorConversationID": "oc-1",
            "ConversationID": "AG_1",
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    result = query_transaction_status(db, receipt="RCPT001", callback_tenant="mayoclinic_db")

    assert captured["url"].endswith("/mpesa/transactionstatus/v1/query")
    payload = captured["payload"]
    assert payload["TransactionID"] == "RCPT001"
    assert payload["CommandID"] == "TransactionStatusQuery"
    assert payload["PartyA"] == "174379"
    assert payload["Initiator"] == "testapi"
    assert "SecurityCredential" in payload
    assert "/status/result/mayoclinic_db/" in payload["ResultURL"]
    assert "/status/timeout/mayoclinic_db/" in payload["QueueTimeOutURL"]
    assert result["ResponseDescription"] == "Accept the service request successfully."


def test_query_transaction_status_requires_a_receipt(db):
    with pytest.raises(HTTPException):
        query_transaction_status(db, receipt="", callback_tenant="mayoclinic_db")


def test_query_transaction_status_uses_the_transaction_specific_till(db, monkeypatch):
    """Mirrors query_stk's equivalent test: verification must be signed with
    the SAME till the payment actually landed on, not always the hospital
    default, or a department-till receipt can never be verified."""
    _fake_oauth(monkeypatch)
    import secrets
    from app.models.messaging import Department
    from app.utils.encryption import encrypt_data

    dept = Department(name=f"C2B-status-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()

    make_mpesa_config(db, shortcode="100001", initiator_name="default-api")  # must NOT be used
    dept_config = make_mpesa_config(
        db, shortcode="200002", initiator_name="dept-api", department_id=dept.department_id,
    )
    dept_config.initiator_password_encrypted = encrypt_data("dept-pass")
    db.commit()
    _make_txn(db, amount=Decimal("100.00"), receipt="DEPTRCPT", mpesa_config_id=dept_config.id)

    captured = {}

    def fake_post(url, **kw):
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {"ResponseDescription": "ok"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    query_transaction_status(db, receipt="DEPTRCPT", callback_tenant="mayoclinic_db")

    assert captured["payload"]["PartyA"] == "200002"
    assert captured["payload"]["Initiator"] == "dept-api"


# ─── account_balance ─────────────────────────────────────────────────────────


def test_account_balance_submits_a_request_and_never_guesses_the_figures(db, monkeypatch):
    """The real Account Balance answer arrives asynchronously on a result
    callback (see the module docstring), so this call cannot know the
    figures yet. It must return None, never 0, for both balances: telling an
    operator there is no float when the truth is simply "not answered yet"
    is the exact wrong-fact failure this guards against."""
    _fake_oauth(monkeypatch)
    from app.utils.encryption import encrypt_data

    config = make_mpesa_config(db, shortcode="174379", initiator_name="testapi")
    config.initiator_password_encrypted = encrypt_data("initiator-pass")
    db.commit()

    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {
            "ConversationID": "AG_bal_1",
            "ResponseDescription": "Accept the service request successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    result = account_balance(db, callback_tenant="mayoclinic_db")

    assert captured["url"].endswith("/mpesa/accountbalance/v1/query")
    assert captured["payload"]["CommandID"] == "AccountBalance"
    assert captured["payload"]["PartyA"] == "174379"
    assert "/balance/result/mayoclinic_db/" in captured["payload"]["ResultURL"]
    assert "/balance/timeout/mayoclinic_db/" in captured["payload"]["QueueTimeOutURL"]

    assert result["utility_balance"] is None
    assert result["working_balance"] is None
    assert result["shortcode"] == "174379"
    assert result["conversation_id"] == "AG_bal_1"


def test_account_balance_requires_an_initiator_name(db):
    make_mpesa_config(db, shortcode="174379")  # no initiator_name set

    with pytest.raises(HTTPException):
        account_balance(db, callback_tenant="mayoclinic_db")
