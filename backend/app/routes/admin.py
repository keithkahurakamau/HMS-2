from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, date

from app.config.database import get_db
from app.models.user import User, Role, Permission 
from app.models.patient import Patient
from app.models.wards import AdmissionRecord
from app.models.billing import Invoice
from app.models.inventory import StockBatch, InventoryItem
from app.models.audit import AuditLog
from app.models.laboratory import LabTestCatalog
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/admin", tags=["Admin Controls"])

# ==========================================
# 1. SYSTEM METRICS OVERVIEW
# ==========================================
@router.get("/metrics", dependencies=[Depends(RequirePermission("users:manage"))])
def get_system_metrics(db: Session = Depends(get_db)):
    total_patients = db.query(func.count(Patient.patient_id)).scalar()
    active_admissions = db.query(func.count(AdmissionRecord.admission_id)).filter(AdmissionRecord.status == "Active").scalar()
    today = date.today()
    daily_revenue = db.query(func.sum(Invoice.total_amount)).filter(func.date(Invoice.billing_date) == today).scalar() or 0.0
    low_stock_count = db.query(func.count(StockBatch.batch_id)).join(InventoryItem, StockBatch.item_id == InventoryItem.item_id).filter(StockBatch.quantity <= InventoryItem.reorder_threshold).scalar()

    return {
        "total_patients": total_patients,
        "active_admissions": active_admissions,
        "daily_revenue": float(daily_revenue),
        "low_stock_alerts": low_stock_count
    }

# ==========================================
# 2. STAFF DIRECTORY & PROVISIONING
# ==========================================
@router.get("/users", dependencies=[Depends(RequirePermission("users:manage"))])
def get_staff_directory(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "Unknown",
            "specialization": u.specialization,
            "license_number": u.license_number,
            "is_active": u.is_active
        } for u in users
    ]

from pydantic import BaseModel, EmailStr, field_validator
import re

class StaffCreateRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str
    specialization: str | None = None
    license_number: str | None = None

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r"[A-Z]", v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r"[a-z]", v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r"\d", v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('Password must contain at least one special character')
        return v

@router.post("/users", dependencies=[Depends(RequirePermission("users:manage"))])
def create_staff(payload: StaffCreateRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from app.core.security import get_password_hash
    
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")
        
    role = db.query(Role).filter(Role.name == payload.role).first()
    if not role:
        raise HTTPException(status_code=400, detail="Invalid role specified.")
        
    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role_id=role.role_id,
        specialization=payload.specialization,
        license_number=payload.license_number,
        is_active=True,
        must_change_password=True
    )
    db.add(new_user)
    db.commit()
    return {"message": "Staff created successfully"}

