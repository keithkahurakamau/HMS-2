import json
import logging

from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session, joinedload, selectinload
from app.config.database import get_db, get_master_db
from app.config.settings import settings
from app.models.master import SuperAdmin
from app.models.user import User, Role, Permission, UserPermissionOverride

logger = logging.getLogger(__name__)


# DB-001: optional Redis-backed permission cache keyed on the access token's
# jti, with TTL <= access-token lifetime. Saves three queries per request
# (User + Role + Permission joins). Falls back to direct DB lookup when
# REDIS_URL is unset or the Redis call fails.
_perm_cache_client = None
if settings.REDIS_URL:
    try:
        import redis  # type: ignore

        _perm_cache_client = redis.Redis.from_url(
            settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5,
        )
    except Exception:  # noqa: BLE001 — Redis is optional
        logger.warning("Permission cache: failed to construct Redis client; disabled.")
        _perm_cache_client = None


def _cache_get(jti: str):
    if not _perm_cache_client or not jti:
        return None
    try:
        raw = _perm_cache_client.get(f"perm:{jti}")
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def _cache_put(jti: str, value: dict) -> None:
    if not _perm_cache_client or not jti:
        return
    try:
        _perm_cache_client.setex(
            f"perm:{jti}",
            max(60, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
            json.dumps(value),
        )
    except Exception:  # noqa: BLE001
        pass


# H-2: per-tenant permission epoch. The per-jti cache above means a permission
# revocation, role change, or user deactivation otherwise only takes effect when
# the cached envelope expires (up to one access-token lifetime) — "revoke now"
# didn't mean now, and a cache hit returned before the is_active check. We stamp
# each envelope with the tenant's current epoch; any write that changes a user's
# effective permissions / role / role-permissions / active state bumps the
# epoch, so the next request sees a stale stamp, misses the cache, and re-runs
# the live lookup (which re-checks is_active). Bumps/reads are best-effort: if
# Redis is down the cache itself is disabled, so there is no staleness to fix.
def _perm_epoch_key(tenant: str) -> str:
    return f"permepoch:{tenant or '_'}"


def _get_perm_epoch(tenant: str) -> int:
    if not _perm_cache_client:
        return 0
    try:
        raw = _perm_cache_client.get(_perm_epoch_key(tenant))
        return int(raw) if raw else 0
    except Exception:  # noqa: BLE001
        return 0


def bump_perm_epoch(tenant: str | None) -> None:
    """Invalidate every cached permission envelope for a tenant. Call after any
    write that changes a user's effective permissions, role, a role's
    permissions, or active state (H-2)."""
    if not _perm_cache_client or not tenant:
        return
    try:
        _perm_cache_client.incr(_perm_epoch_key(tenant))
    except Exception:  # noqa: BLE001
        pass


def resolve_effective_permissions(db: Session, user: User) -> list[str]:
    """Compute the user's effective permission set.

    Effective set = (role permissions ∪ explicit grants) − explicit revokes.
    Returns sorted permission codenames so callers and the UI see a stable
    order.
    """
    role_perms: set[str] = set()
    if user.role and user.role.permissions:
        role_perms = {p.codename for p in user.role.permissions}

    overrides = (
        db.query(UserPermissionOverride, Permission.codename)
        .join(Permission, Permission.permission_id == UserPermissionOverride.permission_id)
        .filter(UserPermissionOverride.user_id == user.user_id)
        .all()
    )
    grants = {codename for ovr, codename in overrides if ovr.granted}
    revokes = {codename for ovr, codename in overrides if not ovr.granted}

    return sorted((role_perms | grants) - revokes)


def require_superadmin(request: Request, db: Session = Depends(get_master_db)) -> dict:
    """Authenticates a platform-level superadmin via HttpOnly cookie.

    The cookie 'superadmin_token' is set by POST /api/public/superadmin/login
    and lives outside JS reach, so an XSS in the platform console can't
    exfiltrate the JWT (the old implementation kept it in localStorage where
    any compromised dependency could read window.localStorage and steal it).
    Superadmin tokens are not tenant-scoped: they carry role='superadmin' and
    grant platform-level powers (tenant provisioning, hospital suspension).
    """
    token = request.cookies.get("superadmin_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Superadmin authentication required",
        )

    try:
        # AUTH-002: superadmin tokens don't carry a tenant audience — disable
        # audience verification here. The role+admin_id checks below still
        # ensure the token can't be substituted for a tenant access token.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired superadmin token",
        )

    if payload.get("role") != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin role required")

    admin_id = payload.get("user_id")
    if admin_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed superadmin token")

    admin = db.query(SuperAdmin).filter(SuperAdmin.admin_id == admin_id).first()
    if not admin or admin.is_active is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Superadmin account not found or disabled")

    return {"admin_id": admin.admin_id, "email": admin.email, "full_name": admin.full_name}

