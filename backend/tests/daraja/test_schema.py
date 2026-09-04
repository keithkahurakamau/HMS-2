import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction
from app.config.database import Base
from app.config.settings import settings
from app.utils.encryption import decrypt_data
from app.services.daraja.tokens import (
    mint_callback_token,
    store_callback_token,
    token_lookup_hash,
)


def _load_migration_module():
    """Load the e1f2a3b4c5d6 revision by file path.

    alembic/versions has no __init__.py (alembic loads its revisions
    dynamically, not as a normal package), so this is the straightforward
    way to reach CALLBACK_TOKEN_PAIR_CHECK_SQL/NAME from a test: importing
    them, rather than retyping the constraint text here, is what keeps the
    test honest about testing the constraint the migration actually applies
    instead of a hand-copied lookalike that could silently drift from it.
    """
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "alembic" / "versions" / "e1f2a3b4c5d6_daraja_schema.py"
    )
    spec = importlib.util.spec_from_file_location("daraja_schema_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tables_registered_in_metadata():
    names = set(Base.metadata.tables)
    assert {"mpesa_configs", "mpesa_transactions", "mpesa_refunds"} <= names


def test_receipt_number_is_unique():
    """The replay defence. A repeated callback must not double-credit."""
    assert MpesaTransaction.__table__.c.receipt_number.unique is True


def test_originator_conversation_id_is_unique():
    """The double-refund defence."""
    assert MpesaRefund.__table__.c.originator_conversation_id.unique is True


def test_callback_token_is_unique():
    assert MpesaConfig.__table__.c.callback_token_lookup.unique is True


def test_no_plaintext_secret_columns():
    """Every credential column must carry the _encrypted suffix."""
    suspicious = {
        "consumer_key", "consumer_secret", "passkey", "initiator_password",
        "callback_token",
    }
    assert suspicious.isdisjoint(set(MpesaConfig.__table__.c.keys()))


def test_token_lookup_hash_is_deterministic_and_not_plaintext():
    token = mint_callback_token()
    first = token_lookup_hash(token)
    second = token_lookup_hash(token)
    assert first == second
    assert first != token


class _StubConfig:
    """Plain stand-in for MpesaConfig with just the two token attributes.

    Instantiating the real MpesaConfig here would force SQLAlchemy to
    configure every mapper in the app's declarative registry (including
    relationships on unrelated models this isolated test suite never loads),
    which is unrelated to what this test is checking: that
    store_callback_token sets its two attributes consistently on whatever
    object it is given.
    """

    callback_token_encrypted = None
    callback_token_lookup = None


def test_store_callback_token_sets_both_columns_consistently():
    config = _StubConfig()
    token = mint_callback_token()
    store_callback_token(config, token)

    assert config.callback_token_encrypted is not None
    assert config.callback_token_lookup is not None
    assert config.callback_token_lookup == token_lookup_hash(token)
    assert config.callback_token_encrypted != token
    assert decrypt_data(config.callback_token_encrypted) == token


def test_callback_token_pair_check_constraint_rejects_half_written_row():
    """Proves the CHECK constraint at the database level, not merely in Python.

    store_callback_token setting both columns together only proves the
    helper is well-behaved; it says nothing about a direct attribute write,
    a raw SQL UPDATE, or a hand-applied data fix that skips the helper
    entirely. Only a database CHECK constraint holds against those paths,
    so this test goes straight at Postgres: it opens a real connection to
    the locally configured database (the same one tests/conftest.py already
    uses for mayoclinic_db), builds a session-scoped temporary table (never
    persisted, dropped automatically at the end of the transaction, and
    never touching mayoclinic_db or any other real table) carrying the
    exact constraint text the migration applies, and confirms Postgres
    itself rejects a half-written pair while accepting a complete pair and
    an empty pair.
    """
    migration = _load_migration_module()
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(
                    "CREATE TEMP TABLE ck_callback_token_pair_probe ("
                    "callback_token_encrypted VARCHAR(255), "
                    "callback_token_lookup VARCHAR(64), "
                    f"CONSTRAINT {migration.CALLBACK_TOKEN_PAIR_CHECK_NAME} "
                    f"CHECK ({migration.CALLBACK_TOKEN_PAIR_CHECK_SQL})"
                    ") ON COMMIT DROP"
                ))

                # Both NULL: accepted (no token minted yet).
                conn.execute(text(
                    "INSERT INTO ck_callback_token_pair_probe VALUES (NULL, NULL)"
                ))
                # Both set: accepted (a complete pair).
                conn.execute(text(
                    "INSERT INTO ck_callback_token_pair_probe VALUES ('enc', 'lookup')"
                ))

                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(text(
                        "INSERT INTO ck_callback_token_pair_probe "
                        "VALUES ('enc-only', NULL)"
                    ))
                savepoint.rollback()

                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(text(
                        "INSERT INTO ck_callback_token_pair_probe "
                        "VALUES (NULL, 'lookup-only')"
                    ))
                savepoint.rollback()
            finally:
                trans.rollback()
    finally:
        engine.dispose()
