"""Master-DB schema for the subscription rail: platform_mpesa_*.

These tables belong to the MASTER database (hms_master) only. Tenant
databases must never see them. That guarantee lives at the source level,
not the runtime one: `backend/scripts/migrate_all_tenants.py` runs an
unfiltered `Base.metadata.create_all()` against every tenant engine using
whatever is listed in its `from app.models import (...)` block, so a model
module reachable from that block is a model module created inside every
hospital database. This project has hit that exact failure twice already
(see platform_payhero, which is deliberately absent from the same block),
so the regression guard below reads the script's source rather than its
runtime metadata.
"""
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.config.database import Base
from app.config.settings import settings
from app.models.platform_mpesa import PlatformMpesaConfig, PlatformMpesaTransaction
from app.services.daraja.tokens import mint_callback_token, token_lookup_hash


def _migrate_script_source() -> str:
    path = Path(__file__).parents[2] / "scripts" / "migrate_all_tenants.py"
    return path.read_text()


def test_platform_tables_are_not_created_in_tenant_databases():
    """Regression guard for the footgun this codebase has hit twice.

    If app.models.platform_mpesa ever lands in the migrate script's import
    block, create_all() puts the operator's billing tables in every hospital
    database. This test reads the script's source rather than its runtime
    metadata, because the failure is a source-level edit.
    """
    src = _migrate_script_source()
    import_block = src.split("from app.models import (")[1].split(")")[0]
    assert "platform_mpesa" not in import_block
    assert "platform_mpesa_configs" in src  # but it IS in MASTER_DB_PATCHES
    assert "platform_mpesa_transactions" in src


def test_master_patches_create_both_tables_idempotently():
    src = _migrate_script_source()
    assert "CREATE TABLE IF NOT EXISTS platform_mpesa_configs" in src
    assert "CREATE TABLE IF NOT EXISTS platform_mpesa_transactions" in src


def test_tables_registered_in_metadata():
    """The model file itself is legitimate SQLAlchemy metadata: it is only
    excluded from the tenant migration script's import list, not broken."""
    names = set(Base.metadata.tables)
    assert {"platform_mpesa_configs", "platform_mpesa_transactions"} <= names


def test_config_defaults_to_unconfigured_sandbox():
    """MediFleet holds no Daraja credentials of its own (Go-Live for the
    MediFleet shortcode has not been completed). An unconfigured platform
    config must default to sandbox with no credentials, and that has to be
    a normal state, not something that reads as broken configuration."""
    assert PlatformMpesaConfig.__table__.c.environment.default.arg == "sandbox"
    for col in ("consumer_key_encrypted", "consumer_secret_encrypted", "passkey_encrypted"):
        assert PlatformMpesaConfig.__table__.c[col].nullable is True


def test_no_plaintext_secret_columns():
    """Every credential column must carry the _encrypted suffix."""
    suspicious = {
        "consumer_key", "consumer_secret", "passkey", "initiator_password",
        "callback_token",
    }
    assert suspicious.isdisjoint(set(PlatformMpesaConfig.__table__.c.keys()))


def test_callback_token_lookup_is_unique():
    assert PlatformMpesaConfig.__table__.c.callback_token_lookup.unique is True


def test_external_reference_and_receipt_number_are_unique():
    assert PlatformMpesaTransaction.__table__.c.external_reference.unique is True
    assert PlatformMpesaTransaction.__table__.c.receipt_number.unique is True


def test_subscription_invoice_id_is_a_nullable_fk_into_the_receivables_ledger():
    """The whole point of this table: a subscription STK payment must be
    linkable to a real invoice in the receivables ledger, not left sitting
    as an untracked receipt nobody ages. Nullable because a transaction can
    exist before it is matched to an invoice."""
    col = PlatformMpesaTransaction.__table__.c.subscription_invoice_id
    assert col.nullable is True
    fk_targets = {fk.target_fullname for fk in col.foreign_keys}
    assert "subscription_invoices.id" in fk_targets


def test_token_lookup_hash_is_deterministic_and_not_plaintext():
    """The platform config is expected to reuse the same daraja.tokens
    helpers as the tenant config, so both columns are always written in
    the same consistent pair rather than through a bespoke path."""
    token = mint_callback_token()
    first = token_lookup_hash(token)
    second = token_lookup_hash(token)
    assert first == second
    assert first != token


def _callback_token_pair_check_sql() -> str:
    for constraint in PlatformMpesaConfig.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and (
            constraint.name == "ck_platform_mpesa_configs_callback_token_pair"
        ):
            return str(constraint.sqltext)
    raise AssertionError("ck_platform_mpesa_configs_callback_token_pair not found on the model")


def test_master_patches_carry_the_same_check_constraint_name_as_the_model():
    """Guards against the model and the raw-SQL MASTER_DB_PATCHES entry
    drifting apart: the constraint has to exist in both places under the
    same name, since MASTER_DB_PATCHES (not Alembic) is what actually
    creates it in production."""
    assert "ck_platform_mpesa_configs_callback_token_pair" in _migrate_script_source()


def test_callback_token_pair_check_constraint_rejects_half_written_row():
    """Proves the CHECK constraint at the database level, not merely in
    Python. Mirrors tests/daraja/test_schema.py's equivalent test for the
    tenant-side mpesa_configs constraint: opens a real connection to the
    locally configured database, builds a session-scoped temporary table
    (dropped automatically, never touching any real table) carrying the
    exact constraint text the model declares, and confirms Postgres itself
    rejects a half-written pair while accepting a complete pair and an
    empty pair.
    """
    check_sql = _callback_token_pair_check_sql()
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(
                    "CREATE TEMP TABLE ck_platform_callback_token_pair_probe ("
                    "callback_token_encrypted VARCHAR(255), "
                    "callback_token_lookup VARCHAR(64), "
                    "CONSTRAINT ck_platform_mpesa_configs_callback_token_pair "
                    f"CHECK ({check_sql})"
                    ") ON COMMIT DROP"
                ))

                # Both NULL: accepted (no token minted yet).
                conn.execute(text(
                    "INSERT INTO ck_platform_callback_token_pair_probe VALUES (NULL, NULL)"
                ))
                # Both set: accepted (a complete pair).
                conn.execute(text(
                    "INSERT INTO ck_platform_callback_token_pair_probe VALUES ('enc', 'lookup')"
                ))

                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(text(
                        "INSERT INTO ck_platform_callback_token_pair_probe "
                        "VALUES ('enc-only', NULL)"
                    ))
                savepoint.rollback()

                savepoint = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(text(
                        "INSERT INTO ck_platform_callback_token_pair_probe "
                        "VALUES (NULL, 'lookup-only')"
                    ))
                savepoint.rollback()
            finally:
                trans.rollback()
    finally:
        engine.dispose()
