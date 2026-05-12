from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.config.database import get_db, get_master_db
from app.config.settings import settings
from app.models.master import SuperAdmin
from app.models.user import User, Role, Permission, UserPermissionOverride


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
    """Authenticates a platform-level superadmin via Bearer token.

    Superadmin tokens are not tenant-scoped: they're issued by
    POST /api/public/superadmin/login and carry role='superadmin'. The token
    arrives in the Authorization header (the front-office UI keeps it in
    localStorage rather than the HttpOnly tenant cookie used by hospital users).
    """
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Superadmin authentication required",
        )
    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
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
    token = request.cookies.get("access_token")
    if not token:
        print("AUTH_ERROR: No access_token cookie found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated. No access token cookie found."
        )
        
    if token.startswith("Bearer "):
        token = token.split("Bearer ")[1]
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print(f"DECODED PAYLOAD: {payload}")
        user_id = payload.get("user_id") or payload.get("sub")
        token_tenant_id = payload.get("tenant_id")
        
        if user_id is None or token_tenant_id is None:
            print("AUTH_ERROR: Invalid payload structure")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
        request_tenant_id = request.headers.get("X-Tenant-ID")
        if request_tenant_id != token_tenant_id:
            print(f"AUTH_ERROR: Tenant mismatch: req={request_tenant_id}, tok={token_tenant_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access strictly forbidden")
            
    except JWTError as e:
        print(f"AUTH_ERROR: JWT decode failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        
    # Verify user exists and fetch live permissions
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        print("AUTH_ERROR: User not found in DB")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
    if not user.is_active:
        print("AUTH_ERROR: User is not active")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer active")

    role = db.query(Role).filter(Role.role_id == user.role_id).first()
    # Effective permissions apply per-user overrides on top of the role's
    # baseline grants, so admins can fine-tune a single user without minting
    # a new role for the exception.
    permissions = resolve_effective_permissions(db, user)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": role.name if role else "UNKNOWN",
        "full_name": user.full_name,
        "permissions": permissions
    }

class RequirePermission:
    """
    Dependency class to enforce RBAC on endpoints.
    Usage: @router.post("/", dependencies=[Depends(RequirePermission("patients:write"))])
    """
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    def __call__(self, current_user: dict = Depends(get_current_user)):
        if self.required_permission not in current_user["permissions"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Requires '{self.required_permission}'"
            )
        return current_user