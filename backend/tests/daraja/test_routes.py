"""Route-level tests for Task 9: the six Daraja callback routes and the
authenticated STK-push / admin surface in app/routes/mpesa_payment.py and
app/routes/mpesa_admin.py.

Every callback test monkeypatches resolve_tenant_by_hint as imported into
the route module (app.routes.mpesa_payment), never the underlying
app.core.daraja_callback module: the route holds its own name binding, and
patching the origin module would silently do nothing.
"""
from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core.daraja_callback import ACK_C2B_DECLINE, ACK_OK, TenantLookupUnavailable
from app.core.dependencies import RequirePermission, get_current_user
from app.main import app
from app.utils.encryption import encrypt_data
from app.models.mpesa import MpesaRefund, MpesaTransaction
from tests.daraja.conftest import make_invoice, make_mpesa_config, make_pending_transaction

# The six token-addressed callback paths Task 9 wires, matching
# app/main.py's _CSRF_EXEMPT_PATHS exactly.
CALLBACK_PATH_TEMPLATES = [
    "/api/payments/mpesa/stk/callback/{hint}/{token}",
    "/api/payments/mpesa/c2b/validation/{hint}/{token}",
    "/api/payments/mpesa/c2b/confirmation/{hint}/{token}",
    "/api/payments/mpesa/status/result/{hint}/{token}",
    "/api/payments/mpesa/status/timeout/{hint}/{token}",
    "/api/payments/mpesa/platform/stk/callback/{hint}/{token}",
]

# Same six, minus C2B validation: that one route diverges from the
# 503-on-TenantLookupUnavailable rule on purpose (I1, never-decline wins
# there; see test_c2b_validation_accepts_when_tenant_lookup_is_unavailable
# below), so it is tested separately rather than in this parametrized set.
CALLBACK_PATH_TEMPLATES_EXCEPT_C2B_VALIDATION = [
    t for t in CALLBACK_PATH_TEMPLATES if "/c2b/validation/" not in t
]


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


class _FakeTenantSession:
    """Stands in for a real tenant Session where a callback test wants
    resolution to succeed but never touches the database: cheaper than a
    real tenant engine and irrelevant to what these tests assert."""

    def close(self):
        pass


@pytest.fixture()
def _unauthenticated_client() -> Iterator[TestClient]:
    """No dependency overrides at all: these callbacks are public and
    token-authenticated, not session-authenticated, and CSRF-exempt by path
    (see app/main.py's _CSRF_EXEMPT_PATHS)."""
    yield TestClient(app)


# ─── Ordering invariant outcomes, all six callbacks ─────────────────────────


@pytest.mark.parametrize("template", CALLBACK_PATH_TEMPLATES)
def test_callback_acks_200_on_an_evaluated_non_match(template, monkeypatch, _unauthenticated_client):
    """A tenant_hint/token pair that resolves to nothing (wrong, forged, or
    simply unrecognised) is a payload we DID evaluate and reject: Safaricom
    must not retry it, so the response is 200 with the accepting body, never
    a decline-shaped one."""
    monkeypatch.setattr("app.routes.mpesa_payment.resolve_tenant_by_hint", lambda hint, token: None)
    path = template.format(hint="does-not-exist", token="bad-token")
    resp = _unauthenticated_client.post(path, json={"anything": "here"})
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_OK)


@pytest.mark.parametrize("template", CALLBACK_PATH_TEMPLATES_EXCEPT_C2B_VALIDATION)
def test_callback_returns_503_when_tenant_lookup_is_unavailable(template, monkeypatch, _unauthenticated_client):
    """A lookup we could NOT perform (a master- or tenant-DB failure) must
    never be acknowledged the same way as one we evaluated: Safaricom has to
    retry, so this is the one case that is not a 200. C2B validation is the
    one exception (I1) and is tested separately below."""
    def _boom(hint, token):
        raise TenantLookupUnavailable("simulated master-DB outage")

    monkeypatch.setattr("app.routes.mpesa_payment.resolve_tenant_by_hint", _boom)
    path = template.format(hint="whoever", token="whatever")
    resp = _unauthenticated_client.post(path, json={"anything": "here"})
    assert resp.status_code == 503


