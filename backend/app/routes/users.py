from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse
from app.core.dependencies import get_current_user, RequirePermission, resolve_effective_permissions
from app.core.security import get_password_hash
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/users", tags=["User Management"])

# ==========================================
# 1. CURRENT USER IDENTITY & RBAC
# ==========================================
@router.get("/me")
def get_current_user_profile(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns the profile data for the currently authenticated user. Required by React AuthContext."""
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found in database.")
    
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "Unassigned",
        "specialization": user.specialization,
        "license_number": user.license_number
    }

@router.get("/me/permissions")
def get_my_permissions(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns an array of permission strings based on the user's role.
    The frontend AuthContext uses this to hide/show UI elements and unlock routes.
    """
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user or not user.role:
        return []
    return resolve_effective_permissions(db, user)

# ==========================================
# 2. USER MANAGEMENT (CRUD)
# ==========================================
@router.get("/", response_model=List[UserResponse], dependencies=[Depends(RequirePermission("users:manage"))])
def list_users(db: Session = Depends(get_db)):
    """Lists all system users."""
    return db.query(User).all()

@router.post("/", response_model=UserResponse, dependencies=[Depends(RequirePermission("users:manage"))])
def create_user(user_in: UserCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Provisions a new staff account."""
    # Enforce unique email
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user_data = user_in.model_dump()
    user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
    
    new_user = User(**user_data)
    db.add(new_user)
    db.flush()

    log_audit(db, current_user["user_id"], "CREATE", "User", str(new_user.user_id), None, {"email": new_user.email}, request.client.host)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.patch("/{user_id}/deactivate", dependencies=[Depends(RequirePermission("users:manage"))])
def deactivate_user(user_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Sever API access for a compromised or terminated staff member."""
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_active = False
    log_audit(db, current_user["user_id"], "UPDATE", "User", str(user.user_id), {"is_active": True}, {"is_active": False}, request.client.host)
    db.commit()
    return {"message": f"User {user.email} deactivated successfully"}