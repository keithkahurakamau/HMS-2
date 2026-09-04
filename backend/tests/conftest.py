"""
Test configuration: generates JWT tokens directly to bypass the 5/min login rate limit.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.core.security import create_tokens
from app.models.user import User

TENANT = "mayoclinic_db"
DOMAIN = "mayoclinic.com"

def _get_tenant_db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    return sessionmaker(bind=engine)()


def make_cookies(email: str) -> dict:
    """Generate real JWT cookies for a user without hitting the login endpoint."""
    db = _get_tenant_db()
    user = db.query(User).filter(User.email == email).first()
    assert user is not None, f"User not found: {email}"
    access_token, refresh_token, _jti, _expires_at = create_tokens(subject=user.user_id, tenant_id=TENANT)
    db.close()
    # csrf_token rides along so a per-request `cookies=` override still
    # satisfies double-submit; see TEST_CSRF_TOKEN below.
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "csrf_token": TEST_CSRF_TOKEN,
    }


# ─── Module-level cookie fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_cookies():
    return make_cookies(f"admin@{DOMAIN}")

@pytest.fixture(scope="module")
def doctor_cookies():
    return make_cookies(f"dr.kahura@{DOMAIN}")

@pytest.fixture(scope="module")
def nurse_cookies():
    return make_cookies(f"nurse.joy@{DOMAIN}")

@pytest.fixture(scope="module")
def pharmacist_cookies():
    return make_cookies(f"pharm.keith@{DOMAIN}")

@pytest.fixture(scope="module")
def lab_cookies():
    return make_cookies(f"lab.alice@{DOMAIN}")

@pytest.fixture(scope="module")
def radiologist_cookies():
    return make_cookies(f"rad.mwangi@{DOMAIN}")

@pytest.fixture(scope="module")
def receptionist_cookies():
    return make_cookies(f"rec.brian@{DOMAIN}")


# ─── CSRF for the live-server suites ──────────────────────────────────────────
#
# app/main.py's csrf_middleware enforces double-submit on every unsafe method:
# a `csrf_token` cookie must match an `X-CSRF-Token` header. A browser gets the
# cookie from any GET and its JS echoes it back in the header. These suites
# mint their JWT cookies directly (to dodge the login rate limit) and so never
# performed that handshake, which failed every POST, PATCH, PUT and DELETE in
# them with a 403 regardless of what the endpoint under test actually did.
#
# The token value does not need to be unpredictable here. Double-submit proves
# the caller can both read and write the same value, which a cross-site
# attacker cannot; a fixed value in a test harness proves exactly that and
# keeps the fixtures deterministic.
TEST_CSRF_TOKEN = "test-csrf-token-fixed-for-the-suite"


# Patched at conftest IMPORT time, not in a fixture. The suites build their
# httpx.Client in a module-scoped fixture, which pytest instantiates before any
# function-scoped autouse fixture runs, so a monkeypatch fixture would apply
# too late to matter.
def _patch_httpx_client_for_csrf() -> None:
    import httpx

    if getattr(httpx.Client, "_csrf_patched", False):
        return

    original_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault("X-CSRF-Token", TEST_CSRF_TOKEN)
        kwargs["headers"] = headers
        cookies = dict(kwargs.get("cookies") or {})
        cookies.setdefault("csrf_token", TEST_CSRF_TOKEN)
        kwargs["cookies"] = cookies
        return original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init
    httpx.Client._csrf_patched = True


_patch_httpx_client_for_csrf()
