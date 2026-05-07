from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from jose import jwt
from pydantic import BaseModel, EmailStr, field_validator
from typing import List, Optional
import re

from app.config.database import get_master_db
from app.config.settings import settings
from app.core.dependencies import require_superadmin
from app.models.master import Tenant, SuperAdmin
from app.core.security import get_password_hash, verify_password, create_tokens
from app.services.tenant_provisioning import provision_tenant

router = APIRouter(prefix="/api/public", tags=["Public Portal"])


@router.get("/hospitals")
def get_available_hospitals(db: Session = Depends(get_master_db)):
    """Returns all active tenants from the master registry."""
    tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
    return [
        {
            "id": f"tenant_{t.tenant_id}",
            "name": t.name,
            "domain": t.domain,
            "db_name": t.db_name,
            "theme_color": t.theme_color,
            "is_premium": t.is_premium
        }
        for t in tenants
    ]


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


@router.patch("/hospitals/{tenant_id}", dependencies=[Depends(require_superadmin)])
def update_tenant(tenant_id: int, payload: TenantUpdate, db: Session = Depends(get_master_db)):
    """Updates a tenant's display attributes or suspension state. Identifier
    fields (db_name) are intentionally not editable — renaming a database
    is a destructive operation that requires data migration."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    update = payload.model_dump(exclude_unset=True)
    for field, value in update.items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return {
        "id": f"tenant_{tenant.tenant_id}",
        "name": tenant.name,
        "domain": tenant.domain,
        "db_name": tenant.db_name,
        "theme_color": tenant.theme_color,
        "is_premium": tenant.is_premium,
        "is_active": tenant.is_active,
    }


class SuperAdminLogin(BaseModel):
    email: str
    password: str


@router.post("/superadmin/login")
def superadmin_login(payload: SuperAdminLogin, db: Session = Depends(get_master_db)):
    """Authenticates the HMS platform superadmin."""
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
