from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.config.database import get_db
from app.config.settings import settings
from app.models.user import User
from app.core.security import verify_password, create_tokens
from app.core.limiter import limiter
from pydantic import BaseModel, EmailStr, field_validator

router = APIRouter(prefix="/api/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    
    if not user:
        # Prevent timing attacks by returning generic error
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    # Lockout check
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Account locked. Try again in {remaining} minutes."
        )

    # Password validation
    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Success reset
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    # Block login if forced password change is required
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PASSWORD_CHANGE_REQUIRED",
            headers={"X-User-ID": str(user.user_id)}
        )

    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-Tenant-ID header is required")

    # Token generation with tenant binding
    access_token, refresh_token = create_tokens(subject=user.user_id, tenant_id=tenant_id)

    # Secure Cookie configurations
    is_production = settings.MPESA_ENV.lower() == "production"
    cookie_params = {
        "httponly": True,
        "secure": is_production, # Must be True in production for SameSite=None
        "samesite": "none" if is_production else "lax",
        "domain": None,
        "path": "/"
    }

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_params
    )
    
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **cookie_params
    )

    # Fetch permissions for the frontend payload
    permissions = [perm.codename for perm in user.role.permissions] if user.role else []

    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else None,
        "permissions": permissions
    }

@router.post("/logout")
async def logout(response: Response):
    is_production = settings.MPESA_ENV.lower() == "production"
    cookie_params = {
        "httponly": True,
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
        "domain": None,
        "path": "/"
    }
    response.delete_cookie("access_token", **cookie_params)
    response.delete_cookie("refresh_token", **cookie_params)
    return {"message": "Logged out securely"}


class ChangePasswordRequest(BaseModel):
    user_id: int
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v):
        import re
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

@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(request: Request, payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    """Allows a user to set a new password when must_change_password is True."""
    from app.core.security import get_password_hash
    user = db.query(User).filter(User.user_id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    db.commit()
    return {"message": "Password updated successfully. Please log in with your new credentials."}