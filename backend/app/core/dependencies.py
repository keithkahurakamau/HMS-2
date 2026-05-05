from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.config.settings import settings
from app.models.user import User, Role

def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """
    Extracts the JWT access token from the HttpOnly cookie.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated. No access token cookie found."
        )
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("user_id")
        token_tenant_id: str = payload.get("tenant_id")
        
        if user_id is None or token_tenant_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
        request_tenant_id = request.headers.get("X-Tenant-ID")
        if request_tenant_id != token_tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access strictly forbidden")
            
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        
    # Verify user exists and fetch live permissions
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer active")

    role = db.query(Role).filter(Role.role_id == user.role_id).first()
    permissions = [p.codename for p in role.permissions] if role else []
        
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
        if "users:manage" in current_user["permissions"]:
            return current_user # Admins automatically bypass specific permission checks
            
        if self.required_permission not in current_user["permissions"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Requires '{self.required_permission}'"
            )
        return current_user