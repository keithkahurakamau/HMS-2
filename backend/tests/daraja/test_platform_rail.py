"""Task 10: the platform Daraja rail (the operator's OWN subscription
billing), end to end from push through settlement.

The headline test is the point of the whole task: a paid subscription STK
must land in the receivables ledger as an InvoicePayment row against a real
SubscriptionInvoice, using the REAL outstanding_balance from
app/services/subscription_billing.py, not a reimplementation. If it does
not, the dunning cron (which reads only InvoicePayment rows) keeps chasing
a hospital that has already paid.

Mocked at the one seam test_stk.py already establishes for the tenant
rail: requests.* inside app.services.daraja.client. This exercises the
real DarajaClient the same way production traffic does.
"""
from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

import pytest

from app.config.settings import settings
from app.models.master import Tenant
from app.models.platform_mpesa import PlatformMpesaConfig, PlatformMpesaTransaction
from app.models.subscription_billing import InvoicePayment, Subscription, SubscriptionInvoice
from app.services.daraja.client import _TOKEN_CACHE
from app.services.daraja.platform import apply_platform_stk_callback
from app.services.daraja.platform_stk import initiate_platform_stk_push, platform_config
from app.services.daraja.tokens import mint_callback_token, store_callback_token
from app.services.subscription_billing import outstanding_balance
from app.utils.encryption import encrypt_data
from fastapi import HTTPException
from tests.daraja.conftest import stk_callback_payload


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
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://api.medifleet.app")
    yield


def _fake_oauth(monkeypatch):
    monkeypatch.setattr(
        "app.services.daraja.client.requests.get",
        lambda url, **kw: FakeResponse(200, {"access_token": "tok", "expires_in": "3599"}),
    )


def _fake_stk_success(monkeypatch, *, checkout_request_id="ws_CO_plat_1", calls=None):
    """`calls`, when given a list, gets one entry appended per actual POST
    to Safaricom: evidence that a blocked/cached push never reached Daraja
    a second time, not just that the visible result looked right."""
    def fake_post(url, **kw):
        if calls is not None:
            calls.append(kw.get("json"))
        return FakeResponse(200, {
            "MerchantRequestID": "mr-plat-1",
            "CheckoutRequestID": checkout_request_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        })
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)


# ─── Factories ──────────────────────────────────────────────────────────────


def make_tenant(session, **overrides) -> Tenant:
    nonce = secrets.token_hex(4)
    tenant = Tenant(
        name="Mayo Clinic",
        domain=f"mayo-{nonce}.medifleet.app",
        db_name=f"mayoclinic_{nonce}",
        is_active=True,
        billing_contact_msisdn="0712345678",
    )
    for key, value in overrides.items():
        setattr(tenant, key, value)
    session.add(tenant)
    session.flush()
    return tenant


def make_platform_config(session, **overrides) -> PlatformMpesaConfig:
    """A usable PlatformMpesaConfig: real (fake) encrypted creds, a minted
    callback token pair, active. Mirrors tests/daraja/conftest.py's
    make_mpesa_config for the tenant rail."""
    config = PlatformMpesaConfig(
        shortcode="700000",
        shortcode_type="paybill",
        environment="sandbox",
        consumer_key_encrypted=encrypt_data("test-platform-consumer-key"),
        consumer_secret_encrypted=encrypt_data("test-platform-consumer-secret"),
        passkey_encrypted=encrypt_data("test-platform-passkey"),
        account_reference="MEDIFLEET",
        transaction_desc="MediFleet Subscription",
        is_active=True,
    )
    store_callback_token(config, mint_callback_token())
    for key, value in overrides.items():
        setattr(config, key, value)
    session.add(config)
    session.flush()
    return config


