"""C2B: validation, confirmation, and the Transaction Status result that
carries the actual verdict. See app/services/daraja/c2b.py's module
docstring for why this is the most dangerous flow in the migration, and why
verification (and settlement with it) is deferred to a separate result
callback rather than decided inline: Safaricom's Transaction Status query is
documented as asynchronous, so its synchronous acknowledgment is not a
verdict on anything.

Daraja itself is mocked at one seam only: requests.* inside
app.services.daraja.client, exercised through the real DarajaClient exactly
as production traffic is.
"""
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.models.billing import Payment
from app.models.mpesa import MpesaTransaction
from app.models.patient import Patient
from app.services.daraja.c2b import (
    c2b_readiness,
    handle_confirmation,
    handle_validation,
    match_c2b_invoice,
    register_c2b_urls,
)
from app.services.daraja.status import (
    handle_transaction_status_result,
    handle_transaction_status_timeout,
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
    """Firing a Transaction Status query signs it the same way B2C does, via
    SecurityCredential = RSA-encrypt(initiator password). The real Safaricom
    .cer files are not checked into this repo (see
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


def _fake_status_ack(monkeypatch, *, conversation_id="AG-1", originator_conversation_id="OC-1"):
    """Fake Daraja's Transaction Status ACKNOWLEDGMENT only: OAuth succeeds,
    and a POST to the Transaction Status endpoint returns Safaricom's
    same-request acceptance (ConversationID/OriginatorConversationID), never
    a verdict. That is the whole point of the redesign this test file
    covers: handle_confirmation only ever sees this shape, never an amount
    or a found/not-found answer, because Safaricom does not put those in
    this response."""
    _fake_oauth(monkeypatch)

    def fake_post(url, **kw):
        if "/transactionstatus/" in url:
            return FakeResponse(200, {
                "OriginatorConversationID": originator_conversation_id,
                "ConversationID": conversation_id,
                "ResponseCode": "0",
                "ResponseDescription": "Accept the service request successfully.",
            })
        return FakeResponse(200, {"ResponseDescription": "Accepted"})

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)


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


def _status_result(
    *, conversation_id, originator_conversation_id="OC-1", result_code=0,
    result_desc="The service request is processed successfully.", amount=None,
    amount_key="TransactionAmount", receipt=None, receipt_key="TransactionReceipt",
    transaction_status="Completed", extra_params=None,
) -> dict:
    """Shaped like Safaricom's real asynchronous Transaction Status result
    callback: the verdict lives here, never in query_transaction_status's
    own synchronous return value.

    `amount_key` and `receipt_key` default to one spelling each so callers
    can deliberately build the OTHER spelling too (Amount vs
    TransactionAmount, ReceiptNo vs TransactionReceipt): Safaricom's own key
    name for each field is not settled between documentation sources, and a
    test suite that only ever builds one spelling would never catch the
    implementation silently assuming the wrong one.
    """
    result_parameters = []
    if amount is not None:
        result_parameters.append({"Key": amount_key, "Value": amount})
    if receipt is not None:
        result_parameters.append({"Key": receipt_key, "Value": receipt})
    if transaction_status is not None:
        result_parameters.append({"Key": "TransactionStatus", "Value": transaction_status})
    if extra_params:
        result_parameters.extend(extra_params)
    return {
        "Result": {
            "ResultType": 0,
            "ResultCode": result_code,
            "ResultDesc": result_desc,
            "OriginatorConversationID": originator_conversation_id,
            "ConversationID": conversation_id,
            "TransactionID": "whatever",
            "ResultParameters": {"ResultParameter": result_parameters},
            "ReferenceData": {"ReferenceItem": {"Key": "Occasion", "Value": ""}},
        }
    }


def _status_timeout(*, conversation_id, originator_conversation_id="OC-1") -> dict:
    return {
        "Result": {
            "ResultType": 1,
            "ResultCode": 1,
            "ResultDesc": "The service request timed out.",
            "OriginatorConversationID": originator_conversation_id,
            "ConversationID": conversation_id,
        }
    }


def _make_config_with_initiator(db, *, shortcode: str, **overrides):
    """A config that can actually fire a Transaction Status request
    (Initiator + SecurityCredential), for tests that expect
    handle_confirmation to genuinely reach Daraja rather than fail on
    missing configuration."""
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


# ─── The critical test: confirmation never settles synchronously ───────────


def test_c2b_confirmation_is_not_posted_to_the_ledger_until_verified(db, monkeypatch):
    """A C2B confirmation has no prior record by definition: the customer
    just walked up and paid the till. Verification is asynchronous
    (Transaction Status answers on a separate result callback, not in the
    query's own response), so handle_confirmation itself must NEVER settle:
    it only records Unverified and fires the query. Unverified receipts sit
    on the unmatched queue for a human until (if) a result arrives."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="XYZ789", amount="1500", shortcode=config.shortcode)
    _fake_status_ack(monkeypatch, conversation_id="AG-XYZ", originator_conversation_id="OC-XYZ")

    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.verified_at is None
    assert txn.status == "Unverified"
    assert txn.conversation_id == "AG-XYZ"
    assert txn.originator_conversation_id == "OC-XYZ"
    assert db.query(Payment).count() == 0


def test_c2b_confirmation_replay_is_a_no_op(db, monkeypatch):
    """Safaricom retries. A second delivery of the same receipt must not
    create a second MpesaTransaction or re-fire the Transaction Status
    query."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="REPLAY001", amount="500", shortcode=config.shortcode)

    query_calls = {"n": 0}

    def fake_post(url, **kw):
        if "/transactionstatus/" in url:
            query_calls["n"] += 1
            return FakeResponse(200, {"ConversationID": "AG-1", "OriginatorConversationID": "OC-1"})
        return FakeResponse(200, {})

    _fake_oauth(monkeypatch)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert query_calls["n"] == 1
    assert db.query(MpesaTransaction).filter(MpesaTransaction.receipt_number == "REPLAY001").count() == 1


def test_c2b_confirmation_for_an_unknown_shortcode_is_recorded_unverified(db):
    """A shortcode that matches no active till in this tenant cannot fire a
    Transaction Status request (there is no config to sign it with), but the
    money still happened, so it stays on record rather than being dropped."""
    payload = _c2b_confirmation(receipt="NOCFG001", amount="200", shortcode="000000")

    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unverified"
    assert txn.verified_at is None
    assert txn.mpesa_config_id is None
    assert txn.conversation_id is None
    assert db.query(Payment).count() == 0


def test_c2b_confirmation_survives_a_query_failure(db, monkeypatch):
    """A network hiccup submitting the Transaction Status query is not a
    reason to lose the record of money that already reached the till: the
    row is still created, Unverified, with no correlation ids. result_desc
    must still say something a human can act on: a message this test does
    not check is a guarantee nobody is actually holding this code to."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="NETFAIL001", amount="200", shortcode=config.shortcode)

    _fake_oauth(monkeypatch)

    import requests as requests_module

    def fake_post(url, **kw):
        raise requests_module.exceptions.ConnectionError("boom")

    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unverified"
    assert txn.conversation_id is None
    assert db.query(Payment).count() == 0
    # Not an exact string: the message must exist and must actually
    # describe a network problem, so a cashier reading the unmatched queue
    # is not left with an empty or meaningless field.
    assert txn.result_desc
    assert "unreachable" in txn.result_desc.lower()


def test_c2b_confirmation_result_desc_names_missing_initiator_credentials(db):
    """This IS the entire point of the initiator-credential coupling work:
    a till can be fully registered with Safaricom and still be unable to
    verify a single payment because nobody set its initiator credentials.
    result_desc is the ONE human-facing signal that tells a cashier why a
    verifying-nothing till is verifying nothing; if this message were
    silently empty or wrong, a hospital would see a green till, take real
    money, and have no way to learn why nothing settles.

    Deliberately asserts on MEANING (non-empty, names the missing
    credential) rather than an exact string, so a later wording change does
    not break this test but a silently empty or wrong message does.
    """
    # No initiator_name / initiator_password_encrypted set: make_mpesa_config
    # (unlike _make_config_with_initiator) leaves both unset.
    config = make_mpesa_config(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="NOINITIATOR001", amount="300", shortcode=config.shortcode)

    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    assert txn.status == "Unverified"
    assert txn.conversation_id is None
    assert db.query(Payment).count() == 0
    assert txn.result_desc
    assert "initiator" in txn.result_desc.lower()


# ─── The critical test: the Transaction Status result decides everything ───


def test_transaction_status_result_corroborating_amount_settles(db, monkeypatch):
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    payload = _c2b_confirmation(
        receipt="TSR001", amount="500", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-TSR001")
    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")
    assert txn.status == "Unverified"

    result_payload = _status_result(
        conversation_id="AG-TSR001", result_code=0, amount="500", receipt="TSR001",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Success"
    assert resolved.verified_at is not None
    assert resolved.verification_source == "transaction_status"
    assert resolved.match_basis == "bill_ref_number"
    assert db.query(Payment).count() == 1

    db.refresh(invoice)
    assert invoice.amount_paid == Decimal("500.00")
    assert invoice.status == "Paid"


def test_transaction_status_result_contradicting_amount_quarantines(db, monkeypatch):
    """Safaricom knowing the receipt is not enough: the amount it reports
    must also match what the confirmation claimed, or a forged/malformed
    confirmation could under-report Safaricom's own figure and still pass."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("1500.00"))
    payload = _c2b_confirmation(
        receipt="MISMATCH001", amount="1500", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-MISMATCH")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-MISMATCH", result_code=0, amount="1.00", receipt="MISMATCH001",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert resolved.verified_at is None
    assert db.query(Payment).count() == 0
    db.refresh(invoice)
    assert invoice.amount_paid == 0
    assert invoice.status == "Pending"


def test_c2b_quarantine_notification_identifies_the_receipt_and_till(db, monkeypatch):
    """_notify_quarantine (settlement.py) swallows every exception raised
    inside it, since a notification failure must never look like a
    settlement failure. That is exactly the combination, untested plus
    silent, that hides a defect indefinitely: before this fix, every C2B
    quarantine notification read "CheckoutRequestID None: ...", which told
    a cashier nothing about which payment to look for. Monkeypatches
    notify_permission directly and asserts the actual body names both the
    receipt and the till, rather than trusting that _notify_quarantine ran
    without raising."""
    config = _make_config_with_initiator(db, shortcode="900009")
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    payload = _c2b_confirmation(
        receipt="QUARANTINE001", amount="500", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-QUARANTINE")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    captured = {}

    def fake_notify_permission(db, codename, *, title, body=None, **kwargs):
        captured["codename"] = codename
        captured["title"] = title
        captured["body"] = body
        return 0

    monkeypatch.setattr("app.utils.notify.notify_permission", fake_notify_permission)

    result_payload = _status_result(
        conversation_id="AG-QUARANTINE", result_code=0, amount="1.00", receipt="QUARANTINE001",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert captured.get("codename") == "billing:manage"
    assert captured.get("body")
    assert "QUARANTINE001" in captured["body"]
    assert "900009" in captured["body"]


def test_transaction_status_result_for_unknown_conversation_id_is_ignored(db, monkeypatch):
    """A result whose ConversationID matches no row we created (forged, for
    another deployment, or a replay of one already resolved) is ignored, not
    acted on: there is nothing here to guess at."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="REALROW001", amount="300", shortcode=config.shortcode)
    _fake_status_ack(monkeypatch, conversation_id="AG-REAL")
    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    resolved = handle_transaction_status_result(
        db, _status_result(
            conversation_id="AG-DOES-NOT-EXIST", result_code=0, amount="300",
            receipt="REALROW001",
        ),
    )

    assert resolved is None
    db.refresh(txn)
    assert txn.status == "Unverified"
    assert txn.verified_at is None
    assert db.query(Payment).count() == 0


def test_transaction_status_timeout_leaves_row_unverified(db, monkeypatch):
    """A timeout means Safaricom gave up waiting on the query, not that the
    money is not real. The row stays Unverified rather than the timeout
    deciding an outcome on its own."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="TIMEOUT001", amount="150", shortcode=config.shortcode)
    _fake_status_ack(monkeypatch, conversation_id="AG-TIMEOUT")
    txn = handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    resolved = handle_transaction_status_timeout(
        db, _status_timeout(conversation_id="AG-TIMEOUT"),
    )

    assert resolved is not None
    assert resolved.id == txn.id
    db.refresh(txn)
    assert txn.status == "Unverified"
    assert txn.verified_at is None
    assert db.query(Payment).count() == 0


def test_transaction_status_result_with_no_invoice_match_is_unmatched(db, monkeypatch):
    """A corroborated receipt that matches no invoice by any basis is
    recorded Unmatched, on the record, but nothing is posted against any
    invoice."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(
        receipt="NOMATCH001", amount="750", shortcode=config.shortcode,
        bill_ref="not-a-reference", msisdn="254700000000",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-NOMATCH")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    resolved = handle_transaction_status_result(
        db, _status_result(
            conversation_id="AG-NOMATCH", result_code=0, amount="750", receipt="NOMATCH001",
        ),
    )

    assert resolved.status == "Unmatched"
    assert resolved.match_basis == "unmatched"
    assert resolved.verified_at is not None
    assert resolved.invoice_id is None
    assert db.query(Payment).count() == 0


def test_transaction_status_result_settles_using_the_other_amount_and_receipt_spelling(db, monkeypatch):
    """Safaricom's key names for the amount and the receipt are not settled
    between documentation sources (Amount vs TransactionAmount, ReceiptNo vs
    TransactionReceipt). This test deliberately builds the OTHER spelling
    from every other test in this file, so the suite as a whole does not
    assume either one is correct."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("650.00"))
    payload = _c2b_confirmation(
        receipt="ALTSPELL001", amount="650", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-ALTSPELL")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-ALTSPELL", result_code=0,
        amount="650", amount_key="Amount",
        receipt="ALTSPELL001", receipt_key="ReceiptNo",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Success"
    assert db.query(Payment).count() == 1


def test_transaction_status_result_missing_amount_is_a_diagnostic_quarantine_not_kes_none(db, monkeypatch):
    """When NEITHER amount spelling is present, the quarantine reason must
    name the keys that actually arrived rather than claim Safaricom reported
    "KES None", which would misrepresent a missing field as a wrong value
    Safaricom never sent."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="NOAMOUNT001", amount="400", shortcode=config.shortcode)
    _fake_status_ack(monkeypatch, conversation_id="AG-NOAMOUNT")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-NOAMOUNT", result_code=0,
        receipt="NOAMOUNT001",  # receipt present, amount deliberately absent
        extra_params=[{"Key": "SomeOtherKey", "Value": "whatever"}],
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert "KES None" not in resolved.result_desc
    assert "SomeOtherKey" in resolved.result_desc
    assert db.query(Payment).count() == 0


def test_transaction_status_result_receipt_mismatch_quarantines(db, monkeypatch):
    """conversation_id carries no unique constraint. If a result's own
    reported receipt does not match the receipt THIS row recorded, settling
    anyway would risk applying Safaricom's answer to the wrong row's
    patient. Cross-checked and refused here rather than trusted."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("900.00"))
    payload = _c2b_confirmation(
        receipt="REALRECEIPT001", amount="900", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-RECEIPTMISMATCH")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-RECEIPTMISMATCH", result_code=0,
        amount="900", receipt="SOMEOTHERRECEIPT999",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert db.query(Payment).count() == 0
    db.refresh(invoice)
    assert invoice.status == "Pending"


def test_transaction_status_result_not_completed_quarantines_not_settles(db, monkeypatch):
    """ResultCode 0 only means the QUERY succeeded, not that the payment
    itself did. A receipt Safaricom knows about but marks Reversed (or
    Failed) must never settle just because the query worked."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("1200.00"))
    payload = _c2b_confirmation(
        receipt="REVERSED001", amount="1200", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-REVERSED")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-REVERSED", result_code=0,
        amount="1200", receipt="REVERSED001", transaction_status="Reversed",
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert "Reversed" in resolved.result_desc
    assert db.query(Payment).count() == 0
    db.refresh(invoice)
    assert invoice.amount_paid == 0
    assert invoice.status == "Pending"


def test_transaction_status_result_settles_using_the_alternate_status_spelling(db, monkeypatch):
    """No source contradicts "TransactionStatus" the way sources contradict
    Amount/Receipt, so this is a consistency measure rather than a known
    defect, applied for the same reason: a bare "Status" is tolerated as a
    plausible alternate spelling."""
    config = _make_config_with_initiator(db, shortcode="174379")
    invoice = make_invoice(db, total_amount=Decimal("333.00"))
    payload = _c2b_confirmation(
        receipt="ALTSTATUS001", amount="333", shortcode=config.shortcode,
        bill_ref=f"INV-{invoice.invoice_id}",
    )
    _fake_status_ack(monkeypatch, conversation_id="AG-ALTSTATUS")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-ALTSTATUS", result_code=0,
        amount="333", receipt="ALTSTATUS001",
        transaction_status=None,  # do not write "TransactionStatus" at all
        extra_params=[{"Key": "Status", "Value": "Completed"}],
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Success"
    assert db.query(Payment).count() == 1


def test_transaction_status_result_missing_status_is_a_diagnostic_quarantine_not_a_false_reversed(db, monkeypatch):
    """A missing TransactionStatus key and a genuinely-not-Completed
    transaction are different facts. Treating an ABSENT status field the
    same as a present-but-not-Completed one would produce the identical
    quarantine message for both, misdiagnosing the first real sandbox
    delivery that happens to omit the field under a name this code does
    not check."""
    config = _make_config_with_initiator(db, shortcode="174379")
    payload = _c2b_confirmation(receipt="NOSTATUS001", amount="222", shortcode=config.shortcode)
    _fake_status_ack(monkeypatch, conversation_id="AG-NOSTATUS")
    handle_confirmation(db, payload, callback_tenant="mayoclinic_db")

    result_payload = _status_result(
        conversation_id="AG-NOSTATUS", result_code=0,
        amount="222", receipt="NOSTATUS001",
        transaction_status=None,  # neither TransactionStatus nor Status present
    )
    resolved = handle_transaction_status_result(db, result_payload)

    assert resolved.status == "Quarantined"
    assert "not Completed" not in resolved.result_desc
    assert "status" in resolved.result_desc.lower()
    assert "keys present" in resolved.result_desc
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


def test_c2b_matching_by_bill_ref_never_matches_a_cancelled_invoice(db):
    """Cancelled means voided with the ledger posting reversed in this
    codebase. A patient typing an old or voided invoice number at the till
    must not have real money posted against it: settle_invoice_match would
    then mark a voided invoice Paid again, resurrecting it. The bill-ref
    matcher must apply the same outstanding-status filter its two sibling
    matchers (OPD number, phone) already use."""
    cancelled_invoice = make_invoice(db, total_amount=Decimal("400.00"))
    cancelled_invoice.status = "Cancelled"
    db.commit()

    invoice, basis = match_c2b_invoice(
        db, bill_ref_number=f"INV-{cancelled_invoice.invoice_id}", msisdn="254700000099",
    )

    assert invoice is None
    assert basis == "unmatched"


# ─── Validation ─────────────────────────────────────────────────────────────


def test_handle_validation_accepts_a_known_active_till(db):
    config = make_mpesa_config(db, shortcode="174379")
    payload = {"BusinessShortCode": config.shortcode, "TransAmount": "100"}

    assert handle_validation(db, payload) is True


def test_handle_validation_accepts_an_unknown_shortcode(db):
    """Safaricom only ever calls the URL we ourselves registered for a
    specific till. An unknown or inactive shortcode reaching validation
    means OUR configuration drifted, not that the payment is illegitimate:
    declining here would cost a real patient their payment for a problem
    that is entirely ours, and confirmation plus Transaction Status is
    already the gate that stops unverified money from posting."""
    make_mpesa_config(db, shortcode="174379")
    payload = {"BusinessShortCode": "999999", "TransAmount": "100"}

    assert handle_validation(db, payload) is True


def test_handle_validation_accepts_when_the_config_lookup_fails(db, monkeypatch):
    """No route exists yet to decide what an exception here should become,
    so a database error must accept rather than leave that decision
    undefined."""
    make_mpesa_config(db, shortcode="174379")

    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(db, "query", _boom)
    payload = {"BusinessShortCode": "174379", "TransAmount": "100"}

    assert handle_validation(db, payload) is True


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
    # No initiator credentials were set on config_a: registration succeeds
    # (Safaricom's registerurl call neither needs nor checks them), but
    # verification_ready must say plainly that this till can never verify
    # a payment yet, rather than the response implying setup is complete.
    assert result["results"][0]["verification_ready"] is False
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


def test_register_c2b_urls_reports_verification_ready_when_initiator_credentials_set(db, monkeypatch):
    _fake_oauth(monkeypatch)
    monkeypatch.setattr(
        "app.services.daraja.client.requests.post",
        lambda url, **kw: FakeResponse(200, {"ResponseDescription": "success"}),
    )

    config = _make_config_with_initiator(db, shortcode="300003")

    result = register_c2b_urls(db, callback_tenant="mayoclinic_db")

    assert result["results"][0]["registered"] is True
    assert result["results"][0]["verification_ready"] is True
    assert config.initiator_name and config.initiator_password_encrypted


def test_c2b_readiness_flags_a_registered_till_with_no_initiator_credentials(db):
    """The exact blocker the coupling fix exists to surface: an active till
    with C2B registered that LOOKS complete but can never verify a payment.
    A health panel reads this to catch it before a hospital discovers it
    only after taking real, unverifiable money."""
    config = make_mpesa_config(db, shortcode="400004")
    config.c2b_urls_registered_at = datetime.now(timezone.utc)
    db.commit()

    readiness = c2b_readiness(db)

    row = next(r for r in readiness if r["shortcode"] == "400004")
    assert row["c2b_urls_registered_at"] is not None
    assert row["verification_ready"] is False


def test_c2b_readiness_is_a_pure_read_and_never_calls_daraja(db, monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("c2b_readiness must never call Safaricom")

    monkeypatch.setattr("app.services.daraja.client.requests.post", _fail_if_called)
    monkeypatch.setattr("app.services.daraja.client.requests.get", _fail_if_called)

    _make_config_with_initiator(db, shortcode="500005")

    readiness = c2b_readiness(db)

    row = next(r for r in readiness if r["shortcode"] == "500005")
    assert row["verification_ready"] is True