@pytest.mark.parametrize("template", CALLBACK_PATH_TEMPLATES)
def test_callback_acks_200_on_unparseable_json(template, monkeypatch, _unauthenticated_client):
    """A body that isn't even valid JSON is acknowledged, not processed:
    there is nothing evaluable to reject, and nothing retryable to gain by
    a non-200 either."""
    monkeypatch.setattr(
        "app.routes.mpesa_payment.resolve_tenant_by_hint", lambda hint, token: "mayoclinic_db",
    )
    monkeypatch.setattr(
        "app.routes.mpesa_payment._tenant_session", lambda name: _FakeTenantSession(),
    )
    path = template.format(hint="mayoclinic_db", token="tok")
    resp = _unauthenticated_client.post(path, content=b"not-json-at-all")
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_OK)


# ─── C2B validation: the one path that must never turn an error into a decline ─


def test_c2b_validation_accepts_when_tenant_lookup_is_unavailable(monkeypatch, _unauthenticated_client):
    """I1. Every other callback 503s on TenantLookupUnavailable so Safaricom
    retries. C2B validation is the one route where that would cost a real
    patient their payment for no gain: validation is synchronous and
    one-shot, so there is nothing to retry into, and the confirmation that
    follows carries the same hint/token and IS retried if it 503s."""
    def _boom(hint, token):
        raise TenantLookupUnavailable("simulated master-DB outage")

    monkeypatch.setattr("app.routes.mpesa_payment.resolve_tenant_by_hint", _boom)
    resp = _unauthenticated_client.post(
        "/api/payments/mpesa/c2b/validation/mayoclinic_db/tok",
        json={"TransAmount": "100"},
    )
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_OK)


def test_c2b_validation_accepts_when_the_handler_raises(monkeypatch, _unauthenticated_client):
    monkeypatch.setattr(
        "app.routes.mpesa_payment.resolve_tenant_by_hint", lambda hint, token: "mayoclinic_db",
    )
    monkeypatch.setattr(
        "app.routes.mpesa_payment._tenant_session", lambda name: _FakeTenantSession(),
    )

    def _boom(db, payload):
        raise RuntimeError("simulated handler bug")

    monkeypatch.setattr("app.routes.mpesa_payment.handle_validation", _boom)

    resp = _unauthenticated_client.post(
        "/api/payments/mpesa/c2b/validation/mayoclinic_db/tok",
        json={"TransAmount": "100", "BusinessShortCode": "174379"},
    )
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_OK), "an internal error must accept, never decline a real payment"


def test_c2b_validation_declines_only_on_a_genuine_evaluated_rejection(monkeypatch, _unauthenticated_client):
    monkeypatch.setattr(
        "app.routes.mpesa_payment.resolve_tenant_by_hint", lambda hint, token: "mayoclinic_db",
    )
    monkeypatch.setattr(
        "app.routes.mpesa_payment._tenant_session", lambda name: _FakeTenantSession(),
    )
    monkeypatch.setattr("app.routes.mpesa_payment.handle_validation", lambda db, payload: False)

    resp = _unauthenticated_client.post(
        "/api/payments/mpesa/c2b/validation/mayoclinic_db/tok",
        json={"TransAmount": "-1"},
    )
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_C2B_DECLINE)


# ─── Platform callback: only the reserved platform hint may settle there ────


def test_platform_callback_rejects_a_real_tenant_db_name_resolution(monkeypatch, _unauthenticated_client):
    """resolve_tenant_by_hint could in principle resolve a token against a
    real tenant's own MpesaConfig (a wrong token/route pairing); the
    platform route must refuse to treat that as a platform settlement even
    though resolution technically "succeeded"."""
    monkeypatch.setattr(
        "app.routes.mpesa_payment.resolve_tenant_by_hint", lambda hint, token: "mayoclinic_db",
    )
    resp = _unauthenticated_client.post(
        "/api/payments/mpesa/platform/stk/callback/mayoclinic_db/tok", json={},
    )
    assert resp.status_code == 200
    assert resp.json() == dict(ACK_OK)