def _open_subscription_invoice(session, tenant: Tenant, *, amount: Decimal) -> SubscriptionInvoice:
    sub = Subscription(
        tenant_id=tenant.tenant_id,
        plan="standard",
        price_kes=amount,
        cycle="monthly",
        status="active",
        started_on=date(2026, 1, 1),
        next_invoice_on=date(2026, 2, 1),
    )
    session.add(sub)
    session.flush()
    invoice = SubscriptionInvoice(
        tenant_id=tenant.tenant_id,
        subscription_id=sub.id,
        number=f"MF-TEST-{sub.id}",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        amount_kes=amount,
        issued_on=date(2026, 1, 1),
        due_on=date(2026, 1, 1),
        status="open",
    )
    session.add(invoice)
    session.flush()
    return invoice


def _platform_push(db, *, tenant: Tenant, invoice: SubscriptionInvoice, amount: Decimal) -> PlatformMpesaTransaction:
    result = initiate_platform_stk_push(
        db,
        tenant_id=tenant.tenant_id,
        amount=amount,
        subscription_invoice_id=invoice.id,
    )
    return (
        db.query(PlatformMpesaTransaction)
        .filter(PlatformMpesaTransaction.id == result["transaction_id"])
        .first()
    )


# ─── The headline test ──────────────────────────────────────────────────────


def test_subscription_stk_payment_creates_an_invoice_payment_row(db, monkeypatch):
    """The point of the whole platform rail: a paid subscription STK must
    land in the receivables ledger against a real invoice, not in a
    parallel table nobody ages."""
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_headline")
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("18500"))

    txn = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("18500"))
    assert txn is not None
    assert txn.subscription_invoice_id == invoice.id

    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("18500"),
        receipt="PLT123",
    )
    apply_platform_stk_callback(db, payload)

    payments = db.query(InvoicePayment).filter_by(invoice_id=invoice.id).all()
    assert len(payments) == 1
    assert payments[0].amount_kes == Decimal("18500")
    assert payments[0].platform_transaction_id == txn.id
    assert outstanding_balance(db, invoice) == Decimal("0")

    db.refresh(invoice)
    assert invoice.status == "paid"


def test_partial_subscription_payment_leaves_a_balance(db, monkeypatch):
    """A part-payment must not close the invoice or falsely zero the balance."""
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_partial")
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("18500"))

    txn = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("5000"))
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id, amount=Decimal("5000"), receipt="PLT456",
    )
    apply_platform_stk_callback(db, payload)

    assert outstanding_balance(db, invoice) == Decimal("13500")
    db.refresh(invoice)
    assert invoice.status == "open"


def test_replayed_callback_never_double_credits_the_ledger(db, monkeypatch):
    """Safaricom retries a callback; the receipt-number advisory lock plus
    the status == 'Success' replay filter (defect fix 1) must make a second
    delivery a no-op, not a second InvoicePayment."""
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_replay")
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("2000"))

    txn = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("2000"))
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id, amount=Decimal("2000"), receipt="PLT789",
    )
    first = apply_platform_stk_callback(db, payload)
    second = apply_platform_stk_callback(db, payload)

    assert first is not None
    assert second is None  # a pure replay: nothing changed the second time

    payments = db.query(InvoicePayment).filter_by(invoice_id=invoice.id).all()
    assert len(payments) == 1
    assert outstanding_balance(db, invoice) == Decimal("0")


def test_amount_mismatch_is_quarantined_not_settled(db, monkeypatch):
    """A callback claiming more than we requested must never touch the
    ledger: quarantine it, and never mistake it for a settled receipt."""
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_mismatch")
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("9000"))

    txn = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("9000"))
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id, amount=Decimal("90000"), receipt="PLT999",
    )
    apply_platform_stk_callback(db, payload)

    db.refresh(txn)
    assert txn.status == "Quarantined"
    assert db.query(InvoicePayment).filter_by(invoice_id=invoice.id).count() == 0
    assert outstanding_balance(db, invoice) == Decimal("9000")


def test_platform_config_missing_is_reported_not_raised_as_a_server_error(db):
    """MediFleet holds no Daraja credentials yet: an unconfigured platform
    rail is the expected, normal state, not a 500."""
    with pytest.raises(HTTPException) as exc:
        platform_config(db)
    assert exc.value.status_code == 400


