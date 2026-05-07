from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base


class RefreshToken(Base):
    """
    Server-side refresh token registry. Issued at login; rotated on /auth/refresh.
    Storing the *hash* of the JWT lets us revoke tokens server-side and detect
    reuse — a property the bare JWT cannot provide.
    """
    __tablename__ = "refresh_tokens"

    token_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    # SHA-256 of the JWT string. We never store the raw token.
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    # Unique JWT id ("jti") — embedded in the JWT itself for fast lookups.
    jti = Column(String(64), unique=True, index=True, nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    # Set when this token has been rotated — points at the new token's id.
    replaced_by_id = Column(Integer, ForeignKey("refresh_tokens.token_id"), nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)


Index("ix_refresh_tokens_user_active", RefreshToken.user_id, RefreshToken.revoked)


class PasswordResetToken(Base):
    """
    Single-use password reset token for the forgot-password flow.
    The token in the email is random + signed; only the SHA-256 hash is stored
    so a database read alone cannot enable account takeover.
    """
    __tablename__ = "password_reset_tokens"

    reset_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    requested_ip = Column(String(45), nullable=True)
