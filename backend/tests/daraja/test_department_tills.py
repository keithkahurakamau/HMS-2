"""Per-department tills: mpesa_configs becomes multi-row with a nullable
department_id, config_for() resolves it, and mpesa_transactions records
which till took the money.

Department rows are not truncated by the shared `db` fixture (they belong
to app/models/messaging.py, not this package's table list), so every
department here gets a name unique to the test, not a fixed literal, to
avoid colliding with department rows left behind by other tests in the
same session-scoped database.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.messaging import Department
from app.models.mpesa import MpesaTransaction
from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.stk import config_for, initiate_stk_push
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


def _fake_stk_success(monkeypatch, *, checkout_request_id="ws_CO_dept"):
    def fake_post(url, **kw):
        return FakeResponse(200, {
            "MerchantRequestID": "mr-dept",
            "CheckoutRequestID": checkout_request_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        })
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)


def make_department(db, *, name: str, is_active: bool = True) -> Department:
    dept = Department(name=name, is_active=is_active)
    db.add(dept)
    db.flush()
    return dept


def test_department_with_its_own_till_uses_it(db):
    dept = make_department(db, name="Pharmacy-owns-till")
    default_config = make_mpesa_config(db, shortcode="000000")
    dept_config = make_mpesa_config(db, shortcode="111111", department_id=dept.department_id)

    resolved = config_for(db, department_id=dept.department_id)

    assert resolved.id == dept_config.id
    assert resolved.id != default_config.id


def test_department_without_a_till_falls_back_to_the_hospital_default(db):
    dept = make_department(db, name="Laboratory-no-till")
    default_config = make_mpesa_config(db, shortcode="222222")

    resolved = config_for(db, department_id=dept.department_id)

    assert resolved.id == default_config.id


def test_inactive_department_till_falls_back_rather_than_failing(db):
    dept = make_department(db, name="Maternity-switched-off")
    default_config = make_mpesa_config(db, shortcode="333333")
    make_mpesa_config(
        db, shortcode="444444", department_id=dept.department_id, is_active=False,
    )

    # An inactive department till must NOT raise: the department keeps
    # collecting through the hospital default instead.
    resolved = config_for(db, department_id=dept.department_id)

    assert resolved.id == default_config.id


def test_no_config_at_all_raises_not_configured(db):
    with pytest.raises(HTTPException) as exc_info:
        config_for(db)
    assert exc_info.value.status_code == 400


def test_two_default_rows_are_rejected_by_the_database(db):
    make_mpesa_config(db, shortcode="555555")
    with pytest.raises(IntegrityError):
        make_mpesa_config(db, shortcode="666666")


def test_two_configs_for_one_department_are_rejected_by_the_database(db):
    dept = make_department(db, name="Outpatient-double-config")
    make_mpesa_config(db, shortcode="777777", department_id=dept.department_id)
    with pytest.raises(IntegrityError):
        make_mpesa_config(db, shortcode="888888", department_id=dept.department_id)


def test_transaction_records_which_till_took_the_money(db, monkeypatch):
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_till_record")
    dept = make_department(db, name="Radiology-till-record")
    make_mpesa_config(db, shortcode="999999")  # hospital default, must NOT be used
    dept_config = make_mpesa_config(
        db, shortcode="121212", department_id=dept.department_id,
    )
    invoice = make_invoice(db, total_amount=Decimal("300.00"))

    result = initiate_stk_push(
        db,
        phone_number="0712345678",
        amount=Decimal("300.00"),
        invoice_id=invoice.invoice_id,
        callback_tenant="mayoclinic_db",
        department_id=dept.department_id,
    )

    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.id == result["transaction_id"])
        .first()
    )
    assert txn is not None
    assert txn.mpesa_config_id == dept_config.id
