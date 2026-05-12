"""Cheque register — track cheque payments through their lifecycle

Revision ID: f9b2c81e4a37
Revises: d4e8a1b29fc6
Create Date: 2026-05-12 17:00:00.000000

Adds:
- cheques table covering Received → Deposited → Cleared / Bounced / Cancelled
- cheques:read / cheques:manage permissions
- grants cheques:read+manage to Admin, cheques:read+manage to Receptionist,
  cheques:read to Doctor and Nurse (so they can see whether an invoice was
  paid by cheque when reviewing a patient's account).

Idempotent so re-runs are safe.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9b2c81e4a37"
down_revision: Union[str, Sequence[str], None] = "d4e8a1b29fc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "cheques" not in inspector.get_table_names():
        op.create_table(
            "cheques",
            sa.Column("cheque_id", sa.Integer(), primary_key=True),
            sa.Column("cheque_number", sa.String(length=60), nullable=False),
            sa.Column("drawer_name", sa.String(length=255), nullable=False),
            sa.Column("drawer_type", sa.String(length=40), nullable=False, server_default=sa.text("'Other'")),
            sa.Column("bank_name", sa.String(length=120), nullable=False),
            sa.Column("bank_branch", sa.String(length=120), nullable=True),

            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default=sa.text("'KES'")),

            sa.Column("date_on_cheque", sa.Date(), nullable=True),
            sa.Column("date_received", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("deposit_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deposit_account", sa.String(length=120), nullable=True),
            sa.Column("clearance_date", sa.DateTime(timezone=True), nullable=True),

            sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'Received'")),
            sa.Column("bounce_reason", sa.String(length=255), nullable=True),
            sa.Column("cancel_reason", sa.String(length=255), nullable=True),

            sa.Column("invoice_id", sa.Integer(),
                      sa.ForeignKey("invoices.invoice_id", ondelete="SET NULL"), nullable=True),
            sa.Column("patient_id", sa.Integer(),
                      sa.ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True),

            sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("last_updated_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

        op.create_index("ix_cheques_cheque_number", "cheques", ["cheque_number"])
        op.create_index("ix_cheques_date_received", "cheques", ["date_received"])
        op.create_index("ix_cheques_invoice_id", "cheques", ["invoice_id"])
        op.create_index("ix_cheques_patient_id", "cheques", ["patient_id"])
        op.create_index("ix_cheques_received_by", "cheques", ["received_by"])
        op.create_index("ix_cheques_status", "cheques", ["status"])
        op.create_index("idx_cheque_drawer_bank_number", "cheques",
                        ["drawer_name", "bank_name", "cheque_number"])
        op.create_index("idx_cheque_status_received", "cheques",
                        ["status", "date_received"])

    # Permissions catalogue
    for codename, description in [
        ("cheques:read", "View the cheque register"),
        ("cheques:manage", "Record, deposit, clear, bounce, or cancel cheques"),
    ]:
        op.execute(
            sa.text(
                "INSERT INTO permissions (codename, description) "
                "SELECT :c, :d WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = :c)"
            ).bindparams(c=codename, d=description)
        )

    # Grants
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename IN ('cheques:read', 'cheques:manage')
          AND r.name IN ('Admin', 'Receptionist')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )
    # Read-only for clinical roles so they can see payment status during care.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'cheques:read'
          AND r.name IN ('Doctor', 'Nurse')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename IN ('cheques:read', 'cheques:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('cheques:read', 'cheques:manage');")
    op.execute("DROP INDEX IF EXISTS idx_cheque_status_received;")
    op.execute("DROP INDEX IF EXISTS idx_cheque_drawer_bank_number;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_status;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_received_by;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_patient_id;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_invoice_id;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_date_received;")
    op.execute("DROP INDEX IF EXISTS ix_cheques_cheque_number;")
    op.execute("DROP TABLE IF EXISTS cheques;")
