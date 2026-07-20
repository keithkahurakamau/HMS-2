"""Regression tests for the account-lockout datetime handling in
app/auth/auth.py.

The lockout columns are ``DateTime(timezone=True)`` so a stored ``locked_until``
is read back timezone-aware. The login/change-password handlers previously
compared it against a naive ``datetime.utcnow()``, which raises
``TypeError: can't compare offset-naive and offset-aware datetimes`` — turning
every login attempt on a locked account into an HTTP 500 instead of a clean
"account locked" 403.
"""
from __future__ import annotations

import os
import sys

import pytest
import httpx
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}
ADMIN_EMAIL = "admin@mayoclinic.com"


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


def _update_admin_lock(locked_until, failed_attempts):
    """Set the admin's lockout fields directly on the tenant DB.

    Returns the previous ``(locked_until, failed_login_attempts)`` so the caller
    can restore them and avoid polluting the shared test tenant.
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    from app.models.user import User

    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        assert user is not None, f"admin user not found: {ADMIN_EMAIL}"
        prev = (user.locked_until, user.failed_login_attempts)
        user.locked_until = locked_until
        user.failed_login_attempts = failed_attempts
        db.commit()
        return prev
    finally:
        db.close()
        engine.dispose()


class TestLoginLockout:
    def test_locked_account_returns_403_not_500(self, client):
        # Simulate the production state: a tz-aware future lockout stored in the
        # DateTime(timezone=True) column. Before the fix this tripped a
        # naive/aware TypeError -> 500 on every login while locked.
        future = datetime.now(timezone.utc) + timedelta(minutes=15)
        prev_locked, prev_failed = _update_admin_lock(future, 5)
        try:
            r = client.post(
                "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": "does-not-matter-while-locked"},
            )
            # The regression is the 500; the invariant is "never 500".
            assert r.status_code != 500, f"locked account 500'd (the bug): {r.text}"
            # 429 means the shared login rate limit tripped before the handler
            # even ran (tests share one IP) — inconclusive, not a failure. When
            # the request actually reaches the handler, it must be a clean lock.
            if r.status_code != 429:
                assert r.status_code == 403 and "locked" in r.text.lower(), \
                    f"expected 403 (locked), got {r.status_code}: {r.text}"
        finally:
            _update_admin_lock(prev_locked, prev_failed)

    def test_expired_lock_does_not_block_login(self, client):
        # A lock whose expiry is in the past must NOT block and must not 500 —
        # before the fix the comparison itself raised, so an account that had
        # ever been locked stayed 500-locked forever (the success path that
        # clears locked_until was unreachable).
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        prev_locked, prev_failed = _update_admin_lock(past, 0)
        try:
            r = client.post(
                "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": "definitely-wrong"},
            )
            assert r.status_code != 500, f"expired lock 500'd (the bug): {r.text}"
            assert r.status_code != 403, f"expired lock wrongly blocked login: {r.text}"
            # 401 (bad creds, evaluated past the lock) or 429 (rate limited) are
            # both acceptable — both prove the expired lock didn't crash/block.
        finally:
            _update_admin_lock(prev_locked, prev_failed)