def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """
    Extracts the JWT access token from the HttpOnly cookie.
    """
    # Audit SEC-003: previously every auth event was emitted via print() to
    # stdout — including the decoded JWT payload, tenant IDs, and "user not
    # found" outcomes. On Render that stdout is captured by the platform log
    # store, so any operator with log-read access could harvest live JWT
    # claims. We now log at debug/warning with no token contents.
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. No access token cookie found."
        )

    if token.startswith("Bearer "):
        token = token.split("Bearer ")[1]

    try:
        # AUTH-002: tokens minted post-upgrade carry aud=tenant_id. Old tokens
        # (pre-rollout) don't, so we verify aud manually below — disabling
        # the library check lets both shapes through during the rollover.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
        )
        user_id = payload.get("user_id") or payload.get("sub")
        token_tenant_id = payload.get("tenant_id")

        if user_id is None or token_tenant_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        # If the token has an aud claim (new format), it must equal tenant_id —
        # belt-and-braces against future code that mints with the wrong scope.
        aud = payload.get("aud")
        if aud and aud != token_tenant_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Audience mismatch")

        request_tenant_id = request.headers.get("X-Tenant-ID")
        if request_tenant_id != token_tenant_id:
            # Cross-tenant attempts are interesting; log the user id but never
            # the raw tenant strings (they can carry inferable schema hints).
            logger.warning("Cross-tenant access denied for user_id=%s", user_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access strictly forbidden")

    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # DB-001: cache the full identity envelope against the JWT's jti so a
    # burst of authenticated requests doesn't reissue the 3-query lookup.
    jti = payload.get("jti")
    cached = _cache_get(jti) if jti else None
    # H-2: only trust the cache while its epoch stamp still matches the tenant's
    # current epoch. A revocation/deactivation bumps the epoch, forcing a fresh
    # lookup (and thus a live is_active re-check) here.
    if cached is not None and cached.get("_epoch") == _get_perm_epoch(token_tenant_id):
        return cached

    # Verify user exists and fetch live permissions. DB-001: joinedload the
    # role + its permissions in a single query so resolve_effective_permissions
    # doesn't trigger a second lazy SELECT for `user.role.permissions`.
    user = (
        db.query(User)
        .options(joinedload(User.role).selectinload(Role.permissions))
        .filter(User.user_id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer active")

    # Effective permissions apply per-user overrides on top of the role's
    # baseline grants, so admins can fine-tune a single user without minting
    # a new role for the exception.
    permissions = resolve_effective_permissions(db, user)

    envelope = {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role.name if user.role else "UNKNOWN",
        "full_name": user.full_name,
        "permissions": permissions,
        "_epoch": _get_perm_epoch(token_tenant_id),
    }
    if jti:
        _cache_put(jti, envelope)
    return envelope

class RequirePermission:
    """
    Dependency class to enforce RBAC on endpoints.
    Usage:
        Depends(RequirePermission("patients:write"))               # single
        Depends(RequirePermission("payhero:manage", "mpesa:manage"))  # any-of

    Any-of semantics let us add a new codename without immediately stranding
    users whose role still grants the old one (e.g. the Pay Hero swap renames
    ``mpesa:manage`` → ``payhero:manage`` via migration ``aa2b7c3d8e91``, but
    cached JWTs and un-migrated tenants keep working until they roll over).
    """
    def __init__(self, *required_permissions: str):
        if not required_permissions:
            raise ValueError("RequirePermission requires at least one codename")
        self.required_permissions: tuple[str, ...] = required_permissions

    def __call__(self, current_user: dict = Depends(get_current_user)):
        held = set(current_user["permissions"])
        if not any(p in held for p in self.required_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Operation not permitted. Requires "
                    f"{' or '.join(repr(p) for p in self.required_permissions)}"
                ),
            )
        return current_user