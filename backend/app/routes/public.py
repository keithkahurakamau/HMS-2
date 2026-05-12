from datetime import datetime, timedelta, timezone
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, sessionmaker
from jose import jwt
from pydantic import BaseModel, EmailStr, field_validator
from typing import List, Optional, Dict, Any
import re

from app.config.database import get_master_db, get_tenant_engine
from app.config.settings import settings
from app.core.dependencies import require_superadmin
from app.models.master import Tenant, SuperAdmin
from app.models.patient import Patient
from app.core.security import get_password_hash, verify_password, create_tokens
from app.services.tenant_provisioning import provision_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["Public Portal"])


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


@router.get("/hospitals")
def get_available_hospitals(
    include_inactive: bool = False,
    db: Session = Depends(get_master_db),
):
    """Returns tenants from the master registry.

    By default only active ones are listed (used by the public hospital
    picker). Superadmins pass ``include_inactive=true`` to see suspended
    rows from the Tenants Manager.
    """
    query = db.query(Tenant)
    if not include_inactive:
        query = query.filter(Tenant.is_active == True)
    tenants = query.order_by(Tenant.name).all()
    return [_serialize_tenant(t) for t in tenants]


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
    for field, value in update.items():
        if field in ("feature_flags", "plan_limits"):
            setattr(tenant, field, json.dumps(value) if value is not None else None)
        else:
            setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
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
                    q = q.filter(
                        (Patient.surname.ilike(f"%{needle}%"))
                        | (Patient.other_names.ilike(f"%{needle}%"))
                        | (Patient.outpatient_no.ilike(f"%{needle}%"))
                        | (Patient.telephone_1.ilike(f"%{needle}%"))
                    )
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
            logger.warning("Failed to read patients from tenant %s: %s", t.db_name, exc)
            errors.append({"tenant_id": str(t.tenant_id), "tenant_db": t.db_name, "error": str(exc)})

    return {
        "patients": aggregated,
        "count": len(aggregated),
        "tenants_scanned": len(tenants),
        "errors": errors,
    }


@router.get("/superadmin/patients/{tenant_id}/{patient_id}", dependencies=[Depends(require_superadmin)])
def get_patient_detail(
    tenant_id: int,
    patient_id: int,
    master_db: Session = Depends(get_master_db),
):
    """Returns a single patient's full profile (read-only)."""
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

        # Hand back every column on Patient. Cross-tenant superadmin access
        # is logged separately by the caller; this endpoint is read-only by
        # design — no write paths exposed.
        out: Dict[str, Any] = {
            "tenant": _serialize_tenant(t, include_flags=False),
        }
        for col in p.__table__.columns.keys():
            val = getattr(p, col, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            out[col] = val
        return out
    finally:
        session.close()


class SuperAdminLogin(BaseModel):
    email: str
    password: str


@router.post("/superadmin/login")
def superadmin_login(payload: SuperAdminLogin, db: Session = Depends(get_master_db)):
    """Authenticates the MediFleet platform superadmin."""
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == payload.email).first()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid superadmin credentials")
    if admin.is_active is False:
        raise HTTPException(status_code=403, detail="Superadmin account disabled")

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
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return {
        "access_token": token,
        "full_name": admin.full_name,
        "expires_in": int(ttl.total_seconds()),
    }
