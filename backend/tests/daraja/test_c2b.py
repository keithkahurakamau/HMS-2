"""C2B: validation, confirmation, and the Transaction Status verification
that stands in for the missing prior record. See app/services/daraja/c2b.py's
module docstring for why this is the most dangerous flow in the migration:
a C2B confirmation has no Pending row to cross-check an amount against, so
verify_receipt (Transaction Status) is the entire third defence.

Daraja itself is mocked at one seam only: requests.* inside
app.services.daraja.client, exercised through the real DarajaClient exactly
as production traffic is.
"""
import secrets
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.models.billing import Payment
from app.models.mpesa import MpesaTransaction
from app.models.patient import Patient
from app.services.daraja.c2b import (
    handle_confirmation,
    handle_validation,
    match_c2b_invoice,
    register_c2b_urls,
)
from app.services.daraja.client import _TOKEN_CACHE
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


@pytest.fixture(autouse=True)
def _fake_safaricom_public_key(monkeypatch):
    """verify_receipt signs a Transaction Status request the same way B2C
    does, via SecurityCredential = RSA-encrypt(initiator password). The real
    Safaricom .cer files are not checked into this repo (see
    tests/daraja/test_credentials.py), so a locally generated keypair stands
    in for it here, the same technique Task 7 (B2C) uses: this exercises the
    real encryption code path in credentials.security_credential without
    needing Safaricom's actual certificate."""
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


@contextmanager
def _daraja_status_returns(*, found: bool, amount=None, capture=None):
    """Fake Daraja for the duration of the block: OAuth always succeeds, and
    a POST to the Transaction Status endpoint reports either a confirmed
    receipt (found=True, with `amount`) or Safaricom not recognising it
    (found=False). Any other POST (e.g. registerurl) gets a generic accept,
    since some tests only care about the status endpoint's behaviour.
    """
    import app.services.daraja.client as client_module

    original_get = client_module.requests.get
    original_post = client_module.requests.post

    def fake_get(url, **kw):
        return FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        if capture is not None:
            capture["url"] = url
            capture["payload"] = kw.get("json")
        if "/transactionstatus/" in url:
            if found:
                return FakeResponse(200, {
                    "ResultCode": "0",
                    "ResultDesc": "The service request has been accepted successfully.",
                    "Amount": str(amount),
                })
            return FakeResponse(200, {
                "ResultCode": "1",
                "ResultDesc": "The transaction could not be found.",
            })
        return FakeResponse(200, {"ResponseDescription": "Accepted"})

    client_module.requests.get = fake_get
    client_module.requests.post = fake_post
    try:
        yield
    finally:
        client_module.requests.get = original_get
        client_module.requests.post = original_post


def _c2b_confirmation(
    *, receipt="XYZ789", amount="1500", shortcode="174379", bill_ref="", msisdn="254712345678"
) -> dict:
    """Shaped like Daraja's real C2B Confirmation body."""
    return {
        "TransactionType": "Pay Bill",
        "TransID": receipt,
        "TransTime": "20260901103000",
        "TransAmount": str(amount),
        "BusinessShortCode": shortcode,
        "BillRefNumber": bill_ref,
        "InvoiceNumber": "",
        "OrgAccountBalance": "10000.00",
        "ThirdPartyTransID": "",
        "MSISDN": msisdn,
        "FirstName": "John",
        "MiddleName": "",
        "LastName": "Doe",
    }


def _make_config_with_initiator(db, *, shortcode: str, **overrides):
    """A config that can actually pass verify_receipt's credential check
    (Initiator + SecurityCredential), for tests that expect Safaricom's
    Transaction Status to be genuinely reachable and only fail (or succeed)
    on the found/amount comparison, not on missing configuration."""
    from app.utils.encryption import encrypt_data

    config = make_mpesa_config(
        db, shortcode=shortcode, initiator_name="testapi", **overrides,
    )
    config.initiator_password_encrypted = encrypt_data("initiator-pass")
    db.commit()
    return config


def _make_patient(db, *, phone: str) -> Patient:
    suffix = secrets.token_hex(4)
    patient = Patient(
        outpatient_no=f"OPD-{suffix}",
        surname="Test",
        other_names="Patient",
        sex="Female",
        date_of_birth=date(1990, 1, 1),
        telephone_1=phone,
    )
    db.add(patient)
    db.flush()
    return patient


# ─── The critical verification test ─────────────────────────────────────────


