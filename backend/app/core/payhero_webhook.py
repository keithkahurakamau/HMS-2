"""Pay Hero webhook authentication.

PAY-002: prior M-Pesa callback accepted any unauthenticated POST. Pay Hero
signs every callback with a shared secret; we verify the HMAC and also
enforce an IP allow-list as defence-in-depth (covers key rotation gaps).

Production behaviour:
  * Both signature and IP checks are enforced — fail-closed.
Development behaviour (settings.is_production == False):
  * Signature check is enforced when PAYHERO_WEBHOOK_SECRET is set; skipped
    otherwise so local fixture tests can post fabricated payloads.
  * IP allow-list is enforced when PAYHERO_WEBHOOK_CIDRS is set.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
from typing import Iterable

from fastapi import HTTPException, Request

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _parse_cidrs(raw: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            logger.warning("Ignoring malformed PAYHERO_WEBHOOK_CIDRS entry: %r", chunk)
    return out


_ALLOWED_NETS: list[ipaddress._BaseNetwork] = _parse_cidrs(settings.PAYHERO_WEBHOOK_CIDRS)


def _client_ip(request: Request) -> ipaddress._BaseAddress | None:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        try:
            return ipaddress.ip_address(first)
        except ValueError:
            pass
    if request.client and request.client.host:
        try:
            return ipaddress.ip_address(request.client.host)
        except ValueError:
            return None
    return None


def _signature_valid(raw_body: bytes, header_value: str | None, secret: str) -> bool:
    if not header_value:
        return False
    secret_bytes = (secret or "").encode("utf-8")
    if not secret_bytes:
        return False
    expected = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
    # Tolerate either hex or "sha256=hex" forms — Pay Hero changed format
    # between docs versions.
    candidate = header_value.split("=", 1)[1] if "=" in header_value else header_value
    return hmac.compare_digest(expected, candidate.strip())


async def verify_payhero(request: Request, expected_secret: str | None = None) -> bytes:
    """Verify a Pay Hero webhook request and return the raw body bytes.

    ``expected_secret`` is the resolved per-tenant webhook secret (each hospital
    owns its own Pay Hero account, so each signs with its own secret). When it
    is None — the tenant set no secret, or the callback is for the operator's
    own account — we fall back to the global settings.PAYHERO_WEBHOOK_SECRET.

    Raises HTTPException on any failure.
    """
    raw = await request.body()
    is_prod = settings.is_production
    secret = expected_secret or settings.payhero_webhook_secret

    # IP allow-list
    if _ALLOWED_NETS:
        ip = _client_ip(request)
        if ip is None or not any(ip in net for net in _ALLOWED_NETS):
            logger.warning("Pay Hero webhook from disallowed IP: %s", ip)
            raise HTTPException(status_code=403, detail="Source IP not allow-listed")
    elif is_prod:
        # Production must have CIDRs configured.
        logger.error("Pay Hero webhook hit in production with empty allow-list")
        raise HTTPException(status_code=500, detail="Webhook allow-list not configured")

    # HMAC signature
    sig_header = (
        request.headers.get("x-payhero-signature")
        or request.headers.get("x-signature")
    )
    if secret:
        if not _signature_valid(raw, sig_header, secret):
            raise HTTPException(status_code=401, detail="Webhook signature invalid")
    elif is_prod:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    return raw


def allowed_networks() -> Iterable[ipaddress._BaseNetwork]:
    """Exposed for tests + diagnostic endpoints."""
    return tuple(_ALLOWED_NETS)
