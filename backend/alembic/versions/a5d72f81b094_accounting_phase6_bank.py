"""Accounting Phase 6 — bank accounts + statement reconciliation

Revision ID: a5d72f81b094
Revises: f4b8e2c91a36
Create Date: 2026-05-16 23:30:00.000000

2 new tenant tables:
- acc_bank_accounts        (bank account master, linked to GL asset acct)
- acc_bank_transactions    (statement lines + reconciliation status)

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5d72f81b094"
down_revision: Union[str, Sequence[str], None] = "f4b8e2c91a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _missing(inspector, "acc_bank_accounts"):
        op.create_table(
            "acc_bank_accounts",
            sa.Column("bank_account_id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("bank_name", sa.String(length=120), nullable=False),
            sa.Column("branch", sa.String(length=120), nullable=True),
            sa.Column("account_number", sa.String(length=60), nullable=False),
            sa.Column("swift_code", sa.String(length=20), nullable=True),
            sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="KES"),
            sa.Column("gl_account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("bank_name", "account_number", name="uq_acc_bank_accounts_bank_number"),
        )
        op.create_index("ix_acc_bank_accounts_name", "acc_bank_accounts", ["name"])

    if _missing(inspector, "acc_bank_transactions"):
        op.create_table(
            "acc_bank_transactions",
            sa.Column("bank_transaction_id", sa.Integer(), primary_key=True),
            sa.Column("bank_account_id", sa.Integer(),
                      sa.ForeignKey("acc_bank_accounts.bank_account_id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("running_balance", sa.Numeric(14, 2), nullable=True),
            sa.Column("reference", sa.String(length=120), nullable=True),
            sa.Column("reconciliation_status", sa.String(length=15), nullable=False, server_default="unreconciled"),
            sa.Column("journal_line_id", sa.Integer(),
                      sa.ForeignKey("acc_journal_lines.line_id"), nullable=True),
            sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reconciled_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("ignore_reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.CheckConstraint(
                "reconciliation_status IN ('unreconciled','matched','ignored')",
                name="ck_acc_bank_transactions_recon",
            ),
        )
        op.create_index("ix_acc_bank_transactions_account", "acc_bank_transactions", ["bank_account_id"])
        op.create_index("ix_acc_bank_transactions_date",    "acc_bank_transactions", ["transaction_date"])
        op.create_index("ix_acc_bank_transactions_recon",   "acc_bank_transactions", ["reconciliation_status"])
        op.create_index("ix_acc_bank_transactions_ref",     "acc_bank_transactions", ["reference"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS acc_bank_transactions CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_bank_accounts CASCADE;")
