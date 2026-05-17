"""Accounting Phase 5 — debtor lifecycle (claim schedules, client deposits)

Revision ID: f4b8e2c91a36
Revises: e3a91c2d7f48
Create Date: 2026-05-16 22:30:00.000000

4 new tenant tables:
- acc_claim_schedules           (insurance claim batches)
- acc_claim_schedule_items      (invoices inside each batch)
- acc_client_deposits           (patient pre-payments)
- acc_deposit_applications      (audit trail of deposit-to-invoice apply)

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b8e2c91a36"
down_revision: Union[str, Sequence[str], None] = "e3a91c2d7f48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _missing(inspector, "acc_claim_schedules"):
        op.create_table(
            "acc_claim_schedules",
            sa.Column("schedule_id", sa.Integer(), primary_key=True),
            sa.Column("schedule_number", sa.String(length=40), nullable=False),
            sa.Column("provider_id", sa.Integer(),
                      sa.ForeignKey("acc_insurance_providers.provider_id"), nullable=False),
            sa.Column("scheme_id", sa.Integer(),
                      sa.ForeignKey("acc_medical_schemes.scheme_id"), nullable=True),
            sa.Column("period_from", sa.Date(), nullable=False),
            sa.Column("period_to", sa.Date(), nullable=False),
            sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("settled_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("settled_amount", sa.Numeric(14, 2), nullable=True),
            sa.Column("settlement_reference", sa.String(length=120), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("schedule_number", name="uq_acc_claim_schedules_number"),
            sa.CheckConstraint("status IN ('draft','submitted','settled','rejected')",
                               name="ck_acc_claim_schedules_status"),
        )
        op.create_index("ix_acc_claim_schedules_number",   "acc_claim_schedules", ["schedule_number"])
        op.create_index("ix_acc_claim_schedules_provider", "acc_claim_schedules", ["provider_id"])
        op.create_index("ix_acc_claim_schedules_status",   "acc_claim_schedules", ["status"])

    if _missing(inspector, "acc_claim_schedule_items"):
        op.create_table(
            "acc_claim_schedule_items",
            sa.Column("item_id", sa.Integer(), primary_key=True),
            sa.Column("schedule_id", sa.Integer(),
                      sa.ForeignKey("acc_claim_schedules.schedule_id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"), nullable=True),
            sa.Column("invoice_reference", sa.String(length=80), nullable=True),
            sa.Column("patient_name", sa.String(length=200), nullable=True),
            sa.Column("member_number", sa.String(length=80), nullable=True),
            sa.Column("amount_claimed", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("amount_approved", sa.Numeric(14, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_acc_claim_schedule_items_schedule", "acc_claim_schedule_items", ["schedule_id"])
        op.create_index("ix_acc_claim_schedule_items_invoice",  "acc_claim_schedule_items", ["invoice_id"])

    if _missing(inspector, "acc_client_deposits"):
        op.create_table(
            "acc_client_deposits",
            sa.Column("deposit_id", sa.Integer(), primary_key=True),
            sa.Column("deposit_number", sa.String(length=40), nullable=False),
            sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id"), nullable=False),
            sa.Column("deposit_date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("amount_applied", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("method", sa.String(length=40), nullable=False),
            sa.Column("reference", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="available"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("deposit_number", name="uq_acc_client_deposits_number"),
            sa.CheckConstraint("status IN ('available','partially_applied','fully_applied','refunded')",
                               name="ck_acc_client_deposits_status"),
            sa.CheckConstraint("amount > 0", name="ck_acc_client_deposits_positive"),
            sa.CheckConstraint("amount_applied >= 0 AND amount_applied <= amount",
                               name="ck_acc_client_deposits_applied_bounds"),
        )
        op.create_index("ix_acc_client_deposits_number",  "acc_client_deposits", ["deposit_number"])
        op.create_index("ix_acc_client_deposits_patient", "acc_client_deposits", ["patient_id"])
        op.create_index("ix_acc_client_deposits_status",  "acc_client_deposits", ["status"])

    if _missing(inspector, "acc_deposit_applications"):
        op.create_table(
            "acc_deposit_applications",
            sa.Column("application_id", sa.Integer(), primary_key=True),
            sa.Column("deposit_id", sa.Integer(),
                      sa.ForeignKey("acc_client_deposits.deposit_id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("applied_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.CheckConstraint("amount > 0", name="ck_acc_deposit_applications_positive"),
        )
        op.create_index("ix_acc_deposit_applications_deposit", "acc_deposit_applications", ["deposit_id"])
        op.create_index("ix_acc_deposit_applications_invoice", "acc_deposit_applications", ["invoice_id"])


    # Seed the deposit-applied mapping introduced in this phase, if absent.
    op.execute(
        sa.text(
            "INSERT INTO acc_ledger_mappings "
            "(source_key, debit_account_id, credit_account_id, description, is_active) "
            "SELECT 'billing.deposit.applied', "
            "       (SELECT account_id FROM acc_accounts WHERE code = '2170'), "
            "       (SELECT account_id FROM acc_accounts WHERE code = '1140'), "
            "       'Deposit applied to invoice: clear Patient Deposits liability against Accounts Receivable', "
            "       true "
            "WHERE NOT EXISTS (SELECT 1 FROM acc_ledger_mappings WHERE source_key = 'billing.deposit.applied')"
        )
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS acc_deposit_applications CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_client_deposits CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_claim_schedule_items CASCADE;")
    op.execute("DROP TABLE IF EXISTS acc_claim_schedules CASCADE;")
