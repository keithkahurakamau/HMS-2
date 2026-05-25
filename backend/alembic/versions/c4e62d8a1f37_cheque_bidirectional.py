"""Bidirectional cheque register — outgoing direction

Adds the columns needed to track cheques the HOSPITAL ISSUES alongside
the existing incoming-only flow.

  + direction         varchar(20)   default 'incoming'
  + payee_name        varchar(255)
  + payee_type        varchar(40)
  + date_issued       timestamptz
  + dispatch_date     timestamptz
  + return_reason     varchar(255)  (outgoing equivalent of bounce_reason)
  + stop_reason       varchar(255)  (stop-payment instruction reason)
  + idx_cheque_dir_status (direction, status)

Existing rows are left as `direction='incoming'` (the default), which
matches their semantics — every previously-entered cheque was something
the hospital received from someone else.

Every statement is wrapped in IF NOT EXISTS so re-running on a tenant
that already has the columns is a no-op. The matching idempotent block
is also appended to TENANT_COLUMN_PATCHES in
backend/scripts/migrate_all_tenants.py so legacy-stamped tenants pick
the change up at the next deploy without needing a manual patch.

Revision ID: c4e62d8a1f37
Revises: ab3c9e5d27f8
Create Date: 2026-05-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4e62d8a1f37"
down_revision: Union[str, Sequence[str], None] = "ab3c9e5d27f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PATCHES = [
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS direction VARCHAR(20) NOT NULL DEFAULT 'incoming';",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS payee_name VARCHAR(255);",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS payee_type VARCHAR(40);",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS date_issued TIMESTAMPTZ;",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS dispatch_date TIMESTAMPTZ;",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS return_reason VARCHAR(255);",
    "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS stop_reason VARCHAR(255);",
    # Relax NOT NULL on drawer_name / drawer_type so outgoing cheques can
    # leave those fields blank. Existing rows are unaffected (they all have
    # values) and the application schema enforces "incoming requires
    # drawer_name" / "outgoing requires payee_name" loudly anyway.
    "ALTER TABLE cheques ALTER COLUMN drawer_name DROP NOT NULL;",
    "ALTER TABLE cheques ALTER COLUMN drawer_type DROP NOT NULL;",
    "CREATE INDEX IF NOT EXISTS idx_cheque_dir_status ON cheques (direction, status);",
    "CREATE INDEX IF NOT EXISTS ix_cheques_direction ON cheques (direction);",
]


def upgrade() -> None:
    for stmt in PATCHES:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_cheques_direction;")
    op.execute("DROP INDEX IF EXISTS idx_cheque_dir_status;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS stop_reason;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS return_reason;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS dispatch_date;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS date_issued;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS payee_type;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS payee_name;")
    op.execute("ALTER TABLE cheques DROP COLUMN IF EXISTS direction;")
    # NOTE: not re-adding NOT NULL on drawer_* — existing rows are fine
    # without it and re-adding would fail on outgoing rows.
