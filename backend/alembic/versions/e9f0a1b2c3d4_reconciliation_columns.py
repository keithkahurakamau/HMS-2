"""Reconciliation columns: refund status-query correlation, surfaced_at

Revision ID: e9f0a1b2c3d4
Revises: d6e7f8a9b0c1
Create Date: 2026-09-02 00:00:00.000000

Adds three nullable columns Task 8's reconciliation job needs:

  * mpesa_refunds.status_query_conversation_id: Safaricom's own id for a
    reconciliation Transaction Status query fired against a Processing
    refund's own conversation_id (Daraja's TransactionStatusQuery accepts
    an OriginalConversationID as an alternative to a receipt-based
    TransactionID, which a Processing B2C payout does not have yet). A
    separate column from conversation_id on purpose: writing there would
    destroy the B2C dispatch's own correlation id and the evidence
    b2c.py's double-dispatch alarm depends on.
  * mpesa_transactions.surfaced_at and mpesa_refunds.surfaced_at: set once,
    the first time reconciliation surfaces a row stuck past 24 hours (or,
    for a refund Approved with a dispatch marker already set, past the
    stuck-refund threshold at all). Checked before notifying again, so a
    stuck row does not renotify a danger-category channel every 15-minute
    cron run forever.

Idempotent, like its neighbours in this package.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_refunds ADD COLUMN IF NOT EXISTS "
        "status_query_conversation_id VARCHAR(64);"
    )
    op.execute(
        "ALTER TABLE mpesa_refunds ADD COLUMN IF NOT EXISTS surfaced_at TIMESTAMPTZ;"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS surfaced_at TIMESTAMPTZ;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS surfaced_at;"
    )
    op.execute(
        "ALTER TABLE mpesa_refunds DROP COLUMN IF EXISTS surfaced_at;"
    )
    op.execute(
        "ALTER TABLE mpesa_refunds DROP COLUMN IF EXISTS status_query_conversation_id;"
    )
