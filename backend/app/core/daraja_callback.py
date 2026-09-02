"""Daraja callback authentication.

Safaricom does not sign callbacks: it sends an unauthenticated HTTP POST to
whatever URL we registered. Anyone who learns or guesses a callback URL can
POST a fabricated "payment received" body at it. See
docs/superpowers/specs/2026-08-29-daraja-migration-design.md, section "The
one thing that makes this harder than it looks", for the full reasoning.

Authentication is rebuilt from three parts:

  1. An unguessable, rotatable callback token in the path, plus a tenant
     routing hint carried alongside it (this module: mint_callback_token /
     resolve_tenant_by_hint / resolve_tenant_by_token).
  2. A Safaricom IP allow-list, fail-closed in production when unconfigured
     (this module: verify_daraja_source).
  3. A settlement cross-check that never trusts the callback's claimed
     amount (built into the settlement paths that call into this module,
     not here).

No single one of these is sufficient on its own; the settlement cross-check
is the one that still holds if the other two fail.

ORDERING INVARIANT, load-bearing: a route MUST call verify_daraja_source
BEFORE resolve_tenant_by_hint or resolve_tenant_by_token. The IP gate is
what keeps a per-request database lookup from being something an
unauthenticated caller can trigger for free. resolve_tenant_by_hint is one
indexed lookup and cheap even without the IP gate, but resolve_tenant_by_token
(the legacy scan, see its own docstring) is a lookup per active tenant, and
nothing inside either function enforces this ordering. A route that resolves
the tenant before checking the source IP has removed the one thing standing
between an open endpoint and a query-cost denial-of-service.

The old Pay Hero design put the tenant's DATABASE NAME in the callback path
(``/api/payments/payhero/callback/{tenant_db}``). Under Pay Hero that was
safe because the HMAC signature was the real gate and the path was only for
routing. Carried forward unchanged to an unsigned protocol, it becomes a way
to mint free payments against any hospital whose database name can be
guessed (e.g. "mayoclinic_db"). Neither resolve_tenant_by_hint nor
resolve_tenant_by_token accepts a database name, or anything else, by
resemblance: both hash whatever they are given with the same deterministic
HMAC used to write MpesaConfig.callback_token_lookup and look that hash up
by equality. Neither ever decrypts callback_token_encrypted to compare
tokens, which would be an O(n) scan decrypting every tenant's secret on
every inbound request. A tenant routing hint that names the wrong tenant, or
a tenant that does not exist, simply fails to find the token: the hint is
routing information, never the gate, exactly the property that made a
guessable value unsafe under Pay Hero and safe here. Tenant database names
are already publicly enumerable through GET /api/public/hospitals, so the
hint discloses nothing an attacker could not already learn.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import time
from collections import OrderedDict
from threading import Lock
from types import MappingProxyType
from typing import Iterable

from fastapi import HTTPException, Request

from app.config.settings import settings
from app.services.daraja.tokens import mint_callback_token, token_lookup_hash

logger = logging.getLogger(__name__)

__all__ = [
    "mint_callback_token",
    "resolve_tenant_by_hint",
    "resolve_tenant_by_token",
    "verify_daraja_source",
    "TenantLookupUnavailable",
    "ACK_OK",
    "ACK_REJECT",
    "ACK_C2B_DECLINE",
    "allowed_networks",
    "clear_negative_cache",
    "PLATFORM_HINT",
]


class TenantLookupUnavailable(Exception):
    """Raised when a callback token could not be evaluated at all, e.g. a
    master-DB or tenant-DB failure. This is NOT the same outcome as a token
    or tenant that genuinely does not match, and the two must never be
    confused (this was Finding 3 of the first review round).

    resolve_tenant_by_hint and resolve_tenant_by_token return None for "we
    checked and it does not match", which a route may acknowledge with
    ACK_REJECT: HTTP 200, Safaricom will not retry, because we evaluated the
    payload and rejected it. They raise this instead for "we could not
    check", which a route must answer with a non-200 so Safaricom retries:
    the "always acknowledge 200" rule covers a payload we evaluated and
    rejected, never one we failed to evaluate.

    This matters most for C2B confirmations. An STK callback that is lost
    this way still has the reconciliation poller as a safety net. A C2B
    confirmation does not: by definition there is no prior record, so one
    dropped during an outage is money that reached the hospital's till,
    never posted to the ledger, with no record anywhere that it happened.
    """


# Callbacks always return HTTP 200, including when we reject the content: a
# non-200 makes Safaricom retry a payload we already decided is bad, and on
# C2B validation specifically a non-200 can cause the customer's payment to
# be declined at the till, a real person standing at a counter unable to
# pay. Rejection is recorded on our side and acknowledged on theirs. This
# covers a payload we EVALUATED and rejected; a lookup we could not perform
# at all raises TenantLookupUnavailable instead (see its docstring) and must
# not be acknowledged the same way.
#
# Immutable (MappingProxyType): these are shared, reused objects, not
# templates copied per call. A route that mutated one in place (even
# something as small as `body["ResultDesc"] = "..."`) would silently poison
# it for every callback handled afterwards.
ACK_OK = MappingProxyType({"ResultCode": 0, "ResultDesc": "Accepted"})
ACK_REJECT = MappingProxyType({"ResultCode": 0, "ResultDesc": "Accepted"})
# C2B validation is the one place a rejection is genuinely expressed to
# Safaricom, because there it means "do not accept this payment at the
# till", not merely "we chose not to process what you already accepted".
ACK_C2B_DECLINE = MappingProxyType({"ResultCode": "C2B00016", "ResultDesc": "Rejected"})


# --- Source IP allow-list -------------------------------------------------
# Ported near-verbatim from app.core.payhero_webhook: that module's
# X-Forwarded-For handling is already correct (audit H-4) and rewriting it
# from memory risks reintroducing the bug it fixed. The HMAC signature
# verification is dropped: there is no signature to check. Do not "fix"
# _peer_is_trusted_proxy or _client_ip themselves: the behaviour they inherit
# from Pay Hero is faithful, not a defect introduced here. What changed is
# the risk weight (see verify_daraja_source's production check below): under
# Pay Hero the HMAC was the real gate and this list was defence in depth,
# under Daraja this list is one of only two layers and it also gates the
# database lookup.

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
    disallowed source, or when required configuration is missing in
    production (fail closed rather than accept every source).

    There is no signature to verify here: Daraja does not sign callbacks.
    The IP allow-list is one layer of defence-in-depth; the callback token
    (plus its tenant routing hint) and the settlement cross-check are the
    other two.

    Callers must run this BEFORE resolve_tenant_by_hint / resolve_tenant_by_token
    (see the module docstring's ordering invariant): this is the only gate
    standing between an unauthenticated caller and a per-request database
    lookup.
    """
    is_prod = settings.is_production

    if _ALLOWED_NETS:
        if is_prod and not _TRUSTED_PROXY_NETS:
            # Finding 2 (review round 1): behind a platform load balancer the
            # immediate peer is private, so the empty-proxy-list fallback in
            # _peer_is_trusted_proxy trusts X-Forwarded-For from that private
            # peer. Standard proxies APPEND to XFF rather than replace it, so
            # the leftmost entry is still whatever the original client sent.
            # In production that means anyone who can reach the app through
            # the load balancer can set X-Forwarded-For to a Safaricom IP and
            # pass the allow-list unchecked. Without an explicit trusted-proxy
            # list we cannot tell a real proxy hop from a spoofed header, so
            # fail closed exactly as we already do for an empty allow-list.
            logger.error(
                "Daraja callback hit in production with DARAJA_TRUSTED_PROXIES "
                "unset; the IP allow-list would be bypassable via a spoofed "
                "X-Forwarded-For header"
            )
            raise HTTPException(
                status_code=500, detail="Webhook trusted-proxy list not configured"
            )
        ip = _client_ip(request)
        if ip is None or not any(ip in net for net in _ALLOWED_NETS):
            logger.warning("Daraja callback from disallowed IP: %s", ip)
            raise HTTPException(status_code=403, detail="Source IP not allow-listed")
    elif is_prod:
        # Production must have CIDRs configured. Fail closed.
        logger.error("Daraja callback hit in production with empty allow-list")
        raise HTTPException(status_code=500, detail="Webhook allow-list not configured")

    # Read the body only after the source has cleared the allow-list. Pay
    # Hero read it first because verify_payhero needed the bytes for the HMAC
    # check; that reason is gone here, and reading first would let a
    # disallowed source make the server buffer an arbitrary body before the
    # cheapest possible rejection.
    return await request.body()


