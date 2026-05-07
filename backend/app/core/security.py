import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
import bcrypt
from app.config.settings import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)


def get_password_hash(password: str) -> str:
    """Generates a bcrypt hash from a plaintext password."""
    password_byte_enc = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_byte_enc, salt)
    return hashed_password.decode('utf-8')


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, jti: str):
    """Refresh tokens carry a unique jti so we can revoke specific sessions."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def hash_token(token: str) -> str:
    """SHA-256 hash for storing tokens in the DB without leaking the original."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


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
