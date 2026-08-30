"""Shared fixtures for the pharmacy starter catalogue suite.

Real Postgres, isolated database, no live server: same pattern as
tests/accounting and tests/receivables. The feature only touches
InventoryItem/Location (no new tables, per the design constraint), so the
seed here is intentionally tiny compared to the accounting suite's CoA
setup.
"""
from __future__ import annotations

import os
import sys
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

# Import every model module so Base.metadata has the full FK graph
# resolvable (inventory.py's StockTransfer/DispenseLog/InventoryUsageLog
# reference users/patients/medical_records even though this suite doesn't
# exercise them). Mirrors tests/accounting/conftest.py.
import app.models.master as _master                       # noqa: F401
import app.models.user as _user                            # noqa: F401
import app.models.patient as _patient                       # noqa: F401
import app.models.billing as _billing                       # noqa: F401
import app.models.clinical as _clinical                     # noqa: F401
import app.models.inventory as _inventory                   # noqa: F401
import app.models.wards as _wards                           # noqa: F401
import app.models.laboratory as _laboratory                 # noqa: F401
import app.models.radiology as _radiology                   # noqa: F401
import app.models.medical_history as _med_history           # noqa: F401
import app.models.audit as _audit                           # noqa: F401
import app.models.auth_tokens as _auth_tokens                # noqa: F401
import app.models.idempotency as _idempotency                # noqa: F401
import app.models.payhero as _payhero                        # noqa: F401
import app.models.breach as _breach                          # noqa: F401
import app.models.notification as _notification              # noqa: F401
import app.models.messaging as _messaging                    # noqa: F401
import app.models.settings as _settings                      # noqa: F401
import app.models.referral as _referral                      # noqa: F401
import app.models.cheque as _cheque                          # noqa: F401
import app.models.support as _support                        # noqa: F401
import app.models.accounting as _accounting                  # noqa: F401
from app.config.database import Base
from app.models.inventory import InventoryItem

TEST_DB = os.getenv("PHARMACY_STARTER_TEST_DB", "hms_pharmacy_starter_test")


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
def db(engine) -> Iterator[Session]:
    """Per-test session, truncated between tests so each test starts from
    an empty inventory catalog."""
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.rollback()
        for table in ("dispense_logs", "stock_batches", "inventory_items", "locations"):
            session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
        session.commit()
        session.close()


def seed_inventory_item(db: Session, *, name: str, unit_cost="55.00", unit_price="120.00") -> InventoryItem:
    """Drop in a pre-existing, already-priced inventory item: used to prove
    adoption never overwrites a hospital's own pricing work."""
    item = InventoryItem(
        item_code=f"SEED-{name[:6].upper()}",
        name=name,
        category="Drug",
        unit_cost=unit_cost,
        unit_price=unit_price,
        reorder_threshold=10,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
