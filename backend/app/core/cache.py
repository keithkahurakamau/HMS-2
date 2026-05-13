"""
Per-tenant Redis cache for hot read paths.

Design rules:
  * Cache keys are namespaced by tenant. Cross-tenant key collisions would be
    a data-leak bug, so every key is prefixed with the X-Tenant-ID header
    value. Background callers without a tenant context use the "_global_"
    namespace.
  * TTL is mandatory. Callers pass a `ttl_seconds` — no infinite caches.
  * Failures degrade gracefully. If Redis is unreachable, the wrapped
    function is invoked normally and we log a warning. The application
    must keep serving traffic even when the cache is sick.
  * Values are JSON-encoded. Pydantic models / SQLAlchemy rows must be
    serialised to dicts by the caller before they reach the cache.
"""
from __future__ import annotations

import functools
import inspect
import json
import logging
from typing import Any, Callable, Optional

from fastapi import Request

from app.config.settings import settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "hms:cache:"
GLOBAL_NS = "_global_"

# Lazy singleton — created on first use so apps without REDIS_URL configured
# never pay the connection cost. Stored module-level so all routers share it.
_client = None
_client_failed = False  # one-shot flag — stop spamming logs after first failure


def _get_client():
    """Return a sync Redis client or None if Redis isn't usable.

    On first call this opens a connection and PINGs to verify reachability.
    Subsequent calls reuse the client. If the initial connect fails we mark
    the cache disabled for the process lifetime — periodic retry is the
    operator's job (restart the service after Redis recovers).
    """
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    if not settings.REDIS_URL:
        return None
    try:
        import redis  # type: ignore
        client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2)
        client.ping()
        _client = client
        logger.info("Cache backend ready: %s", settings.REDIS_URL)
        return _client
    except Exception as exc:  # noqa: BLE001
        _client_failed = True
        logger.warning("Cache disabled — Redis unreachable: %s", exc)
        return None


def _tenant_from_request(request: Optional[Request]) -> str:
    """Extract the tenant namespace for a request, falling back to global."""
    if request is None:
        return GLOBAL_NS
    return request.headers.get("X-Tenant-ID") or GLOBAL_NS


def _build_key(prefix: str, tenant: str, suffix: str) -> str:
    return f"{KEY_PREFIX}{tenant}:{prefix}:{suffix}"


# ─── Low-level helpers ──────────────────────────────────────────────────────
def get(prefix: str, suffix: str, tenant: Optional[str] = None) -> Any:
    """Fetch a cached value. Returns None on miss or on any failure."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(_build_key(prefix, tenant or GLOBAL_NS, suffix))
        return json.loads(raw) if raw is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache.get failed for %s/%s: %s", prefix, suffix, exc)
        return None


def set(prefix: str, suffix: str, value: Any, ttl_seconds: int, tenant: Optional[str] = None) -> None:  # noqa: A001
    """Write a value with a TTL. Silently no-ops if the cache is down."""
    client = _get_client()
    if client is None:
        return
    try:
        client.set(
            _build_key(prefix, tenant or GLOBAL_NS, suffix),
            json.dumps(value, default=str),
            ex=ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache.set failed for %s/%s: %s", prefix, suffix, exc)


def invalidate(prefix: str, suffix: str, tenant: Optional[str] = None) -> None:
    """Drop a single key."""
    client = _get_client()
    if client is None:
        return
    try:
        client.delete(_build_key(prefix, tenant or GLOBAL_NS, suffix))
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache.invalidate failed for %s/%s: %s", prefix, suffix, exc)


def invalidate_prefix(prefix: str, tenant: Optional[str] = None) -> int:
    """Drop every key under a prefix (per tenant). Uses SCAN, not KEYS, so
    it's safe to call against a busy Redis instance. Returns the number of
    keys removed."""
    client = _get_client()
    if client is None:
        return 0
    pattern = _build_key(prefix, tenant or GLOBAL_NS, "*")
    removed = 0
    try:
        for key in client.scan_iter(match=pattern, count=200):
            try:
                client.delete(key)
                removed += 1
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache.invalidate_prefix failed for %s: %s", prefix, exc)
    return removed


# ─── Decorator for route-level caching ──────────────────────────────────────
def cached(prefix: str, ttl_seconds: int, key_fn: Optional[Callable[..., str]] = None):
    """Decorator that caches a FastAPI route handler per tenant.

    The wrapped function MUST accept a `request: Request` parameter (FastAPI
    injects it). The cache key is composed of the tenant header + the
    function name + a stringified key_fn result (default: empty suffix, so
    the handler effectively caches one value per tenant).

    Example:
        @router.get("/dashboard")
        @cached("analytics:dashboard", ttl_seconds=30)
        def dashboard(request: Request, db: Session = Depends(get_db)):
            ...

    Notes:
      * Only return values that JSON-serialise cleanly. SQLAlchemy rows do
        not — convert to dicts first.
      * Mutations to the underlying data MUST call invalidate_prefix() or
        invalidate() to avoid stale reads. Cache TTL is the safety net,
        not the contract.
    """
    def decorator(fn: Callable):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                request = _extract_request(args, kwargs)
                tenant = _tenant_from_request(request)
                suffix = (key_fn(*args, **kwargs) if key_fn else "_")
                hit = get(prefix, suffix, tenant)
                if hit is not None:
                    return hit
                result = await fn(*args, **kwargs)
                set(prefix, suffix, result, ttl_seconds, tenant)
                return result
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            request = _extract_request(args, kwargs)
            tenant = _tenant_from_request(request)
            suffix = (key_fn(*args, **kwargs) if key_fn else "_")
            hit = get(prefix, suffix, tenant)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            set(prefix, suffix, result, ttl_seconds, tenant)
            return result
        return sync_wrapper

    return decorator


def _extract_request(args: tuple, kwargs: dict) -> Optional[Request]:
    """Pull the FastAPI Request out of a handler's call args."""
    for v in args:
        if isinstance(v, Request):
            return v
    for v in kwargs.values():
        if isinstance(v, Request):
            return v
    return None
