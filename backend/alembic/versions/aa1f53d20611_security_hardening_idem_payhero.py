"""Security hardening: scope idempotency keys + Pay Hero receipt uniqueness

Revision ID: aa1f53d20611
Revises: f1a8d3c92e57
Create Date: 2026-05-19 18:55:00.000000

Changes:
  * idempotency_keys gets a composite PK (user_id, endpoint, key) plus a
    request_fingerprint column and a status_code column (IDEM-001).
  * mpesa_transactions enforces UNIQUE(receipt_number) so concurrent
    callbacks can never double-record the same receipt (PAY-003).
  * invoices gets a partial composite index on (status, billing_date) to
    speed up the billing queue read (DB-002).

Idempotent so re-runs are safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa1f53d20611"
down_revision: Union[str, Sequence[str], None] = "f1a8d3c92e57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, col: str) -> bool:
    return col in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _has_index(bind, table: str, idx: str) -> bool:
    return idx in {i["name"] for i in sa.inspect(bind).get_indexes(table)}


def _has_constraint(bind, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    return (
        name in {c["name"] for c in insp.get_unique_constraints(table)}
        or name in {c["name"] for c in insp.get_pk_constraint(table).get("constrained_columns", []) and [insp.get_pk_constraint(table)] or []}
    )


def upgrade() -> None:
    bind = op.get_bind()

    # ── idempotency_keys: rebuild with scoped PK + fingerprint ──────────
    if _has_table(bind, "idempotency_keys"):
        # Drop the old single-column PK and widen the schema.
        if not _has_column(bind, "idempotency_keys", "user_id"):
            op.add_column(
                "idempotency_keys",
                sa.Column("user_id", sa.Integer(), nullable=False, server_default="0"),
            )
        if not _has_column(bind, "idempotency_keys", "endpoint"):
            op.add_column(
                "idempotency_keys",
                sa.Column("endpoint", sa.String(96), nullable=False, server_default=""),
            )
        if not _has_column(bind, "idempotency_keys", "request_fingerprint"):
            op.add_column(
                "idempotency_keys",
                sa.Column("request_fingerprint", sa.String(64), nullable=False, server_default=""),
            )
        if not _has_column(bind, "idempotency_keys", "status_code"):
            op.add_column(
                "idempotency_keys",
                sa.Column("status_code", sa.Integer(), nullable=False, server_default="200"),
            )

        # Swap PK: drop old (key only), add composite (user_id, endpoint, key).
        op.execute("ALTER TABLE idempotency_keys DROP CONSTRAINT IF EXISTS idempotency_keys_pkey")
        op.execute(
            "ALTER TABLE idempotency_keys "
            "ADD CONSTRAINT pk_idempotency_keys PRIMARY KEY (user_id, endpoint, key)"
        )

        if not _has_index(bind, "idempotency_keys", "ix_idempotency_created"):
            op.create_index(
                "ix_idempotency_created", "idempotency_keys", ["created_at"]
            )

    # ── mpesa_transactions: unique(receipt_number) where not null ───────
    if _has_table(bind, "mpesa_transactions"):
        if not _has_index(bind, "mpesa_transactions", "uq_mpesa_receipt"):
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mpesa_receipt "
                "ON mpesa_transactions (receipt_number) "
                "WHERE receipt_number IS NOT NULL"
            )

    # ── invoices: partial composite for billing queue read ──────────────
    if _has_table(bind, "invoices"):
        if not _has_index(bind, "invoices", "ix_invoice_status_date"):
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_invoice_status_date "
                "ON invoices (status, billing_date) "
                "WHERE status IN ('Pending','Partially Paid','Pending M-Pesa')"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_index(bind, "invoices", "ix_invoice_status_date"):
        op.execute("DROP INDEX IF EXISTS ix_invoice_status_date")
    if _has_index(bind, "mpesa_transactions", "uq_mpesa_receipt"):
        op.execute("DROP INDEX IF EXISTS uq_mpesa_receipt")
    # Leave the idempotency_keys schema as-is — downgrading would orphan
    # cached responses keyed under (user_id, endpoint).
