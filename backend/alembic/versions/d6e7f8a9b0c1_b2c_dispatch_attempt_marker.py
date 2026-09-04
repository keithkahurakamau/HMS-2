"""B2C refund dispatch-attempt marker

Revision ID: d6e7f8a9b0c1
Revises: b4c5d6e7f8a9
Create Date: 2026-09-01 00:00:00.000000

Adds mpesa_refunds.first_dispatch_attempted_at, a nullable timestamp
written and committed by dispatch_refund BEFORE it calls Safaricom.

Why this is its own column rather than something derived from existing
ones: a refund's status column is only written AFTER a synchronous
response comes back, so "Approved" is structurally ambiguous between
"never dispatched" and "dispatched once, response lost before we learned
the outcome" (a read timeout, a dropped connection, a breaker trip on the
response leg after Safaricom already processed the request). Both cases
leave status == "Approved" and conversation_id == NULL; no query against
those two columns can tell them apart, because the fact that distinguishes
them was never recorded in the first place. This column exists purely to
record that fact, independent of whatever happens to the request
afterwards.

Idempotent, like its neighbours in this package.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_refunds ADD COLUMN IF NOT EXISTS "
        "first_dispatch_attempted_at TIMESTAMPTZ;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_refunds DROP COLUMN IF EXISTS first_dispatch_attempted_at;"
    )
