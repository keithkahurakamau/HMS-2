"""Normalize blank users.license_number to NULL

Revision ID: d4e8a1b29fc6
Revises: c7a2e94d318f
Create Date: 2026-05-12 16:00:00.000000

The previous version of POST /api/admin/users persisted an empty string when
the operator left license_number blank. PostgreSQL treats two empty strings
as equal, so the second insert tripped the unique index and produced a 500.
The new code coerces blanks to NULL at the validator, but tenants already
have an empty-string row in users — scrub it (and the matching specialization
case) so the next insert from the UI works without further intervention.

Idempotent: re-running is safe because the UPDATE is a no-op once converged.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e8a1b29fc6"
down_revision: Union[str, Sequence[str], None] = "c7a2e94d318f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wrap in DO so the migration is a no-op on the master DB (which doesn't
    # have a `users` table); tenant DBs do the cleanup.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
                UPDATE users SET license_number = NULL
                 WHERE license_number IS NOT NULL AND btrim(license_number) = '';
                UPDATE users SET specialization = NULL
                 WHERE specialization IS NOT NULL AND btrim(specialization) = '';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Don't restore empty strings — the previous behavior was a bug.
    pass
