from datetime import datetime, timedelta, timezone
import json
import logging
import secrets
import string

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, sessionmaker
from jose import jwt
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional, Dict, Any
import re

from app.config.database import get_master_db, get_tenant_engine, invalidate_tenant_registry
from app.utils.audit import log_audit
from app.utils.blind_index import phone_bidx
from app.config.settings import settings
from app.core.dependencies import require_superadmin, optional_superadmin
from app.core.limiter import limiter
from app.models.master import Tenant, SuperAdmin
from app.models.support import SupportTicket, SupportMessage
from app.models.patient import Patient
from app.models.user import User, Role
from app.core.security import get_password_hash, verify_password, create_tokens
from app.services.tenant_provisioning import provision_tenant
from app.services.email_service import email_service
from app.services.email_templates import render_contact_message
from app.services.webhook_security import verify_svix_webhook
from app.services.email_suppression import process_event as process_email_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["Public Portal"])


def _generate_temp_password(length: int = 14) -> str:
    """Cryptographically-strong temporary password that satisfies the app's
    password policy (>=8 chars, upper, lower, digit, special). Used only as a
    one-time credential the superadmin relays to a locked-out user — it is
    hashed (Argon2id) before storage and the user is forced to change it on
    next login. The plaintext is returned to the caller exactly once and is
    never persisted in clear.
    """
    rng = secrets.SystemRandom()
    specials = "!@#$%^&*"
    pool = string.ascii_letters + string.digits + specials
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(specials),
    ]
    rest = [secrets.choice(pool) for _ in range(max(length, 8) - len(required))]
    chars = required + rest
    rng.shuffle(chars)
    return "".join(chars)


def _is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.now(timezone.utc))


