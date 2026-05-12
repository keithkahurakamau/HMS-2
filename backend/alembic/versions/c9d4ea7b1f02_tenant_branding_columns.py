"""Add tenant branding columns to master.tenants

Revision ID: c9d4ea7b1f02
Revises: b58e1d72a3c4
Create Date: 2026-05-12 19:30:00.000000

The ``tenants`` table lives on the master DB only — alembic's per-tenant
runner won't see it. We still ship this migration for parity with the
master-DB patches in ``scripts/migrate_all_tenants.py``: anyone driving
master DB upgrades through alembic directly (e.g. local dev with a single
master URL) gets the same result.

Columns added (all nullable):
  - logo_data_url        TEXT
  - background_data_url  TEXT
  - brand_primary        VARCHAR(16)
  - brand_accent         VARCHAR(16)
  - print_templates      TEXT  (JSON-encoded)

Idempotent — uses IF NOT EXISTS so re-running on a converged DB is a no-op.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c9d4ea7b1f02"
down_revision: Union[str, Sequence[str], None] = "b58e1d72a3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS logo_data_url TEXT;")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS background_data_url TEXT;")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS brand_primary VARCHAR(16);")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS brand_accent VARCHAR(16);")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS print_templates TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS print_templates;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS brand_accent;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS brand_primary;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS background_data_url;")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS logo_data_url;")
