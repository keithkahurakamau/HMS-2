"""Pharmacy payment flow — link M-Pesa transactions to dispense logs

Revision ID: c8e21f47a309
Revises: a5d72f81b094
Create Date: 2026-05-17 10:00:00.000000

Adds `mpesa_transactions.dispense_id` (nullable FK to dispense_logs). When
an STK push is initiated from the pharmacy module, the resulting M-Pesa
transaction is linked to BOTH the invoice AND the originating dispense so
the callback can resolve back to the dispense without ambiguity.

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e21f47a309"
down_revision: Union[str, Sequence[str], None] = "a5d72f81b094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mpesa_transactions "
        "ADD COLUMN IF NOT EXISTS dispense_id INTEGER "
        "REFERENCES dispense_logs(dispense_id) ON DELETE SET NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_transactions_dispense_id "
        "ON mpesa_transactions (dispense_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mpesa_transactions_dispense_id;")
    op.execute("ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS dispense_id;")
