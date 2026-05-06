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
    access_token, refresh_token = create_tokens(subject=user.user_id, tenant_id=TENANT)
    db.close()
    return {"access_token": access_token, "refresh_token": refresh_token}


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
