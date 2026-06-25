from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session, joinedload

from app.config.database import get_db
from app.models.user import User
from app.models.auth_tokens import PasswordResetToken
from app.schemas.user import UserCreate, UserResponse
from app.core.dependencies import get_current_user, RequirePermission, resolve_effective_permissions, bump_perm_epoch
from app.core.security import get_password_hash, generate_reset_token, hash_token, verify_password
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

class ProfileUpdate(BaseModel):
    """Self-service profile edits. Email and role are deliberately NOT here —
    changing your own email breaks login identity and role escalation must go
    through an admin. Those stay admin-only."""
    full_name: Optional[str] = None
    specialization: Optional[str] = None
    license_number: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def _name_nonempty(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Name cannot be empty.")
        return v.strip() if v else v


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong_enough(cls, v):
        if len(v or "") < 8:
            raise ValueError("New password must be at least 8 characters.")
        return v


@router.patch("/me")
def update_my_profile(
    payload: ProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Each user maintains their own profile (name, specialization, licence).
    Any authenticated user may edit their own — no extra permission needed."""
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")

    data = payload.model_dump(exclude_unset=True)
    before = {"full_name": user.full_name, "specialization": user.specialization, "license_number": user.license_number}

    if "license_number" in data and data["license_number"]:
        clash = (
            db.query(User)
            .filter(User.license_number == data["license_number"], User.user_id != user.user_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="That licence number is already on file for another user.")

    if "full_name" in data and data["full_name"]:
        user.full_name = data["full_name"]
    if "specialization" in data:
        user.specialization = data["specialization"] or None
    if "license_number" in data:
        user.license_number = data["license_number"] or None

    log_audit(db, user.user_id, "UPDATE", "User", str(user.user_id), before,
              {k: data[k] for k in data}, request.client.host if request.client else None)
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "Unassigned",
        "specialization": user.specialization,
        "license_number": user.license_number,
    }


@router.post("/me/change-password")
def change_my_password(
    payload: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Self password change — requires the current password. Distinct from the
    admin invite / reset-token rail; this is the in-app 'change my password'."""
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must differ from the current one.")

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    log_audit(db, user.user_id, "UPDATE", "User", str(user.user_id),
              {"password": "***"}, {"password": "changed"},
              request.client.host if request.client else None)
    db.commit()
    return {"message": "Password changed successfully."}


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
def _serialize_user(db: Session, user: User) -> dict:
    """Shape a User into the UserResponse contract.

    UserResponse expects ``role`` as the role *name* (string) and
    ``permissions`` as a flat list of permission strings — neither is a direct
    column on User (``role`` is a relationship; permissions are derived). The
    raw ORM object therefore fails response validation, so we build the dict
    here. Mirrors the /me + /me/permissions endpoints.
    """
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "Unassigned",
        "permissions": resolve_effective_permissions(db, user) if user.role else [],
        "is_active": user.is_active,
        "specialization": user.specialization,
        "license_number": user.license_number,
    }


@router.get("/", response_model=List[UserResponse], dependencies=[Depends(RequirePermission("users:manage"))])
def list_users(db: Session = Depends(get_db)):
    """Lists all system users."""
    # Eager-load the role to drop the per-user role lazy-load. Effective
    # permission resolution stays per-user (it reads the same role graph and
    # would need a shared-helper refactor to batch); staff lists are small.
    users = db.query(User).options(joinedload(User.role)).all()
    return [_serialize_user(db, u) for u in users]

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

    return _serialize_user(db, new_user)

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
    bump_perm_epoch(request.headers.get("X-Tenant-ID"))  # H-2: cut cached access now
    return {"message": f"User {user.email} deactivated successfully"}