def _serialize_user(t: Tenant, u: User, role_name: Optional[str]) -> Dict[str, Any]:
    """Safe, plaintext-free projection of a tenant user for the superadmin
    console. Deliberately omits ``hashed_password`` — passwords are one-way
    hashed and must never be exposed through the API surface.
    """
    return {
        "tenant_id": t.tenant_id,
        "tenant_name": t.name,
        "tenant_db": t.db_name,
        "user_id": u.user_id,
        "email": u.email,
        "full_name": u.full_name,
        "role": role_name,
        "specialization": u.specialization,
        "is_active": bool(u.is_active),
        "must_change_password": bool(u.must_change_password),
        "is_locked": _is_locked(u),
        "locked_until": u.locked_until.isoformat() if u.locked_until else None,
        "failed_login_attempts": u.failed_login_attempts or 0,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


def _decode_json(value: Optional[str], default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _serialize_tenant(t: Tenant, *, include_flags: bool = True) -> Dict[str, Any]:
    base = {
        "id": f"tenant_{t.tenant_id}",
        "tenant_id": t.tenant_id,
        "name": t.name,
        "domain": t.domain,
        "db_name": t.db_name,
        "theme_color": t.theme_color,
        "is_premium": t.is_premium,
        "is_active": t.is_active,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if include_flags:
        base["feature_flags"] = _decode_json(t.feature_flags, {})
        base["plan_limits"] = _decode_json(t.plan_limits, {})
        base["notes"] = t.notes
    return base


@router.get("/superadmin/overview", dependencies=[Depends(require_superadmin)])
def get_platform_overview(master_db: Session = Depends(get_master_db)):
    """Aggregated platform telemetry for the superadmin Global Overview page.

    Returns:
      * tenant counts (total, active, suspended, premium, standard)
      * platform MRR + ARR (computed off the same tier prices the billing UI
        applies — see TIER_PRICING below)
      * 30-day growth (tenants provisioned in the trailing window)
      * total active users across every active tenant DB (best-effort —
        failures per tenant are surfaced under ``user_count_errors`` so the
        UI can warn instead of silently under-counting)
      * the 5 most recently provisioned tenants
      * open ticket count (so the overview can hint at queue pressure)

    All work happens behind ``require_superadmin``. The cross-tenant user
    count holds a session per tenant DB just long enough for a single
    aggregate query and disposes it.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text
    from app.models.support import SupportTicket
    from app.config.database import get_tenant_engine

    # Tier pricing mirrors the frontend PlatformBilling client constants.
    # When the canonical pricing moves into a config table this constant
    # should be replaced with a DB lookup.
    TIER_PRICING = {"premium": 49500, "standard": 18500}

    tenants = master_db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    active = [t for t in tenants if t.is_active]
    suspended = [t for t in tenants if not t.is_active]
    premium_count = sum(1 for t in active if t.is_premium)
    standard_count = len(active) - premium_count

    mrr = premium_count * TIER_PRICING["premium"] + standard_count * TIER_PRICING["standard"]

    # 30-day growth — tenants whose created_at falls inside the trailing window.
    # We compare in UTC; the column has timezone=True so the math is honest.
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    recent_window = [t for t in tenants if t.created_at and t.created_at >= cutoff]
    prior_total = max(len(tenants) - len(recent_window), 1)
    growth_pct = round((len(recent_window) / prior_total) * 100, 1)

    # Aggregate users across every active tenant DB. Best-effort: one tenant
    # failing must not nuke the whole dashboard. Errors are returned so the UI
    # can render a "partial data" notice.
    total_users = 0
    user_count_errors: list[dict] = []
    for t in active:
        try:
            engine = get_tenant_engine(t.db_name)
            with engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM users WHERE is_active = true")).scalar()
                total_users += int(count or 0)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            # Full exception text stays in server logs only; the API surface
            # gets a sanitized indicator so we don't leak stack-trace or
            # driver-internal details to the superadmin UI (CodeQL alert #6).
            logger.warning("overview: user count failed for %s — %s", t.db_name, exc, exc_info=True)
            user_count_errors.append({"tenant": t.db_name, "error": "fetch_failed"})

    open_tickets = master_db.query(SupportTicket).filter(SupportTicket.status == "Open").count()
    in_progress_tickets = master_db.query(SupportTicket).filter(SupportTicket.status == "In Progress").count()

    recent_tenants = [
        {
            "tenant_id": t.tenant_id,
            "name": t.name,
            "domain": t.domain,
            "is_premium": bool(t.is_premium),
            "is_active": bool(t.is_active),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tenants[:5]
    ]

    return {
        "tenants": {
            "total": len(tenants),
            "active": len(active),
            "suspended": len(suspended),
            "premium": premium_count,
            "standard": standard_count,
        },
        "users": {
            "total_active": total_users,
            "errors": user_count_errors,
        },
        "revenue": {
            "mrr": mrr,
            "arr": mrr * 12,
            "currency": "KES",
        },
        "growth": {
            "window_days": 30,
            "new_tenants": len(recent_window),
            "percent": growth_pct,
        },
        "tickets": {
            "open": open_tickets,
            "in_progress": in_progress_tickets,
        },
        "recent_tenants": recent_tenants,
    }


@router.get("/superadmin/module-catalogue", dependencies=[Depends(require_superadmin)])
def get_module_catalogue():
    """Returns the canonical list of gateable modules for the package editor.

    The Tenants Manager uses this to render a curated checklist instead of
    free-text flag keys (which were silently mis-spellable and never gated
    anything). Always-on modules are marked so the UI can lock their
    toggles.
    """
    from app.core.modules import MODULES
    return [
        {
            "key": m.key,
            "label": m.label,
            "description": m.description,
            "always_on": m.always_on,
            "default_enabled": m.default_enabled,
        }
        for m in MODULES
    ]


@router.get("/hospitals")
def get_available_hospitals(
    include_inactive: bool = False,
    db: Session = Depends(get_master_db),
    admin=Depends(optional_superadmin),
):
    """Returns tenants from the master registry.

    This endpoint is public (the portal hospital picker needs it before any
    login), so anonymous callers get an active-only list with *minimal*
    fields. The commercial internals (feature_flags, plan_limits, operator
    notes) and suspended tenants are only revealed to an authenticated
    superadmin (Tenants Manager). Without this split anyone could enumerate
    every hospital's plan and private operator notes. (SEC: info disclosure.)
    """
    is_admin = admin is not None
    query = db.query(Tenant)
    # Only a superadmin may list suspended tenants.
    if not (include_inactive and is_admin):
        query = query.filter(Tenant.is_active == True)  # noqa: E712
    tenants = query.order_by(Tenant.name).all()
    return [_serialize_tenant(t, include_flags=is_admin) for t in tenants]


class TenantCreate(BaseModel):
    name: str
    domain: str
    db_name: str
    admin_email: EmailStr
    admin_full_name: str
    theme_color: str = "blue"
    is_premium: bool = False

    @field_validator("db_name")
    @classmethod
    def db_name_safe(cls, v: str) -> str:
        # PostgreSQL identifier rules + our own conservative subset.
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,62}", v):
            raise ValueError("db_name must start with a letter, be lowercase, and use only [a-z0-9_]")
        return v


@router.post("/hospitals", dependencies=[Depends(require_superadmin)])
def provision_hospital(tenant: TenantCreate, db: Session = Depends(get_master_db)):
    """
    Provisions a brand-new hospital tenant end-to-end:
      - Creates the PostgreSQL database
      - Builds the schema
      - Seeds RBAC roles + permissions
      - Creates the Admin account with a one-time temporary password

    The temp password is returned in the response *once*. The operator must
    deliver it to the new admin via a secure channel; we do not persist it.
    """
    try:
        new_tenant, temp_password = provision_tenant(
            db,
            name=tenant.name,
            domain=tenant.domain,
            db_name=tenant.db_name,
            admin_email=tenant.admin_email,
            admin_full_name=tenant.admin_full_name,
            theme_color=tenant.theme_color,
            is_premium=tenant.is_premium,
        )
    except ValueError as e:
        # 409 for "already exists" so the UI can show a clean conflict message
        # rather than the generic 500 the global handler would produce.
        msg = str(e)
        code = status.HTTP_409_CONFLICT if "already exists" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return {
        "message": "Tenant provisioned. Database created, schema applied, admin seeded.",
        "tenant_id": new_tenant.tenant_id,
        "db_name": new_tenant.db_name,
        "admin_email": tenant.admin_email,
        "admin_temp_password": temp_password,
        "warning": (
            "This temporary password is shown once. Deliver it to the admin securely. "
            "The admin will be forced to change it on first login."
        ),
    }


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    theme_color: Optional[str] = None
    is_premium: Optional[bool] = None
    is_active: Optional[bool] = None
    feature_flags: Optional[Dict[str, Any]] = None
    plan_limits: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


@router.patch("/hospitals/{tenant_id}", dependencies=[Depends(require_superadmin)])
def update_tenant(tenant_id: int, payload: TenantUpdate, db: Session = Depends(get_master_db)):
    """Updates a tenant's display attributes, suspension state, or flexible
    config. ``db_name`` stays immutable — renaming a database is destructive
    and requires explicit data migration.
    """
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    update = payload.model_dump(exclude_unset=True)
    flags_changed = "feature_flags" in update
    for field, value in update.items():
        if field in ("feature_flags", "plan_limits"):
            setattr(tenant, field, json.dumps(value) if value is not None else None)
        else:
            setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    # Tenant entitlements are cached in Redis (~60s) so the module gate doesn't
    # query the master DB on every request. When a superadmin toggles a
    # module, drop the cached entry so the next request reflects the change.
    if flags_changed and tenant.db_name:
        try:
            from app.core.modules import invalidate_tenant_flags_cache
            invalidate_tenant_flags_cache(tenant.db_name)
        except Exception:  # noqa: BLE001 — never fail the write on a cache miss
            pass
    # C-2: a suspension (is_active flip) or rename must drop the cached
    # registry verdict so get_db stops admitting the tenant before the TTL.
    if tenant.db_name and ("is_active" in update or "db_name" in update):
        try:
            invalidate_tenant_registry(tenant.db_name)
        except Exception:  # noqa: BLE001
            pass
    return _serialize_tenant(tenant)


# ─────────────────────────────────────────────────────────────────────────────
# Superadmin read-only patient browser (cross-tenant)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/superadmin/patients", dependencies=[Depends(require_superadmin)])
def list_patients_across_tenants(
    tenant_id: Optional[int] = Query(default=None, description="Restrict to one tenant"),
    search: Optional[str] = Query(default=None, description="Substring filter on name / OP# / phone"),
    limit_per_tenant: int = Query(default=50, ge=1, le=500),
    master_db: Session = Depends(get_master_db),
):
    """Aggregates a patient summary across every active tenant database.

    Read-only: no mutation endpoints are exposed. Each tenant's DB is queried
    in its own session so a single bad tenant can't poison the response.
    Failures per tenant are reported in the response under ``errors``.
    """
    query = master_db.query(Tenant).filter(Tenant.is_active == True)
    if tenant_id:
        query = query.filter(Tenant.tenant_id == tenant_id)
    tenants = query.all()

    aggregated: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    needle = (search or "").strip().lower()

    for t in tenants:
        try:
            engine = get_tenant_engine(t.db_name)
            TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            session = TenantSession()
            try:
                q = session.query(Patient).filter(Patient.is_active == True)
                if needle:
                    # M-1 phase 2: telephone_1 is encrypted — match it by blind
                    # index (exact). Name + OP number stay substring.
                    conds = [
                        Patient.surname.ilike(f"%{needle}%"),
                        Patient.other_names.ilike(f"%{needle}%"),
                        Patient.outpatient_no.ilike(f"%{needle}%"),
                    ]
                    ph = phone_bidx(needle)
                    if ph:
                        conds.append(Patient.telephone_1_bidx == ph)
                    q = q.filter(or_(*conds))
                rows = q.order_by(Patient.registered_on.desc()).limit(limit_per_tenant).all()
                for p in rows:
                    aggregated.append({
                        "tenant_id": t.tenant_id,
                        "tenant_name": t.name,
                        "tenant_db": t.db_name,
                        "patient_id": p.patient_id,
                        "outpatient_no": p.outpatient_no,
                        "surname": p.surname,
                        "other_names": p.other_names,
                        "sex": p.sex,
                        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
                        "telephone_1": p.telephone_1,
                        "town": p.town,
                        "blood_group": p.blood_group,
                        "registered_on": p.registered_on.isoformat() if p.registered_on else None,
                    })
            finally:
                session.close()
        except Exception as exc:
            # Full exception text is for operators (server logs); the response
            # body returns a sanitized marker so we don't surface stack traces
            # or driver-internal strings to the superadmin UI (CodeQL alert #5).
            logger.warning("Failed to read patients from tenant %s: %s", t.db_name, exc, exc_info=True)
            errors.append({"tenant_id": str(t.tenant_id), "tenant_db": t.db_name, "error": "fetch_failed"})

    return {
        "patients": aggregated,
        "count": len(aggregated),
        "tenants_scanned": len(tenants),
        "errors": errors,
    }


# Most-sensitive identifiers we do NOT blanket-reflect in the cross-tenant
# superadmin read (H-5): the national ID is masked to its last 4 digits, and
# password material can never appear in an API surface.
_PATIENT_SENSITIVE_COLS = {"id_number"}
_PATIENT_NEVER_COLS = {"hashed_password", "password", "portal_password_hash"}


def _mask_tail(value: Any, keep: int = 4) -> Optional[str]:
    s = str(value or "")
    if not s:
        return None
    return ("•" * max(len(s) - keep, 0)) + s[-keep:]


@router.get("/superadmin/patients/{tenant_id}/{patient_id}")
def get_patient_detail(
    tenant_id: int,
    patient_id: int,
    request: Request,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    """Returns a single patient's profile (read-only, cross-tenant superadmin).

    H-5: this is a cross-tenant PHI read by a platform superadmin. Every access
    is recorded in the tenant DB's immutable audit log (KDPA accountability),
    and the most sensitive identifier (national ID) is masked rather than
    blanket-reflected.
    """
    t = master_db.query(Tenant).filter(Tenant.tenant_id == tenant_id, Tenant.is_active == True).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive.")

    engine = get_tenant_engine(t.db_name)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TenantSession()
    try:
        p = session.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Patient not found.")

        out: Dict[str, Any] = {
            "tenant": _serialize_tenant(t, include_flags=False),
        }
        for col in p.__table__.columns.keys():
            if col in _PATIENT_NEVER_COLS:
                continue
            val = getattr(p, col, None)
            if col in _PATIENT_SENSITIVE_COLS:
                out[col] = _mask_tail(val)
                continue
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            out[col] = val

        # H-5: durable, per-access record in the tenant DB. The superadmin is
        # not a tenant user, so user_id is NULL (AuditLog.user_id is nullable,
        # ON DELETE SET NULL) and the platform identity rides in new_value.
        try:
            log_audit(
                session,
                user_id=None,
                action="READ",
                entity_type="Patient",
                entity_id=str(patient_id),
                new_value={
                    "superadmin_access": True,
                    "admin_id": admin.get("admin_id"),
                    "admin_email": admin.get("email"),
                    "access_reason": "superadmin cross-tenant patient detail",
                },
                ip_address=request.client.host if request.client else None,
            )
            session.commit()
        except Exception:  # noqa: BLE001 — never fail the read on an audit hiccup
            session.rollback()
            logger.exception("H-5: failed to write superadmin patient-read audit (tenant=%s)", t.db_name)

        # The access is recorded in the durable, access-controlled DB audit row
        # above (actor + tenant + patient). We intentionally do NOT echo the
        # patient id / tenant to stdout — keeping PHI-adjacent identifiers out
        # of captured logs (SEC-003 ethos).
        return out
    finally:
        session.close()


# ────────────────────────────────────────────────────────────────────────────
#  Superadmin cross-tenant User Management.
#
#  SECURE BY DESIGN: there is NO endpoint that returns a user's password.
#  Passwords are Argon2id-hashed (one-way) — they cannot be read back. The
#  superadmin recovery model is *reset, not reveal*: issue a one-time temp
#  password (forced change on next login), or lock/unlock/disable an account.
#  Every mutating action is logged with the acting superadmin's identity.
# ────────────────────────────────────────────────────────────────────────────

@router.get("/superadmin/users", dependencies=[Depends(require_superadmin)])
def list_users_across_tenants(
    tenant_id: Optional[int] = Query(default=None, description="Restrict to one tenant"),
    search: Optional[str] = Query(default=None, description="Substring filter on name / email / role"),
    limit_per_tenant: int = Query(default=100, ge=1, le=500),
    master_db: Session = Depends(get_master_db),
):
    """Aggregates staff users across every active tenant database.

    Read-only listing. Passwords are NEVER included — only safe metadata
    (status, lockout, must-change flag, timestamps). One session per tenant DB
    so a single bad tenant can't poison the whole response; per-tenant failures
    are surfaced under ``errors``.
    """
    query = master_db.query(Tenant).filter(Tenant.is_active == True)  # noqa: E712
    if tenant_id:
        query = query.filter(Tenant.tenant_id == tenant_id)
    tenants = query.all()

    aggregated: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    needle = (search or "").strip().lower()

    for t in tenants:
        try:
            engine = get_tenant_engine(t.db_name)
            TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            session = TenantSession()
            try:
                q = session.query(User, Role.name).outerjoin(Role, User.role_id == Role.role_id)
                if needle:
                    q = q.filter(
                        (User.full_name.ilike(f"%{needle}%"))
                        | (User.email.ilike(f"%{needle}%"))
                        | (Role.name.ilike(f"%{needle}%"))
                    )
                rows = q.order_by(User.full_name.asc()).limit(limit_per_tenant).all()
                for u, role_name in rows:
                    aggregated.append(_serialize_user(t, u, role_name))
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            logger.warning("Failed to read users from tenant %s: %s", t.db_name, exc, exc_info=True)
            errors.append({"tenant_id": str(t.tenant_id), "tenant_db": t.db_name, "error": "fetch_failed"})

    return {
        "users": aggregated,
        "count": len(aggregated),
        "tenants_scanned": len(tenants),
        "errors": errors,
    }


def _resolve_active_tenant(master_db: Session, tenant_id: int) -> Tenant:
    t = master_db.query(Tenant).filter(Tenant.tenant_id == tenant_id, Tenant.is_active == True).first()  # noqa: E712
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found or inactive.")
    return t


class SuperadminPasswordReset(BaseModel):
    # Optional admin-chosen password. If omitted, a strong temp password is
    # generated and returned once. Either way the user must change it at login.
    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def _min_length(cls, v: Optional[str]):
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


@router.post("/superadmin/users/{tenant_id}/{user_id}/reset-password", dependencies=[Depends(require_superadmin)])
def superadmin_reset_user_password(
    tenant_id: int,
    user_id: int,
    payload: SuperadminPasswordReset,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    """Issues a one-time temporary password for a tenant user (RESET, not reveal).

    Sets ``must_change_password`` so the user is forced to choose a new password
    on next login, clears any lockout, and revokes existing refresh sessions
    (the old credential is considered compromised). Returns the temporary
    password exactly once — it is never stored in clear.
    """
    from app.models.auth_tokens import RefreshToken

    t = _resolve_active_tenant(master_db, tenant_id)
    engine = get_tenant_engine(t.db_name)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TenantSession()
    try:
        u = session.query(User).filter(User.user_id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found.")

        temp_password = payload.new_password or _generate_temp_password()
        generated = payload.new_password is None

        u.hashed_password = get_password_hash(temp_password)
        u.must_change_password = True
        u.failed_login_attempts = 0
        u.locked_until = None

        # Revoke live refresh sessions — the prior password is now invalid.
        try:
            session.query(RefreshToken).filter(
                RefreshToken.user_id == u.user_id,
                RefreshToken.revoked == False,  # noqa: E712
            ).update({"revoked": True})
        except Exception as exc:  # noqa: BLE001 — token table is best-effort here
            logger.warning("reset-password: refresh revoke skipped for tenant %s: %s", t.db_name, exc)

        session.commit()

        # Security audit trail — actor + target, never the password.
        logger.info(
            "SUPERADMIN password reset: admin=%s (%s) -> tenant=%s user_id=%s email=%s generated=%s",
            admin.get("email"), admin.get("admin_id"), t.db_name, u.user_id, u.email, generated,
        )

        return {
            "message": "Temporary password issued. The user must change it at next login.",
            "tenant_id": t.tenant_id,
            "user_id": u.user_id,
            "email": u.email,
            "temporary_password": temp_password,
            "generated": generated,
            "must_change_password": True,
        }
    finally:
        session.close()


class SuperadminAccountAction(BaseModel):
    # At least one of these should be set. is_active toggles enable/disable;
    # unlock clears a lockout (failed attempts + locked_until).
    is_active: Optional[bool] = None
    unlock: Optional[bool] = None


@router.post("/superadmin/users/{tenant_id}/{user_id}/account", dependencies=[Depends(require_superadmin)])
def superadmin_update_user_account(
    tenant_id: int,
    user_id: int,
    payload: SuperadminAccountAction,
    master_db: Session = Depends(get_master_db),
    admin: dict = Depends(require_superadmin),
):
    """Enable/disable a user account and/or clear a lockout. No password access."""
    if payload.is_active is None and not payload.unlock:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    from app.models.auth_tokens import RefreshToken

    t = _resolve_active_tenant(master_db, tenant_id)
    engine = get_tenant_engine(t.db_name)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TenantSession()
    try:
        u = session.query(User).filter(User.user_id == user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found.")

        actions = []
        if payload.is_active is not None:
            u.is_active = payload.is_active
            actions.append("enabled" if payload.is_active else "disabled")
            # Disabling an account should also kill its live sessions.
            if payload.is_active is False:
                try:
                    session.query(RefreshToken).filter(
                        RefreshToken.user_id == u.user_id,
                        RefreshToken.revoked == False,  # noqa: E712
                    ).update({"revoked": True})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("account: refresh revoke skipped for tenant %s: %s", t.db_name, exc)
        if payload.unlock:
            u.failed_login_attempts = 0
            u.locked_until = None
            actions.append("unlocked")

        role_name = session.query(Role.name).filter(Role.role_id == u.role_id).scalar()
        session.commit()

        # H-2: a superadmin disabling an account must cut its cached access now,
        # not at access-token expiry. The tenant epoch lives in the same Redis.
        if payload.is_active is False:
            try:
                from app.core.dependencies import bump_perm_epoch
                bump_perm_epoch(t.db_name)
            except Exception:  # noqa: BLE001
                pass

        logger.info(
            "SUPERADMIN account update: admin=%s (%s) -> tenant=%s user_id=%s email=%s actions=%s",
            admin.get("email"), admin.get("admin_id"), t.db_name, u.user_id, u.email, ",".join(actions),
        )

        return {
            "message": f"Account {', '.join(actions)}.",
            "user": _serialize_user(t, u, role_name),
        }
    finally:
        session.close()


class SuperAdminLogin(BaseModel):
    email: str
    password: str


@router.post("/superadmin/login")
@limiter.limit("5/minute")
def superadmin_login(request: Request, payload: SuperAdminLogin, response: Response, db: Session = Depends(get_master_db)):
    """Authenticates the MediFleet platform superadmin.

    H-1: the superadmin holds platform-wide power (provision/suspend tenants,
    cross-tenant patient read, the money-receiving rail), so this is the
    highest-value credential in the system. It now carries the same protection
    as the tenant login: a 5/minute IP rate limit plus a 5-strike, 15-minute
    account lockout — previously it had neither.
    """
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == payload.email).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid superadmin credentials")

    now = datetime.now(timezone.utc)
    if admin.locked_until and admin.locked_until > now:
        remaining = max(1, int((admin.locked_until - now).total_seconds() / 60))
        raise HTTPException(
            status_code=403,
            detail=f"Account locked. Try again in {remaining} minute(s).",
        )

    if not verify_password(payload.password, admin.hashed_password):
        admin.failed_login_attempts = (admin.failed_login_attempts or 0) + 1
        if admin.failed_login_attempts >= 5:
            admin.locked_until = now + timedelta(minutes=15)
            logger.warning("SUPERADMIN login lockout: email=%s after %s strikes", admin.email, admin.failed_login_attempts)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid superadmin credentials")

    if admin.is_active is False:
        raise HTTPException(status_code=403, detail="Superadmin account disabled")

    # Success — clear any accumulated strikes / lockout.
    if admin.failed_login_attempts or admin.locked_until:
        admin.failed_login_attempts = 0
        admin.locked_until = None
        db.commit()

    # Platform sessions are short-lived by design — superadmin tokens carry the
    # power to provision/suspend tenants, so we cap the bearer at 20 minutes.
    ttl = timedelta(minutes=20)
    expire = datetime.now(timezone.utc) + ttl
    token = jwt.encode(
        {
            "user_id": admin.admin_id,
            "role": "superadmin",
            "type": "access",
            "exp": expire,
        },
        settings.jwt_secret,
        algorithm=settings.ALGORITHM,
    )

    # HttpOnly cookie keeps the JWT off page JS — previously this token sat in
    # localStorage where any XSS on the platform console could read the key
    # and impersonate the superadmin. SameSite=None is required because the
    # SPA on Vercel reaches the API on Render cross-origin (Secure is then
    # mandatory). `expires_in` is still returned so the SPA can show a
    # "session expires in N minutes" indicator without reading the cookie.
    is_production = settings.is_production
    response.set_cookie(
        "superadmin_token",
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        path="/",
    )
    return {
        "full_name": admin.full_name,
        "expires_in": int(ttl.total_seconds()),
    }


@router.post("/superadmin/logout")
def superadmin_logout(response: Response):
    """Clears the superadmin session cookie."""
    response.delete_cookie("superadmin_token", path="/")
    return {"detail": "Logged out"}


@router.get("/superadmin/me")
def superadmin_me(admin: dict = Depends(require_superadmin)):
    """Returns the current superadmin session. The SPA calls this on platform
    bootstrap to verify the cookie is still valid (the JWT itself is HttpOnly
    so the SPA can't decode it locally)."""
    return admin


# =====================================================================
# Public contact form — landing-page lead capture
# =====================================================================
# Contact-form department → ticket category (→ superadmin desk tab).
#   general → Onboarding (Support desk) · billing → Billing (Finance desk)
#   technical → Bug (Technical desk)
_DEPARTMENT_CATEGORY = {"general": "Onboarding", "billing": "Billing", "technical": "Bug"}


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(min_length=1, max_length=5000)
    subject: Optional[str] = Field(default=None, max_length=160)
    company: Optional[str] = Field(default=None, max_length=160)
    # Which team the enquiry is for. Unknown values fall back to 'general'.
    department: Optional[str] = Field(default="general", max_length=20)
    # Honeypot: a hidden field real users never see. Bots fill it; we drop
    # those silently. Kept loose (no length cap) so a filled value validates
    # and we can detect-and-discard rather than 422.
    website: Optional[str] = None


@router.post("/contact")
@limiter.limit("5/minute")
async def submit_contact(
    request: Request,
    payload: ContactRequest,
    background_tasks: BackgroundTasks,
    master_db: Session = Depends(get_master_db),
):
    """Public website contact form → support ticket + email notification.

    Unauthenticated; CSRF is satisfied by the SPA's double-submit token. Files
    an "Unassigned" (tenant-less) ticket in the platform inbox so leads are
    durable + assignable, AND emails the operator (Reply-To = visitor) so they
    can reply straight away. Independent of the inbound-email pipeline (which is
    restricted to known contacts) — this is open lead capture.
    """
    # Honeypot tripped → act successful, persist/send nothing.
    if payload.website:
        logger.info("[contact] honeypot tripped from %s — dropped", payload.email)
        return {"message": "Thanks — we'll be in touch shortly."}

    # 1) Durable record: an Unassigned ticket in the superadmin inbox, routed to
    #    the chosen department's desk. Best-effort — a DB hiccup must not fail
    #    the public form.
    category = _DEPARTMENT_CATEGORY.get((payload.department or "general").lower(), "Onboarding")
    body = payload.message.strip()
    if payload.company:
        body = f"Company: {payload.company}\n\n{body}"
    try:
        ticket = SupportTicket(
            tenant_id=None, tenant_name=None,           # Unassigned — triage later
            submitter_email=payload.email,
            submitter_name=payload.name,
            origin="web",
            subject=(payload.subject or "Website enquiry")[:200],
            category=category,                          # routes to the desk tab
            priority="Normal",
            status="Open",
        )
        master_db.add(ticket)
        master_db.flush()
        master_db.add(SupportMessage(
            ticket_id=ticket.ticket_id,
            author_kind="customer",
            author_name=payload.name,
            source="web",
            from_email=payload.email,
            from_name=payload.name,
            body=body,
        ))
        master_db.commit()
    except Exception:
        logger.exception("[contact] failed to create lead ticket for %s", payload.email)
        master_db.rollback()

    # 2) Notify the operator by email (Reply-To = the visitor).
    recipient = settings.CONTACT_RECIPIENT_EMAIL or settings.EMAIL_REPLY_TO or settings.EMAIL_FROM_SUPPORT or settings.EMAIL_FROM
    if recipient:
        subject, html, text = render_contact_message(
            name=payload.name, email=payload.email, message=payload.message,
            subject=payload.subject, company=payload.company,
        )
        background_tasks.add_task(
            email_service.send,
            to=recipient, subject=subject, html=html, text=text,
            reply_to=payload.email,
        )
    else:
        logger.error("[contact] no recipient configured (EMAIL_REPLY_TO/EMAIL_FROM) — email skipped")

    # Always a friendly success — never leak config/delivery state to the public.
    return {"message": "Thanks — we'll be in touch shortly."}


# =====================================================================
# Resend outbound-email events webhook (EMAIL-004)
# =====================================================================
@router.post("/email/events")
@limiter.limit("120/minute")
async def email_events_webhook(
    request: Request,
    master_db: Session = Depends(get_master_db),
):
    """Receives Resend delivery events (sent/delivered/bounced/complained/…),
    records them, and suppresses hard bounces + spam complaints.

    Machine-to-machine: CSRF-exempt (see main.py), HMAC-signature gated, and a
    404 when disabled so we don't advertise an unconfigured endpoint.
    """
    if not settings.EMAIL_EVENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")

    raw = await request.body()
    if not verify_svix_webhook(raw, request.headers, settings.email_events_signing_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed payload")

    try:
        result = process_email_event(master_db, payload)
    except Exception:
        logger.exception("[email-events] failed to process event")
        master_db.rollback()
        result = {"recorded": False}
    # 200 so the provider stops retrying.
    return result
