"""Idempotency-key storage scoped per-user, per-endpoint, per-fingerprint.

IDEM-001: prior schema used the raw key as the sole primary key, so two
distinct callers who minted the same UUID would collide; more practically,
an attacker who learned another user's key could replay it and receive the
cached response (information disclosure on payment IDs / invoice state).
The new schema scopes keys to (user_id, endpoint, key) and stores a
SHA-256 fingerprint of the request body so the same key reused with a
different payload returns HTTP 409 instead of the wrong cached answer.
"""
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.config.database import Base


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    # Scope fields — together they form the natural primary key.
    user_id = Column(Integer, nullable=False, default=0)
    endpoint = Column(String(96), nullable=False, default="")
    key = Column(String(255), nullable=False)

    # SHA-256 hex of the canonical-JSON request body. Reusing a key with a
    # different body is a programmer error (or an attack) — surface it as 409.
    request_fingerprint = Column(String(64), nullable=False, default="")
    status_code = Column(Integer, nullable=False, default=200)
    response_body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "endpoint", "key", name="pk_idempotency_keys"),
        Index("ix_idempotency_created", "created_at"),
    )