# ─── Authenticated surface: STK push idempotency ────────────────────────────


@pytest.fixture()
def _authenticated_client(db) -> Iterator[TestClient]:
    def _get_db():
        yield db

    def _fake_user():
        return {
            "user_id": 1,
            "email": "route.test@hms.local",
            "role": "Admin",
            "full_name": "Route Test User",
            "permissions": ["billing:manage", "billing:read", "payhero:manage"],
        }

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        client = TestClient(app)
        client.cookies.set("csrf_token", "test-csrf-token")
        client.headers.update({
            "x-csrf-token": "test-csrf-token",
            # The STK push route forwards this as the callback's tenant
            # routing hint (app/services/daraja/stk.py's _callback_url);
            # without it, initiate_stk_push cannot build a CallBackURL at
            # all. Module gating never triggers off this header in tests:
            # ModuleGateMiddleware looks up the tenant's feature_flags from
            # the MASTER database keyed by this exact value, and no such
            # tenant row exists here, so get_tenant_flags_cached simply
            # returns "" and resolve_enabled_modules falls back to
            # DEFAULT_ENABLED, which already includes "mpesa".
            "X-Tenant-ID": "mayoclinic_db",
        })
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _clear_daraja_token_cache():
    from app.services.daraja.client import _TOKEN_CACHE

    _TOKEN_CACHE.clear()
    yield
    _TOKEN_CACHE.clear()


