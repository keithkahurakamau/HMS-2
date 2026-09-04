"""Reason-keyed surfacing throttle (New-3)

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-09-02 00:00:00.000000

Adds surfaced_reason (nullable) to both mpesa_transactions and
mpesa_refunds, alongside the surfaced_at column the previous revision
added.

surfaced_at alone throttles per ROW: once a row is surfaced, it never
notifies again, even if the row's status later changes (a human acts, or
a callback lands) and it becomes stuck a second time for a COMPLETELY
DIFFERENT reason. That silently drops the second alarm: money in flight
past 24 hours, and the only record is a log line asserting a human was
told, which is worse than no throttle at all. Comparing the reason text
before skipping a notification means a genuinely new problem on a
previously-surfaced row always notifies once.

Idempotent, like its neighbours in this package.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS "
        "surfaced_reason VARCHAR(255);"
    )
    op.execute(
        "ALTER TABLE mpesa_refunds ADD COLUMN IF NOT EXISTS "
        "surfaced_reason VARCHAR(255);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_refunds DROP COLUMN IF EXISTS surfaced_reason;"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS surfaced_reason;"
    )