def allowed_networks() -> Iterable[ipaddress._BaseNetwork]:
    """Exposed for tests + diagnostic endpoints."""
    return tuple(_ALLOWED_NETS)


# --- Tenant resolution by callback token ----------------------------------
# The token is looked up by its deterministic HMAC lookup hash, never by
# decrypting callback_token_encrypted and comparing: that would be an O(n)
# scan decrypting every tenant's secret on every inbound request.
#
# resolve_tenant_by_hint is the primary path: the callback URL carries a
# tenant routing hint alongside the token, so resolution is one indexed
# lookup against exactly one tenant database, not a scan. resolve_tenant_by_token
# (below it) is the older scanning form, kept working for callers already
# built against it.

# Indirection point so tests can control the clock without monkeypatching
# the stdlib time module process-wide (which would also affect unrelated
# code, e.g. SQLAlchemy pool recycling, for the duration of the test).
_monotonic = time.monotonic

_NEGATIVE_CACHE_TTL_SECONDS = 5.0
_NEGATIVE_CACHE_MAX_SIZE = 512

_negative_cache: "OrderedDict[str, float]" = OrderedDict()
_negative_cache_lock = Lock()


def _negative_cache_get(cache_key: str) -> bool:
    now = _monotonic()
    with _negative_cache_lock:
        expiry = _negative_cache.get(cache_key)
        if expiry is None:
            return False
        if expiry <= now:
            _negative_cache.pop(cache_key, None)
            return False
        _negative_cache.move_to_end(cache_key)
        return True


