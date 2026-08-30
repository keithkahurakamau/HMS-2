"""Per-department tills, and one pending push per invoice/dispense

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-30 00:00:00.000000

Two related but different problems, in one revision because they touch the
same two tables.

1. Per-department tills. mpesa_configs becomes a multi-row table with a
   nullable department_id: the row with NULL department is the
   hospital-wide default, a department's own active row overrides it when
   present. Two partial unique indexes hold that shape, not one: Postgres
   treats NULL as distinct in a plain unique index, so a single index on
   department_id would happily allow two default rows. mpesa_transactions
   gains mpesa_config_id so a refund knows which till to pay back from and
   reconciliation can tell two tills apart.

2. Many terminals, one till. Two partial unique indexes on
   mpesa_transactions stop two Pending rows existing for the same invoice,
   or the same dispense, at once: at most one prompt in flight per invoice,
   at most one per dispense. app/services/daraja/stk.py inserts and catches
   the conflict rather than checking then inserting, which is the only way
   to close the race between two terminals pushing at the same moment.

Backfill: every existing mpesa_configs row keeps department_id NULL (it
becomes the hospital default), and every existing mpesa_transactions row
with no mpesa_config_id is pointed at it. More than one existing
mpesa_configs row per tenant cannot occur today (the table was singleton
by construction), so this migration asserts that rather than guessing:
it fails loudly, naming the tenant's database, if it is ever false.

A NEW revision on top of e1f2a3b4c5d6, not an amendment: that revision has
already been reviewed twice against three tenant-database shapes, and
reopening it risks verified work.

Idempotent, like its neighbours in this package.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── mpesa_configs: department_id + the two partial uniques ────────────
    op.execute(
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS department_id INTEGER "
        "REFERENCES departments(department_id) ON DELETE SET NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_configs_department_id "
        "ON mpesa_configs (department_id);"
    )

    # The table was singleton by construction until now. Assert that rather
    # than silently picking a "default" row for a human to discover later.
    row_count = conn.execute(sa.text("SELECT COUNT(*) FROM mpesa_configs")).scalar() or 0
    if row_count > 1:
        db_name = conn.engine.url.database
        raise RuntimeError(
            f"tenant database '{db_name}' has {row_count} mpesa_configs rows; "
            "per-department tills expects at most one pre-existing row (it "
            "becomes the hospital-wide default). This should not be "
            "possible, so stop and investigate rather than let this "
            "migration guess which row is the default."
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mpesa_configs_department "
        "ON mpesa_configs (department_id) WHERE department_id IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mpesa_configs_default "
        "ON mpesa_configs ((department_id IS NULL)) WHERE department_id IS NULL;"
    )

    # ── mpesa_transactions: mpesa_config_id + the two concurrency guards ──
    op.execute(
        "ALTER TABLE mpesa_transactions ADD COLUMN IF NOT EXISTS mpesa_config_id INTEGER "
        "REFERENCES mpesa_configs(id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mpesa_transactions_mpesa_config_id "
        "ON mpesa_transactions (mpesa_config_id);"
    )
    # Backfill: the one pre-existing config (if any) is what every
    # pre-existing transaction was actually settled through.
    op.execute(
        "UPDATE mpesa_transactions SET mpesa_config_id = "
        "(SELECT id FROM mpesa_configs ORDER BY id LIMIT 1) "
        "WHERE mpesa_config_id IS NULL AND EXISTS (SELECT 1 FROM mpesa_configs);"
    )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mpesa_txn_one_pending_per_invoice "
        "ON mpesa_transactions (invoice_id) "
        "WHERE status = 'Pending' AND invoice_id IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mpesa_txn_one_pending_per_dispense "
        "ON mpesa_transactions (dispense_id) "
        "WHERE status = 'Pending' AND dispense_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_mpesa_txn_one_pending_per_dispense;")
    op.execute("DROP INDEX IF EXISTS uq_mpesa_txn_one_pending_per_invoice;")
    op.execute("DROP INDEX IF EXISTS ix_mpesa_transactions_mpesa_config_id;")
    op.execute("ALTER TABLE mpesa_transactions DROP COLUMN IF EXISTS mpesa_config_id;")

    op.execute("DROP INDEX IF EXISTS uq_mpesa_configs_default;")
    op.execute("DROP INDEX IF EXISTS uq_mpesa_configs_department;")
    op.execute("DROP INDEX IF EXISTS ix_mpesa_configs_department_id;")
    op.execute("ALTER TABLE mpesa_configs DROP COLUMN IF EXISTS department_id;")
