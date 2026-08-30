"""Daraja callback authentication.

Safaricom does not sign callbacks, so these tests exercise the things that
stand in for a signature: the unguessable per-tenant token plus its tenant
routing hint (never the tenant database name, and never checked in place of
the token), the Safaricom source-IP allow-list (including the
X-Forwarded-For handling ported from Pay Hero's audited, correct version,
and the production requirement that DARAJA_TRUSTED_PROXIES actually be set),
the TenantLookupUnavailable distinction between "rejected" and "could not be
evaluated", and the acknowledgement contract that always looks like
acceptance to Safaricom when, and only when, we evaluated a callback and
rejected it on our own side.
"""
from __future__ import annotations

import asyncio
import ipaddress
import types

import pytest
from fastapi import HTTPException

import app.core.daraja_callback as dc
from app.config.settings import settings
from app.models.mpesa import MpesaConfig
from app.services.daraja.tokens import mint_callback_token, store_callback_token


# --- helpers --------------------------------------------------------------

class _FakeRequest:
    """Stands in for fastapi.Request: an async body() plus client/headers."""

    def __init__(self, peer: str | None, xff: str | None = None, body: bytes = b"{}"):
        self.client = types.SimpleNamespace(host=peer) if peer else None
        self.headers: dict[str, str] = {}
        if xff is not None:
            self.headers["x-forwarded-for"] = xff
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _run(coro):
    return asyncio.run(coro)


class _FakeClock:
    """A monotonic clock the test controls, for deterministic TTL tests.

    Patched onto dc._monotonic (an indirection point the module exposes for
    exactly this purpose), never onto stdlib time.monotonic: patching the
    real stdlib function would also affect unrelated code sharing the
    process during the test, e.g. SQLAlchemy pool recycling.
    """

    def __init__(self, start: float = 0.0):
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.fixture(autouse=True)
def _isolated_negative_cache():
    """Every test starts with an empty negative-lookup cache."""
    dc.clear_negative_cache()
    yield
    dc.clear_negative_cache()


def _new_config(is_active: bool = True) -> MpesaConfig:
    config = MpesaConfig(shortcode="174379", shortcode_type="paybill")
    config.is_active = is_active
    return config


@pytest.fixture
def tenant_registry(monkeypatch):
    """A fake master registry + per-tenant MpesaConfig store, real instances.

    Backs resolve_tenant_by_token's two seams (_active_tenant_db_names and
    _lookup_token_in_tenant) with an in-memory dict of real MpesaConfig rows
    instead of real Postgres tenant databases, which the local dev
    environment has not yet had the Daraja migration applied to. The models
    themselves, and the hashing/storage helpers that write their token
    columns, are the real production code under test.
    """
    tenants: dict[str, MpesaConfig] = {}

    def _active_tenant_db_names():
        return list(tenants.keys())

    def _lookup_token_in_tenant(tenant_db: str, lookup_hash: str, *, raise_on_error: bool = False) -> bool:
        config = tenants.get(tenant_db)
        if config is None:
            return False
        return bool(config.is_active) and config.callback_token_lookup == lookup_hash

    monkeypatch.setattr(dc, "_active_tenant_db_names", _active_tenant_db_names)
    monkeypatch.setattr(dc, "_lookup_token_in_tenant", _lookup_token_in_tenant)
    return tenants


@pytest.fixture
def hint_registry(monkeypatch):
    """Backs resolve_tenant_by_hint's seams: _tenant_hint_is_active,
    _lookup_token_in_tenant (called there with raise_on_error=True), and
    _resolve_platform_token. Returns (tenants, platform): tenants is a
    tenant_hint -> MpesaConfig dict, platform is a one-key dict holding the
    platform's own config (or None) under "config".
    """
    tenants: dict[str, MpesaConfig] = {}
    platform: dict[str, MpesaConfig | None] = {"config": None}

    def _tenant_hint_is_active(tenant_hint: str) -> bool:
        return tenant_hint in tenants

    def _lookup_token_in_tenant(tenant_db: str, lookup_hash: str, *, raise_on_error: bool = False) -> bool:
        config = tenants.get(tenant_db)
        if config is None:
            return False
        return bool(config.is_active) and config.callback_token_lookup == lookup_hash

    def _resolve_platform_token(lookup_hash: str):
        config = platform["config"]
        if config is not None and bool(config.is_active) and config.callback_token_lookup == lookup_hash:
            return dc._PLATFORM_HINT
        return None

    monkeypatch.setattr(dc, "_tenant_hint_is_active", _tenant_hint_is_active)
    monkeypatch.setattr(dc, "_lookup_token_in_tenant", _lookup_token_in_tenant)
    monkeypatch.setattr(dc, "_resolve_platform_token", _resolve_platform_token)
    return tenants, platform


