"""Idempotency primitives shared by every mutating route.

Usage (inside a request handler that already has ``db`` + ``current_user``):

    cached, persist = idempotent_guard(
        db,
        user_id=current_user["user_id"],
        endpoint="billing.process-payment",
        key=req.idempotency_key,
        body=req.dict(),
    )
    if cached is not None:
        return cached
    # ... do the real work ...
    persist(resp_dict, status=200)
    db.commit()

The guard takes a Postgres advisory transaction lock on the (user_id, key)
tuple so concurrent duplicates serialise instead of double-executing
business logic (IDEM-002).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey


def _fingerprint(body: Any) -> str:
    try:
        canonical = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = repr(body)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def idempotent_guard(
    db: Session,
    *,
    user_id: int,
    endpoint: str,
    key: str,
    body: Any,
) -> Tuple[Optional[dict], Optional[Callable[..., None]]]:
    """Return ``(cached_response, persist_fn)``.

    * If the (user, endpoint, key) tuple already exists with the same body
      fingerprint, ``cached_response`` is the prior result and
      ``persist_fn`` is None (caller should ``return`` immediately).
    * If the tuple exists with a different fingerprint, raises HTTP 409.
    * Otherwise, ``cached_response`` is None and ``persist_fn(resp_dict,
      status=200)`` should be called by the caller before ``db.commit()`` so
      the next replay gets the same answer.
    """
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency key is required")

    fp = _fingerprint(body)
    row = (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.key == key,
        )
        .first()
    )
    if row is not None:
        if row.request_fingerprint and row.request_fingerprint != fp:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key reused with a different request body",
            )
        try:
            return json.loads(row.response_body), None
        except (ValueError, TypeError):
            # Corrupt cached response — treat as a miss and overwrite below.
            db.delete(row)
            db.flush()

    # Serialise concurrent duplicates on the same (user, key) tuple. The lock
    # is held for the rest of the transaction so a second request arriving
    # while the first is still executing will block here, then read the cache.
    lock_id = int(hashlib.sha1(f"{user_id}:{endpoint}:{key}".encode()).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    # Re-check after acquiring the lock — the previous holder may have just
    # written the cache row.
    row = (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.key == key,
        )
        .first()
    )
    if row is not None:
        try:
            return json.loads(row.response_body), None
        except (ValueError, TypeError):
            db.delete(row)
            db.flush()

    def _persist(resp: dict, status: int = 200) -> None:
        db.add(
            IdempotencyKey(
                user_id=user_id,
                endpoint=endpoint,
                key=key,
                request_fingerprint=fp,
                status_code=status,
                response_body=json.dumps(resp, default=str),
            )
        )

    return None, _persist
