from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.config.database import get_db
from app.config.settings import settings
from app.models.user import User
from app.core.security import verify_password, create_tokens
from app.core.limiter import limiter
from pydantic import BaseModel, EmailStr

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

    # Token generation
    access_token, refresh_token = create_tokens(subject=user.user_id)

    # Secure Cookie configurations
    cookie_params = {
        "httponly": True,
        "secure": True, # Ensure this is True in Vercel/Render production
        "samesite": "none",
        "domain": None # Adjust if cross-subdomain auth is needed
    }

    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_params
    )
    
    response.set_cookie(
        key="refresh_token",
        value=f"Bearer {refresh_token}",
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