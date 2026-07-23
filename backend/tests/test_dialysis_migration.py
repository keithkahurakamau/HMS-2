"""Dialysis migration: all tables present, checklists + permissions seeded.

Direct-to-DB checks (no live server needed). Assumes `alembic upgrade head`
and the dialysis seed have run against the test tenant (mayoclinic_db).
"""
from sqlalchemy import create_engine, text

from app.config.settings import settings

TENANT = "mayoclinic_db"
TABLES = [
    "dialysis_checklists", "dialysis_machines", "vascular_accesses",
    "dialysis_schedules", "dialysis_orders", "dialysis_observations",
    "dialysis_complications", "dialysis_adequacy", "dialysis_consumables",
    "dialysis_checklist_runs",
]


def _engine():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return create_engine(f"{base}/{TENANT}")


def test_all_dialysis_tables_exist():
    engine = _engine()
    try:
        with engine.connect() as c:
            for t in TABLES:
                got = c.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar()
                assert got is not None, f"missing table: {t}"
    finally:
        engine.dispose()


def test_checklists_seeded():
    engine = _engine()
    try:
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM dialysis_checklists")).scalar()
            assert n >= 5, f"expected >=5 seeded checklists, got {n}"
    finally:
        engine.dispose()


def test_dialysis_permissions_seeded():
    engine = _engine()
    try:
        with engine.connect() as c:
            n = c.execute(text(
                "SELECT count(*) FROM permissions "
                "WHERE codename IN ('dialysis:read','dialysis:manage')"
            )).scalar()
            assert n == 2, f"expected 2 dialysis permissions, got {n}"

            # The active-session partial unique index must exist.
            idx = c.execute(text(
                "SELECT to_regclass('public.uq_dialysis_active_per_patient')"
            )).scalar()
            assert idx is not None, "partial unique index missing"
    finally:
        engine.dispose()
