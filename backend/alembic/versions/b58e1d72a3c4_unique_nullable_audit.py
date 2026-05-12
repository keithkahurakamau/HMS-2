"""Normalize empty strings → NULL on every unique-but-nullable column

Revision ID: b58e1d72a3c4
Revises: a1c3b62e9f48
Create Date: 2026-05-12 18:45:00.000000

Same class of bug we hit on users.license_number can lurk on any
``Column(unique=True, nullable=True)``: PostgreSQL allows multiple NULLs but
treats two empty strings as equal, so a second insert from a form with a
blank field 500s on the unique index. This migration scrubs every such
column platform-wide so the next blank submission lands cleanly.

Columns covered (tenant DBs):
  - users.license_number       (already scrubbed in d4e8a1b29fc6, re-run no-op)
  - users.specialization       (NOT unique but kept tidy)
  - patients.inpatient_no
  - patients.id_number         (NOT unique but indexed; tidy)
  - lab_tests.specimen_id
  - mpesa_transactions.receipt_number
  - payments.transaction_reference

Each UPDATE is a no-op once converged so the migration is fully idempotent.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b58e1d72a3c4"
down_revision: Union[str, Sequence[str], None] = "a1c3b62e9f48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCRUB_STATEMENTS = [
    # (table, column)
    ("users",                "license_number"),
    ("users",                "specialization"),
    ("patients",             "inpatient_no"),
    ("patients",             "id_number"),
    ("lab_tests",            "specimen_id"),
    ("mpesa_transactions",   "receipt_number"),
    ("payments",             "transaction_reference"),
]


def upgrade() -> None:
    # Wrap each in an existence check so the migration is safe to run against
    # tenant DBs that may not have every optional table yet (e.g. fresh
    # tenants built before some module was first introduced).
    for table, column in _SCRUB_STATEMENTS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                ) THEN
                    UPDATE {table}
                       SET {column} = NULL
                     WHERE {column} IS NOT NULL AND btrim({column}) = '';
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    # Don't restore empty strings — the previous behavior was a bug.
    pass
