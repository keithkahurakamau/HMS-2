"""Pharmacy walk-in support — make invoices.patient_id nullable

Revision ID: d18b5e94c620
Revises: c8e21f47a309
Create Date: 2026-05-17 12:00:00.000000

Walk-in (over-the-counter) pharmacy sales don't have a patient record.
The dispense flow used to skip invoice creation for those — leaving us
with no way to collect payment via the new STK / cash flow. Dropping
the NOT NULL on invoices.patient_id lets us create real invoices for
walk-ins and reuse the full payment + receipt pipeline.

Idempotent.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d18b5e94c620"
down_revision: Union[str, Sequence[str], None] = "c8e21f47a309"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE invoices ALTER COLUMN patient_id DROP NOT NULL;")


def downgrade() -> None:
    # Drop walk-in rows before reinstating NOT NULL so the migration succeeds.
    op.execute("DELETE FROM invoices WHERE patient_id IS NULL;")
    op.execute("ALTER TABLE invoices ALTER COLUMN patient_id SET NOT NULL;")
