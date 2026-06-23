"""Encrypt searchable patient identifiers + add blind indexes (audit M-1 ph.2)

telephone_1 / id_number / email move to EncryptedString (Fernet). Their old
plaintext btree indexes become useless on ciphertext and are dropped; a
deterministic blind-index column (*_bidx, HMAC-SHA256) is added + indexed so
exact-match lookup (duplicate detection, find-by-phone/ID) still works. Substring
search on these fields is intentionally dropped (M-1 phase 2 decision).

  patients.id_number    VARCHAR -> TEXT   (encrypted)
  patients.telephone_1  VARCHAR -> TEXT   (encrypted)
  patients.email        VARCHAR -> TEXT   (encrypted)
  + patients.id_number_bidx    VARCHAR(64) indexed
  + patients.telephone_1_bidx  VARCHAR(64) indexed
  + patients.email_bidx        VARCHAR(64) indexed

The blind-index VALUES are populated by:
  * the SQLAlchemy before_insert/before_update listener for new/changed rows, and
  * scripts/backfill_phi_encryption.py for historical rows (run post-deploy).

All statements are guarded (IF [NOT] EXISTS) so the migration is re-runnable and
matches what create_all builds on a fresh tenant.

Revision ID: a6f2d9c4e7b1
Revises: c3e8b1f4a7d2
Create Date: 2026-06-23 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a6f2d9c4e7b1"
down_revision: Union[str, Sequence[str], None] = "c3e8b1f4a7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Widen to TEXT so Fernet ciphertext fits.
    op.execute("ALTER TABLE patients ALTER COLUMN id_number TYPE TEXT;")
    op.execute("ALTER TABLE patients ALTER COLUMN telephone_1 TYPE TEXT;")
    op.execute("ALTER TABLE patients ALTER COLUMN email TYPE TEXT;")

    # Drop the now-useless plaintext indexes (SQLAlchemy's index=True names).
    op.execute("DROP INDEX IF EXISTS ix_patients_id_number;")
    op.execute("DROP INDEX IF EXISTS ix_patients_telephone_1;")

    # Blind-index columns + their indexes.
    op.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS id_number_bidx VARCHAR(64);")
    op.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS telephone_1_bidx VARCHAR(64);")
    op.execute("ALTER TABLE patients ADD COLUMN IF NOT EXISTS email_bidx VARCHAR(64);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_id_number_bidx ON patients (id_number_bidx);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_telephone_1_bidx ON patients (telephone_1_bidx);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_patients_email_bidx ON patients (email_bidx);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_patients_email_bidx;")
    op.execute("DROP INDEX IF EXISTS ix_patients_telephone_1_bidx;")
    op.execute("DROP INDEX IF EXISTS ix_patients_id_number_bidx;")
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS email_bidx;")
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS telephone_1_bidx;")
    op.execute("ALTER TABLE patients DROP COLUMN IF EXISTS id_number_bidx;")
    # Type stays TEXT on downgrade — reverting to VARCHAR would truncate any
    # rows already encrypted, corrupting PHI.
