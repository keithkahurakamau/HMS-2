from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.config.database import get_db
from app.models.user import User, Role, Permission
from app.schemas.user import LoginRequest, UserResponse
from app.core.security import verify_password, create_access_token, create_refresh_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

@router.post("/login")
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    # 1. Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail=f"Account locked. Try again later.")

    # 2. Verify Password
    if not verify_password(request.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 3. Successful login - Reset attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    # 4. Fetch RBAC Permissions
    role = db.query(Role).filter(Role.role_id == user.role_id).first()
    permissions = [p.codename for p in role.permissions] if role else []

    # 5. Generate Tokens
    token_data = {"sub": user.email, "user_id": user.user_id, "role": role.name if role else "UNKNOWN"}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    # 6. Set HttpOnly Cookies (Secure, SameSite)
    response.set_cookie(
        key="access_token", value=access_token, httponly=True, 
        secure=True, samesite="none", max_age=15 * 60
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True, 
        secure=True, samesite="none", max_age=7 * 24 * 60 * 60
    )

    return {
        "message": "Login successful",
        "user": {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "role": role.name if role else "UNKNOWN",
            "permissions": permissions
        }
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, secure=True, samesite="none")
    response.delete_cookie(key="refresh_token", httponly=True, secure=True, samesite="none")
    return {"message": "Logged out successfully"}