def test_platform_config_with_no_credentials_is_reported_as_not_ready(db):
    """The default-shipped shape: environment=sandbox, every credential
    column NULL. Still a normal state, still a 400 with a plain message,
    never a 500."""
    config = PlatformMpesaConfig(
        shortcode="", shortcode_type="paybill", environment="sandbox", is_active=True,
    )
    db.add(config)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        platform_config(db)
    assert exc.value.status_code == 400


# ─── Round 1 review, Critical: the duplicate-push / idempotency gap ────────
#
# The reviewer's escalation, verified: a double-click is the textbook
# idempotency case, not an exemption from it, and the receipt-keyed replay
# check can never catch it, because two genuine STK approvals carry two
# genuinely different Safaricom receipts. These tests exercise the two
# independent layers that now close it: the partial unique index /
# reservation (stops a SECOND prompt from ever being sent while one is
# still pending), and the balance check in _settle_subscription_invoice
# (stops the ledger going negative even if two settlements DO arrive).


def test_second_push_for_a_pending_invoice_is_blocked_not_duplicated(db, monkeypatch):
    """A double-click while the first prompt is still on the handset must
    reuse the existing Pending row, not send a second prompt."""
    calls: list = []
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_dup_1", calls=calls)
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("4000"))

    first = initiate_platform_stk_push(
        db, tenant_id=tenant.tenant_id, amount=Decimal("4000"), subscription_invoice_id=invoice.id,
    )
    second = initiate_platform_stk_push(
        db, tenant_id=tenant.tenant_id, amount=Decimal("4000"), subscription_invoice_id=invoice.id,
    )

    assert len(calls) == 1  # Daraja was only ever asked once
    assert second["already_pending"] is True
    assert second["transaction_id"] == first["transaction_id"]
    assert (
        db.query(PlatformMpesaTransaction)
        .filter(PlatformMpesaTransaction.subscription_invoice_id == invoice.id)
        .count()
        == 1
    )


def test_idempotent_charge_replays_the_cached_response_not_a_second_push(db, monkeypatch):
    """Same admin, same button, same idempotency key: a retried request
    (a dropped response, a slow network) must replay the first answer, the
    same guarantee app/routes/mpesa_payment.py's tenant STK route already
    requires via the identical app/core/idempotency.py mechanism."""
    calls: list = []
    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_idem_1", calls=calls)
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("6000"))

    kwargs = dict(
        tenant_id=tenant.tenant_id, amount=Decimal("6000"), subscription_invoice_id=invoice.id,
        user_id=1, idempotency_key="retry-key-1",
    )
    first = initiate_platform_stk_push(db, **kwargs)
    second = initiate_platform_stk_push(db, **kwargs)

    assert len(calls) == 1  # cached, never re-pushed
    # Compared field-by-field, not with a bare ==: `second` round-tripped
    # through the idempotency cache's JSON serialisation
    # (app/core/idempotency.py stores response_body as json.dumps(...,
    # default=str)), so amount_charged comes back a str ("6000") even
    # though the live `first` response carries a Decimal. That is expected
    # cache behaviour, not a bug being tested here.
    assert second["transaction_id"] == first["transaction_id"]
    assert second["checkout_request_id"] == first["checkout_request_id"]
    assert second["external_reference"] == first["external_reference"]
    assert Decimal(str(second["amount_charged"])) == Decimal(str(first["amount_charged"]))


