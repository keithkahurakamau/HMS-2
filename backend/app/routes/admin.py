from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, date

from app.config.database import get_db
from app.models.user import User, Role
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
@router.get("/metrics")
def get_system_metrics(db: Session = Depends(get_db)):
    """Aggregates top-level hospital metrics for the Admin dashboard."""
    
    # 1. Total Patients
    total_patients = db.query(func.count(Patient.patient_id)).scalar()

    # 2. Active Admissions
    active_admissions = db.query(func.count(AdmissionRecord.admission_id)).filter(
        AdmissionRecord.status == "Active"
    ).scalar()

    # 3. Today's Revenue (Sum of all invoices generated today)
    today = date.today()
    daily_revenue = db.query(func.sum(Invoice.total_amount)).filter(
        func.date(Invoice.billing_date) == today
    ).scalar() or 0.0

    # 4. Low Stock Alerts (Across all locations)
    low_stock_count = db.query(func.count(StockBatch.batch_id)).join(
        InventoryItem, StockBatch.item_id == InventoryItem.item_id
    ).filter(
        StockBatch.quantity <= InventoryItem.reorder_threshold
    ).scalar()

    return {
        "total_patients": total_patients,
        "active_admissions": active_admissions,
        "daily_revenue": float(daily_revenue),
        "low_stock_alerts": low_stock_count
    }

# ==========================================
# 2. STAFF DIRECTORY & PROVISIONING
# ==========================================
@router.get("/users")
def get_staff_directory(db: Session = Depends(get_db)):
    """Fetches all registered staff members."""
    users = db.query(User).all()
    
    # Map response to exclude hashed_passwords
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

@router.patch("/users/{user_id}/status", dependencies=[Depends(RequirePermission("users:manage"))])
def toggle_user_status(user_id: int, status_update: dict, db: Session = Depends(get_db)):
    """Locks or Unlocks a staff account."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = status_update.get("is_active", user.is_active)
    db.commit()
    return {"message": f"User status updated to {'Active' if user.is_active else 'Locked'}"}

@router.patch("/users/{user_id}/role", dependencies=[Depends(RequirePermission("users:manage"))])
def update_user_role(user_id: int, role_update: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Dynamically changes a user's RBAC Role (e.g., promoting a Nurse to Admin)."""
    
    # 1. Find the User
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # 2. Find the requested Role
    new_role_name = role_update.get("role")
    new_role = db.query(Role).filter(Role.name == new_role_name).first()
    if not new_role:
        raise HTTPException(status_code=400, detail=f"Role '{new_role_name}' does not exist.")
        
    # Prevent removing the last Admin
    if user.role.name == "Admin" and new_role_name != "Admin":
        admin_count = db.query(func.count(User.user_id)).join(Role).filter(Role.name == "Admin", User.is_active == True).scalar()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the final active Admin.")

    old_role_name = user.role.name
    user.role_id = new_role.role_id
    
    # 3. Log the security change
    log_audit(
        db=db, 
        user_id=current_user["user_id"], 
        action="UPDATE", 
        entity_type="UserRole", 
        entity_id=str(user.user_id), 
        old_value={"role": old_role_name}, 
        new_value={"role": new_role_name}, 
        ip_address=request.client.host
    )
    
    db.commit()
    return {"message": f"User {user.email} promoted to {new_role_name} successfully."}

# ==========================================
# 3. IMMUTABLE AUDIT LEDGER
# ==========================================
@router.get("/audit-logs")
def get_audit_trail(limit: int = 100, db: Session = Depends(get_db)):
    """Fetches the immutable security audit trails, latest first."""
    
    # Join with User to get the name of the person who took the action
    logs = db.query(
        AuditLog, 
        User.full_name.label("actor_name")
    ).outerjoin(
        User, AuditLog.user_id == User.user_id
    ).order_by(
        AuditLog.timestamp.desc()
    ).limit(limit).all() 

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
    """Fetches base pricing for lab tests and catalog services."""
    return db.query(LabTestCatalog).all()