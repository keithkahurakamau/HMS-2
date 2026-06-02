from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.models.user import User
from app.models.auth_tokens import PasswordResetToken
from app.schemas.user import UserCreate, UserResponse
from app.core.dependencies import get_current_user, RequirePermission, resolve_effective_permissions
from app.core.security import get_password_hash, generate_reset_token, hash_token
from app.core.modules import (
    get_tenant_flags_cached,
    resolve_enabled_modules,
    serialize_module_catalogue,
)
from app.services.auth_emails import send_staff_invite_email, RESET_TOKEN_TTL_MINUTES
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


@router.get("/me/modules")
def get_my_modules(request: Request, current_user: dict = Depends(get_current_user)):
    """List of modules this tenant has purchased.

    The frontend uses this to hide nav items the tenant cannot access and to
    short-circuit the route guard before the user ever triggers a 402. The
    server still gates on the middleware — this endpoint is a UX aid, not a
    security boundary.
    """
    tenant_db = request.headers.get("X-Tenant-ID") or ""
    flags_raw = get_tenant_flags_cached(tenant_db) if tenant_db else ""
    enabled = resolve_enabled_modules(flags_raw)
    return {
        "enabled": enabled,
        "catalogue": serialize_module_catalogue(enabled),
    }

# ==========================================
# 2. USER MANAGEMENT (CRUD)
# ==========================================
@router.get("/", response_model=List[UserResponse], dependencies=[Depends(RequirePermission("users:manage"))])
def list_users(db: Session = Depends(get_db)):
    """Lists all system users."""
    return db.query(User).all()

@router.post("/", response_model=UserResponse, dependencies=[Depends(RequirePermission("users:manage"))])
def create_user(
    user_in: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    send_invite: bool = Query(True, description="Email the new user a set-password invite link."),
):
    """Provisions a new staff account.

    When ``send_invite`` is true (default) the user is emailed a single-use
    set-password link so they choose their own credentials — the admin never
    has to hand out a password. The link rides the same reset-token rail as
    /auth/forgot-password and is tenant-scoped.
    """
    # Enforce unique email
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user_data = user_in.model_dump()
    user_data["hashed_password"] = get_password_hash(user_data.pop("password"))

    new_user = User(**user_data)
    db.add(new_user)
    db.flush()

    invite_token = None
    if send_invite:
        # Mint a set-password token (reuses the password-reset machinery) and
        # require the user to set their own password before the temp one sticks.
        invite_token = generate_reset_token()
        db.add(PasswordResetToken(
            user_id=new_user.user_id,
            token_hash=hash_token(invite_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
            used=False,
            requested_ip=request.client.host if request.client else None,
        ))

    log_audit(db, current_user["user_id"], "CREATE", "User", str(new_user.user_id), None, {"email": new_user.email}, request.client.host)
    db.commit()
    db.refresh(new_user)

    if invite_token:
        send_staff_invite_email(
            background_tasks,
            to=new_user.email,
            raw_token=invite_token,
            tenant_id=request.headers.get("X-Tenant-ID"),
            recipient_name=getattr(new_user, "full_name", None),
        )

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