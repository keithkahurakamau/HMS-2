"""C2B Transaction Status correlation columns on mpesa_transactions

Revision ID: b4c5d6e7f8a9
Revises: f2a3b4c5d6e7
Create Date: 2026-09-01 00:00:00.000000

C2B verification is asynchronous: a Transaction Status query is fired for a
receipt, and the real verdict arrives later on a separate result callback,
not in the query's own synchronous response. That callback identifies which
row it is answering by ConversationID, not by receipt or invoice, since the
receipt is exactly what the callback is trying to confirm. Two nullable,
indexed columns hold what Safaricom handed back when the query was sent, so
the later result can be correlated back to the row that asked:

  conversation_id             Safaricom's own id for this specific query,
                               the correlation key the result callback is
                               matched against.
  originator_conversation_id  Our own id for the request, echoed back;
                               kept for diagnostics and any future retry
                               logic, not used for correlation today.

Mirrors MpesaRefund's existing columns of the same name (B2C already needed
this pattern), except neither is unique here: unlike a refund's own
originator id (which IS the retry-idempotency key), a transaction's status
query is fire-and-forget from this table's point of view, and nothing here
retries it with the same id.

Idempotent, like its neighbours in this package.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS "
        "conversation_id VARCHAR(64);"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS "
        "originator_conversation_id VARCHAR(64);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_transactions_conversation_id "
        "ON mpesa_transactions (conversation_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mpesa_transactions_conversation_id;")
    op.execute(
        "ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS originator_conversation_id;"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS conversation_id;"
    )