# --- token resolution: legacy scanning path -------------------------------

def test_unknown_callback_token_is_rejected(tenant_registry):
    """A forged callback with a guessed URL must not reach settlement."""
    config = _new_config()
    store_callback_token(config, mint_callback_token())
    tenant_registry["mayoclinic_db"] = config

    assert dc.resolve_tenant_by_token("a-token-nobody-ever-minted") is None


def test_tenant_database_name_is_not_accepted_as_a_token(tenant_registry):
    """The Pay Hero design keyed callbacks on the tenant db_name, which is
    guessable. Carrying that forward to an unsigned protocol would let anyone
    who guesses 'mayoclinic_db' mint payments. Explicitly assert it fails."""
    config = _new_config()
    store_callback_token(config, mint_callback_token())
    tenant_registry["mayoclinic_db"] = config

    # The database name itself, offered as if it were the callback token.
    assert dc.resolve_tenant_by_token("mayoclinic_db") is None


def test_a_real_minted_token_resolves_to_its_tenant(tenant_registry):
    """Sanity check: the positive path this whole module exists to gate."""
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenant_registry["mayoclinic_db"] = config

    assert dc.resolve_tenant_by_token(token) == "mayoclinic_db"


def test_empty_token_is_rejected_without_a_scan(tenant_registry, monkeypatch):
    scanned = []
    tenant_registry["mayoclinic_db"] = _new_config()
    original = dc._active_tenant_db_names
    monkeypatch.setattr(dc, "_active_tenant_db_names", lambda: (scanned.append(1) or original()))

    assert dc.resolve_tenant_by_token("") is None
    assert dc.resolve_tenant_by_token(None) is None
    assert scanned == []


def test_token_rotation_invalidates_the_old_token(tenant_registry):
    old_token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, old_token)
    tenant_registry["mayoclinic_db"] = config
    assert dc.resolve_tenant_by_token(old_token) == "mayoclinic_db"

    new_token = mint_callback_token()
    store_callback_token(config, new_token)  # rotation: overwrites both columns

    assert dc.resolve_tenant_by_token(old_token) is None
    assert dc.resolve_tenant_by_token(new_token) == "mayoclinic_db"


def test_negative_cache_does_not_hide_a_rotated_in_token_past_its_ttl(
    tenant_registry, monkeypatch
):
    """A token guessed before it is assigned to any tenant is cached as a
    miss. If that same value is later legitimately rotated in, the cache
    must not keep it invisible for longer than its short TTL."""
    clock = _FakeClock()
    monkeypatch.setattr(dc, "_monotonic", clock)
    monkeypatch.setattr(dc, "_NEGATIVE_CACHE_TTL_SECONDS", 5.0)

    guessed_token = mint_callback_token()
    assert dc.resolve_tenant_by_token(guessed_token) is None  # cached as a miss

    # The same value is now legitimately rotated in to a real tenant.
    config = _new_config()
    store_callback_token(config, guessed_token)
    tenant_registry["new_hospital_db"] = config

    # Still inside the TTL window: the stale negative entry still answers.
    clock.advance(1.0)
    assert dc.resolve_tenant_by_token(guessed_token) is None

    # Past the TTL: the entry has expired, so a live scan runs and finds it.
    clock.advance(10.0)
    assert dc.resolve_tenant_by_token(guessed_token) == "new_hospital_db"


def test_master_registry_failure_raises_lookup_unavailable_not_none(monkeypatch):
    """A master-DB blip must not look the same as 'no tenant matched':
    resolve_tenant_by_token must not swallow it into a None."""
    def _boom():
        raise dc.TenantLookupUnavailable("master db unreachable")

    monkeypatch.setattr(dc, "_active_tenant_db_names", _boom)

    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_token(mint_callback_token())


