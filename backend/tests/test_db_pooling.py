"""Engine-pooling behaviour for the PgBouncer switch.

`DB_POOLER_ENABLED` flips every SQLAlchemy engine between a normal QueuePool
(direct-to-Postgres) and NullPool (behind PgBouncer, which owns pooling). These
are pure unit checks on `_engine_kwargs()` — no DB connection required.
"""
from sqlalchemy.pool import NullPool

from app.config import database
from app.config.settings import settings


def test_engine_kwargs_direct_uses_queuepool():
    original = settings.DB_POOLER_ENABLED
    settings.DB_POOLER_ENABLED = False
    try:
        kw = database._engine_kwargs()
        assert "poolclass" not in kw
        assert kw["pool_size"] == settings.DB_POOL_SIZE
        assert kw["max_overflow"] == settings.DB_MAX_OVERFLOW
        assert kw["pool_pre_ping"] is True
    finally:
        settings.DB_POOLER_ENABLED = original


def test_engine_kwargs_pooler_uses_nullpool():
    original = settings.DB_POOLER_ENABLED
    settings.DB_POOLER_ENABLED = True
    try:
        kw = database._engine_kwargs()
        # NullPool: the pooler pools; SQLAlchemy must not add its own pool sizing.
        assert kw.get("poolclass") is NullPool
        assert "pool_size" not in kw
        assert "max_overflow" not in kw
    finally:
        settings.DB_POOLER_ENABLED = original
