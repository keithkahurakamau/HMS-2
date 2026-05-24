"""Per-tenant M-Pesa tills: env, shortcode type, C2B register state, match basis

Revision ID: e7c63a82d51f
Revises: d18b5e94c620
Create Date: 2026-05-17 14:00:00.000000

Each tenant already has its own MpesaConfig row. This migration teaches
the row to carry the operational settings the Daraja flows need:
- environment (sandbox / production) so the service picks the right base URL
- shortcode_type (paybill / till) — affects how customers pay and what
  Daraja's RegisterURL accepts
- c2b_short_code (some merchants have a different till for collections
  than the one used for STK)
- c2b_response_type + c2b_registered_at — track whether the C2B URLs
  have been pushed to Safaricom yet
- last_test_at + last_test_status — surface "did the test STK actually
  work" on the admin UI

MpesaTransaction grows to support direct-to-till matching:
- transaction_type (STK / C2B)
- bill_ref_number (the 'account number' the customer typed at the till)
- match_basis (invoice_id / opd_number / phone / manual / unmatched)

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7c63a82d51f"
down_revision: Union[str, Sequence[str], None] = "d18b5e94c620"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # mpesa_configs ──────────────────────────────────────────────────────────
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS environment VARCHAR(20) NOT NULL DEFAULT 'sandbox';")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS shortcode_type VARCHAR(20) NOT NULL DEFAULT 'paybill';")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_short_code VARCHAR(20);")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_response_type VARCHAR(20) NOT NULL DEFAULT 'Completed';")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_registered_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_status VARCHAR(40);")
    op.execute("ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_message TEXT;")
    op.execute(
        "ALTER TABLE mpesa_configs DROP CONSTRAINT IF EXISTS ck_mpesa_configs_environment;"
    )
    op.execute(
        "ALTER TABLE mpesa_configs ADD CONSTRAINT ck_mpesa_configs_environment "
        "CHECK (environment IN ('sandbox','production'));"
    )
    op.execute(
        "ALTER TABLE mpesa_configs DROP CONSTRAINT IF EXISTS ck_mpesa_configs_shortcode_type;"
    )
    op.execute(
        "ALTER TABLE mpesa_configs ADD CONSTRAINT ck_mpesa_configs_shortcode_type "
        "CHECK (shortcode_type IN ('paybill','till'));"
    )

    # mpesa_transactions ─────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE mpesa_transactions "
        "ADD COLUMN IF NOT EXISTS transaction_type VARCHAR(10) NOT NULL DEFAULT 'STK';"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions DROP CONSTRAINT IF EXISTS ck_mpesa_transactions_type;"
    )
    op.execute(
        "ALTER TABLE mpesa_transactions ADD CONSTRAINT ck_mpesa_transactions_type "
        "CHECK (transaction_type IN ('STK','C2B'));"
    )
    op.execute("ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS bill_ref_number VARCHAR(80);")
    op.execute("ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS match_basis VARCHAR(20);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_transactions_bill_ref "
        "ON mpesa_transactions (bill_ref_number);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_transactions_match_basis "
        "ON mpesa_transactions (match_basis);"
    )


def downgrade() -> None:
    # mpesa_transactions
    op.execute("DROP INDEX IF EXISTS ix_mpesa_transactions_match_basis;")
    op.execute("DROP INDEX IF EXISTS ix_mpesa_transactions_bill_ref;")
    op.execute("ALTER TABLE mpesa_transactions DROP CONSTRAINT IF EXISTS ck_mpesa_transactions_type;")
    op.execute("ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS match_basis;")
    op.execute("ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS bill_ref_number;")
    op.execute("ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS transaction_type;")

    # mpesa_configs
    op.execute("ALTER TABLE mpesa_configs DROP CONSTRAINT IF EXISTS ck_mpesa_configs_shortcode_type;")
    op.execute("ALTER TABLE mpesa_configs DROP CONSTRAINT IF EXISTS ck_mpesa_configs_environment;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS last_test_message;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS last_test_status;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS last_test_at;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS c2b_registered_at;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS c2b_response_type;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS c2b_short_code;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS shortcode_type;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS environment;")