def test_master_registry_failure_does_not_poison_the_negative_cache(tenant_registry, monkeypatch):
    """A failed lookup for a VALID token must not get cached as a miss: that
    would keep rejecting it for the rest of the TTL even after the master DB
    has recovered."""
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenant_registry["mayoclinic_db"] = config

    real_scan = dc._active_tenant_db_names

    def _boom():
        raise dc.TenantLookupUnavailable("master db unreachable")

    monkeypatch.setattr(dc, "_active_tenant_db_names", _boom)
    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_token(token)

    monkeypatch.setattr(dc, "_active_tenant_db_names", real_scan)
    assert dc.resolve_tenant_by_token(token) == "mayoclinic_db"


# --- token resolution: hinted path (the structural change) ---------------

def test_hinted_resolution_finds_the_right_tenant(hint_registry):
    tenants, _platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenants["mayoclinic_db"] = config

    assert dc.resolve_tenant_by_hint("mayoclinic_db", token) == "mayoclinic_db"


def test_valid_token_under_the_wrong_tenant_hint_is_rejected(hint_registry):
    """The property that makes the routing hint safe to disclose: it is
    never checked in place of the token, only alongside it. A real token
    presented under a hint naming a DIFFERENT tenant must not resolve."""
    tenants, _platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenants["mayoclinic_db"] = config
    tenants["mpshah_db"] = _new_config()  # a second, unrelated real tenant

    assert dc.resolve_tenant_by_hint("mpshah_db", token) is None
    # The correct hint still resolves: the token itself was never touched.
    assert dc.resolve_tenant_by_hint("mayoclinic_db", token) == "mayoclinic_db"


def test_hint_naming_no_tenant_at_all_is_rejected(hint_registry):
    tenants, _platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenants["mayoclinic_db"] = config

    assert dc.resolve_tenant_by_hint("no_such_hospital_db", token) is None


def test_malformed_hint_is_rejected_without_touching_any_database(hint_registry, monkeypatch):
    tenants, _platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenants["mayoclinic_db"] = config

    touched = []
    monkeypatch.setattr(dc, "_tenant_hint_is_active", lambda h: (touched.append(h) or True))

    assert dc.resolve_tenant_by_hint("../etc/passwd", token) is None
    assert dc.resolve_tenant_by_hint("MAYOCLINIC_DB", token) is None  # wrong charset
    assert dc.resolve_tenant_by_hint("mayoclinic-db", token) is None  # hyphen not allowed
    assert touched == []


def test_platform_hint_resolves_against_the_platform_config(hint_registry):
    _tenants, platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    platform["config"] = config

    assert dc.resolve_tenant_by_hint(dc._PLATFORM_HINT, token) == dc._PLATFORM_HINT


def test_reserved_platform_hint_cannot_collide_with_a_tenant_db_name():
    """What makes the reserved hint safe: it contains a character (a hyphen)
    outside the charset every real tenant db_name is provisioned with, so no
    legitimately-provisioned tenant can ever be named the same thing."""
    assert dc._VALID_TENANT_DB_NAME.match(dc._PLATFORM_HINT) is None


def test_tenant_hint_registry_failure_raises_not_none(monkeypatch):
    def _boom(tenant_hint):
        raise dc.TenantLookupUnavailable("master db unreachable")

    monkeypatch.setattr(dc, "_tenant_hint_is_active", _boom)

    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_hint("mayoclinic_db", mint_callback_token())


def test_tenant_db_failure_for_hinted_path_raises_not_none(hint_registry, monkeypatch):
    """The tenant named by the hint exists, but its own database cannot be
    reached: this must surface, not silently resolve to None."""
    tenants, _platform = hint_registry
    tenants["mayoclinic_db"] = _new_config()

    def _boom(tenant_db, lookup_hash, *, raise_on_error=False):
        raise dc.TenantLookupUnavailable("tenant db unreachable")

    monkeypatch.setattr(dc, "_lookup_token_in_tenant", _boom)

    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_hint("mayoclinic_db", mint_callback_token())


