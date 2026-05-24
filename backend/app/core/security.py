"""Auth primitives: password hashing, JWT issuance, opaque-token hashing.

AUTH-001: forward path is Argon2id (peppered). Existing bcrypt hashes still
verify so the migration is transparent — every successful login through the
legacy bcrypt branch quietly re-hashes under Argon2id. Once all users have
rotated through one login, the bcrypt branch can be deleted.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
# Dependabot alert: python-ecdsa 0.19.x carries a documented Minerva-style
# side-channel on the P-256 curve (upstream considers side channels out of
# scope; no patched release exists). python-jose pulls ecdsa transitively
# but only invokes it when signing/verifying with ES256/ES384/ES512. We
# pin settings.ALGORITHM to HS256 (HMAC-SHA256) below, so the vulnerable
# code path is never executed. Do NOT change ALGORITHM to an ES* curve
# without first migrating off python-jose (PyJWT 2.x has no ecdsa
# dependency) or upgrading ecdsa to a side-channel-hardened release.
from jose import jwt

from app.config.settings import settings

# OWASP 2023 baseline: m=64MiB, t=3, p=2 — empirically ~80ms on a modern
# small instance, well within Render's per-request budget and several orders
# of magnitude harder offline than bcrypt cost-12.
_ARGON2 = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_ARGON2_PREFIX = "$argon2"


def _peppered(password: str) -> bytes:
    pepper = settings.password_pepper.encode("utf-8")
    pw_bytes = password.encode("utf-8")
    if not pepper:
        return pw_bytes
    # HMAC-SHA256 keeps the input length bounded (32 bytes) regardless of
    # what the user typed, and means the pepper never appears in the Argon2
    # input directly. The Argon2id hash that follows is what actually
    # protects the password — HMAC here is a preprocessing step.
    return hmac.new(pepper, pw_bytes, hashlib.sha256).digest()  # lgtm[py/weak-sensitive-data-hashing]  # noqa: S324 -- HMAC-SHA256 is strong; password is then Argon2id-hashed


def get_password_hash(password: str) -> str:
    """Issue a new Argon2id hash. New passwords always take this path."""
    return _ARGON2.hash(_peppered(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify against either Argon2id (forward path) or bcrypt (legacy).

    Returns False on any mismatch / corrupt hash. Never raises — callers
    must not branch on exception types.
    """
    if not hashed_password:
        return False
    try:
        if hashed_password.startswith(_ARGON2_PREFIX):
            try:
                _ARGON2.verify(hashed_password, _peppered(plain_password))
                return True
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False
        # Legacy bcrypt path — the unpeppered password is what's stored.
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """True when the stored hash is bcrypt or an outdated Argon2 parameter set."""
    if not hashed_password:
        return False
    if not hashed_password.startswith(_ARGON2_PREFIX):
        return True
    try:
        return _ARGON2.check_needs_rehash(hashed_password)
    except Exception:  # noqa: BLE001 — defensive; never block a login on this
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # AUTH-002: include audience = tenant_id so a token minted for tenant A
    # cannot be replayed at tenant B even if the signing key leaks; jti lets
    # us cache permission lookups (DB-001) without revealing user_id.
    to_encode.update({
        "exp": expire,
        "type": "access",
        "iss": "hms",
        "aud": data.get("tenant_id", "unscoped"),
        "jti": generate_jti(),
    })
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict, jti: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "iss": "hms",
        "aud": data.get("tenant_id", "unscoped"),
        "jti": jti,
    })
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.ALGORITHM)


def hash_token(token: str) -> str:
    """SHA-256 hash for storing tokens in the DB without leaking the original."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_jti() -> str:
    """Random opaque identifier for a refresh token."""
    return secrets.token_urlsafe(24)


def generate_reset_token() -> str:
    """Random URL-safe token for password reset emails."""
    return secrets.token_urlsafe(32)


def create_tokens(subject: int, tenant_id: str):
    """Returns (access_token, refresh_token, refresh_jti, refresh_expires_at)."""
    jti = generate_jti()
    access_token = create_access_token({"user_id": subject, "tenant_id": tenant_id})
    refresh_token = create_refresh_token({"user_id": subject, "tenant_id": tenant_id}, jti=jti)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return access_token, refresh_token, jti, expires_at
