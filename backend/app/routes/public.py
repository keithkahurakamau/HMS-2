from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.config.database import get_master_db
from app.models.master import Tenant, SuperAdmin
from app.core.security import get_password_hash, verify_password, create_tokens

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
    theme_color: str = "blue"
    is_premium: bool = False

@router.post("/hospitals")
def provision_hospital(tenant: TenantCreate, db: Session = Depends(get_master_db)):
    """Provisions a new hospital tenant in the master registry."""
    existing = db.query(Tenant).filter(
        (Tenant.db_name == tenant.db_name) | (Tenant.domain == tenant.domain)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="A tenant with this database name or domain already exists.")

    new_tenant = Tenant(**tenant.model_dump())
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    return {"message": "Tenant registered in master registry.", "tenant_id": new_tenant.tenant_id}


class SuperAdminLogin(BaseModel):
    email: str
    password: str

@router.post("/superadmin/login")
def superadmin_login(payload: SuperAdminLogin, db: Session = Depends(get_master_db)):
    """Authenticates the HMS platform superadmin."""
    admin = db.query(SuperAdmin).filter(SuperAdmin.email == payload.email).first()
    if not admin or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid superadmin credentials")

    # Issue a JWT with a special superadmin claim (no tenant binding)
    from app.config.settings import settings
    from datetime import datetime, timedelta
    import jwt
    token = jwt.encode(
        {"user_id": admin.admin_id, "role": "superadmin", "exp": datetime.utcnow() + timedelta(hours=4)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return {"access_token": token, "full_name": admin.full_name}
