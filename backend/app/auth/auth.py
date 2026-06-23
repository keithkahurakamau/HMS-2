import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
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
    needs_rehash,
    create_tokens,
    create_access_token,
    create_refresh_token,
    hash_token,
    generate_jti,
    generate_reset_token,
)
from app.core.limiter import limiter
from app.services.auth_emails import send_password_reset_email
from app.utils.audit import log_audit
from pydantic import BaseModel, EmailStr, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# =====================================================================
# Cookie helpers
# =====================================================================
def _cookie_params():
    is_production = settings.is_production
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
    # Audit AUTH-001: prior shape was {user_id, new_password} with no
    # authentication factor — any caller who knew a user_id could rewrite
    # that user's password. We now require the email and the current/temp
    # password as a knowledge factor and look the user up server-side from
    # the email (never trust a client-supplied user_id).
    email: EmailStr
    current_password: str
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

    # AUTH-003 (audit M-2): block account enumeration. Previously the
    # not-found path returned immediately (no password hash computed) and
    # disabled / unknown accounts returned distinct messages + status codes —
    # both a response-content oracle AND a timing oracle for "is this a real
    # account?". We now:
    #   • run a dummy Argon2id verify on the not-found / inactive path so the
    #     wall-clock cost matches the real verify branch (same trick used by
    #     /change-password), and
    #   • collapse not-found, inactive, and wrong-password into one generic
    #     401 "Invalid credentials".
    # Lockout still returns 403 (the caller is, by definition, a known account
    # that has already authenticated enough to trip the counter, so there is no
    # new enumeration signal — and the UX benefit of a clear message matters).
    generic_failure = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
    )

    if not user or not user.is_active:
        # Equalize timing with the success path — Argon2id verify dominates the
        # handler's wall-clock cost.
        verify_password(payload.password, _DUMMY_PW_HASH)
        raise generic_failure

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
    # AUTH-001: transparently re-hash legacy bcrypt / outdated-param hashes
    # under Argon2id now that we have the plaintext password verified.
    if needs_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(payload.password)
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
        payload = jwt.decode(
            raw_refresh,
            settings.jwt_secret,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},  # AUTH-002 rollover; tenant_id is the aud
        )
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
        # L-5: make the abuse visible. Previously reuse was handled silently
        # (just a 401) — emit a security event + durable audit row so an
        # operator can investigate a possibly-stolen token, not just guess.
        client_ip = request.client.host if request.client else None
        logger.warning(
            "SECURITY: refresh-token reuse detected — user_id=%s jti=%s ip=%s — all sessions revoked",
            record.user_id, jti, client_ip,
        )
        try:
            log_audit(
                db, record.user_id, "SECURITY", "RefreshToken", str(jti),
                None,
                {"event": "refresh_token_reuse", "action": "all_sessions_revoked",
                 "user_agent": request.headers.get("user-agent")},
                client_ip,
            )
        except Exception:  # noqa: BLE001 — never let audit logging block the revoke
            logger.exception("L-5: failed to write refresh-reuse audit row")
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
                settings.jwt_secret,
                algorithms=[settings.ALGORITHM],
                # We want to revoke even expired tokens; ditto don't gate
                # logout on AUTH-002's aud check during rollover.
                options={"verify_exp": False, "verify_aud": False},
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
# Change password (forced first-login flow + future self-service change)
# =====================================================================
# Module-level dummy bcrypt hash used solely to equalize timing on the
# "user not found" branch so the endpoint can't be used as an email
# enumerator. Computed once at import (≈250 ms cost on cold boot,
# acceptable). We deliberately keep this in-module so a stale hash in
# settings can't accidentally be reused as a real password.
_DUMMY_PW_HASH = get_password_hash("dummy-password-for-constant-time-only-not-a-real-cred")


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(request: Request, payload: ChangePasswordRequest, db: Session = Depends(get_db)):
    """Knowledge-factor-protected password change.

    Same endpoint serves the forced-first-login flow (where current_password
    is the temp password issued at provisioning) and any future "change my
    password from settings" UI. AUTH-001: prior implementation was
    unauthenticated — taking {user_id, new_password} let anyone rewrite
    anyone's password by guessing/iterating the integer user_id.

    Failure responses are intentionally generic and time-equalized to block
    email enumeration.
    """
    generic_failure = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )

    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.is_active:
        # Equalize timing with the success path — bcrypt comparison dominates
        # the wall-clock cost of the handler.
        verify_password(payload.current_password, _DUMMY_PW_HASH)
        raise generic_failure

    # Honour the same lockout policy as /login so this endpoint can't be used
    # as an unrate-limited side channel against a locked account.
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account locked. Try again later.",
        )

    if not verify_password(payload.current_password, user.hashed_password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db.commit()
        raise generic_failure

    user.hashed_password = get_password_hash(payload.new_password)
    user.must_change_password = False
    user.failed_login_attempts = 0
    user.locked_until = None
    # Invalidate any existing refresh sessions for this user — possible
    # compromise of the prior password.
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
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Issues a single-use password reset token. Always returns 200 — never leak
    whether an email is registered. When EMAIL_ENABLED is on, the reset link is
    emailed via the configured SMTP relay. When it's off (dev/CI) we surface the
    token inline (under "dev_token") so the flow can still be tested end-to-end.
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

        # Dispatch the email after the response is sent (BackgroundTasks). The
        # link must carry the tenant id — reset tokens live in the tenant DB.
        send_password_reset_email(
            background_tasks,
            to=user.email,
            raw_token=raw_token,
            tenant_id=request.headers.get("X-Tenant-ID"),
            recipient_name=getattr(user, "full_name", None),
        )

        # M-1: never return the reset token in the HTTP response body — even in
        # dev a single APP_ENV slip (or a staging env that forgot to set
        # APP_ENV=production) would leak live reset tokens to any caller. When no
        # email goes out (dev/CI) we log it server-side so the flow stays
        # testable, but only outside production.
        if not settings.EMAIL_ENABLED and not settings.is_production:
            logger.warning("[dev] password reset token for %s: %s", user.email, raw_token)

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