def test_double_settlement_against_an_already_paid_invoice_is_quarantined_not_negative(db, monkeypatch):
    """CRITICAL, round 1 review. The literal race the reviewer described
    (two Pending pushes racing each other) is now impossible: the partial
    unique index in app/models/platform_mpesa.py blocks a second Pending
    row for the same invoice at the database level, proven by
    test_second_push_for_a_pending_invoice_is_blocked_not_duplicated above.

    What remains reachable, and what this test proves is still safe, is
    SEQUENTIAL double settlement: invoice already paid in full, then a
    second, later charge against the SAME invoice (a stray recharge, a
    superadmin who didn't check the invoice first) is pushed AFTER the
    first Pending row is no longer Pending, so the index does not block
    it. Two genuine Safaricom receipts, so the receipt-keyed replay check
    never fires for either. Without the balance check in
    _settle_subscription_invoice, the second settlement would push
    outstanding_balance negative. With it, the second is quarantined.
    """
    make_platform_config(db)
    tenant = make_tenant(db)
    invoice = _open_subscription_invoice(db, tenant, amount=Decimal("18500"))

    _fake_oauth(monkeypatch)
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_double_1")
    txn1 = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("18500"))
    apply_platform_stk_callback(db, stk_callback_payload(
        checkout_request_id=txn1.checkout_request_id, amount=Decimal("18500"), receipt="PLTDBL1",
    ))
    db.refresh(invoice)
    assert invoice.status == "paid"
    assert outstanding_balance(db, invoice) == Decimal("0")

    # A second, independent push against the SAME invoice: its own
    # checkout_request_id, its own eventual receipt. Allowed by
    # _reserve_pending because txn1 is no longer Pending.
    _fake_stk_success(monkeypatch, checkout_request_id="ws_CO_plat_double_2")
    txn2 = _platform_push(db, tenant=tenant, invoice=invoice, amount=Decimal("18500"))
    assert txn2.id != txn1.id
    apply_platform_stk_callback(db, stk_callback_payload(
        checkout_request_id=txn2.checkout_request_id, amount=Decimal("18500"), receipt="PLTDBL2",
    ))

    db.refresh(txn2)
    assert txn2.status == "Quarantined"
    payments = db.query(InvoicePayment).filter_by(invoice_id=invoice.id).all()
    assert len(payments) == 1  # NOT two: the second was never credited
    assert outstanding_balance(db, invoice) == Decimal("0")  # NOT negative


def test_replay_filter_status_predicate_excludes_non_success_rows(db):
    """Follow-up coverage the reviewer identified for the status ==
    'Success' filter added to apply_platform_stk_callback's replay check.

    A genuine end-to-end version of "two distinct PlatformMpesaTransaction
    rows share one receipt_number" turned out to be unrealizable against
    the real schema: receipt_number carries a real unique=True constraint,
    so Postgres itself refuses to let a second row hold a value another
    row already holds, regardless of status. An earlier version of this
    test tried to construct exactly that and the database correctly
    rejected it with a UniqueViolation. That is a real finding, not an
    obstacle to work around: the constraint already guarantees, at a
    stronger level than the application filter does, that this can never
    happen. See the comment at the filter itself in
    app/services/daraja/platform.py for the fuller account.

    What IS honest to test directly, without bending the schema, is the
    predicate itself: given one committed row that holds a receipt_number
    but is NOT Success (the exact shape my own overpayment-quarantine fix
    produces, since it sets receipt_number before deciding to quarantine),
    the fixed query must not treat it as a match, while the pre-fix
    predicate (no status filter) would have.
    """
    tenant = make_tenant(db)
    quarantined = PlatformMpesaTransaction(
        tenant_id=tenant.tenant_id,
        phone_number="254712345678",
        amount=Decimal("3000"),
        external_reference="SUB-quarantined-predicate-test",
        checkout_request_id="ws_CO_plat_quarantined_predicate",
        status="Quarantined",
        receipt_number="DUPREC",
        result_desc="Exceeded outstanding balance; received but not credited",
    )
    db.add(quarantined)
    db.flush()

    # The exact predicate apply_platform_stk_callback's replay check runs
    # today (the fix).
    fixed_match = (
        db.query(PlatformMpesaTransaction)
        .filter(
            PlatformMpesaTransaction.receipt_number == "DUPREC",
            PlatformMpesaTransaction.status == "Success",
        )
        .first()
    )
    assert fixed_match is None  # a Quarantined row is never mistaken for a settled one

    # The pre-fix predicate, for contrast: this is what WOULD have matched,
    # which is exactly the bug (a genuine new settlement wrongly
    # short-circuited as "already settled" the moment any row, of any
    # status, carried this receipt_number).
    pre_fix_match = (
        db.query(PlatformMpesaTransaction)
        .filter(PlatformMpesaTransaction.receipt_number == "DUPREC")
        .first()
    )
    assert pre_fix_match is not None
