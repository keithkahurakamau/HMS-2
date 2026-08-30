"""Daraja callback authentication.

Safaricom does not sign callbacks: it sends an unauthenticated HTTP POST to
whatever URL we registered. Anyone who learns or guesses a callback URL can
POST a fabricated "payment received" body at it. See
docs/superpowers/specs/2026-08-29-daraja-migration-design.md, section "The
one thing that makes this harder than it looks", for the full reasoning.

Authentication is rebuilt from three parts:

  1. An unguessable, rotatable callback token in the path (this module:
     mint_callback_token / resolve_tenant_by_token).
  2. A Safaricom IP allow-list, fail-closed in production when unconfigured
     (this module: verify_daraja_source).
  3. A settlement cross-check that never trusts the callback's claimed
     amount (built into the settlement paths that call into this module,
     not here).

No single one of these is sufficient on its own; the settlement cross-check
is the one that still holds if the other two fail.

The old Pay Hero design put the tenant's DATABASE NAME in the callback path
(``/api/payments/payhero/callback/{tenant_db}``). Under Pay Hero that was
safe because the HMAC signature was the real gate and the path was only for
routing. Carried forward unchanged to an unsigned protocol, it becomes a way
to mint free payments against any hospital whose database name can be
guessed (e.g. "mayoclinic_db"). resolve_tenant_by_token below never accepts
a database name, or anything else, by resemblance: it hashes whatever it is
given with the same deterministic HMAC used to write
MpesaConfig.callback_token_lookup and looks that hash up by equality. It
never decrypts callback_token_encrypted to compare tokens, which would be an
O(n) scan decrypting every tenant's secret on every inbound request.
"""
from __future__ import annotations

import ipaddress
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Iterable

from fastapi import HTTPException, Request

from app.config.settings import settings
from app.services.daraja.tokens import mint_callback_token, token_lookup_hash

logger = logging.getLogger(__name__)

__all__ = [
    "mint_callback_token",
    "resolve_tenant_by_token",
    "verify_daraja_source",
    "ACK_OK",
    "ACK_REJECT",
    "ACK_C2B_DECLINE",
    "allowed_networks",
    "clear_negative_cache",
]

# Callbacks always return HTTP 200, including when we reject the content: a
# non-200 makes Safaricom retry a payload we already decided is bad, and on
# C2B validation specifically a non-200 can cause the customer's payment to
# be declined at the till, a real person standing at a counter unable to
# pay. Rejection is recorded on our side and acknowledged on theirs.
ACK_OK = {"ResultCode": 0, "ResultDesc": "Accepted"}
ACK_REJECT = {"ResultCode": 0, "ResultDesc": "Accepted"}
# C2B validation is the one place a rejection is genuinely expressed to
# Safaricom, because there it means "do not accept this payment at the
# till", not merely "we chose not to process what you already accepted".
ACK_C2B_DECLINE = {"ResultCode": "C2B00016", "ResultDesc": "Rejected"}


# --- Source IP allow-list -------------------------------------------------
# Ported near-verbatim from app.core.payhero_webhook: that module's
# X-Forwarded-For handling is already correct (audit H-4) and rewriting it
# from memory risks reintroducing the bug it fixed. The HMAC signature
# verification is dropped: there is no signature to check.

