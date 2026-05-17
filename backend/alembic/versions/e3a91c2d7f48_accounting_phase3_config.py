"""Accounting Phase 3 — config tables (suppliers, insurance, schemes, price list, ledger mappings)

Revision ID: e3a91c2d7f48
Revises: d2f4a91c5e83
Create Date: 2026-05-16 21:30:00.000000

Adds the five configuration tables backing Phase 4 auto-posting:
- acc_suppliers
- acc_insurance_providers
- acc_medical_schemes
- acc_price_list
- acc_ledger_mappings

Seeds default ledger mappings keyed to the default CoA so the most
common auto-post flows work out of the box. Tenants who restructure
their CoA can re-point the mappings without changing code.

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3a91c2d7f48"
down_revision: Union[str, Sequence[str], None] = "d2f4a91c5e83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default mapping seeds: (source_key, debit_code, credit_code, description)
# Codes refer to the default CoA seeded in d2f4a91c5e83. If a tenant
# deleted or renamed those accounts, the seed simply skips that row.
DEFAULT_MAPPINGS = [
    ("billing.invoice.created",
     "1140", "4100",
     "Invoice raised: Dr Accounts Receivable, Cr OP Consultation Revenue (override per service via price list)"),
    ("billing.payment.cash",
     "1110", "1140",
     "Patient pays cash against invoice: Dr Cash on Hand, Cr Accounts Receivable"),
    ("billing.payment.bank",
     "1120", "1140",
     "Patient pays via bank transfer/card: Dr Bank Accounts, Cr Accounts Receivable"),
    ("billing.payment.mpesa",
     "1130", "1140",
     "Patient pays via M-Pesa: Dr Mobile Money, Cr Accounts Receivable"),
    ("billing.deposit.received",
     "1110", "2170",
     "Patient pre-payment / deposit: Dr Cash, Cr Patient Deposits (liability)"),
    ("pharmacy.dispense.revenue",
     "1140", "4500",
     "Pharmacy dispensation: Dr Accounts Receivable, Cr Pharmacy Revenue"),
    ("pharmacy.dispense.cogs",
     "5100", "1160",
     "Pharmacy cost of goods sold: Dr Cost of Drugs Sold, Cr Inventory — Pharmacy"),
    ("cheques.deposit.cleared",
     "1120", "1140",
     "Cheque cleared into bank: Dr Bank Accounts, Cr Accounts Receivable"),
    ("mpesa.receipt.direct",
     "1130", "4800",
     "Direct M-Pesa receipt with no prior invoice: Dr Mobile Money, Cr Other Operating Revenue"),
    ("insurance.claim.submitted",
     "1150", "1140",
     "Claim submitted to insurer: move from patient AR to insurance receivable"),
    ("insurance.claim.settled",
     "1120", "1150",
     "Insurer pays: Dr Bank, Cr Insurance Receivable"),
]


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # acc_suppliers
    if _missing(inspector, "acc_suppliers"):
        op.create_table(
            "acc_suppliers",
            sa.Column("supplier_id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("contact_person", sa.String(length=120), nullable=True),
            sa.Column("email", sa.String(length=160), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("tax_pin", sa.String(length=40), nullable=True),
            sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("default_payable_account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_acc_suppliers_name",    "acc_suppliers", ["name"])
        op.create_index("ix_acc_suppliers_tax_pin", "acc_suppliers", ["tax_pin"])

    # acc_insurance_providers
    if _missing(inspector, "acc_insurance_providers"):
        op.create_table(
            "acc_insurance_providers",
            sa.Column("provider_id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("contact_person", sa.String(length=120), nullable=True),
            sa.Column("email", sa.String(length=160), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("default_receivable_account_id", sa.Integer(),
                      sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("name", name="uq_acc_insurance_providers_name"),
        )
        op.create_index("ix_acc_insurance_providers_name", "acc_insurance_providers", ["name"])

    # acc_medical_schemes
    if _missing(inspector, "acc_medical_schemes"):
        op.create_table(
            "acc_medical_schemes",
            sa.Column("scheme_id", sa.Integer(), primary_key=True),
            sa.Column("provider_id", sa.Integer(),
                      sa.ForeignKey("acc_insurance_providers.provider_id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("scheme_code", sa.String(length=60), nullable=True),
            sa.Column("coverage_limit", sa.Numeric(14, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("provider_id", "name", name="uq_acc_medical_schemes_provider_name"),
        )
        op.create_index("ix_acc_medical_schemes_provider", "acc_medical_schemes", ["provider_id"])
        op.create_index("ix_acc_medical_schemes_code",     "acc_medical_schemes", ["scheme_code"])

    # acc_price_list
    if _missing(inspector, "acc_price_list"):
        op.create_table(
            "acc_price_list",
            sa.Column("price_id", sa.Integer(), primary_key=True),
            sa.Column("service_code", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("category", sa.String(length=60), nullable=False),
            sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("revenue_account_id", sa.Integer(), sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("tax_rate_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("service_code", name="uq_acc_price_list_service_code"),
        )
        op.create_index("ix_acc_price_list_service_code", "acc_price_list", ["service_code"])
        op.create_index("ix_acc_price_list_name",         "acc_price_list", ["name"])
        op.create_index("ix_acc_price_list_category",     "acc_price_list", ["category"])

    # acc_ledger_mappings
    if _missing(inspector, "acc_ledger_mappings"):
        op.create_table(
            "acc_ledger_mappings",
            sa.Column("mapping_id", sa.Integer(), primary_key=True),
            sa.Column("source_key", sa.String(length=80), nullable=False),
            sa.Column("debit_account_id",  sa.Integer(), sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("credit_account_id", sa.Integer(), sa.ForeignKey("acc_accounts.account_id"), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("source_key", name="uq_acc_ledger_mappings_source_key"),
        )
        op.create_index("ix_acc_ledger_mappings_source_key", "acc_ledger_mappings", ["source_key"])

    # Seed default ledger mappings — only if the referenced account codes exist.
    for source_key, dr_code, cr_code, desc in DEFAULT_MAPPINGS:
        op.execute(
            sa.text(
                "INSERT INTO acc_ledger_mappings "
                "(source_key, debit_account_id, credit_account_id, description, is_active) "
                "SELECT :sk, "
                "       (SELECT account_id FROM acc_accounts WHERE code = :dr), "
                "       (SELECT account_id FROM acc_accounts WHERE code = :cr), "
                "       :desc, true "
                "WHERE NOT EXISTS (SELECT 1 FROM acc_ledger_mappings WHERE source_key = :sk)"
            ).bindparams(sk=source_key, dr=dr_code, cr=cr_code, desc=desc)
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS acc_ledger_mappings CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_price_list CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_medical_schemes CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_insurance_providers CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_suppliers CASCADE;")
