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

Legacy duplicate Pending rows: mpesa_transactions is the RENAMED
payhero_transactions, and the old Pay Hero path had no per-invoice pending
guard, so any push whose callback never arrived stayed Pending forever.
Two Pending rows for one invoice is therefore ordinary legacy data, not
corruption, and creating the partial unique indexes over it would abort
the whole migration with a UniqueViolation. They are resolved
deterministically first: the NEWEST Pending row per invoice (and per
dispense) is kept, every older one is marked Failed with a result_desc
saying exactly why. Failed is an existing, honest status; no status is
invented for this.

A NEW revision on top of e1f2a3b4c5d6, not an amendment: that revision has
already been reviewed twice against three tenant-database shapes, and
reopening it risks verified work.

Idempotent, like its neighbours in this package.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# What an older duplicate Pending row is stamped with when the newest one
# for its invoice/dispense supersedes it. Mirrored (kept in lockstep) by
# scripts/migrate_all_tenants.py for legacy-stamped tenants, which never
# execute this revision.
SUPERSEDED_PENDING_RESULT_DESC = (
    "Superseded by a newer pending push during the Daraja migration; "
    "outcome never confirmed by Safaricom."
)


def pending_dedup_sql(scope_column: str) -> str:
    """The one statement that resolves pre-existing duplicate Pending rows
    for `scope_column` ('invoice_id' or 'dispense_id'): keep the NEWEST
    Pending row per value (transaction_date, id as the tiebreaker), mark
    every older one Failed. Deterministic, and a no-op once no duplicates
    remain. Exposed as a function so migrate_all_tenants' mirrored copy
    can be checked against it rather than drifting silently."""
    assert scope_column in ("invoice_id", "dispense_id")
    return (
        "UPDATE mpesa_transactions AS t "
        "SET status = 'Failed', result_desc = :desc "
        "FROM ("
        "SELECT id, ROW_NUMBER() OVER ("
        f"PARTITION BY {scope_column} "
        "ORDER BY transaction_date DESC NULLS LAST, id DESC"
        ") AS rn "
        "FROM mpesa_transactions "
        f"WHERE status = 'Pending' AND {scope_column} IS NOT NULL"
        ") ranked "
        "WHERE t.id = ranked.id AND ranked.rn > 1"
    )


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

    # Resolve legacy duplicate Pending rows BEFORE the guards exist (see
    # the module docstring): the old Pay Hero path had no pending guard,
    # so real tenants hold several Pending rows for one invoice, and the
    # CREATE UNIQUE INDEX below would abort on them. Keep the newest per
    # invoice and per dispense, mark the older ones Failed with a
    # result_desc that says exactly why. The invoice pass runs first; the
    # dispense pass then ranks only the rows still Pending, so the whole
    # resolution is deterministic. Still one transaction with everything
    # else here: a failure anywhere leaves the tenant untouched.
    resolved = 0
    for scope_column in ("invoice_id", "dispense_id"):
        result = conn.execute(
            sa.text(pending_dedup_sql(scope_column)),
            {"desc": SUPERSEDED_PENDING_RESULT_DESC},
        )
        resolved += result.rowcount or 0
    if resolved:
        logging.getLogger("alembic.runtime.migration").info(
            "resolved %d pre-existing duplicate Pending mpesa_transactions "
            "row(s): kept the newest per invoice/dispense, marked the "
            "older ones Failed as superseded",
            resolved,
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
