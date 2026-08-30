"""STK Push and STK Query, mocked at the one seam: requests.* inside
app.services.daraja.client. This exercises the real DarajaClient (token
fetch, auth header, error handling) the same way production traffic does,
not a stand-in for it.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.stk import initiate_stk_push, query_stk
from app.models.mpesa import MpesaTransaction
from app.config.settings import settings
from tests.daraja.conftest import make_invoice, make_mpesa_config
from tests.daraja.test_department_tills import make_department


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


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    yield


def _fake_oauth(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )


def _fake_stk_success(monkeypatch, *, checkout_request_id="ws_CO_abc123", capture=None):
    def fake_post(url, **kw):
        if capture is not None:
            capture["url"] = url
            capture["payload"] = kw.get("json")
        return FakeResponse(200, {
            "MerchantRequestID": "mr-1",
            "CheckoutRequestID": checkout_request_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        })
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)


def test_initiate_stk_push_persists_pending_transaction_before_returning(db, monkeypatch):
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_999")
    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))

    result = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("500.00"),
        invoice_id=invoice.invoice_id,
        callback_tenant="mayoclinic_db",
    )

    assert result["checkout_request_id"] == "ws_CO_999"
    assert result["merchant_request_id"] == "mr-1"
    assert result["transaction_id"] is not None

    # Persisted and COMMITTED (a fresh query, not just the in-memory object)
    # before initiate_stk_push returned, exactly so a callback that beats us
    # to the punch still finds a row.
    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == "ws_CO_999")
        .first()
    )
    assert txn is not None
    assert txn.status == "Pending"
    assert txn.amount == Decimal("500.00")
    assert txn.phone_number == "254712345678"
    assert txn.invoice_id == invoice.invoice_id


def test_account_reference_and_transaction_desc_are_truncated_to_daraja_limits(db, monkeypatch):
    """Daraja enforces AccountReference<=12 and TransactionDesc<=13 with an
    opaque error. Truncate here, deliberately, rather than discover it in
    production."""
    _fake_oauth(monkeypatch)
    captured = {}
    _fake_stk_success(monkeypatch, capture=captured)
    make_mpesa_config(db)

    initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("100.00"),
        account_reference="THIS-REFERENCE-IS-WAY-TOO-LONG",
        transaction_desc="This description is also far too long for Daraja",
        callback_tenant="mayoclinic_db",
    )

    payload = captured["payload"]
    assert len(payload["AccountReference"]) <= 12
    assert len(payload["TransactionDesc"]) <= 13
    assert payload["AccountReference"] == "THIS-REFEREN"
    assert payload["TransactionDesc"] == "This descript"


def test_amount_is_sent_as_whole_shillings(db, monkeypatch):
    """Daraja's wire format takes whole shillings; the int() cast is only
    correct at this boundary, never earlier."""
    _fake_oauth(monkeypatch)
    captured = {}
    _fake_stk_success(monkeypatch, capture=captured)
    make_mpesa_config(db)

    initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("1234.00"),
        callback_tenant="mayoclinic_db",
    )

    assert captured["payload"]["Amount"] == 1234
    assert isinstance(captured["payload"]["Amount"], int)


def test_fractional_amount_is_rounded_up_and_persisted_consistently(db, monkeypatch):
    """A fractional invoice (KES 1250.50) must round UP to what Daraja is
    quoted, and the SAME rounded figure must be what MpesaTransaction.amount
    stores. If the two ever diverged, a legitimate callback reporting the
    quoted 1251 would be quarantined against a stored 1250.50, on every
    single invoice with cents."""
    _fake_oauth(monkeypatch)
    captured = {}
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_fraction", capture=captured)
    make_mpesa_config(db)

    result = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("1250.50"),
        callback_tenant="mayoclinic_db",
    )

    assert captured["payload"]["Amount"] == 1251
    assert isinstance(captured["payload"]["Amount"], int)
    assert result["amount_charged"] == Decimal("1251")

    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == "ws_CO_fraction")
        .first()
    )
    assert txn.amount == Decimal("1251")


def test_callback_url_carries_the_tenant_hint_and_the_decrypted_token(db, monkeypatch):
    from app.utils.encryption import decrypt_data

    _fake_oauth(monkeypatch)
    captured = {}
    _fake_stk_success(monkeypatch, capture=captured)
    config = make_mpesa_config(db)

    initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("100.00"),
        callback_tenant="mayoclinic_db",
    )

    url = captured["payload"]["CallBackURL"]
    assert url.startswith(
        "https://mayoclinic.medifleet.app/api/payments/mpesa/stk/callback/mayoclinic_db/"
    )
    # The path segment after the hint must be the plaintext token, decrypted
    # from callback_token_encrypted, never the lookup hash or the ciphertext
    # itself, and never empty.
    token = url.rsplit("/", 1)[-1]
    expected_token = decrypt_data(config.callback_token_encrypted)
    assert token == expected_token
    assert token != config.callback_token_encrypted
    assert token != config.callback_token_lookup


def test_initiate_stk_push_without_a_tenant_hint_raises(db, monkeypatch):
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch)
    make_mpesa_config(db)

    with pytest.raises(HTTPException):
        initiate_stk_push(db, phone_number="0712345678", amount=Decimal("100.00"))


def test_initiate_stk_push_rejects_a_bad_phone_number(db, monkeypatch):
    """normalize_msisdn raises ValueError; the boundary must translate that
    into a 400, not let it escape as an unhandled 500."""
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch)
    make_mpesa_config(db)

    with pytest.raises(HTTPException) as exc_info:
        initiate_stk_push(
            db, phone_number="not-a-phone", amount=Decimal("100.00"),
            callback_tenant="mayoclinic_db",
        )
    assert exc_info.value.status_code == 400


def test_initiate_stk_push_without_a_configured_tenant_raises(db, monkeypatch):
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch)
    # No MpesaConfig row at all.
    with pytest.raises(HTTPException):
        initiate_stk_push(
            db, phone_number="0712345678", amount=Decimal("100.00"),
            callback_tenant="mayoclinic_db",
        )


def test_query_stk_sends_the_checkout_request_id_and_returns_darajas_response(db, monkeypatch):
    _fake_oauth(monkeypatch)
    make_mpesa_config(db)

    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {
            "ResponseCode": "0",
            "ResultCode": "0",
            "ResultDesc": "The service request is processed successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    result = query_stk(db, checkout_request_id="ws_CO_555")

    assert captured["payload"]["CheckoutRequestID"] == "ws_CO_555"
    assert result["ResultDesc"] == "The service request is processed successfully."


def test_query_stk_requires_a_checkout_request_id(db):
    with pytest.raises(HTTPException):
        query_stk(db, checkout_request_id="")


def test_query_stk_uses_the_transaction_specific_till_not_the_default(db, monkeypatch):
    """query_stk must sign with the SAME till the original push used.
    Falling back unconditionally to config_for's hospital default (as an
    earlier version did) makes Daraja reject the signature for any push
    that was made on a department till, since the password is derived
    from the shortcode and passkey: reconciliation could never resolve a
    department-till transaction. The transaction's own mpesa_config_id,
    set at push time, is what query_stk must resolve the config from."""
    _fake_oauth(monkeypatch)
    dept = make_department(db, name="Pharmacy-query-till")
    make_mpesa_config(db, shortcode="100001")  # hospital default, must NOT be used
    dept_config = make_mpesa_config(
        db, shortcode="200002", department_id=dept.department_id,
    )
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=Decimal("100.00"),
        checkout_request_id="ws_CO_dept_query",
        merchant_request_id="mr_dept_query",
        status="Pending",
        transaction_type="STK",
        mpesa_config_id=dept_config.id,
    )
    db.add(txn)
    db.flush()

    captured = {}

    def fake_post(url, **kw):
        captured["payload"] = kw.get("json")
        return FakeResponse(200, {
            "ResponseCode": "0",
            "ResultCode": "0",
            "ResultDesc": "The service request is processed successfully.",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    query_stk(db, checkout_request_id="ws_CO_dept_query")

    assert captured["payload"]["BusinessShortCode"] == "200002"