def test_c2b_confirmation_is_not_posted_to_the_ledger_until_verified(db):
    """A C2B confirmation has no prior record by definition: the customer
    just walked up and paid the till. Since the callback is unsigned, the
    receipt is verified against Daraja's Transaction Status API before any
    money moves. Unverified receipts sit on the unmatched queue for a
    human."""
    config = make_mpesa_config(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="XYZ789", amount="1500", shortcode=config.shortcode)

    with _daraja_status_returns(found=False):
        txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.verified_at is None
    assert txn.status == "Unverified"
    assert db.query(Payment).count() == 0


def test_verified_c2b_confirmation_matches_and_settles(db):
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("1500.00"))
    payload = _c2b_confirmation(
        receipt="VERIFIED001", amount="1500", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )

    with _daraja_status_returns(found=True, amount="1500"):
        txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Success"
    assert txn.verified_at is not None
    assert txn.verification_source == "transaction_status"
    assert txn.match_basis == "bill_ref_number"
    assert db.query(Payment).count() == 1

    db.refresh(invoice)
    assert invoice.amount_paid == Decimal("1500.00")
    assert invoice.status == "Paid"


def test_c2b_confirmation_amount_mismatch_against_safaricom_is_unverified(db):
    """Safaricom knowing the receipt is not enough on its own: the amount it
    reports must also match what the confirmation claimed, or a forged
    confirmation could under-report Safaricom's own figure and still pass."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="MISMATCH001", amount="1500", shortcode=config.shortcode)

    with _daraja_status_returns(found=True, amount="1.00"):
        txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unverified"
    assert txn.verified_at is None
    assert db.query(Payment).count() == 0


def test_c2b_confirmation_replay_is_a_no_op(db):
    """Safaricom retries. A second delivery of the same receipt must not
    create a second MpesaTransaction or a second Payment."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    payload = _c2b_confirmation(
        receipt="REPLAY001", amount="500", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )

    with _daraja_status_returns(found=True, amount="500"):
        handle_confirmation(db, payload, callback_tenant="mayoclinic_db")
        assert db.query(Payment).count() == 1
        handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert db.query(MpesaTransaction).filter(MpesaTransaction.receipt_number == "REPLAY001").count() == 1
    assert db.query(Payment).count() == 1


def test_c2b_confirmation_for_an_unknown_shortcode_is_recorded_unverified(db):
    """A shortcode that matches no active till in this tenant cannot be
    verified (there is no config to sign a Transaction Status request with),
    but the money still happened, so it stays on record rather than being
    dropped."""
    payload = _c2b_confirmation(receipt="NOCFG001", amount="200", shortcode="000000")

    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unverified"
    assert txn.verified_at is None
    assert txn.mpesa_config_id is None
    assert db.query(Payment).count() == 0


# ─── The match-order test ────────────────────────────────────────────────────


def test_c2b_matching_falls_through_bill_ref_then_opd_then_phone(db):
    """Match order: the PayBill account number the customer typed
    (BillRefNumber), then an OPD number, then the phone. Anything unmatched
    goes to the queue rather than being guessed at.

    Each case below is built so more than one basis COULD match, and asserts
    that only the earlier, more specific basis in the documented order is
    the one actually used. That is the property this test exists to prove,
    not merely that each basis works in isolation.
    """
    make_mpesa_config(db, shortcode="174379")

    # 1) bill_ref_number wins even though the payer's phone also resolves to
    #    a different patient's outstanding invoice.
    bill_ref_invoice = make_invoice(db, total_amount=Decimal("500.00"))
    phone_decoy_patient = _make_patient(db, phone="0711000001")
    make_invoice(db, total_amount=Decimal("500.00"), patient_id=phone_decoy_patient.patient_id)

    invoice, basis = match_c2b_invoice(
        db, bill_ref_number=f"INV-{bill_ref_invoice.invoice_id}", msisdn="254711000001",
    )
    assert basis == "bill_ref_number"
    assert invoice.invoice_id == bill_ref_invoice.invoice_id

    # 2) opd_number wins when bill_ref does not resolve to an invoice id,
    #    even though the payer's phone also resolves to a different patient.
    opd_patient = _make_patient(db, phone="0711000002")
    opd_invoice = make_invoice(db, total_amount=Decimal("300.00"), patient_id=opd_patient.patient_id)
    phone_decoy_patient_2 = _make_patient(db, phone="0711000003")
    make_invoice(db, total_amount=Decimal("300.00"), patient_id=phone_decoy_patient_2.patient_id)

    invoice, basis = match_c2b_invoice(
        db, bill_ref_number=opd_patient.outpatient_no, msisdn="254711000003",
    )
    assert basis == "opd_number"
    assert invoice.invoice_id == opd_invoice.invoice_id

    # 3) phone is the last resort, used only when neither of the above
    #    resolves to anything.
    phone_patient = _make_patient(db, phone="0711000004")
    phone_invoice = make_invoice(db, total_amount=Decimal("200.00"), patient_id=phone_patient.patient_id)

    invoice, basis = match_c2b_invoice(
        db, bill_ref_number="not-a-reference", msisdn="254711000004",
    )
    assert basis == "phone"
    assert invoice.invoice_id == phone_invoice.invoice_id

    # 4) nothing matches: queued for a human, never guessed.
    invoice, basis = match_c2b_invoice(
        db, bill_ref_number="still-not-a-reference", msisdn="254799999999",
    )
    assert invoice is None
    assert basis == "unmatched"