def _parse_cidrs(raw: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            # Don't echo the raw config value back into logs, just flag that
            # an entry was malformed so the operator knows to check the env.
            logger.warning(
                "Ignoring a malformed CIDR allow-list entry "
                "(check DARAJA_WEBHOOK_CIDRS / DARAJA_TRUSTED_PROXIES)"
            )
    return out


_ALLOWED_NETS: list[ipaddress._BaseNetwork] = _parse_cidrs(settings.DARAJA_WEBHOOK_CIDRS)
_TRUSTED_PROXY_NETS: list[ipaddress._BaseNetwork] = _parse_cidrs(settings.DARAJA_TRUSTED_PROXIES)


def _peer_is_trusted_proxy(peer: ipaddress._BaseAddress) -> bool:
    """Should we believe this peer's X-Forwarded-For header? (H-4)

    Only if it is a configured trusted proxy. When none are configured we
    fall back to "the peer is a private/loopback/link-local address", the
    shape of being behind a platform load balancer (Render, etc.) on a
    private network. A direct public caller fails this, so it can't spoof
    XFF to dodge the allow-list.
    """
    if _TRUSTED_PROXY_NETS:
        return any(peer in net for net in _TRUSTED_PROXY_NETS)
    return peer.is_private or peer.is_loopback or peer.is_link_local


def _client_ip(request: Request) -> ipaddress._BaseAddress | None:
    peer: ipaddress._BaseAddress | None = None
    if request.client and request.client.host:
        try:
            peer = ipaddress.ip_address(request.client.host)
        except ValueError:
            peer = None

    # H-4: trust X-Forwarded-For ONLY when the request reached us through a
    # trusted proxy, otherwise the header is attacker-controlled.
    if peer is not None and _peer_is_trusted_proxy(peer):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            try:
                return ipaddress.ip_address(first)
            except ValueError:
                pass
    return peer


async def verify_daraja_source(request: Request) -> bytes:
    """Check the inbound callback came from an allow-listed Safaricom IP.

    Returns the raw request body on success. Raises HTTPException on a
    disallowed source, or in production when the allow-list itself is
    unconfigured (fail closed rather than accept every source).

    There is no signature to verify here: Daraja does not sign callbacks.
    The IP allow-list is one layer of defence-in-depth; the callback token
    in the path and the settlement cross-check are the other two.
    """
    raw = await request.body()
    is_prod = settings.is_production

    if _ALLOWED_NETS:
        ip = _client_ip(request)
        if ip is None or not any(ip in net for net in _ALLOWED_NETS):
            logger.warning("Daraja callback from disallowed IP: %s", ip)
            raise HTTPException(status_code=403, detail="Source IP not allow-listed")
    elif is_prod:
        # Production must have CIDRs configured. Fail closed.
        logger.error("Daraja callback hit in production with empty allow-list")
        raise HTTPException(status_code=500, detail="Webhook allow-list not configured")

    return raw


def allowed_networks() -> Iterable[ipaddress._BaseNetwork]:
    """Exposed for tests + diagnostic endpoints."""
    return tuple(_ALLOWED_NETS)


# --- Tenant resolution by callback token ----------------------------------
# The token is looked up by its deterministic HMAC lookup hash, never by
# decrypting callback_token_encrypted and comparing: that would be an O(n)
# scan decrypting every tenant's secret on every inbound request. A hash that
# matches no tenant is cached briefly so a token-guessing flood cannot become
# one database scan per request. A hash that DOES match is never cached, so
# a token rotation takes effect on the very next callback instead of waiting
# out a TTL.

_NEGATIVE_CACHE_TTL_SECONDS = 5.0
_NEGATIVE_CACHE_MAX_SIZE = 512

_negative_cache: "OrderedDict[str, float]" = OrderedDict()
_negative_cache_lock = Lock()


def _negative_cache_get(lookup_hash: str) -> bool:
    now = time.monotonic()
    with _negative_cache_lock:
        expiry = _negative_cache.get(lookup_hash)
        if expiry is None:
            return False
        if expiry <= now:
            _negative_cache.pop(lookup_hash, None)
            return False
        _negative_cache.move_to_end(lookup_hash)
        return True


def _negative_cache_put(lookup_hash: str) -> None:
    with _negative_cache_lock:
        _negative_cache[lookup_hash] = time.monotonic() + _NEGATIVE_CACHE_TTL_SECONDS
        _negative_cache.move_to_end(lookup_hash)
        while len(_negative_cache) > _NEGATIVE_CACHE_MAX_SIZE:
            _negative_cache.popitem(last=False)


def clear_negative_cache() -> None:
    """Drop every cached negative lookup. Test seam + operational escape
    hatch: never needed for correctness (positive lookups are never cached
    and every entry expires on its own), but useful to reset state."""
    with _negative_cache_lock:
        _negative_cache.clear()


def _active_tenant_db_names() -> list[str]:
    """Every active tenant db_name from the master registry.

    Mirrors the master-registry pattern in
    routes/payhero_payment.py:_resolve_tenant_db, except that a Daraja
    callback token carries no tenant hint in the path, so every active
    tenant is a candidate rather than one path-supplied name being
    validated against the registry.
    """
    from app.config.database import MasterSessionLocal
    from app.models.master import Tenant

    master = MasterSessionLocal()
    try:
        rows = (
            master.query(Tenant.db_name)
            .filter(Tenant.is_active == True)  # noqa: E712
            .all()
        )
        return [row[0] for row in rows]
    except Exception:  # noqa: BLE001, a registry failure must not crash the callback
        logger.exception("Daraja callback: tenant registry lookup failed")
        return []
    finally:
        master.close()


def _lookup_token_in_tenant(tenant_db: str, lookup_hash: str) -> bool:
    """True if `tenant_db`'s MpesaConfig carries this lookup hash."""
    from sqlalchemy.orm import sessionmaker

    from app.config.database import get_tenant_engine
    from app.models.mpesa import MpesaConfig

    engine = get_tenant_engine(tenant_db)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        return (
            session.query(MpesaConfig.id)
            .filter(
                MpesaConfig.callback_token_lookup == lookup_hash,
                MpesaConfig.is_active == True,  # noqa: E712
            )
            .first()
            is not None
        )
    except Exception:  # noqa: BLE001, one bad tenant DB must not fail the whole scan
        logger.exception("Daraja callback: token lookup failed for tenant %s", tenant_db)
        return False
    finally:
        session.close()


def resolve_tenant_by_token(token: str) -> str | None:
    """Resolve an inbound callback token to a tenant db_name, or None.

    Hashes `token` with the same deterministic HMAC used to write
    callback_token_lookup and looks that hash up by equality across active
    tenants. A tenant's database name is never accepted here: it is not a
    minted token, so hashing it will not match any stored lookup hash. That
    is the specific old Pay Hero design (a guessable db_name in the callback
    path) this replaces.
    """
    if not token:
        return None

    lookup_hash = token_lookup_hash(token)
    if _negative_cache_get(lookup_hash):
        return None

    for tenant_db in _active_tenant_db_names():
        if _lookup_token_in_tenant(tenant_db, lookup_hash):
            return tenant_db

    _negative_cache_put(lookup_hash)
    return None
