"""Managerial Accounting — budgets, debit/credit notes, bulk allocation

Revision ID: a3f9c1d8b240
Revises: e8c1a4f72d50
Create Date: 2026-06-01 10:00:00.000000

Adds the last three managerial-accounting features:

  * Budgeting        — acc_budgets + acc_budget_lines
  * Debit/credit notes — acc_adjustment_notes
  * Bulk allocation  — acc_claim_schedule_items.amount_allocated +
                       acc_deposit_applications.claim_item_id (and
                       invoice_id relaxed to nullable)

Plus the two new RBAC permissions (granted to Admin + Accountant) and the
ledger mapping the bulk-allocation auto-post needs. Idempotent throughout.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3f9c1d8b240"
down_revision: Union[str, Sequence[str], None] = "e8c1a4f72d50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("accounting:budget.manage", "Create and edit budgets; view budget-vs-actual"),
    ("accounting:notes.manage",  "Issue and post debit/credit notes"),
)


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def _has_column(inspector, table: str, column: str) -> bool:
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── Budgets ──────────────────────────────────────────────────────────
    if _missing(inspector, "acc_budgets"):
        op.create_table(
            "acc_budgets",
            sa.Column("budget_id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("fiscal_year", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("name", "fiscal_year", name="uq_acc_budgets_name_year"),
            sa.CheckConstraint("status IN ('draft','active','archived')", name="ck_acc_budgets_status"),
        )
        op.create_index("ix_acc_budgets_name", "acc_budgets", ["name"])
        op.create_index("ix_acc_budgets_fiscal_year", "acc_budgets", ["fiscal_year"])
        op.create_index("ix_acc_budgets_status", "acc_budgets", ["status"])

    if _missing(inspector, "acc_budget_lines"):
        op.create_table(
            "acc_budget_lines",
            sa.Column("line_id", sa.Integer(), primary_key=True),
            sa.Column("budget_id", sa.Integer(),
                      sa.ForeignKey("acc_budgets.budget_id", ondelete="CASCADE"), nullable=False),
            sa.Column("account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=False),
            sa.Column("period_id", sa.Integer(),
                      sa.ForeignKey("acc_fiscal_periods.period_id"), nullable=False),
            sa.Column("amount", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.UniqueConstraint("budget_id", "account_id", "period_id",
                                name="uq_acc_budget_lines_budget_account_period"),
            sa.CheckConstraint("amount >= 0", name="ck_acc_budget_lines_amount_nonneg"),
        )
        op.create_index("ix_acc_budget_lines_budget", "acc_budget_lines", ["budget_id"])
        op.create_index("ix_acc_budget_lines_account", "acc_budget_lines", ["account_id"])
        op.create_index("ix_acc_budget_lines_period", "acc_budget_lines", ["period_id"])

    # ── Debit / credit notes ─────────────────────────────────────────────
    if _missing(inspector, "acc_adjustment_notes"):
        op.create_table(
            "acc_adjustment_notes",
            sa.Column("note_id", sa.Integer(), primary_key=True),
            sa.Column("note_number", sa.String(length=40), nullable=False),
            sa.Column("note_type", sa.String(length=10), nullable=False),
            sa.Column("note_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(20, 4), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"), nullable=True),
            sa.Column("target_entry_id", sa.Integer(),
                      sa.ForeignKey("acc_journal_entries.entry_id"), nullable=True),
            sa.Column("debit_account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=False),
            sa.Column("credit_account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=False),
            sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="KES"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="draft"),
            sa.Column("journal_entry_id", sa.Integer(),
                      sa.ForeignKey("acc_journal_entries.entry_id"), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("posted_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("voided_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("note_number", name="uq_acc_adjustment_notes_number"),
            sa.CheckConstraint("note_type IN ('debit','credit')", name="ck_acc_adjustment_notes_type"),
            sa.CheckConstraint("status IN ('draft','posted','void')", name="ck_acc_adjustment_notes_status"),
            sa.CheckConstraint("amount > 0", name="ck_acc_adjustment_notes_amount_positive"),
            sa.CheckConstraint("debit_account_id <> credit_account_id",
                               name="ck_acc_adjustment_notes_distinct_accounts"),
        )
        op.create_index("ix_acc_adjustment_notes_number", "acc_adjustment_notes", ["note_number"])
        op.create_index("ix_acc_adjustment_notes_type", "acc_adjustment_notes", ["note_type"])
        op.create_index("ix_acc_adjustment_notes_date", "acc_adjustment_notes", ["note_date"])
        op.create_index("ix_acc_adjustment_notes_invoice", "acc_adjustment_notes", ["invoice_id"])
        op.create_index("ix_acc_adjustment_notes_status", "acc_adjustment_notes", ["status"])

    # ── Bulk allocation column adds ──────────────────────────────────────
    if not _has_column(inspector, "acc_claim_schedule_items", "amount_allocated"):
        op.add_column(
            "acc_claim_schedule_items",
            sa.Column("amount_allocated", sa.Numeric(14, 2), nullable=False, server_default="0"),
        )
        op.create_check_constraint(
            "ck_acc_claim_items_alloc_bounds",
            "acc_claim_schedule_items",
            "amount_allocated >= 0 AND amount_allocated <= amount_claimed",
        )

    if not _has_column(inspector, "acc_deposit_applications", "claim_item_id"):
        op.add_column(
            "acc_deposit_applications",
            sa.Column("claim_item_id", sa.Integer(),
                      sa.ForeignKey("acc_claim_schedule_items.item_id"), nullable=True),
        )
        op.create_index("ix_acc_deposit_applications_claim_item",
                        "acc_deposit_applications", ["claim_item_id"])

    # Relax invoice_id to nullable so an application can target a claim item.
    if _has_column(inspector, "acc_deposit_applications", "invoice_id"):
        op.alter_column("acc_deposit_applications", "invoice_id",
                        existing_type=sa.Integer(), nullable=True)

    # ── RBAC permissions ─────────────────────────────────────────────────
    for code, desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (codename, description) "
                "SELECT :c, :d "
                "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :c)"
            ).bindparams(c=code, d=desc)
        )
        # Admin gets every codename.
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.role_id, p.permission_id "
                "FROM roles r CROSS JOIN permissions p "
                "WHERE p.codename = :c AND r.name = 'Admin' "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM role_permissions rp "
                "    WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id"
                ")"
            ).bindparams(c=code)
        )
        # Accountant gets both feature permissions.
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.role_id, p.permission_id "
                "FROM roles r CROSS JOIN permissions p "
                "WHERE p.codename = :c AND r.name = 'Accountant' "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM role_permissions rp "
                "    WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id"
                ")"
            ).bindparams(c=code)
        )

    # ── Ledger mapping for the bulk-allocation auto-post ─────────────────
    # Dr Patient Deposits (2170) / Cr Accounts Receivable (1140), mirroring
    # the single-apply mapping seeded in the phase-5 migration.
    op.execute(
        sa.text(
            "INSERT INTO acc_ledger_mappings "
            "(source_key, debit_account_id, credit_account_id, description, is_active) "
            "SELECT 'billing.deposit.bulk_allocated', "
            "       (SELECT account_id FROM acc_accounts WHERE code = '2170'), "
            "       (SELECT account_id FROM acc_accounts WHERE code = '1140'), "
            "       'Deposit allocated to claim items in bulk: clear Patient Deposits liability against Accounts Receivable', "
            "       true "
            "WHERE NOT EXISTS (SELECT 1 FROM acc_ledger_mappings WHERE source_key = 'billing.deposit.bulk_allocated')"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute("DELETE FROM acc_ledger_mappings WHERE source_key = 'billing.deposit.bulk_allocated';")

    for code, _desc in NEW_PERMISSIONS:
        op.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id IN (SELECT permission_id FROM permissions WHERE codename = :c)"
            ).bindparams(c=code)
        )
        op.execute(sa.text("DELETE FROM permissions WHERE codename = :c").bindparams(c=code))

    if _has_column(inspector, "acc_deposit_applications", "claim_item_id"):
        op.drop_index("ix_acc_deposit_applications_claim_item", table_name="acc_deposit_applications")
        op.drop_column("acc_deposit_applications", "claim_item_id")

    if _has_column(inspector, "acc_claim_schedule_items", "amount_allocated"):
        op.drop_constraint("ck_acc_claim_items_alloc_bounds", "acc_claim_schedule_items",
                           type_="check")
        op.drop_column("acc_claim_schedule_items", "amount_allocated")

    op.execute("DROP TABLE IF EXISTS acc_adjustment_notes CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_budget_lines CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_budgets CASCADE;")
