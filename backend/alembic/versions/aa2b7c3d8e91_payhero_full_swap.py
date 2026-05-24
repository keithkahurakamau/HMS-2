"""Strip Daraja: rename mpesa_* tables to payhero_*, reshape config columns

Revision ID: aa2b7c3d8e91
Revises: aa1f53d20611
Create Date: 2026-05-19 19:30:00.000000

User-mandated swap: Pay Hero is the only payment aggregator. Multi-tenants
enter their existing PayBill / Buy-Goods till and the bank where Pay Hero
should settle proceeds. The Safaricom Daraja CRUD surface (consumer key /
secret / passkey) is removed entirely.

Schema changes (idempotent — re-runs are safe):
  * Rename ``mpesa_configs`` -> ``payhero_configs`` if present, else create
    fresh.
  * Drop daraja-only columns: ``consumer_key_encrypted``,
    ``consumer_secret_encrypted``, ``passkey_encrypted``, ``environment``,
    ``c2b_short_code``, ``c2b_response_type``, ``c2b_registered_at``,
    ``kcb_account_number``.
  * Rename ``paybill_number`` -> ``shortcode``.
  * Add ``payhero_channel_id``, ``payhero_username_encrypted``,
    ``payhero_password_encrypted``, ``settlement_bank_code``,
    ``settlement_bank_name``, ``settlement_account_number``,
    ``settlement_account_name``.
  * Rename ``mpesa_transactions`` -> ``payhero_transactions``, add
    ``payhero_reference`` and ``external_reference``.
  * Rename ``mpesa:manage`` permission codename -> ``payhero:manage`` and
    keep existing role grants.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa2b7c3d8e91"
down_revision: Union[str, Sequence[str], None] = "aa1f53d20611"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, col: str) -> bool:
    return col in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. payhero_configs ─────────────────────────────────────────────
    if _has_table(bind, "mpesa_configs") and not _has_table(bind, "payhero_configs"):
        op.rename_table("mpesa_configs", "payhero_configs")

    if not _has_table(bind, "payhero_configs"):
        op.create_table(
            "payhero_configs",
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
            sa.Column("account_reference", sa.String(50), server_default="HMS-BILLING"),
            sa.Column("transaction_desc", sa.String(100), server_default="Hospital Bill Payment"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_status", sa.String(40), nullable=True),
            sa.Column("last_test_message", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        )
    else:
        # Reshape an existing table left over from the Daraja era.
        if _has_column(bind, "payhero_configs", "paybill_number") and not _has_column(
            bind, "payhero_configs", "shortcode"
        ):
            op.alter_column("payhero_configs", "paybill_number", new_column_name="shortcode")
        # Add the new Pay Hero / settlement columns when absent.
        for col_name, ddl in (
            ("payhero_channel_id", sa.Column("payhero_channel_id", sa.String(40), nullable=True)),
            ("payhero_username_encrypted", sa.Column("payhero_username_encrypted", sa.String(255), nullable=True)),
            ("payhero_password_encrypted", sa.Column("payhero_password_encrypted", sa.String(255), nullable=True)),
            ("settlement_bank_code", sa.Column("settlement_bank_code", sa.String(20), nullable=False, server_default="")),
            ("settlement_bank_name", sa.Column("settlement_bank_name", sa.String(80), nullable=False, server_default="")),
            ("settlement_account_number", sa.Column("settlement_account_number", sa.String(40), nullable=False, server_default="")),
            ("settlement_account_name", sa.Column("settlement_account_name", sa.String(120), nullable=True)),
        ):
            if not _has_column(bind, "payhero_configs", col_name):
                op.add_column("payhero_configs", ddl)
        # Drop daraja-only columns we no longer support.
        for col in (
            "consumer_key_encrypted",
            "consumer_secret_encrypted",
            "passkey_encrypted",
            "environment",
            "c2b_short_code",
            "c2b_response_type",
            "c2b_registered_at",
            "kcb_account_number",
        ):
            if _has_column(bind, "payhero_configs", col):
                op.drop_column("payhero_configs", col)

    # ── 2. payhero_transactions ────────────────────────────────────────
    if _has_table(bind, "mpesa_transactions") and not _has_table(bind, "payhero_transactions"):
        op.rename_table("mpesa_transactions", "payhero_transactions")

    if not _has_table(bind, "payhero_transactions"):
        op.create_table(
            "payhero_transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"), nullable=True, index=True),
            sa.Column("dispense_id", sa.Integer(), sa.ForeignKey("dispense_logs.dispense_id"), nullable=True, index=True),
            sa.Column("phone_number", sa.String(20), nullable=False, index=True),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("payhero_reference", sa.String(100), nullable=True, index=True),
            sa.Column("external_reference", sa.String(100), nullable=True, index=True),
            sa.Column("receipt_number", sa.String(50), nullable=True, unique=True, index=True),
            sa.Column("status", sa.String(50), nullable=True, server_default="Pending", index=True),
            sa.Column("result_desc", sa.String(255), nullable=True),
            sa.Column("transaction_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
            sa.Column("transaction_type", sa.String(10), nullable=False, server_default="STK", index=True),
            sa.Column("bill_ref_number", sa.String(80), nullable=True, index=True),
            sa.Column("match_basis", sa.String(20), nullable=True, index=True),
        )
    else:
        # Carry forward the prior columns; add Pay Hero references when absent.
        if not _has_column(bind, "payhero_transactions", "payhero_reference"):
            op.add_column(
                "payhero_transactions",
                sa.Column("payhero_reference", sa.String(100), nullable=True, index=True),
            )
        if not _has_column(bind, "payhero_transactions", "external_reference"):
            op.add_column(
                "payhero_transactions",
                sa.Column("external_reference", sa.String(100), nullable=True, index=True),
            )

    # ── 3. permission rename mpesa:manage -> payhero:manage ────────────
    op.execute(
        "UPDATE permissions SET codename = 'payhero:manage' "
        "WHERE codename = 'mpesa:manage'"
    )
    # And replace the human-facing description if it mentions M-Pesa specifically.
    op.execute(
        "UPDATE permissions SET description = 'Configure the Pay Hero payment gateway' "
        "WHERE codename = 'payhero:manage'"
    )


def downgrade() -> None:
    """Downgrades are intentionally lossy — the Daraja credential columns
    held encrypted secrets that we've thrown away. Re-seeding requires the
    operator to re-onboard with Daraja, which is no longer supported."""
    bind = op.get_bind()
    if _has_table(bind, "payhero_transactions") and not _has_table(bind, "mpesa_transactions"):
        op.rename_table("payhero_transactions", "mpesa_transactions")
    if _has_table(bind, "payhero_configs") and not _has_table(bind, "mpesa_configs"):
        op.rename_table("payhero_configs", "mpesa_configs")
    op.execute(
        "UPDATE permissions SET codename = 'mpesa:manage' WHERE codename = 'payhero:manage'"
    )