def test_stk_push_route_is_idempotent_under_a_repeated_key(db, monkeypatch, _authenticated_client):
    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()

    call_count = {"n": 0}

    def fake_oauth(url, **kw):
        return _FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        call_count["n"] += 1
        return _FakeResponse(200, {
            "MerchantRequestID": "mr-route-1",
            "CheckoutRequestID": "ws_CO_route_1",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    body = {
        "phone_number": "254712345678",
        "invoice_id": invoice.invoice_id,
        "amount": "500.00",
        "idempotency_key": f"route-test-{secrets.token_hex(6)}",
    }

    first = _authenticated_client.post("/api/payments/mpesa/stk-push", json=body)
    assert first.status_code == 200, first.text

    second = _authenticated_client.post("/api/payments/mpesa/stk-push", json=body)
    assert second.status_code == 200, second.text

    first_body, second_body = first.json(), second.json()
    # The replayed response round-trips through the idempotency cache's own
    # JSON encoding (app/core/idempotency.py serialises with
    # `default=str`), so a Decimal field comes back as a string on the
    # cache hit even though the first, non-cached response serialised it as
    # a number; that is an existing property of the shared cache, not
    # something this route controls. Compare the identifying fields
    # directly and the money field as a string on both sides.
    assert first_body["checkout_request_id"] == second_body["checkout_request_id"]
    assert first_body["transaction_id"] == second_body["transaction_id"]
    assert str(first_body["amount_charged"]) == str(second_body["amount_charged"])
    assert call_count["n"] == 1, "a repeated key must not push a second STK prompt"


def test_stk_push_route_rejects_a_reused_key_with_a_different_body(db, monkeypatch, _authenticated_client):
    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    make_mpesa_config(db)
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()

    def fake_oauth(url, **kw):
        return _FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        return _FakeResponse(200, {
            "MerchantRequestID": "mr-route-2",
            "CheckoutRequestID": "ws_CO_route_2",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    key = f"route-test-{secrets.token_hex(6)}"
    first = _authenticated_client.post(
        "/api/payments/mpesa/stk-push",
        json={
            "phone_number": "254712345678", "invoice_id": invoice.invoice_id,
            "amount": "500.00", "idempotency_key": key,
        },
    )
    assert first.status_code == 200, first.text

    second = _authenticated_client.post(
        "/api/payments/mpesa/stk-push",
        json={
            "phone_number": "254799999999", "invoice_id": invoice.invoice_id,
            "amount": "100.00", "idempotency_key": key,
        },
    )
    assert second.status_code == 409


def test_stk_push_route_forwards_department_id_to_the_configured_till(db, monkeypatch, _authenticated_client):
    """I4. Without department_id reaching config_for, every push resolves
    to the hospital default no matter which till the request named, and
    Task 14's per-department tills are unreachable from any route. Proves
    the department's OWN shortcode is what actually gets pushed to
    Daraja, not the hospital default's."""
    import secrets as _secrets

    from app.models.messaging import Department

    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    dept = Department(name=f"route-dept-{_secrets.token_hex(4)}", is_active=True)
    db.add(dept)
    db.flush()

    make_mpesa_config(db, shortcode="100001", initiator_name="default-api")
    make_mpesa_config(
        db, shortcode="200002", initiator_name="dept-api", department_id=dept.department_id,
    )
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    db.commit()

    captured = {}

    def fake_oauth(url, **kw):
        return _FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        captured["payload"] = kw.get("json")
        return _FakeResponse(200, {
            "MerchantRequestID": "mr-dept-route",
            "CheckoutRequestID": "ws_CO_dept_route",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    resp = _authenticated_client.post(
        "/api/payments/mpesa/stk-push",
        json={
            "phone_number": "254712345678",
            "invoice_id": invoice.invoice_id,
            "amount": "500.00",
            "department_id": dept.department_id,
            "idempotency_key": f"route-test-{secrets.token_hex(6)}",
        },
    )
    assert resp.status_code == 200, resp.text
    assert captured["payload"]["BusinessShortCode"] == "200002"


# ─── I2: C2B registration, readiness, callback URLs, token rotation ────────


def test_register_c2b_and_readiness_and_callback_urls_routes(db, monkeypatch, _authenticated_client):
    """I2. register_c2b_urls and c2b_readiness had no route anywhere: an
    HTTP request could reach neither, so Safaricom would never be told
    where to send C2B traffic and walk-in payments would go unrecorded
    with no error anywhere. Exercises all three new read/action routes
    together against one real, active till."""
    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    config = make_mpesa_config(db, initiator_name="testapi")
    config.initiator_password_encrypted = encrypt_data("initiator-pass")
    db.commit()

    def fake_oauth(url, **kw):
        return _FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        return _FakeResponse(200, {"ResponseDescription": "success"})

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    register_resp = _authenticated_client.post("/api/admin/mpesa/register-c2b")
    assert register_resp.status_code == 200, register_resp.text
    assert register_resp.json()["results"][0]["registered"] is True

    readiness_resp = _authenticated_client.get("/api/admin/mpesa/c2b-readiness")
    assert readiness_resp.status_code == 200
    assert readiness_resp.json()[0]["verification_ready"] is True

    urls_resp = _authenticated_client.get("/api/admin/mpesa/callback-urls")
    assert urls_resp.status_code == 200
    till = urls_resp.json()["tills"][0]
    assert till["stk_callback_url"].startswith("https://mayoclinic.medifleet.app/api/payments/mpesa/stk/callback/")
    assert "/c2b/confirmation/" in till["c2b_confirmation_url"]
    assert "/c2b/validation/" in till["c2b_validation_url"]
    assert "/status/result/" in till["status_result_url"]
    assert "/status/timeout/" in till["status_timeout_url"]
    # Round 2 fix: the standing GET never shows the real token, only a
    # masked placeholder, the same word app/utils/log_redact.py uses.
    for url in (
        till["stk_callback_url"], till["c2b_confirmation_url"], till["c2b_validation_url"],
        till["status_result_url"], till["status_timeout_url"],
    ):
        assert url.endswith("/<redacted>"), f"callback-urls leaked a real token in {url!r}"


def test_rotate_token_invalidates_the_old_lookup_hash(db, _authenticated_client):
    """I2. Without a rotate route, a leaked callback token (one of only two
    authentication layers for an unsigned protocol) had no remediation
    short of a manual database UPDATE."""
    config = make_mpesa_config(db)
    db.commit()
    old_lookup = config.callback_token_lookup
    assert old_lookup is not None

    resp = _authenticated_client.post("/api/admin/mpesa/rotate-token")
    assert resp.status_code == 200, resp.text
    assert "register-c2b" in resp.json()["message"]

    db.refresh(config)
    assert config.callback_token_lookup is not None
    assert config.callback_token_lookup != old_lookup


def test_rotate_token_reveals_the_real_token_once_then_callback_urls_masks_it(
    db, monkeypatch, _authenticated_client,
):
    """Round 2 fix: the credential-exposure decision. rotate-token is the
    ONE place the plaintext token is ever shown, embedded in the real
    callback URLs, because that is the moment an operator actually needs
    it (Safaricom portal-side registration). The standing callback-urls
    GET must never show it, before or after a rotation: a role holding
    payhero:manage (e.g. Accountant, documented read-only for M-Pesa) must
    not be able to pull the live credential just by polling that route."""
    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    make_mpesa_config(db)
    db.commit()

    rotate_resp = _authenticated_client.post("/api/admin/mpesa/rotate-token")
    assert rotate_resp.status_code == 200, rotate_resp.text
    rotate_body = rotate_resp.json()
    # _public_view's own field, spread at the top level of this response.
    assert rotate_body["callback_token_rotated_at"] is not None
    revealed = rotate_body["urls"]
    assert revealed is not None
    assert not revealed["stk_callback_url"].endswith("/<redacted>")
    real_token = revealed["stk_callback_url"].rsplit("/", 1)[-1]
    assert len(real_token) > 8, "rotate-token must reveal the real, full-length token"
    # concern 3's fix: no part of the token is exposed, but WHICH token is
    # live is still answerable from a timestamp alone.
    assert revealed["callback_token_rotated_at"] is not None

    masked_resp = _authenticated_client.get("/api/admin/mpesa/callback-urls")
    assert masked_resp.status_code == 200
    masked_till = masked_resp.json()["tills"][0]
    assert masked_till["stk_callback_url"].endswith("/<redacted>")
    assert real_token not in masked_till["stk_callback_url"]
    assert masked_till["callback_token_rotated_at"] == revealed["callback_token_rotated_at"]


# ─── Route-inventory permission regression net ──────────────────────────────


def test_every_mutating_mpesa_route_requires_its_exact_write_permission():
    """A one-time reading that the right permission gates these routes is
    not a net: a future edit that drops the dependency, or widens it to an
    any-of with a read permission, would silently hand every holder of that
    other permission a write it should not have. Mirrors
    tests/daraja/test_refunds.py's equivalent for the B2C refund routes."""
    expectations = {
        "/api/payments/mpesa/stk-push": ("billing:manage",),
        "/api/admin/mpesa/config": ("payhero:manage",),
        "/api/admin/mpesa/unmatched/{txn_id}/assign": ("payhero:manage",),
        "/api/admin/mpesa/register-c2b": ("payhero:manage",),
        "/api/admin/mpesa/rotate-token": ("payhero:manage",),
    }

    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if path not in expectations:
            continue
        methods = getattr(route, "methods", None) or set()
        if "GET" in methods:
            continue
        checked += 1
        required = [
            dep.call.required_permissions
            for dep in route.dependant.dependencies
            if isinstance(dep.call, RequirePermission)
        ]
        assert required, f"{methods} {path} carries no RequirePermission dependency at all"
        assert required == [expectations[path]], (
            f"{methods} {path} must require exactly {expectations[path]}, found {required}"
        )
    assert checked == len(expectations), (
        f"expected to check {len(expectations)} mutating routes, checked {checked}"
    )


def test_callback_urls_get_requires_exactly_the_write_permission_not_any_of():
    """GET /callback-urls is the one read-shaped route in this module
    deliberately NOT on the any-of read set (payhero:manage OR mpesa:read):
    round 1 gated it that way because it returned the plaintext token,
    round 2 masks that token but keeps the tighter gate on purpose (see
    the route's own docstring). The general route-inventory test above
    skips every GET, reasoning that a read endpoint may reasonably accept
    an any-of; this route is the one exception, so it gets its own pinned
    assertion rather than being silently exempted along with every other
    GET. A future "simplify GETs to the read set" pass must not widen this
    one without a deliberate decision to do so.
    """
    route = next(
        r for r in app.routes if getattr(r, "path", "") == "/api/admin/mpesa/callback-urls"
    )
    required = [
        dep.call.required_permissions
        for dep in route.dependant.dependencies
        if isinstance(dep.call, RequirePermission)
    ]
    assert required == [("payhero:manage",)], (
        f"GET /callback-urls must require exactly ('payhero:manage',), found {required}"
    )


# ─── Refund register: list ──────────────────────────────────────────────────


def test_list_refunds_route_returns_newest_first_and_respects_status_filter(
    db, _authenticated_client,
):
    """GET /api/payments/mpesa/refunds is the Refunds screen's list source
    (Task 11): it did not exist before this route, leaving the refund
    register visible only one row at a time via GET /refunds/{id}."""
    invoice = make_invoice(db, total_amount=Decimal("1000"))
    txn = make_pending_transaction(db, amount=Decimal("500"), invoice_id=invoice.invoice_id)
    txn.status = "Success"
    txn.receipt_number = "QRC0001"
    db.flush()

    older = MpesaRefund(
        source_transaction_id=txn.id, invoice_id=invoice.invoice_id,
        phone_number="254712345678", amount=Decimal("100"), reason="Duplicate charge",
        status="Requested", requested_by=1,
        originator_conversation_id="OCID-OLDER",
    )
    newer = MpesaRefund(
        source_transaction_id=txn.id, invoice_id=invoice.invoice_id,
        phone_number="254712345678", amount=Decimal("50"), reason="Overcharge",
        status="Completed", requested_by=1,
        originator_conversation_id="OCID-NEWER",
    )
    db.add_all([older, newer])
    db.commit()
    # Force a deterministic ordering independent of same-instant server
    # defaults: requested_at is server_default=func.now().
    from datetime import timedelta
    newer.requested_at = older.requested_at + timedelta(seconds=1)
    db.commit()

    resp = _authenticated_client.get("/api/payments/mpesa/refunds")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [r["id"] for r in body]
    assert ids.index(newer.id) < ids.index(older.id)

    filtered = _authenticated_client.get("/api/payments/mpesa/refunds?status=Completed")
    assert filtered.status_code == 200, filtered.text
    assert [r["id"] for r in filtered.json()] == [newer.id]


# ─── Test STK push (admin surface) ──────────────────────────────────────────


def test_admin_test_stk_push_sends_kes_1_with_no_invoice_and_records_last_test(
    db, monkeypatch, _authenticated_client,
):
    """Task 11's settings page needs a real end-to-end test push. It must
    never touch a real invoice (TEST-{token} external_reference, no
    invoice_id/dispense_id) and must record last_test_at/status/message on
    the config so the settings page can show when it last ran."""
    monkeypatch.setattr("app.config.settings.settings.PUBLIC_BASE_URL", "https://mayoclinic.medifleet.app")
    config = make_mpesa_config(db)
    db.commit()

    def fake_oauth(url, **kw):
        return _FakeResponse(200, {"access_token": "tok", "expires_in": "3599"})

    def fake_post(url, **kw):
        return _FakeResponse(200, {
            "MerchantRequestID": "mr-test-1",
            "CheckoutRequestID": "ws_CO_test_1",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
        })

    monkeypatch.setattr("app.services.daraja.client.requests.get", fake_oauth)
    monkeypatch.setattr("app.services.daraja.client.requests.post", fake_post)

    resp = _authenticated_client.post(
        "/api/admin/mpesa/test-stk",
        json={"phone_number": "254712345678", "idempotency_key": f"test-{secrets.token_hex(6)}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkout_request_id"] == "ws_CO_test_1"
    assert body["external_reference"].startswith("TEST-")

    db.refresh(config)
    assert config.last_test_status == "STK Push Sent"
    assert config.last_test_at is not None

    txn = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == "ws_CO_test_1")
        .first()
    )
    assert txn is not None
    assert txn.invoice_id is None
    assert txn.dispense_id is None


def test_admin_test_stk_push_without_config_is_400(db, _authenticated_client):
    resp = _authenticated_client.post(
        "/api/admin/mpesa/test-stk",
        json={"phone_number": "254712345678", "idempotency_key": f"test-{secrets.token_hex(6)}"},
    )
    assert resp.status_code == 400, resp.text
    assert "not configured" in resp.text.lower()
