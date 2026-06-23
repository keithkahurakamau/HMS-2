"""Widen PHI columns to TEXT for column-level encryption (audit M-1)

The EncryptedString type (app/utils/db_types.py) stores Fernet ciphertext,
which is non-deterministic and ~100+ chars even for short inputs. Columns that
were VARCHAR(n) must be widened to TEXT or the ciphertext would be truncated.

This migration ONLY changes column storage type (VARCHAR(n) -> TEXT). It does
not encrypt existing rows — EncryptedString reads tolerate plaintext, and new
/ updated rows encrypt automatically. Run scripts/backfill_phi_encryption.py
once per tenant to encrypt historical rows at rest.

Columns already TEXT (patients.allergies / chronic_conditions / notes,
medical_history_entries.description) need no DDL and are omitted.

ALTER ... TYPE TEXT on a column that is already TEXT is a harmless no-op, so
this migration is safe to re-run.

Revision ID: c3e8b1f4a7d2
Revises: f1a2c7d9e3b6
Create Date: 2026-06-23 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3e8b1f4a7d2"
down_revision: Union[str, Sequence[str], None] = "f1a2c7d9e3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs whose VARCHAR(n) must become TEXT to hold ciphertext.
_WIDEN: list[tuple[str, str]] = [
    ("patients", "postal_address"),
    ("patients", "residence"),
    ("patients", "occupation"),
    ("patients", "employer_name"),
    ("patients", "nok_name"),
    ("patients", "nok_contact"),
    ("medical_history_entries", "title"),
]


def upgrade() -> None:
    for table, col in _WIDEN:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TEXT;")


def downgrade() -> None:
    # Intentionally a no-op. Reverting TEXT -> VARCHAR(n) would truncate any
    # rows that have already been encrypted (ciphertext exceeds the old width),
    # silently corrupting PHI. The widened TEXT type is backward-compatible with
    # plaintext, so leaving it in place on downgrade is safe.
    pass
