"""Pay Hero webhook source-IP resolution (security audit H-4).

X-Forwarded-For must only be trusted when the request reached us through a
trusted proxy — otherwise a direct caller could spoof an allow-listed source IP
and bypass the allow-list. These tests poke _client_ip with a fake request.
"""
from __future__ import annotations

import ipaddress
import types

import app.core.payhero_webhook as wh


def _req(peer: str | None, xff: str | None = None):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    client = types.SimpleNamespace(host=peer) if peer else None
    return types.SimpleNamespace(client=client, headers=headers)


def test_xff_trusted_when_peer_is_private(monkeypatch):
    # Behind a platform LB (private peer) → trust the forwarded client IP.
    monkeypatch.setattr(wh, "_TRUSTED_PROXY_NETS", [])
    ip = wh._client_ip(_req("10.0.0.5", xff="41.90.1.2, 10.0.0.5"))
    assert ip == ipaddress.ip_address("41.90.1.2")


def test_xff_ignored_when_peer_is_public(monkeypatch):
    # Direct public caller spoofing XFF → we use the real peer, not the header.
    monkeypatch.setattr(wh, "_TRUSTED_PROXY_NETS", [])
    spoofer = "8.8.8.8"
    ip = wh._client_ip(_req(spoofer, xff="41.90.1.2"))  # claims an allow-listed IP
    assert ip == ipaddress.ip_address(spoofer)


def test_explicit_trusted_proxy_list(monkeypatch):
    monkeypatch.setattr(wh, "_TRUSTED_PROXY_NETS", wh._parse_cidrs("198.51.100.0/24"))
    # Peer in the trusted set → trust XFF.
    assert wh._client_ip(_req("198.51.100.9", xff="41.90.1.2")) == ipaddress.ip_address("41.90.1.2")
    # Peer NOT in the trusted set → ignore XFF, use peer.
    assert wh._client_ip(_req("8.8.8.8", xff="41.90.1.2")) == ipaddress.ip_address("8.8.8.8")


def test_no_xff_uses_peer(monkeypatch):
    monkeypatch.setattr(wh, "_TRUSTED_PROXY_NETS", [])
    assert wh._client_ip(_req("10.0.0.5")) == ipaddress.ip_address("10.0.0.5")