def test_c2b_confirmation_with_no_invoice_match_is_unmatched_not_guessed(db):
    """A verified receipt that matches no invoice by any basis is recorded
    Unmatched, on the record, but nothing is posted against any invoice."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(
        receipt="NOMATCH001", amount="750", shortcode=config.shortcode,
        bill_ref="not-a-reference", msisdn="254700000000",
    )

    with _daraja_status_returns(found=True, amount="750"):
        txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unmatched"
    assert txn.match_basis == "unmatched"
    assert txn.verified_at is not None
    assert txn.invoice_id is None
    assert db.query(Payment).count() == 0


# ─── Validation ─────────────────────────────────────────────────────────────


def test_handle_validation_accepts_a_known_active_till(db):
    config = make_mpesa_config(db, shortcode="174379")
    payload = {"BusinessShortCode": config.shortcode, "TransAmount": "100"}

    assert handle_validation(db, payload) is True


def test_handle_validation_rejects_an_unknown_shortcode(db):
    make_mpesa_config(db, shortcode="174379")
    payload = {"BusinessShortCode": "999999", "TransAmount": "100"}

    assert handle_validation(db, payload) is False


def test_handle_validation_rejects_a_non_positive_amount(db):
    config = make_mpesa_config(db, shortcode="174379")
    payload = {"BusinessShortCode": config.shortcode, "TransAmount": "0"}

    assert handle_validation(db, payload) is False


# ─── Registration ───────────────────────────────────────────────────────────


def test_register_c2b_urls_registers_every_active_till(db, monkeypatch):
    _fake_oauth(monkeypatch)
    captured = []

    def fake_post(url, **kw):
        captured.append((url, kw.get("json")))
        return FakeResponse(200, {"ResponseDescription": "success"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    config_a = make_mpesa_config(db, shortcode="100001")

    result = register_c2b_urls(db, callback_tenant="mayoclinic_db")

    assert result["results"][0]["registered"] is True
    db.refresh(config_a)
    assert config_a.c2b_urls_registered_at is not None

    url, payload = captured[0]
    assert url.endswith("/mpesa/c2b/v1/registerurl")
    assert payload["ShortCode"] == "100001"
    assert payload["ResponseType"] == "Completed"
    assert "/c2b/confirmation/mayoclinic_db/" in payload["ConfirmationURL"]
    assert "/c2b/validation/mayoclinic_db/" in payload["ValidationURL"]


def test_register_c2b_urls_does_not_stop_on_one_failing_config(db, monkeypatch):
    _fake_oauth(monkeypatch)

    def fake_post(url, **kw):
        payload = kw.get("json") or {}
        if payload.get("ShortCode") == "BAD001":
            return FakeResponse(500, {"errorMessage": "boom"})
        return FakeResponse(200, {"ResponseDescription": "success"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    # Only one NULL-department (hospital default) config row is allowed, so
    # the failing config is given a department of its own rather than
    # sharing the default slot with the one that should succeed.
    from app.models.messaging import Department
    dept = Department(name=f"C2B-fail-dept-{secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()

    make_mpesa_config(db, shortcode="BAD001", department_id=dept.department_id)
    good = make_mpesa_config(db, shortcode="200002")

    result = register_c2b_urls(db, callback_tenant="mayoclinic_db")

    by_shortcode = {row["shortcode"]: row for row in result["results"]}
    assert by_shortcode["BAD001"]["registered"] is False
    assert by_shortcode["200002"]["registered"] is True
    db.refresh(good)
    assert good.c2b_urls_registered_at is not None
