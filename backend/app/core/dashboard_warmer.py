"""Background warmer for the Command Center dashboard cache.

The `/analytics/dashboard` payload is Redis-cached with a short TTL. On a cold
cache (startup, or after the TTL lapses during a quiet spell) the first request
pays the full cold-aggregation cost. This loop recomputes each active tenant's
dashboard just under the TTL so the shared cache is always hot and no user ever
hits a cold miss.

Only meaningful with Redis (the cache is a no-op otherwise — nothing to warm),
and a cross-worker NX lock ensures just ONE worker warms per tick, so the DB
load is O(tenants) per interval regardless of WEB_CONCURRENCY.
"""
import asyncio
import logging

from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.config.database import MasterSessionLocal, get_tenant_engine
from app.core import cache
from app.models.master import Tenant

logger = logging.getLogger(__name__)

_LOCK_SUFFIX = "_warmlock"


def _active_tenant_db_names() -> list[str]:
    db = MasterSessionLocal()
    try:
        return [t.db_name for t in db.query(Tenant).filter(Tenant.is_active == True).all()]  # noqa: E712
    finally:
        db.close()


def _acquire_warm_lock(ttl_seconds: int) -> bool:
    """SET-NX a short-lived lock so only one worker warms per tick."""
    client = cache._get_client()
    if client is None:
        return False
    try:
        key = cache._build_key("analytics:dashboard", cache.GLOBAL_NS, _LOCK_SUFFIX)
        return bool(client.set(key, "1", nx=True, ex=max(1, ttl_seconds)))
    except Exception as exc:  # noqa: BLE001
        logger.debug("warm-lock acquire failed: %s", exc)
        return False


def _warm_once() -> int:
    """Recompute + cache the dashboard for every active tenant. Runs in a
    worker thread (sync SQLAlchemy). Returns how many tenants were warmed."""
    # Imported lazily to avoid any import-order coupling with the routes package.
    from app.routes.analytics import compute_dashboard, _DASHBOARD_PREFIX, _DASHBOARD_TTL

    warmed = 0
    for db_name in _active_tenant_db_names():
        try:
            Session = sessionmaker(bind=get_tenant_engine(db_name))
            session = Session()
            try:
                data = compute_dashboard(session)
                # Match the route's cache key exactly: suffix "_" (the decorator
                # default) + tenant = the DB name (the X-Tenant-ID value).
                cache.set(_DASHBOARD_PREFIX, "_", data, ttl_seconds=_DASHBOARD_TTL, tenant=db_name)
                warmed += 1
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001 — one bad tenant must not stop the rest
            logger.debug("dashboard warm failed for tenant %r: %s", db_name, exc)
    return warmed


async def dashboard_warm_loop() -> None:
    interval = max(5, int(settings.DASHBOARD_WARM_INTERVAL_SECONDS))
    lock_ttl = max(1, interval - 2)  # free again before the next tick
    logger.info("Dashboard cache warmer started (every %ss).", interval)
    try:
        while True:
            try:
                if _acquire_warm_lock(lock_ttl):
                    n = await asyncio.to_thread(_warm_once)
                    logger.debug("Dashboard warmer refreshed %d tenant(s).", n)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("dashboard warm loop tick error: %s", exc)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Dashboard cache warmer stopped.")
        raise
