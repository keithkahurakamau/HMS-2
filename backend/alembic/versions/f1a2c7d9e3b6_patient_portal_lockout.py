"""Patient-portal brute-force lockout columns

Audit M-3: the self-service patient portal authenticates with low-entropy
knowledge factors (OP number + DOB + last-4 phone). The per-IP rate limit
doesn't stop a rotating-IP attacker who already knows a target's OP number
from brute-forcing the 10^4 phone-suffix space. We add a per-patient failed
attempt counter + temporary lock, mirroring the staff-login lockout.

  + portal_failed_attempts  integer      NOT NULL DEFAULT 0
  + portal_locked_until      timestamptz  (nullable)

Both wrapped in IF NOT EXISTS so re-running on a tenant that already has the
columns is a no-op. The matching idempotent patches are appended to
TENANT_COLUMN_PATCHES in backend/scripts/migrate_all_tenants.py so
legacy-stamped tenants pick them up at the next deploy.

Revision ID: f1a2c7d9e3b6
Revises: b9e3f47a21c8
Create Date: 2026-06-23 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f1a2c7d9e3b6"
down_revision: Union[str, Sequence[str], None] = "b9e3f47a21c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE patients "
        "ADD COLUMN IF NOT EXISTS portal_failed_attempts INTEGER NOT NULL DEFAULT 0;"
    )
    op.execute(
        "ALTER TABLE patients "
        "ADD COLUMN IF NOT EXISTS portal_locked_until TIMESTAMPTZ;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS portal_locked_until;")
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS portal_failed_attempts;")
