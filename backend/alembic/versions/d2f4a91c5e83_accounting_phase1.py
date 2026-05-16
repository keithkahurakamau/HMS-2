"""Managerial Accounting — Phase 1 (CoA, journals, currencies, periods)

Revision ID: d2f4a91c5e83
Revises: c9d4ea7b1f02
Create Date: 2026-05-16 19:30:00.000000

Creates the foundational double-entry tables and seeds:
- a single base currency (KES) per tenant,
- a default Kenyan-healthcare Chart of Accounts,
- an `acc_settings` row,
- the `accounting:*` permission codenames so `tenant_provisioning`'s
  backfill can attach them to the Admin role.

Idempotent so it can be re-run safely on partially-migrated tenants.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f4a91c5e83"
down_revision: Union[str, Sequence[str], None] = "c9d4ea7b1f02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default Chart of Accounts for a Kenyan healthcare facility.
# Codes follow the conventional 1xxx assets / 2xxx liabilities / 3xxx equity
# / 4xxx revenue / 5xxx COGS / 6xxx expenses layout. Parents are non-postable
# rollups; leaves are postable.
DEFAULT_COA = [
    # (code, name, type, parent_code, is_postable)
    ("1000", "Assets",                              "Asset",     None,   False),
    ("1100", "Current Assets",                      "Asset",     "1000", False),
    ("1110", "Cash on Hand",                        "Asset",     "1100", True),
    ("1120", "Bank Accounts",                       "Asset",     "1100", True),
    ("1130", "Mobile Money (M-Pesa)",               "Asset",     "1100", True),
    ("1140", "Accounts Receivable",                 "Asset",     "1100", True),
    ("1150", "Insurance Receivable",                "Asset",     "1100", True),
    ("1160", "Inventory — Pharmacy",                "Asset",     "1100", True),
    ("1170", "Inventory — Consumables",             "Asset",     "1100", True),
    ("1180", "Prepayments",                         "Asset",     "1100", True),
    ("1200", "Non-Current Assets",                  "Asset",     "1000", False),
    ("1210", "Property, Plant & Equipment",         "Asset",     "1200", True),
    ("1220", "Accumulated Depreciation",            "Asset",     "1200", True),

    ("2000", "Liabilities",                         "Liability", None,   False),
    ("2100", "Current Liabilities",                 "Liability", "2000", False),
    ("2110", "Accounts Payable",                    "Liability", "2100", True),
    ("2120", "Accrued Expenses",                    "Liability", "2100", True),
    ("2130", "PAYE Payable",                        "Liability", "2100", True),
    ("2140", "NHIF Payable",                        "Liability", "2100", True),
    ("2150", "NSSF Payable",                        "Liability", "2100", True),
    ("2160", "VAT Payable",                         "Liability", "2100", True),
    ("2170", "Patient Deposits",                    "Liability", "2100", True),
    ("2200", "Non-Current Liabilities",             "Liability", "2000", False),
    ("2210", "Long-term Loans",                     "Liability", "2200", True),

    ("3000", "Equity",                              "Equity",    None,   False),
    ("3100", "Owner's Capital",                     "Equity",    "3000", True),
    ("3200", "Retained Earnings",                   "Equity",    "3000", True),
    ("3300", "Current Year Earnings",               "Equity",    "3000", True),

    ("4000", "Revenue",                             "Revenue",   None,   False),
    ("4100", "Out-Patient Consultation",            "Revenue",   "4000", True),
    ("4200", "In-Patient Ward Charges",             "Revenue",   "4000", True),
    ("4300", "Laboratory Revenue",                  "Revenue",   "4000", True),
    ("4400", "Radiology Revenue",                   "Revenue",   "4000", True),
    ("4500", "Pharmacy Revenue",                    "Revenue",   "4000", True),
    ("4600", "Theatre / Surgery Revenue",           "Revenue",   "4000", True),
    ("4700", "Maternity Revenue",                   "Revenue",   "4000", True),
    ("4800", "Other Operating Revenue",             "Revenue",   "4000", True),

    ("5000", "Cost of Services",                    "Expense",   None,   False),
    ("5100", "Pharmacy — Cost of Drugs Sold",       "Expense",   "5000", True),
    ("5200", "Lab — Reagents & Consumables",        "Expense",   "5000", True),
    ("5300", "Radiology — Films & Contrast",        "Expense",   "5000", True),
    ("5400", "Theatre — Disposables",               "Expense",   "5000", True),

    ("6000", "Operating Expenses",                  "Expense",   None,   False),
    ("6100", "Salaries & Wages",                    "Expense",   "6000", True),
    ("6200", "Rent",                                "Expense",   "6000", True),
    ("6300", "Utilities",                           "Expense",   "6000", True),
    ("6400", "Repairs & Maintenance",               "Expense",   "6000", True),
    ("6500", "Office & Admin",                      "Expense",   "6000", True),
    ("6600", "Marketing & PR",                      "Expense",   "6000", True),
    ("6700", "Insurance Premiums",                  "Expense",   "6000", True),
    ("6800", "Depreciation",                        "Expense",   "6000", True),
    ("6900", "Bank Charges",                        "Expense",   "6000", True),
    ("6950", "Other Operating Expenses",            "Expense",   "6000", True),
]

ACCOUNTING_PERMISSIONS = [
    ("accounting:view",            "View the accounting module"),
    ("accounting:coa.manage",      "Create and edit chart of accounts"),
    ("accounting:journal.create",  "Create draft journal entries"),
    ("accounting:journal.post",    "Post journal entries to the ledger"),
    ("accounting:settings.manage", "Manage accounting currencies, periods and settings"),
]


def _table_missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── acc_currencies ──────────────────────────────────────────────────────
    if _table_missing(inspector, "acc_currencies"):
        op.create_table(
            "acc_currencies",
            sa.Column("currency_id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=3), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("symbol", sa.String(length=8), nullable=True),
            sa.Column("decimals", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("code", name="uq_acc_currencies_code"),
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_acc_currencies_one_base "
            "ON acc_currencies (is_base) WHERE is_base = true;"
        )

    # ── acc_fx_rates ────────────────────────────────────────────────────────
    if _table_missing(inspector, "acc_fx_rates"):
        op.create_table(
            "acc_fx_rates",
            sa.Column("fx_rate_id", sa.Integer(), primary_key=True),
            sa.Column("from_currency", sa.String(length=3), nullable=False),
            sa.Column("to_currency", sa.String(length=3), nullable=False),
            sa.Column("rate", sa.Numeric(20, 10), nullable=False),
            sa.Column("effective_date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("from_currency", "to_currency", "effective_date",
                                name="uq_acc_fx_rates_pair_date"),
            sa.CheckConstraint("rate > 0", name="ck_acc_fx_rates_positive"),
        )
        op.create_index("ix_acc_fx_rates_from_currency", "acc_fx_rates", ["from_currency"])
        op.create_index("ix_acc_fx_rates_to_currency",   "acc_fx_rates", ["to_currency"])
        op.create_index("ix_acc_fx_rates_effective",     "acc_fx_rates", ["effective_date"])

    # ── acc_accounts ────────────────────────────────────────────────────────
    if _table_missing(inspector, "acc_accounts"):
        op.create_table(
            "acc_accounts",
            sa.Column("account_id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("account_type", sa.String(length=20), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("acc_accounts.account_id", ondelete="RESTRICT"), nullable=True),
            sa.Column("currency_code", sa.String(length=3), nullable=True),
            sa.Column("is_postable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("code", name="uq_acc_accounts_code"),
            sa.CheckConstraint(
                "account_type IN ('Asset','Liability','Equity','Revenue','Expense')",
                name="ck_acc_accounts_valid_type",
            ),
        )
        op.create_index("ix_acc_accounts_code",         "acc_accounts", ["code"])
        op.create_index("ix_acc_accounts_name",         "acc_accounts", ["name"])
        op.create_index("ix_acc_accounts_account_type", "acc_accounts", ["account_type"])
        op.create_index("ix_acc_accounts_parent_id",    "acc_accounts", ["parent_id"])

    # ── acc_fiscal_periods ──────────────────────────────────────────────────
    if _table_missing(inspector, "acc_fiscal_periods"):
        op.create_table(
            "acc_fiscal_periods",
            sa.Column("period_id", sa.Integer(), primary_key=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="open"),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.UniqueConstraint("year", "month", name="uq_acc_fiscal_periods_year_month"),
            sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_acc_fiscal_periods_month"),
            sa.CheckConstraint("status IN ('open','closed')", name="ck_acc_fiscal_periods_status"),
        )
        op.create_index("ix_acc_fiscal_periods_year",   "acc_fiscal_periods", ["year"])
        op.create_index("ix_acc_fiscal_periods_status", "acc_fiscal_periods", ["status"])

    # ── acc_journal_entries ─────────────────────────────────────────────────
    if _table_missing(inspector, "acc_journal_entries"):
        op.create_table(
            "acc_journal_entries",
            sa.Column("entry_id", sa.Integer(), primary_key=True),
            sa.Column("entry_number", sa.String(length=40), nullable=False),
            sa.Column("entry_date", sa.Date(), nullable=False),
            sa.Column("fiscal_period_id", sa.Integer(), sa.ForeignKey("acc_fiscal_periods.period_id"), nullable=False),
            sa.Column("currency_code", sa.String(length=3), nullable=False),
            sa.Column("fx_rate", sa.Numeric(20, 10), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="draft"),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.Column("reference", sa.String(length=120), nullable=True),
            sa.Column("source_type", sa.String(length=40), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("posted_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reversed_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reverses_entry_id", sa.Integer(), sa.ForeignKey("acc_journal_entries.entry_id"), nullable=True),
            sa.UniqueConstraint("entry_number", name="uq_acc_journal_entries_number"),
            sa.CheckConstraint(
                "status IN ('draft','posted','reversed')",
                name="ck_acc_journal_entries_status",
            ),
            sa.CheckConstraint("fx_rate > 0", name="ck_acc_journal_entries_fx_positive"),
        )
        op.create_index("ix_acc_journal_entries_number",      "acc_journal_entries", ["entry_number"])
        op.create_index("ix_acc_journal_entries_date",        "acc_journal_entries", ["entry_date"])
        op.create_index("ix_acc_journal_entries_status",      "acc_journal_entries", ["status"])
        op.create_index("ix_acc_journal_entries_period",      "acc_journal_entries", ["fiscal_period_id"])
        op.create_index("ix_acc_journal_entries_reference",   "acc_journal_entries", ["reference"])
        op.create_index("ix_acc_journal_entries_source_type", "acc_journal_entries", ["source_type"])
        op.create_index("ix_acc_journal_entries_source_id",   "acc_journal_entries", ["source_id"])

    # ── acc_journal_lines ───────────────────────────────────────────────────
    if _table_missing(inspector, "acc_journal_lines"):
        op.create_table(
            "acc_journal_lines",
            sa.Column("line_id", sa.Integer(), primary_key=True),
            sa.Column("entry_id", sa.Integer(), sa.ForeignKey("acc_journal_entries.entry_id", ondelete="CASCADE"), nullable=False),
            sa.Column("line_number", sa.Integer(), nullable=False),
            sa.Column("account_id", sa.Integer(), sa.ForeignKey("acc_accounts.account_id"), nullable=False),
            sa.Column("debit", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("credit", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("debit_base", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("credit_base", sa.Numeric(20, 4), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.UniqueConstraint("entry_id", "line_number", name="uq_acc_journal_lines_entry_line"),
            sa.CheckConstraint(
                "(debit = 0 AND credit > 0) OR (debit > 0 AND credit = 0) "
                "OR (debit = 0 AND credit = 0)",
                name="ck_acc_journal_lines_dr_xor_cr",
            ),
        )
        op.create_index("ix_acc_journal_lines_entry",   "acc_journal_lines", ["entry_id"])
        op.create_index("ix_acc_journal_lines_account", "acc_journal_lines", ["account_id"])

    # ── acc_settings ────────────────────────────────────────────────────────
    if _table_missing(inspector, "acc_settings"):
        op.create_table(
            "acc_settings",
            sa.Column("settings_id", sa.Integer(), primary_key=True),
            sa.Column("base_currency_code", sa.String(length=3), nullable=False, server_default="KES"),
            sa.Column("go_live_date", sa.Date(), nullable=True),
            sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "fiscal_year_start_month BETWEEN 1 AND 12",
                name="ck_acc_settings_fy_month",
            ),
        )

    # ── Seed base currency (KES), settings row, and default CoA ─────────────
    op.execute(
        """
        INSERT INTO acc_currencies (code, name, symbol, decimals, is_base, is_active)
        SELECT 'KES', 'Kenyan Shilling', 'KSh', 2, true, true
        WHERE NOT EXISTS (SELECT 1 FROM acc_currencies WHERE code = 'KES');
        """
    )
    op.execute(
        """
        INSERT INTO acc_settings (base_currency_code, fiscal_year_start_month)
        SELECT 'KES', 1
        WHERE NOT EXISTS (SELECT 1 FROM acc_settings);
        """
    )

    # Seed default Chart of Accounts. Two-pass: parents first (parent_id NULL),
    # then children resolving parent_id via subquery. Idempotent on `code`.
    bind = op.get_bind()
    for code, name, acc_type, parent_code, is_postable in DEFAULT_COA:
        if parent_code is None:
            bind.execute(
                sa.text(
                    "INSERT INTO acc_accounts (code, name, account_type, parent_id, is_postable, is_active) "
                    "SELECT :code, :name, :acc_type, NULL, :is_postable, true "
                    "WHERE NOT EXISTS (SELECT 1 FROM acc_accounts WHERE code = :code)"
                ),
                {"code": code, "name": name, "acc_type": acc_type, "is_postable": is_postable},
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO acc_accounts (code, name, account_type, parent_id, is_postable, is_active) "
                    "SELECT :code, :name, :acc_type, "
                    "       (SELECT account_id FROM acc_accounts WHERE code = :parent_code), "
                    "       :is_postable, true "
                    "WHERE NOT EXISTS (SELECT 1 FROM acc_accounts WHERE code = :code)"
                ),
                {
                    "code": code, "name": name, "acc_type": acc_type,
                    "parent_code": parent_code, "is_postable": is_postable,
                },
            )

    # Seed permission codenames so backfill_admin_permissions attaches them.
    for code, desc in ACCOUNTING_PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (codename, description) "
                "SELECT :code, :desc "
                "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :code)"
            ).bindparams(code=code, desc=desc)
        )


def downgrade() -> None:
    # Drop in reverse FK order. Permissions stay — easier to roll forward
    # than to figure out which roles still need them.
    op.execute("DROP TABLE IF EXISTS acc_journal_lines CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_journal_entries CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_fiscal_periods CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_fx_rates CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_currencies CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_settings CASCADE;")