def _negative_cache_put(cache_key: str) -> None:
    with _negative_cache_lock:
        _negative_cache[cache_key] = _monotonic() + _NEGATIVE_CACHE_TTL_SECONDS
        _negative_cache.move_to_end(cache_key)
        while len(_negative_cache) > _NEGATIVE_CACHE_MAX_SIZE:
            _negative_cache.popitem(last=False)


def clear_negative_cache() -> None:
    """Drop every cached negative lookup. Test seam + operational escape
    hatch: never needed for correctness (positive lookups are never cached
    and every entry expires on its own), but useful to reset state.

    Never called on a TenantLookupUnavailable path: a lookup that failed is
    not a lookup that resolved to "no match", and caching it as one would
    keep rejecting a VALID token for the rest of the TTL even after the
    underlying master-DB or tenant-DB failure has recovered (Finding 3).
    """
    with _negative_cache_lock:
        _negative_cache.clear()


# What this cache actually bounds: a REPEATED guess of the same token (or the
# same wrong tenant-hint/token pair), and Safaricom's own retries of a
# callback we already rejected. It does NOT bound a flood of DISTINCT guesses
# (a different random token on every request never hits the cache), which is
# the realistic shape of a brute-force attempt against a 32-byte
# secrets.token_urlsafe value; token entropy, not this cache, is what makes
# that attack infeasible. Overstating this cache's coverage here would be
# exactly the kind of stale security claim the main.py CSRF comment rewrite
# in this same task was written to avoid.


# Reserved routing-hint value for the platform's own Daraja config
# (PlatformMpesaConfig, master database), which is not a tenant database and
# so has no db_name. "platform-rail" contains a hyphen, which is outside
# app.config.database._VALID_TENANT_DB_NAME's charset ([a-z_][a-z0-9_]*):
# every real tenant db_name is provisioned through that exact same charset
# (see the comment on _VALID_TENANT_DB_NAME), so no legitimately-provisioned
# tenant can ever be named "platform-rail" or anything else containing a
# hyphen. The collision this guards against is therefore not just unlikely,
# it is impossible without a change to the provisioning charset itself.
_PLATFORM_HINT = "platform-rail"
# Public alias, for a route that needs to compare a resolved hint against
# this reserved value (app/routes/mpesa_payment.py's platform_stk_callback):
# reaching into a leading-underscore name from another module is a smell
# this module can remove for free. _PLATFORM_HINT itself stays, unchanged,
# since tests/daraja/test_callback_auth.py already exercises it directly.
PLATFORM_HINT = _PLATFORM_HINT

