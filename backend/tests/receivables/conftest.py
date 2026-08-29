"""Fixtures for the receivables suite.

Real Postgres rather than SQLite, matching tests/accounting: the production
database is Postgres and Numeric semantics differ enough to matter when the
subject is money.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Import every model module so SQLAlchemy's Base.metadata catalogues every
# table it needs. subscription_billing is deliberately absent from
# migrate_all_tenants.py's import block (it is a master-DB-only concern,
# not part of the per-tenant bootstrap), so this conftest imports it
# explicitly rather than relying on that script.
import app.models.master as _master                       # noqa: F401,E402
import app.models.user as _user                           # noqa: F401,E402
import app.models.notification as _notification           # noqa: F401,E402
import app.models.subscription_billing as _sub            # noqa: F401,E402
from app.config.database import Base                      # noqa: E402
from app.models.master import SuperAdmin, Tenant            # noqa: E402
from app.models.subscription_billing import Subscription   # noqa: E402

TEST_DB = os.getenv("RECEIVABLES_TEST_DB", "hms_receivables_test")


@pytest.fixture(scope="session")
def engine():
    admin_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{TEST_DB}"
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def master_db(engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine)()
    yield session
    session.rollback()
    # Order matters: children before parents.
    for table in ("dunning_events", "invoice_payments", "subscription_invoices",
                  "subscriptions", "tenants", "superadmins"):
        session.execute(text(f"DELETE FROM {table}"))
    session.commit()
    session.close()


@pytest.fixture()
def client_superadmin(master_db) -> Iterator["TestClient"]:
    """A TestClient authenticated as a superadmin.

    require_superadmin is overridden directly rather than logging in through
    a real cookie, so the test never depends on JWT secrets or the superadmin
    login flow. get_master_db is overridden to hand back this test's own
    master_db session (bound to the receivables test database) instead of
    the app's real hms_master engine.

    A real SuperAdmin row is still created, because InvoicePayment.recorded_by
    is a foreign key into superadmins: recording a payment as an admin_id
    that doesn't exist would fail with a FK violation, not prove anything
    about the route.

    The app's CSRF middleware rejects unsafe methods (POST/PUT) without a
    matching csrf_token cookie and X-CSRF-Token header, so both are seeded
    with the same value up front, the same "double submit cookie" contract
    the middleware checks.
    """
    from fastapi.testclient import TestClient

    from app.config.database import get_master_db
    from app.core.dependencies import require_superadmin
    from app.main import app

    admin = SuperAdmin(email="test-superadmin@example.test", full_name="Test Superadmin",
                       hashed_password="not-a-real-hash", is_active=True)
    master_db.add(admin)
    master_db.commit()

    def _get_master_db():
        yield master_db

    def _require_superadmin():
        return {"admin_id": admin.admin_id, "email": admin.email, "full_name": admin.full_name}

    app.dependency_overrides[get_master_db] = _get_master_db
    app.dependency_overrides[require_superadmin] = _require_superadmin
    try:
        client = TestClient(app)
        client.cookies.set("csrf_token", "test-csrf-token")
        client.headers.update({"x-csrf-token": "test-csrf-token"})
        # Tests that need to assert attribution (e.g. a payment's
        # recorded_by) read the real id off the client rather than
        # assuming 1: DELETE-based cleanup between tests never resets the
        # superadmins sequence, so it climbs across the run.
        client.admin_id = admin.admin_id
        yield client
    finally:
        app.dependency_overrides.pop(get_master_db, None)
        app.dependency_overrides.pop(require_superadmin, None)


@pytest.fixture()
def client_anonymous() -> Iterator["TestClient"]:
    """A TestClient with no auth at all: require_superadmin is not
    overridden, so every receivables endpoint must reject it."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.cookies.set("csrf_token", "test-csrf-token")
    client.headers.update({"x-csrf-token": "test-csrf-token"})
    yield client


@pytest.fixture()
def make_tenant(master_db):
    """Create a tenant with an active subscription. Returns (tenant, subscription)."""
    def _make(name="Test Hospital", price=Decimal("18500.00"),
              started=date(2026, 1, 1), next_on=date(2026, 8, 1), paused=False):
        t = Tenant(name=name, domain=f"{name.lower().replace(' ', '')}.test",
                   db_name=f"db_{name.lower().replace(' ', '_')}", is_active=True)
        master_db.add(t)
        master_db.flush()
        s = Subscription(tenant_id=t.tenant_id, plan="standard", price_kes=price,
                         cycle="monthly", status="active", started_on=started,
                         next_invoice_on=next_on, reminders_paused=paused)
        master_db.add(s)
        master_db.commit()
        return t, s
    return _make
