"""Daraja tenant schema: mpesa_configs, mpesa_transactions, mpesa_refunds

Revision ID: e1f2a3b4c5d6
Revises: c3d4e5f6a7b8
Create Date: 2026-08-29 00:00:00.000000

Reverses the Pay Hero rename from aa2b7c3d8e91 back to provider-neutral
mpesa_* names (M-Pesa is the rail no matter who fronts it), widens money
columns to Numeric(12, 2), adds the Daraja credential and refund-control
columns, and creates mpesa_refunds: the B2C refund register.

Tolerates three starting shapes:

  Shape A: payhero_* present (the current state) -> rename in place, so
    the data and the foreign keys survive.
  Shape B: mpesa_* already present (a legacy tenant that never got the
    payhero rename from aa2b7c3d8e91) -> leave the tables, add the
    missing columns.
  Shape C: neither -> create from scratch.

The column lists below are column-for-column with app/models/mpesa.py so
the create path and the add-missing path cannot drift apart.

Drops the Pay Hero-specific columns (aggregator channel id, aggregator
credentials, settlement bank details) when present: under Daraja there is
no aggregator settlement bank to nominate, Safaricom pays the hospital's
own shortcode directly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Pay Hero-only columns on mpesa_configs (post-rename name). Dropped if
# present, left alone otherwise (a Shape B legacy mpesa_configs never had
# them in the first place).
PAYHERO_ONLY_CONFIG_COLUMNS = (
    "payhero_channel_id",
    "payhero_username_encrypted",
    "payhero_password_encrypted",
    "payhero_webhook_secret_encrypted",
    "settlement_bank_code",
    "settlement_bank_name",
    "settlement_account_number",
    "settlement_account_name",
)


def _table_exists(conn, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


def _column_names(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _index_names(conn, table: str) -> set:
    return {ix["name"] for ix in sa.inspect(conn).get_indexes(table)}


def _mpesa_config_columns():
    """Column-for-column with MpesaConfig. Returns fresh Column instances on
    every call: a Column can only be bound to one table, and both the
    create path and the add-missing path need their own copy.
    """
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shortcode", sa.String(20), nullable=False, server_default=""),
        sa.Column("shortcode_type", sa.String(20), nullable=False, server_default="paybill"),
        sa.Column("environment", sa.String(20), nullable=False, server_default="sandbox"),
        sa.Column("consumer_key_encrypted", sa.String(255), nullable=True),
        sa.Column("consumer_secret_encrypted", sa.String(255), nullable=True),
        sa.Column("passkey_encrypted", sa.String(255), nullable=True),
        sa.Column("initiator_name", sa.String(80), nullable=True),
        sa.Column("initiator_password_encrypted", sa.String(255), nullable=True),
        sa.Column("callback_token_encrypted", sa.String(255), nullable=True),
        sa.Column("callback_token_lookup", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("callback_token_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunds_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("refund_max_amount", sa.Numeric(12, 2), nullable=False, server_default="10000"),
        sa.Column("refund_daily_cap", sa.Numeric(12, 2), nullable=False, server_default="50000"),
        sa.Column("refund_dual_approval_above", sa.Numeric(12, 2), nullable=False, server_default="5000"),
        sa.Column("account_reference", sa.String(50), nullable=True, server_default="HMS-BILLING"),
        sa.Column("transaction_desc", sa.String(100), nullable=True, server_default="Hospital Bill Payment"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("c2b_urls_registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(40), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
    ]


def _mpesa_transaction_columns():
    """Column-for-column with MpesaTransaction. See _mpesa_config_columns."""
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"),
            nullable=True, index=True,
        ),
        sa.Column(
            "dispense_id", sa.Integer(), sa.ForeignKey("dispense_logs.dispense_id"),
            nullable=True, index=True,
        ),
        sa.Column("phone_number", sa.String(20), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("checkout_request_id", sa.String(100), nullable=True, index=True),
        sa.Column("merchant_request_id", sa.String(100), nullable=True, index=True),
        sa.Column("external_reference", sa.String(100), nullable=True, index=True),
        sa.Column("receipt_number", sa.String(50), nullable=True, unique=True, index=True),
        sa.Column("status", sa.String(50), nullable=True, server_default="Pending", index=True),
        sa.Column("result_desc", sa.String(255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_source", sa.String(30), nullable=True),
        sa.Column("transaction_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
        sa.Column("transaction_type", sa.String(10), nullable=False, server_default="STK", index=True),
        sa.Column("bill_ref_number", sa.String(80), nullable=True, index=True),
        sa.Column("match_basis", sa.String(20), nullable=True, index=True),
    ]


def _mpesa_refund_columns():
    """Column-for-column with MpesaRefund. Brand-new table: no legacy shape
    to reconcile, so this is only ever used to create the table fresh."""
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "source_transaction_id", sa.Integer(), sa.ForeignKey("mpesa_transactions.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "invoice_id", sa.Integer(), sa.ForeignKey("invoices.invoice_id"),
            nullable=True, index=True,
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Requested", index=True),
        sa.Column("originator_conversation_id", sa.String(64), nullable=False, unique=True),
        sa.Column("conversation_id", sa.String(64), nullable=True, index=True),
        sa.Column("transaction_receipt", sa.String(50), nullable=True, unique=True, index=True),
        sa.Column("result_desc", sa.String(255), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _add_columns_if_missing(conn, table_name, columns) -> None:
    """Add each column not already on the table, with its index.

    op.add_column does realise a Column's index=True/unique=True into real
    indexes of its own, so handing it a flagged Column and then creating the
    index here raises DuplicateTable. The flags are cleared for the ALTER and
    the index is created explicitly afterwards, which keeps the index name
    under this revision's control and lets it be guarded against a name that
    already exists (a renamed table carries its old indexes with it).
    """
    existing = _column_names(conn, table_name)
    existing_indexes = _index_names(conn, table_name)
    for column in columns:
        if column.name in existing:
            continue
        is_unique = bool(column.unique)
        has_index = bool(column.index)
        column.index = None
        column.unique = None
        op.add_column(table_name, column)
        if has_index or is_unique:
            index_name = f"ix_{table_name}_{column.name}"
            if index_name not in existing_indexes:
                op.create_index(index_name, table_name, [column.name], unique=is_unique)
                existing_indexes.add(index_name)


def _drop_columns_if_present(conn, table_name, column_names) -> None:
    existing = _column_names(conn, table_name)
    for name in column_names:
        if name in existing:
            op.drop_column(table_name, name)


def _widen_numeric_column(conn, table_name, column_name, precision, scale) -> None:
    """Widen a pre-existing Numeric column to (precision, scale).

    _add_columns_if_missing only adds columns that are absent, so a money
    column that already existed under the old Numeric(10, 2) (amount, on a
    renamed or legacy table) is never touched by it. This is the one place
    the old precision is upgraded to the Numeric(12, 2) the model declares.
    A no-op when the column is already at the target precision/scale, or
    doesn't exist yet (the fresh-create path already builds it correctly).
    """
    for col in sa.inspect(conn).get_columns(table_name):
        if col["name"] != column_name:
            continue
        col_type = col["type"]
        if (getattr(col_type, "precision", None), getattr(col_type, "scale", None)) != (precision, scale):
            op.alter_column(
                table_name, column_name,
                type_=sa.Numeric(precision, scale),
                existing_nullable=False,
            )
        return


def upgrade() -> None:
    conn = op.get_bind()

    # Shape A: payhero_* present (the current state) -> rename in place, so
    # the data and the foreign keys survive.
    # Shape B: mpesa_* already present (a legacy tenant that never got the
    # payhero rename) -> leave the tables, add the missing columns.
    # Shape C: neither -> create from scratch.
    for old, new in (
        ("payhero_configs", "mpesa_configs"),
        ("payhero_transactions", "mpesa_transactions"),
    ):
        if _table_exists(conn, old) and not _table_exists(conn, new):
            op.rename_table(old, new)

    # ── mpesa_configs ────────────────────────────────────────────────────
    if not _table_exists(conn, "mpesa_configs"):
        op.create_table("mpesa_configs", *_mpesa_config_columns())
    else:
        # A Shape B legacy mpesa_configs (never renamed to payhero_configs)
        # still carries the pre-rename column name; a Shape A table
        # (renamed from payhero_configs) already has shortcode.
        cols = _column_names(conn, "mpesa_configs")
        if "paybill_number" in cols and "shortcode" not in cols:
            op.alter_column("mpesa_configs", "paybill_number", new_column_name="shortcode")
        _add_columns_if_missing(conn, "mpesa_configs", _mpesa_config_columns())
        _drop_columns_if_present(conn, "mpesa_configs", PAYHERO_ONLY_CONFIG_COLUMNS)

    # ── mpesa_transactions ───────────────────────────────────────────────
    if not _table_exists(conn, "mpesa_transactions"):
        op.create_table("mpesa_transactions", *_mpesa_transaction_columns())
    else:
        _add_columns_if_missing(conn, "mpesa_transactions", _mpesa_transaction_columns())
        # amount pre-dates this revision at Numeric(10, 2) on both a renamed
        # payhero_transactions and a legacy mpesa_transactions; add-missing
        # skips it because the column already exists, so it is widened here.
        _widen_numeric_column(conn, "mpesa_transactions", "amount", 12, 2)

    if "ix_mpesa_txn_status_date" not in _index_names(conn, "mpesa_transactions"):
        op.create_index(
            "ix_mpesa_txn_status_date", "mpesa_transactions", ["status", "transaction_date"]
        )

    # ── mpesa_refunds ────────────────────────────────────────────────────
    # Brand new table: no prior shape to reconcile, so a plain
    # create-if-not-exists guard is enough.
    if not _table_exists(conn, "mpesa_refunds"):
        op.create_table("mpesa_refunds", *_mpesa_refund_columns())


def downgrade() -> None:
    """Reverses the renames and drops mpesa_refunds.

    Lossy: the Daraja credential and refund-control columns added here are
    not recreated as payhero_* columns on the way back down, the same way
    aa2b7c3d8e91's downgrade does not restore the Daraja columns it dropped.
    """
    conn = op.get_bind()
    if _table_exists(conn, "mpesa_refunds"):
        op.drop_table("mpesa_refunds")
    if _table_exists(conn, "mpesa_transactions") and not _table_exists(conn, "payhero_transactions"):
        op.rename_table("mpesa_transactions", "payhero_transactions")
    if _table_exists(conn, "mpesa_configs") and not _table_exists(conn, "payhero_configs"):
        op.rename_table("mpesa_configs", "payhero_configs")
