"""Add feature_flags, plan_limits, notes to tenants

Revision ID: c7a2e94d318f
Revises: b27f4e91d563
Create Date: 2026-05-12 15:30:00.000000

Per-tenant flexibility configuration that lives on the master ``tenants``
table. JSON-encoded TEXT keeps the schema flat — new flags / limits ship as
data, not migrations. This migration targets the master DB; tenant DBs
already have a no-op pass because the columns live elsewhere.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7a2e94d318f"
down_revision: Union[str, Sequence[str], None] = "b27f4e91d563"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded so it's safe to re-run against either master OR tenant DBs. On a
    # tenant DB the ``tenants`` table won't exist; the WHERE-clause short-
    # circuits cleanly.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_flags TEXT;
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan_limits TEXT;
                ALTER TABLE tenants ADD COLUMN IF NOT EXISTS notes TEXT;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tenants') THEN
                ALTER TABLE tenants DROP COLUMN IF EXISTS notes;
                ALTER TABLE tenants DROP COLUMN IF EXISTS plan_limits;
                ALTER TABLE tenants DROP COLUMN IF EXISTS feature_flags;
            END IF;
        END
        $$;
        """
    )