def test_hinted_lookup_failure_does_not_poison_the_negative_cache(hint_registry, monkeypatch):
    tenants, _platform = hint_registry
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenants["mayoclinic_db"] = config

    real_lookup = dc._lookup_token_in_tenant

    def _boom(tenant_db, lookup_hash, *, raise_on_error=False):
        raise dc.TenantLookupUnavailable("tenant db unreachable")

    monkeypatch.setattr(dc, "_lookup_token_in_tenant", _boom)
    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_hint("mayoclinic_db", token)

    monkeypatch.setattr(dc, "_lookup_token_in_tenant", real_lookup)
    assert dc.resolve_tenant_by_hint("mayoclinic_db", token) == "mayoclinic_db"


# --- source IP allow-list -----------------------------------------------

def test_correct_token_from_disallowed_ip_is_rejected(tenant_registry, monkeypatch):
    """Even a callback carrying a real, resolvable token must not pass the
    source-IP gate: the token and the IP allow-list are independent layers."""
    token = mint_callback_token()
    config = _new_config()
    store_callback_token(config, token)
    tenant_registry["mayoclinic_db"] = config
    assert dc.resolve_tenant_by_token(token) == "mayoclinic_db"  # the token IS valid

    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])

    request = _FakeRequest(peer="8.8.8.8")
    with pytest.raises(HTTPException) as exc:
        _run(dc.verify_daraja_source(request))
    assert exc.value.status_code == 403


def test_allowed_ip_passes(monkeypatch):
    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])
    request = _FakeRequest(peer="196.201.214.10", body=b'{"hello": true}')
    assert _run(dc.verify_daraja_source(request)) == b'{"hello": true}'


def test_x_forwarded_for_is_only_trusted_behind_a_configured_proxy(monkeypatch):
    """Ported from the Pay Hero tests, which got this right. A direct public
    caller must not be able to spoof XFF to dodge the allow-list."""
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])

    # Peer is a public address (not private/loopback) -> XFF is attacker
    # controlled and must be ignored; the real peer IP is used instead.
    spoofer = "8.8.8.8"
    claimed = "196.201.214.10"  # an address that WOULD be allow-listed
    ip = dc._client_ip(_FakeRequest(peer=spoofer, xff=claimed))
    assert ip == ipaddress.ip_address(spoofer)

    # Now behind a configured trusted proxy: XFF is believed.
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", dc._parse_cidrs("10.0.0.0/8"))
    ip = dc._client_ip(_FakeRequest(peer="10.0.0.5", xff=claimed))
    assert ip == ipaddress.ip_address(claimed)

    # A public peer is still not trusted even with a proxy list configured.
    ip = dc._client_ip(_FakeRequest(peer=spoofer, xff=claimed))
    assert ip == ipaddress.ip_address(spoofer)


def test_disallowed_ip_via_spoofed_xff_is_still_rejected(monkeypatch):
    """End-to-end version of the XFF test: a public caller cannot spoof its
    way past verify_daraja_source's allow-list by forging X-Forwarded-For."""
    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])

    request = _FakeRequest(peer="8.8.8.8", xff="196.201.214.10")
    with pytest.raises(HTTPException) as exc:
        _run(dc.verify_daraja_source(request))
    assert exc.value.status_code == 403


def test_production_with_empty_allowlist_fails_closed(monkeypatch):
    monkeypatch.setattr(dc, "_ALLOWED_NETS", [])
    monkeypatch.setattr(settings, "APP_ENV", "production")
    request = _FakeRequest(peer="196.201.214.10")
    with pytest.raises(HTTPException) as exc:
        _run(dc.verify_daraja_source(request))
    assert exc.value.status_code == 500


def test_production_ip_allowlist_without_trusted_proxies_fails_closed(monkeypatch):
    """Finding 2 (review round 1): behind a load balancer the immediate peer
    is private, so the empty-trusted-proxy fallback in _peer_is_trusted_proxy
    would trust a spoofed X-Forwarded-For from that peer. An allow-list
    configured without an explicit trusted-proxy list is bypassable in
    production, so it must fail closed exactly like an empty allow-list."""
    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])
    monkeypatch.setattr(settings, "APP_ENV", "production")

    request = _FakeRequest(peer="196.201.214.10")
    with pytest.raises(HTTPException) as exc:
        _run(dc.verify_daraja_source(request))
    assert exc.value.status_code == 500


