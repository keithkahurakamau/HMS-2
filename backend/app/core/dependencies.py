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
        if self.required_permission not in current_user["permissions"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Requires '{self.required_permission}'"
            )
        return current_user