"""Theatre migration: all tables present, WHO checklist + permissions seeded.

Direct-to-DB (no live server). Assumes `alembic upgrade head` + the theatre
seed have run against the test tenant (mayoclinic_db).
"""
from sqlalchemy import create_engine, text

from app.config.settings import settings

TENANT = "mayoclinic_db"
TABLES = [
    "theatre_rooms", "surgical_checklists", "surgical_cases", "surgical_checklist_runs",
    "operative_notes", "anaesthesia_records", "surgical_team_members",
    "surgical_consumables", "recovery_observations",
]


def _engine():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return create_engine(f"{base}/{TENANT}")


def test_all_theatre_tables_exist():
    engine = _engine()
    try:
        with engine.connect() as c:
            for t in TABLES:
                got = c.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar()
                assert got is not None, f"missing table: {t}"
    finally:
        engine.dispose()


def test_who_checklist_seeded():
    engine = _engine()
    try:
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM surgical_checklists")).scalar()
            assert n >= 15, f"expected >=15 WHO checklist items, got {n}"
            phases = {row[0] for row in c.execute(text("SELECT DISTINCT phase FROM surgical_checklists"))}
            assert phases == {"SignIn", "TimeOut", "SignOut"}, phases
    finally:
        engine.dispose()


def test_theatre_permissions_seeded():
    engine = _engine()
    try:
        with engine.connect() as c:
            n = c.execute(text(
                "SELECT count(*) FROM permissions WHERE codename IN ('theatre:read','theatre:manage')"
            )).scalar()
            assert n == 2, f"expected 2 theatre permissions, got {n}"
    finally:
        engine.dispose()