def test_production_with_trusted_proxies_configured_still_works(monkeypatch):
    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", dc._parse_cidrs("10.0.0.0/8"))
    monkeypatch.setattr(settings, "APP_ENV", "production")

    request = _FakeRequest(peer="10.0.0.5", xff="196.201.214.10", body=b'{"ok": 1}')
    assert _run(dc.verify_daraja_source(request)) == b'{"ok": 1}'


def test_development_with_empty_allowlist_is_permissive(monkeypatch):
    """Mirrors verify_payhero's posture: an empty allow-list is only
    tolerated outside production, so local fixture tests can post."""
    monkeypatch.setattr(dc, "_ALLOWED_NETS", [])
    monkeypatch.setattr(settings, "APP_ENV", "development")
    request = _FakeRequest(peer="8.8.8.8", body=b'{"ok": 1}')
    assert _run(dc.verify_daraja_source(request)) == b'{"ok": 1}'


def test_body_is_not_read_before_the_ip_check_rejects(monkeypatch):
    """The body used to be read first (Pay Hero needed the bytes for its
    HMAC check). Daraja has no signature, so reading first only lets a
    disallowed source make the server buffer an arbitrary body before the
    cheapest possible rejection."""
    monkeypatch.setattr(dc, "_ALLOWED_NETS", dc._parse_cidrs("196.201.214.0/24"))
    monkeypatch.setattr(dc, "_TRUSTED_PROXY_NETS", [])

    calls = []

    class _CountingRequest(_FakeRequest):
        async def body(self):
            calls.append(1)
            return await super().body()

    request = _CountingRequest(peer="8.8.8.8")
    with pytest.raises(HTTPException):
        _run(dc.verify_daraja_source(request))
    assert calls == []


# --- acknowledgement contract --------------------------------------------

def test_rejected_callback_still_returns_200(tenant_registry):
    """Safaricom retries non-200s, and on C2B validation a non-200 can
    decline the customer's payment at the till. We reject in our own
    records and acknowledge on theirs: resolve_tenant_by_token records the
    rejection by returning None without raising, so a route can always
    respond 200 with ACK_REJECT rather than propagating an error status."""
    tenant_registry["mayoclinic_db"] = _new_config()

    resolved = dc.resolve_tenant_by_token("not-a-real-token")

    assert resolved is None
    # The body a caller sends back on this path carries ResultCode 0, which
    # Safaricom reads as accepted and will not retry.
    assert dc.ACK_REJECT == {"ResultCode": 0, "ResultDesc": "Accepted"}
    assert dc.ACK_OK == {"ResultCode": 0, "ResultDesc": "Accepted"}


def test_lookup_failure_is_not_the_same_contract_as_a_rejection(monkeypatch):
    """The distinction Finding 3 is about, stated as a test: a rejection
    (None) is fine to acknowledge as 200. A failure to evaluate must raise
    instead, so a route never accidentally answers 200 for a callback nobody
    actually checked."""
    def _boom():
        raise dc.TenantLookupUnavailable("master db unreachable")

    monkeypatch.setattr(dc, "_active_tenant_db_names", _boom)

    with pytest.raises(dc.TenantLookupUnavailable):
        dc.resolve_tenant_by_token(mint_callback_token())


def test_c2b_decline_is_the_one_genuine_rejection(monkeypatch):
    """C2B validation is the one place a rejection is actually expressed to
    Safaricom, because there it means 'do not accept this payment at the
    till' rather than 'we silently dropped what you already accepted'."""
    assert dc.ACK_C2B_DECLINE["ResultCode"] != 0
    assert dc.ACK_C2B_DECLINE != dc.ACK_OK
    assert dc.ACK_C2B_DECLINE != dc.ACK_REJECT


def test_ack_bodies_are_immutable():
    """A route mutating one of these in place would poison it for every
    later callback: they are shared, reused objects, not per-call templates."""
    with pytest.raises(TypeError):
        dc.ACK_OK["ResultCode"] = 1
    with pytest.raises(TypeError):
        dc.ACK_REJECT["ResultCode"] = 1
    with pytest.raises(TypeError):
        dc.ACK_C2B_DECLINE["ResultCode"] = 1
