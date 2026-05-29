"""Per-tenant Pay Hero webhook secret

In the operator model each hospital owns its OWN Pay Hero account, so each
account signs callbacks with its own HMAC secret. A single platform-wide
PAYHERO_WEBHOOK_SECRET cannot verify all of them, so we store an optional
per-tenant secret on payhero_configs (encrypted at rest). When NULL,
verify_payhero falls back to the global secret (the operator's own account).

  + payhero_webhook_secret_encrypted  varchar(255)  (nullable)

Wrapped in IF NOT EXISTS so re-running on a tenant that already has the
column is a no-op. The matching idempotent patch is appended to
TENANT_COLUMN_PATCHES in backend/scripts/migrate_all_tenants.py so
legacy-stamped tenants pick it up at the next deploy.

Revision ID: d7a1f9c34b85
Revises: c4e62d8a1f37
Create Date: 2026-05-29 16:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d7a1f9c34b85"
down_revision: Union[str, Sequence[str], None] = "c4e62d8a1f37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE payhero_configs "
        "ADD COLUMN IF NOT EXISTS payhero_webhook_secret_encrypted VARCHAR(255);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE payhero_configs "
        "DROP COLUMN IF EXISTS payhero_webhook_secret_encrypted;"
    )
