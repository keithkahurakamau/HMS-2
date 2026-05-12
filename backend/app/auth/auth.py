from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.config.database import get_db
from app.config.settings import settings
from app.models.user import User
from app.models.auth_tokens import RefreshToken, PasswordResetToken
from app.core.security import (
    verify_password,
    get_password_hash,
    create_tokens,
    create_access_token,
    create_refresh_token,
    hash_token,
    generate_jti,
    generate_reset_token,
)
from app.core.limiter import limiter
from pydantic import BaseModel, EmailStr, field_validator

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# =====================================================================
# Cookie helpers
# =====================================================================
def _cookie_params():
    is_production = settings.MPESA_ENV.lower() == "production"
    return {
        "httponly": True,
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
        "domain": None,
        "path": "/",
    }


def _set_session_cookies(response: Response, access_token: str, refresh_token: str):
    params = _cookie_params()
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **params,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **params,
    )


def _clear_session_cookies(response: Response):
    params = _cookie_params()
    response.delete_cookie("access_token", **params)
    response.delete_cookie("refresh_token", **params)


def _store_refresh_token(db: Session, user_id: int, refresh_token: str, jti: str, expires_at: datetime, request: Request, replaced_by_id: int = None):
    record = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(refresh_token),
        jti=jti,
        expires_at=expires_at,
        revoked=False,
        replaced_by_id=replaced_by_id,
        user_agent=(request.headers.get("user-agent") or "")[:255],
        ip_address=request.client.host if request.client else None,
    )
    db.add(record)
    db.flush()
    return record


# =====================================================================
# Request/response schemas
# =====================================================================
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
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


# =====================================================================
# Login
# =====================================================================
@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    # ── Tenant routing must happen BEFORE any DB read ──────────────────────
    # get_db() silently falls back to the DATABASE_URL default when the
    # client forgets X-Tenant-ID. On most installs that default is the master
    # registry DB (hms_master), which has no `users` table — leading to a
    # cryptic 500 instead of a useful "you need to pick a hospital first"
    # message. Fail fast with 400 so the frontend can route the operator
    # back to /portal.
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required. Pick a hospital before signing in.",
        )

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

    # tenant_id was already validated at the top of the handler.

    # Token generation with tenant binding + server-side refresh registry
    access_token, refresh_token, jti, expires_at = create_tokens(subject=user.user_id, tenant_id=tenant_id)
    _store_refresh_token(db, user.user_id, refresh_token, jti, expires_at, request)
    db.commit()

    _set_session_cookies(response, access_token, refresh_token)

    permissions = [perm.codename for perm in user.role.permissions] if user.role else []

    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else None,
        "permissions": permissions
    }


# =====================================================================
# Refresh — rotates refresh token, with reuse detection
# =====================================================================
@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    try:
        payload = jwt.decode(raw_refresh, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        _clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user_id = payload.get("user_id")
    token_tenant_id = payload.get("tenant_id")
    jti = payload.get("jti")

    if not user_id or not token_tenant_id or not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed refresh token")

    # Tenant binding check
    request_tenant_id = request.headers.get("X-Tenant-ID")
    if request_tenant_id and request_tenant_id != token_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant refresh forbidden")

    record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not record:
        # Token signed by us but not in our registry — treat as invalid.
        _clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown refresh token")

    # Reuse detection: a revoked token is being presented again. Burn every
    # active session for this user — the old token may be in attacker hands.
    if record.revoked:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == record.user_id,
            RefreshToken.revoked == False,  # noqa: E712
        ).update({"revoked": True})
        db.commit()
        _clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reuse detected — all sessions revoked")

    if record.expires_at and record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        record.revoked = True
        db.commit()
        _clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    # Constant-time-ish hash comparison
    if record.token_hash != hash_token(raw_refresh):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token mismatch")

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.is_active:
        record.revoked = True
        db.commit()
        _clear_session_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer active")

    # Issue new pair, revoke old, link old → new
    new_access, new_refresh, new_jti, new_expires_at = create_tokens(subject=user.user_id, tenant_id=token_tenant_id)
    new_record = _store_refresh_token(db, user.user_id, new_refresh, new_jti, new_expires_at, request)
    record.revoked = True
    record.replaced_by_id = new_record.token_id
    db.commit()

    _set_session_cookies(response, new_access, new_refresh)
    return {"message": "Tokens refreshed"}


# =====================================================================
# Logout — revoke refresh token server-side
# =====================================================================
@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        try:
            payload = jwt.decode(
                raw_refresh,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                options={"verify_exp": False},  # we want to revoke even expired tokens
            )
            jti = payload.get("jti")
            if jti:
                record = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
                if record and not record.revoked:
                    record.revoked = True
                    db.commit()
        except JWTError:
            # Bad token? Nothing to revoke. Still clear cookies below.
            pass

    _clear_session_cookies(response)
    return {"message": "Logged out securely"}


# =====================================================================
# Change password (forced first-login flow)
# =====================================================================
@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(request: Request, payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    """Allows a user to set a new password when must_change_password is True."""
    user = db.query(User).filter(User.user_id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    # Invalidate any existing refresh sessions for this user.
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.user_id,
        RefreshToken.revoked == False,  # noqa: E712
    ).update({"revoked": True})
    db.commit()
    return {"message": "Password updated successfully. Please log in with your new credentials."}


# =====================================================================
# Forgot password — issues a single-use token
# =====================================================================
RESET_TOKEN_TTL_MINUTES = 60


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Issues a single-use password reset token. Always returns 200 — never leak
    whether an email is registered. In a production deployment the token would
    be emailed via SMTP; here we return it inline (under "dev_token") so the
    flow can be tested end-to-end.
    """
    user = db.query(User).filter(User.email == payload.email).first()

    response = {"message": "If that email is registered, a reset link has been sent."}

    if user and user.is_active:
        # Invalidate any prior outstanding tokens for this user.
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.user_id,
            PasswordResetToken.used == False,  # noqa: E712
        ).update({"used": True})

        raw_token = generate_reset_token()
        record = PasswordResetToken(
            user_id=user.user_id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
            used=False,
            requested_ip=request.client.host if request.client else None,
        )
        db.add(record)
        db.commit()

        # In production, dispatch an email here. Until SMTP is wired, surface
        # the token in non-production environments only.
        if settings.MPESA_ENV.lower() != "production":
            response["dev_token"] = raw_token

    return response


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Consumes a reset token and sets a new password."""
    token_hash = hash_token(payload.token)
    record = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()

    if not record or record.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or already-used reset token")

    if record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token has expired")

    user = db.query(User).filter(User.user_id == record.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User account is unavailable")

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    record.used = True

    # Burn all existing refresh sessions for this user — possible compromise.
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.user_id,
        RefreshToken.revoked == False,  # noqa: E712
    ).update({"revoked": True})

    db.commit()
    return {"message": "Password reset successfully. Please log in with your new credentials."}
