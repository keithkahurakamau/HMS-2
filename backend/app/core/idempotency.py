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
    persist_and_commit(
        db, persist, resp_dict, status=200,
        user_id=current_user["user_id"], endpoint="billing.process-payment",
        key=req.idempotency_key, body=req.dict(),
    )

The guard takes a Postgres advisory transaction lock on the (user_id, key)
tuple so concurrent duplicates serialise instead of double-executing
business logic (IDEM-002). That lock is only held for as long as the
CALLER's transaction stays open: a caller who commits mid-flight for its
own reasons (a slow downstream call it does not want to hold the lock
across; see app/services/daraja/stk.py's _reserve_pending for a documented
example) ends the transaction and releases the lock before persist() ever
runs, so a second caller can slip past the re-check and reach persist()
too. persist_and_commit exists to make that specific, narrow race safe: it
commits the cache write, and if it collides with a concurrent winner's
INSERT on the (user_id, endpoint, key) primary key, it rolls back and
replays the winner's cached response instead of surfacing the collision as
an uncaught IntegrityError. Use plain ``persist(...); db.commit()`` when
the caller's own transaction is guaranteed not to have released the
guard's lock early; use persist_and_commit whenever it might have.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey

# The name Postgres reports for IdempotencyKey's primary key (user_id,
# endpoint, key). Only THIS constraint means "someone else already cached
# the answer for this exact tuple": any other IntegrityError is a real,
# unrelated bug and must be re-raised, not mistaken for a race and turned
# into a wrong cached response. Same pattern as
# app/services/daraja/stk.py's _PENDING_GUARD_CONSTRAINTS.
_CACHE_ROW_CONSTRAINT = "pk_idempotency_keys"


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
    # Non-cryptographic use: derive a stable Postgres advisory-lock id from
    # the (user, endpoint, key) tuple. SHA-256 here is overkill but free.
    lock_id = int(hashlib.sha256(f"{user_id}:{endpoint}:{key}".encode()).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    # Re-check after acquiring the lock — the previous holder may have just
    # written the cache row. Same fingerprint check as the pre-lock read
    # above, and for the same reason: a concurrent caller who reused this
    # key with a DIFFERENT body must still get 409 here, not the winner's
    # unrelated cached answer, whether the mismatch was visible before the
    # lock was taken or only appeared while this caller was waiting for it.
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


def persist_and_commit(
    db: Session,
    persist: Callable[..., None],
    resp: dict,
    *,
    status: int = 200,
    user_id: int,
    endpoint: str,
    key: str,
    body: Any,
) -> dict:
    """Call `persist(resp, status=status)` and commit, tolerant of the race
    described in the module docstring: a caller whose OWN transaction
    already released idempotent_guard's advisory lock mid-flight (before
    persist() ever ran) can have a concurrent duplicate slip past the
    re-check and reach persist() too. Both then try to INSERT the same
    (user_id, endpoint, key) primary key.

    On that specific collision (pk_idempotency_keys), the loser rolls back
    its own attempt and re-reads idempotent_guard for the same tuple,
    returning the winner's now-committed response exactly as a normal
    cache hit would, so neither caller sees an uncaught IntegrityError and
    both see the SAME answer. Re-reading is safe without re-locking here:
    Postgres does not report a duplicate-key error until the other
    transaction holding that key has actually committed, so by the time
    this collision surfaces the winner's row is guaranteed visible.

    Any OTHER IntegrityError is re-raised, never mistaken for "someone else
    already cached the answer": a blind catch here would swallow a real,
    unrelated constraint failure (a NOT NULL slip, a bad FK) behind a wrong
    cached response.
    """
    persist(resp, status=status)
    try:
        db.commit()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint != _CACHE_ROW_CONSTRAINT:
            raise
        db.rollback()
        cached, _ = idempotent_guard(db, user_id=user_id, endpoint=endpoint, key=key, body=body)
        if cached is not None:
            return cached
        raise
    return resp