_VALID_TENANT_DB_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _active_tenant_db_names() -> list[str]:
    """Every active tenant db_name from the master registry.

    Used by resolve_tenant_by_token's scan (see its docstring for why the
    hinted path does not need this).

    Raises TenantLookupUnavailable on a master-registry failure rather than
    returning an empty list: an empty list here previously meant "there are
    no active tenants", indistinguishable from "the master DB could not be
    reached", which is exactly the ambiguity Finding 3 was raised against.
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
    except Exception as exc:  # noqa: BLE001, converted to a typed failure below
        logger.exception("Daraja callback: tenant registry lookup failed")
        raise TenantLookupUnavailable("tenant registry lookup failed") from exc
    finally:
        master.close()


def _lookup_token_in_tenant(
    tenant_db: str, lookup_hash: str, *, raise_on_error: bool = False
) -> bool:
    """True if `tenant_db`'s MpesaConfig carries this lookup hash.

    raise_on_error=True is for resolve_tenant_by_hint: that path names
    exactly one tenant, so a failure reaching that tenant's own database
    must surface as TenantLookupUnavailable, not be silently treated as "no
    match" (Finding 3). The legacy scanning path (resolve_tenant_by_token)
    passes raise_on_error=False (the default) and keeps its old
    catch-and-continue behaviour: there, one unreachable tenant is one
    candidate among many rather than the sole candidate the caller named, so
    the scan still needs to try the rest.
    """
    from sqlalchemy.orm import sessionmaker

    from app.config.database import get_tenant_engine
    from app.models.mpesa import MpesaConfig

    try:
        engine = get_tenant_engine(tenant_db)
        session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    except Exception as exc:  # noqa: BLE001, converted to a typed failure below
        logger.exception("Daraja callback: could not open tenant database")
        if raise_on_error:
            raise TenantLookupUnavailable("could not open tenant database") from exc
        return False

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
    except Exception as exc:  # noqa: BLE001, converted to a typed failure below
        logger.exception("Daraja callback: token lookup failed for a tenant")
        if raise_on_error:
            raise TenantLookupUnavailable("tenant token lookup failed") from exc
        return False
    finally:
        session.close()


def _tenant_hint_is_active(tenant_hint: str) -> bool:
    """True if tenant_hint names a real, active tenant in the master registry.

    Raises TenantLookupUnavailable on a master-DB failure rather than
    returning False: a registry lookup we could not perform must not be
    mistaken for "no such tenant" (Finding 3). A registry lookup that
    SUCCEEDS and finds no matching active tenant returns False, which
    resolve_tenant_by_hint treats as a rejection: a wrong or spoofed hint is
    supposed to simply fail to find the token, not raise an error.
    """
    from app.config.database import MasterSessionLocal
    from app.models.master import Tenant

    master = MasterSessionLocal()
    try:
        return (
            master.query(Tenant.tenant_id)
            .filter(Tenant.db_name == tenant_hint, Tenant.is_active == True)  # noqa: E712
            .first()
            is not None
        )
    except Exception as exc:  # noqa: BLE001, converted to a typed failure below
        logger.exception("Daraja callback: tenant registry lookup failed for a routing hint")
        raise TenantLookupUnavailable("tenant registry lookup failed") from exc
    finally:
        master.close()


def _resolve_platform_token(lookup_hash: str) -> str | None:
    """Resolve a callback token against the platform's own Daraja config.

    PlatformMpesaConfig lives in the master database (it is MediFleet's own
    subscription-billing rail, not a hospital's), so this is a single query
    against master rather than opening a tenant engine. Returns _PLATFORM_HINT
    on a match, the same shape resolve_tenant_by_hint returns for a tenant
    match, so callers do not need a special case.

    Raises TenantLookupUnavailable on a master-DB failure, the same contract
    as the tenant path (Finding 3).
    """
    from app.config.database import MasterSessionLocal
    from app.models.platform_mpesa import PlatformMpesaConfig

    master = MasterSessionLocal()
    try:
        matched = (
            master.query(PlatformMpesaConfig.id)
            .filter(
                PlatformMpesaConfig.callback_token_lookup == lookup_hash,
                PlatformMpesaConfig.is_active == True,  # noqa: E712
            )
            .first()
            is not None
        )
    except Exception as exc:  # noqa: BLE001, converted to a typed failure below
        logger.exception("Daraja callback: platform token lookup failed")
        raise TenantLookupUnavailable("platform token lookup failed") from exc
    finally:
        master.close()
    return _PLATFORM_HINT if matched else None


def resolve_tenant_by_hint(tenant_hint: str, token: str) -> str | None:
    """Resolve a callback token to a tenant db_name using the routing hint
    carried alongside it in the callback path, e.g.
    /api/payments/mpesa/stk/callback/{tenant_hint}/{token}.

    This is the resolution path routes should use. It opens exactly one
    tenant database (the one named by tenant_hint) and does one indexed
    equality lookup, instead of resolve_tenant_by_token's scan across every
    active tenant. tenant_hint == _PLATFORM_HINT resolves against the
    platform's own master-DB config instead of a tenant database.

    The token remains the sole gate. A wrong or spoofed hint does not grant
    access to a tenant: it is looked up like any other hint, and simply
    fails to find the token if it does not name the tenant that actually
    holds it. This is the property that makes the hint safe to disclose (see
    the module docstring): unlike the old Pay Hero design, the hint here is
    never checked in place of a token, only alongside one.

    Callers MUST run verify_daraja_source first (see the module docstring's
    ordering invariant).

    Raises TenantLookupUnavailable if the callback could not be evaluated at
    all (a master-DB or tenant-DB failure). Callers must not acknowledge
    that outcome as accepted; see TenantLookupUnavailable's docstring.
    """
    if not token or not tenant_hint:
        return None

    lookup_hash = token_lookup_hash(token)
    cache_key = f"{tenant_hint}:{lookup_hash}"
    if _negative_cache_get(cache_key):
        return None

    if tenant_hint == _PLATFORM_HINT:
        resolved = _resolve_platform_token(lookup_hash)
    elif _VALID_TENANT_DB_NAME.match(tenant_hint):
        resolved = None
        if _tenant_hint_is_active(tenant_hint) and _lookup_token_in_tenant(
            tenant_hint, lookup_hash, raise_on_error=True
        ):
            resolved = tenant_hint
    else:
        # Malformed hint: cannot possibly be a real tenant db_name or the
        # reserved platform hint. Reject without touching any database.
        resolved = None

    if resolved is None:
        _negative_cache_put(cache_key)
    return resolved


def resolve_tenant_by_token(token: str) -> str | None:
    """Resolve an inbound callback token to a tenant db_name by scanning
    every active tenant, or None.

    Deprecated for routing: resolve_tenant_by_hint is what routes use going
    forward, an O(1) lookup against the tenant named by the callback path's
    routing hint instead of a scan across every active tenant. This function
    is kept working because it is cheap to keep and existing callers/tests
    should not break, not because new code should call it.

    Hashes `token` with the same deterministic HMAC used to write
    callback_token_lookup and looks that hash up by equality across active
    tenants. A tenant's database name is never accepted here: it is not a
    minted token, so hashing it will not match any stored lookup hash. That
    is the specific old Pay Hero design (a guessable db_name in the callback
    path) this replaces.

    Callers MUST run verify_daraja_source first (see the module docstring's
    ordering invariant): the IP gate is the only thing keeping this scan's
    cost acceptable, since nothing here enforces that ordering itself.

    Raises TenantLookupUnavailable if the master tenant registry could not
    be reached at all (Finding 3): that failure must never be treated the
    same as "no tenant matched". An individual tenant database being
    unreachable during the scan is still treated as "does not match" and the
    scan continues to the next tenant, since that tenant is one candidate
    among many here, not the sole candidate the caller named; this gap does
    not exist for resolve_tenant_by_hint, which targets exactly one tenant.
    """
    if not token:
        return None

    lookup_hash = token_lookup_hash(token)
    if _negative_cache_get(lookup_hash):
        return None

    for tenant_db in _active_tenant_db_names():  # may raise TenantLookupUnavailable
        if _lookup_token_in_tenant(tenant_db, lookup_hash):
            return tenant_db

    _negative_cache_put(lookup_hash)
    return None
