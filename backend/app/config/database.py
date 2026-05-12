"""
Multi-tenant database orchestration.

Architecture:
  - Master DB ("hms_master")  — superadmins + tenant registry. Single per platform.
  - Tenant DBs               — one PostgreSQL database per hospital. Schema is
                               identical across tenants; data is fully isolated.

Per-tenant SQLAlchemy engines are cached in a bounded LRU so a deployment with
hundreds of tenants does not exhaust connection-pool memory. All engines apply
DB pool sizing from settings, which is intended to sit behind PgBouncer in
production. See `docs/DEPLOYMENT.md` for the production-ready PgBouncer recipe.
"""
from collections import OrderedDict
from threading import Lock
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from fastapi import Request

from app.config.settings import settings


def _normalize_db_url(raw: str) -> str:
    """Coerce a raw DATABASE_URL into a form SQLAlchemy 2.x accepts.

    Common gotchas this catches:
      * Render/Heroku hand out URLs starting with ``postgres://`` — SQLAlchemy
        2.x rejects that scheme with "Can't load plugin: postgres". Rewrite
        to ``postgresql://``.
      * If someone pastes the *dashboard* URL by mistake (``https://...``),
        fail loudly with a useful error instead of the cryptic
        "Can't load plugin: https".
    """
    if not raw:
        raise RuntimeError("DATABASE_URL is empty — set it on the host environment.")
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    if raw.startswith(("postgresql://", "postgresql+")):
        return raw
    raise RuntimeError(
        "DATABASE_URL must start with postgresql:// (or postgres://). "
        f"Got scheme: {raw.split('://', 1)[0]!r}. "
        "Did you paste the dashboard/web URL instead of the connection string?"
    )


DATABASE_URL = _normalize_db_url(settings.DATABASE_URL)


def _engine_kwargs() -> dict:
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
        "pool_pre_ping": True,
    }


# --- Default + Master engines (always-on) -----------------------------
default_engine = create_engine(DATABASE_URL, **_engine_kwargs())
DefaultSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=default_engine)

_master_db_url = DATABASE_URL.rsplit('/', 1)[0] + "/hms_master"
master_engine = create_engine(_master_db_url, **_engine_kwargs())
MasterSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=master_engine)

Base = declarative_base()


def get_master_db():
    """Yields a session to the central hms_master database."""
    db = MasterSessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Tenant engine cache (LRU + thread-safe) --------------------------
_tenant_engines_lock = Lock()
tenant_engines: OrderedDict = OrderedDict()


def _evict_engine_if_needed() -> None:
    while len(tenant_engines) > settings.TENANT_ENGINE_CACHE_SIZE:
        _, oldest_engine = tenant_engines.popitem(last=False)
        try:
            oldest_engine.dispose()
        except Exception:
            pass


def get_tenant_engine(tenant_db_name: str):
    """Returns a SQLAlchemy engine bound to the tenant's database.

    Engines are cached behind a bounded LRU so memory + connection pools do not
    grow without limit on platforms with hundreds of tenants. Eviction calls
    .dispose() on the displaced engine so its pool is released cleanly.
    """
    with _tenant_engines_lock:
        if tenant_db_name in tenant_engines:
            tenant_engines.move_to_end(tenant_db_name)
            return tenant_engines[tenant_db_name]

        base_url = DATABASE_URL.rsplit('/', 1)[0]
        db_url = f"{base_url}/{tenant_db_name}"

        engine = create_engine(db_url, **_engine_kwargs())
        tenant_engines[tenant_db_name] = engine
        _evict_engine_if_needed()
        return engine


def get_db(request: Request = None):
    """Yields a SQLAlchemy session bound to the caller's tenant DB.

    Tenant routing is keyed off the ``X-Tenant-ID`` request header. Earlier
    versions of this function silently fell back to the DB named in
    ``DATABASE_URL`` (typically ``hms_master``) when the header was absent —
    that defaulted unauthenticated requests to a database that has none of
    the tenant tables, producing cryptic 500s like
    ``relation "patients" does not exist``. The fallback is gone: requests
    without ``X-Tenant-ID`` get a 400 with a clear message so the caller
    can route through the hospital picker.

    Background callers (CLI scripts, tests, lifespan tasks) pass
    ``request=None`` and get the default session as before.
    """
    from fastapi import HTTPException, status

    if not request:
        db = DefaultSessionLocal()
        try:
            yield db
        finally:
            db.close()
        return

    tenant_db_name = request.headers.get("X-Tenant-ID")
    if not tenant_db_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required for this endpoint.",
        )

    engine = get_tenant_engine(tenant_db_name)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
