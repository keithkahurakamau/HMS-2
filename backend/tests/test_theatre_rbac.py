"""Theatre module registration + DB-backed permissions (server-free)."""
from sqlalchemy import create_engine, text

from app.config.settings import settings
from app.core.modules import MODULES, URL_PREFIX_MAP

TENANT = "mayoclinic_db"


def test_theatre_module_registered():
    keys = {m.key for m in MODULES}
    assert "theatre" in keys
    assert ("/api/theatre/", "theatre") in URL_PREFIX_MAP


def test_theatre_permissions_in_db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    try:
        with engine.connect() as c:
            n = c.execute(text(
                "SELECT count(*) FROM permissions WHERE codename IN ('theatre:read','theatre:manage')"
            )).scalar()
            assert n == 2
    finally:
        engine.dispose()
