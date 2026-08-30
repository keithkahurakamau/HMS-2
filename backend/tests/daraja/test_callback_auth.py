"""Daraja callback authentication.

Safaricom does not sign callbacks, so these tests exercise the three things
that stand in for a signature: the unguessable per-tenant token (never the
tenant database name), the Safaricom source-IP allow-list (including the
X-Forwarded-For handling ported from Pay Hero's audited, correct version),
and the acknowledgement contract that always looks like acceptance to
Safaricom even when we have rejected a callback on our own side.
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
    """A monotonic clock the test controls, for deterministic TTL tests."""

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

    def _lookup_token_in_tenant(tenant_db: str, lookup_hash: str) -> bool:
        config = tenants.get(tenant_db)
        if config is None:
            return False
        return bool(config.is_active) and config.callback_token_lookup == lookup_hash

    monkeypatch.setattr(dc, "_active_tenant_db_names", _active_tenant_db_names)
    monkeypatch.setattr(dc, "_lookup_token_in_tenant", _lookup_token_in_tenant)
    return tenants


def _new_config(is_active: bool = True) -> MpesaConfig:
    config = MpesaConfig(shortcode="174379", shortcode_type="paybill")
    config.is_active = is_active
    return config


# --- token resolution -------------------------------------------------

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
    monkeypatch.setattr(dc.time, "monotonic", clock)
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


def test_development_with_empty_allowlist_is_permissive(monkeypatch):
    """Mirrors verify_payhero's posture: an empty allow-list is only
    tolerated outside production, so local fixture tests can post."""
    monkeypatch.setattr(dc, "_ALLOWED_NETS", [])
    monkeypatch.setattr(settings, "APP_ENV", "development")
    request = _FakeRequest(peer="8.8.8.8", body=b'{"ok": 1}')
    assert _run(dc.verify_daraja_source(request)) == b'{"ok": 1}'


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


def test_c2b_decline_is_the_one_genuine_rejection(monkeypatch):
    """C2B validation is the one place a rejection is actually expressed to
    Safaricom, because there it means 'do not accept this payment at the
    till' rather than 'we silently dropped what you already accepted'."""
    assert dc.ACK_C2B_DECLINE["ResultCode"] != 0
    assert dc.ACK_C2B_DECLINE != dc.ACK_OK
    assert dc.ACK_C2B_DECLINE != dc.ACK_REJECT
