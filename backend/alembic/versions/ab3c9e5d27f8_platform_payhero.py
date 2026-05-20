"""Platform Pay Hero — superadmin-level subscription billing

Revision ID: ab3c9e5d27f8
Revises: aa2b7c3d8e91
Create Date: 2026-05-20 10:00:00.000000

Adds the master-DB tables for the platform's own Pay Hero account:
  * platform_payhero_configs        — singleton (one row, owned by superadmin)
  * platform_payhero_transactions   — log of STK pushes against tenants
And augments ``tenants`` with billing contact fields so superadmin doesn't
retype them every cycle.

Idempotent — only writes the master DB. Tenant DBs are untouched (the
migrate_all_tenants script skips master-only revisions when running per-tenant).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab3c9e5d27f8"
down_revision: Union[str, Sequence[str], None] = "aa2b7c3d8e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, col: str) -> bool:
    return col in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # Master-only migration: short-circuit if we're running against a tenant DB
    # (no ``tenants`` table there).
    if not _has_table(bind, "tenants") or not _has_table(bind, "superadmins"):
        return

    # ── tenants: billing contact ───────────────────────────────────────
    if not _has_column(bind, "tenants", "billing_contact_msisdn"):
        op.add_column("tenants", sa.Column("billing_contact_msisdn", sa.String(20), nullable=True))
    if not _has_column(bind, "tenants", "billing_contact_name"):
        op.add_column("tenants", sa.Column("billing_contact_name", sa.String(120), nullable=True))

    # ── platform_payhero_configs ───────────────────────────────────────
    if not _has_table(bind, "platform_payhero_configs"):
        op.create_table(
            "platform_payhero_configs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("shortcode", sa.String(20), nullable=False, server_default=""),
            sa.Column("shortcode_type", sa.String(20), nullable=False, server_default="paybill"),
            sa.Column("payhero_channel_id", sa.String(40), nullable=True),
            sa.Column("payhero_username_encrypted", sa.String(255), nullable=True),
            sa.Column("payhero_password_encrypted", sa.String(255), nullable=True),
            sa.Column("settlement_bank_code", sa.String(20), nullable=False, server_default=""),
            sa.Column("settlement_bank_name", sa.String(80), nullable=False, server_default=""),
            sa.Column("settlement_account_number", sa.String(40), nullable=False, server_default=""),
            sa.Column("settlement_account_name", sa.String(120), nullable=True),
            sa.Column("account_reference", sa.String(50), server_default="MEDIFLEET"),
            sa.Column("transaction_desc", sa.String(100), server_default="MediFleet Subscription"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_status", sa.String(40), nullable=True),
            sa.Column("last_test_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("superadmins.admin_id"), nullable=True),
        )

    # ── platform_payhero_transactions ──────────────────────────────────
    if not _has_table(bind, "platform_payhero_transactions"):
        op.create_table(
            "platform_payhero_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.tenant_id"), nullable=False, index=True),
            sa.Column("phone_number", sa.String(20), nullable=False, index=True),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("payhero_reference", sa.String(100), nullable=True, index=True),
            sa.Column("external_reference", sa.String(100), nullable=False, unique=True),
            sa.Column("receipt_number", sa.String(50), nullable=True, unique=True, index=True),
            sa.Column("status", sa.String(50), nullable=True, server_default="Pending", index=True),
            sa.Column("result_desc", sa.String(255), nullable=True),
            sa.Column("period_label", sa.String(120), nullable=True),
            sa.Column("initiated_by", sa.Integer(), sa.ForeignKey("superadmins.admin_id"), nullable=True),
            sa.Column("initiated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "platform_payhero_transactions"):
        op.drop_table("platform_payhero_transactions")
    if _has_table(bind, "platform_payhero_configs"):
        op.drop_table("platform_payhero_configs")
    if _has_table(bind, "tenants"):
        if _has_column(bind, "tenants", "billing_contact_name"):
            op.drop_column("tenants", "billing_contact_name")
        if _has_column(bind, "tenants", "billing_contact_msisdn"):
            op.drop_column("tenants", "billing_contact_msisdn")