@router.patch("/users/{user_id}/status", dependencies=[Depends(RequirePermission("users:manage"))])
def toggle_user_status(user_id: int, status_update: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Safety Protocol: You cannot lock your own active session.")
        
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_status = user.is_active
    user.is_active = status_update.get("is_active", user.is_active)
    
    log_audit(db=db, user_id=current_user["user_id"], action="UPDATE", entity_type="UserStatus", entity_id=str(user.user_id), old_value={"is_active": old_status}, new_value={"is_active": user.is_active}, ip_address=request.client.host)
    db.commit()
    return {"message": f"User status updated to {'Active' if user.is_active else 'Locked'}"}

@router.patch("/users/{user_id}/role", dependencies=[Depends(RequirePermission("users:manage"))])
def update_user_role(user_id: int, role_update: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_role_name = role_update.get("role")
    new_role = db.query(Role).filter(Role.name == new_role_name).first()
    if not new_role:
        raise HTTPException(status_code=400, detail=f"Role '{new_role_name}' does not exist.")
        
    if user.role.name == "Admin" and new_role_name != "Admin":
        admin_count = db.query(func.count(User.user_id)).join(Role).filter(Role.name == "Admin", User.is_active == True).scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the final active Admin.")

    old_role_name = user.role.name
    user.role_id = new_role.role_id
    
    log_audit(db=db, user_id=current_user["user_id"], action="UPDATE", entity_type="UserRole", entity_id=str(user.user_id), old_value={"role": old_role_name}, new_value={"role": new_role_name}, ip_address=request.client.host)
    db.commit()
    return {"message": f"User {user.email} promoted to {new_role_name} successfully."}

# ==========================================
# 3. IMMUTABLE AUDIT LEDGER
# ==========================================
@router.get("/audit-logs", dependencies=[Depends(RequirePermission("users:manage"))])
def get_audit_trail(limit: int = 100, db: Session = Depends(get_db)):
    logs = db.query(AuditLog, User.full_name.label("actor_name")).outerjoin(User, AuditLog.user_id == User.user_id).order_by(AuditLog.timestamp.desc()).limit(limit).all() 
    formatted_logs = []
    for log, actor_name in logs:
        formatted_logs.append({
            "log_id": log.log_id,
            "timestamp": log.timestamp.isoformat(),
            "user_id": f"{actor_name} (ID: {log.user_id})" if actor_name else "SYSTEM",
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "old_value": log.old_value,
            "new_value": log.new_value
        })
    return formatted_logs

# ==========================================
# 4. MASTER CATALOG PRICING
# ==========================================
@router.get("/pricing", dependencies=[Depends(RequirePermission("users:manage"))])
def get_service_pricing(db: Session = Depends(get_db)):
    return db.query(LabTestCatalog).order_by(LabTestCatalog.category, LabTestCatalog.test_name).all()

@router.post("/pricing", dependencies=[Depends(RequirePermission("users:manage"))])
def create_service_pricing(payload: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_service = LabTestCatalog(
        test_name=payload.get("test_name"),
        category=payload.get("category"),
        base_price=float(payload.get("base_price", 0.0)),
        default_specimen_type=payload.get("description", "") # Mapping description to existing column
    )
    db.add(new_service)
    
    log_audit(db=db, user_id=current_user["user_id"], action="CREATE", entity_type="PricingCatalog", entity_id=payload.get("test_name"), old_value=None, new_value=payload, ip_address=request.client.host)
    
    db.commit()
    return {"message": "Service package added to catalog."}

@router.put("/pricing/{catalog_id}", dependencies=[Depends(RequirePermission("users:manage"))])
def update_service_pricing(catalog_id: int, payload: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    item = db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id == catalog_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Service package not found.")
        
    old_data = {"test_name": item.test_name, "base_price": item.base_price}
    
    item.test_name = payload.get("test_name", item.test_name)
    item.category = payload.get("category", item.category)
    item.base_price = float(payload.get("base_price", item.base_price))
    item.default_specimen_type = payload.get("description", item.default_specimen_type)
    
    log_audit(db=db, user_id=current_user["user_id"], action="UPDATE", entity_type="PricingCatalog", entity_id=str(catalog_id), old_value=old_data, new_value=payload, ip_address=request.client.host)
    
    db.commit()
    return {"message": "Service package updated."}

# ==========================================
# 5. ROLE PERMISSIONS MANAGEMENT
# ==========================================
@router.get("/roles/{role_name}/permissions", dependencies=[Depends(RequirePermission("users:manage"))])
def get_role_permissions(role_name: str, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return [p.codename for p in role.permissions]

@router.put("/roles/{role_name}/permissions", dependencies=[Depends(RequirePermission("users:manage"))])
def update_role_permissions(role_name: str, payload: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if role_name == "Admin":
        raise HTTPException(status_code=400, detail="Admin permissions cannot be restricted.")

    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    new_perms_list = payload.get("permissions", [])
    valid_perms = db.query(Permission).filter(Permission.codename.in_(new_perms_list)).all()
    old_perms = [p.codename for p in role.permissions]

    role.permissions = valid_perms

    log_audit(
        db=db, user_id=current_user["user_id"], action="UPDATE", 
        entity_type="RolePermissions", entity_id=role_name, 
        old_value={"permissions": old_perms}, 
        new_value={"permissions": [p.codename for p in valid_perms]}, 
        ip_address=request.client.host
    )

    db.commit()
    return {"message": f"Permissions for {role_name} updated successfully."}

# ==========================================
# 6. CUSTOM ROLE MANAGEMENT
# ==========================================
# Admins can mint new roles beyond the seven baked-in ones (Doctor, Nurse, etc.)
# so the system isn't capped to a fixed staff taxonomy. Each custom role picks
# its own permission set from the catalogue. The seven baseline roles can have
# their permissions edited but cannot be renamed or deleted — they're hard-wired
# into the frontend's RoleBasedRedirect default-landing logic.
PROTECTED_ROLE_NAMES = {
    "Admin", "Doctor", "Nurse", "Pharmacist",
    "Lab Technician", "Radiologist", "Receptionist",
}


class RoleCreateRequest(BaseModel):
    name: str
    description: str | None = None
    permissions: list[str] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Role name cannot be empty.")
        if len(v) > 50:
            raise ValueError("Role name must be 50 characters or fewer.")
        return v


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("/permissions", dependencies=[Depends(RequirePermission("roles:manage"))])
def list_permissions(db: Session = Depends(get_db)):
    """Catalogue of every permission codename in the system (for the role editor UI)."""
    perms = db.query(Permission).order_by(Permission.codename).all()
    return [
        {"codename": p.codename, "description": p.description}
        for p in perms
    ]


@router.get("/roles", dependencies=[Depends(RequirePermission("roles:manage"))])
def list_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).order_by(Role.name).all()
    out = []
    for r in roles:
        user_count = db.query(func.count(User.user_id)).filter(User.role_id == r.role_id).scalar()
        out.append({
            "role_id": r.role_id,
            "name": r.name,
            "description": r.description,
            "is_system": r.name in PROTECTED_ROLE_NAMES,
            "user_count": int(user_count or 0),
            "permissions": [p.codename for p in r.permissions],
        })
    return out


@router.post("/roles", dependencies=[Depends(RequirePermission("roles:manage"))])
def create_role(payload: RoleCreateRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    if db.query(Role).filter(func.lower(Role.name) == payload.name.lower()).first():
        raise HTTPException(status_code=409, detail=f"Role '{payload.name}' already exists.")

    role = Role(name=payload.name, description=payload.description)
    if payload.permissions:
        perms = db.query(Permission).filter(Permission.codename.in_(payload.permissions)).all()
        role.permissions = perms
    db.add(role)
    db.flush()

    log_audit(
        db=db, user_id=current_user["user_id"], action="CREATE",
        entity_type="Role", entity_id=role.name, old_value=None,
        new_value={"name": role.name, "permissions": [p.codename for p in role.permissions]},
        ip_address=request.client.host,
    )
    db.commit()
    db.refresh(role)
    return {
        "role_id": role.role_id,
        "name": role.name,
        "description": role.description,
        "is_system": role.name in PROTECTED_ROLE_NAMES,
        "permissions": [p.codename for p in role.permissions],
    }


@router.patch("/roles/{role_id}", dependencies=[Depends(RequirePermission("roles:manage"))])
def update_role(role_id: int, payload: RoleUpdateRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    if role.name in PROTECTED_ROLE_NAMES and payload.name and payload.name != role.name:
        raise HTTPException(status_code=400, detail="Built-in role names cannot be changed.")

    if payload.name and payload.name != role.name:
        clash = db.query(Role).filter(func.lower(Role.name) == payload.name.lower(), Role.role_id != role_id).first()
        if clash:
            raise HTTPException(status_code=409, detail="Another role with this name already exists.")
        old_name = role.name
        role.name = payload.name.strip()
        log_audit(
            db=db, user_id=current_user["user_id"], action="UPDATE",
            entity_type="Role", entity_id=str(role_id),
            old_value={"name": old_name}, new_value={"name": role.name},
            ip_address=request.client.host,
        )

    if payload.description is not None:
        role.description = payload.description

    db.commit()
    db.refresh(role)
    return {"role_id": role.role_id, "name": role.name, "description": role.description}


@router.put("/roles/id/{role_id}/permissions", dependencies=[Depends(RequirePermission("roles:manage"))])
def update_role_permissions_by_id(role_id: int, payload: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """ID-keyed counterpart to /roles/{role_name}/permissions for custom roles
    that may not be safely addressable by name from the UI.
    """
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.name == "Admin":
        raise HTTPException(status_code=400, detail="Admin permissions cannot be restricted.")

    requested = payload.get("permissions", [])
    valid_perms = db.query(Permission).filter(Permission.codename.in_(requested)).all()
    old_perms = [p.codename for p in role.permissions]
    role.permissions = valid_perms

    log_audit(
        db=db, user_id=current_user["user_id"], action="UPDATE",
        entity_type="RolePermissions", entity_id=role.name,
        old_value={"permissions": old_perms},
        new_value={"permissions": [p.codename for p in valid_perms]},
        ip_address=request.client.host,
    )
    db.commit()
    return {"role_id": role.role_id, "name": role.name, "permissions": [p.codename for p in role.permissions]}


@router.delete("/roles/{role_id}", dependencies=[Depends(RequirePermission("roles:manage"))])
def delete_role(role_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.name in PROTECTED_ROLE_NAMES:
        raise HTTPException(status_code=400, detail="Built-in roles cannot be deleted.")

    in_use = db.query(func.count(User.user_id)).filter(User.role_id == role_id).scalar()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete role: {in_use} user(s) still have it. Reassign them first.",
        )

    log_audit(
        db=db, user_id=current_user["user_id"], action="DELETE",
        entity_type="Role", entity_id=role.name,
        old_value={"name": role.name, "permissions": [p.codename for p in role.permissions]},
        new_value=None, ip_address=request.client.host,
    )
    db.delete(role)
    db.commit()
    return {"deleted": True}