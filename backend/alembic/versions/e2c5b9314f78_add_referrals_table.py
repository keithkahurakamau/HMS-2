"""Add external referrals table

Revision ID: e2c5b9314f78
Revises: d8b46e91527a
Create Date: 2026-05-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2c5b9314f78"
down_revision: Union[str, Sequence[str], None] = "d8b46e91527a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("referral_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("record_id", sa.Integer(), sa.ForeignKey("medical_records.record_id", ondelete="SET NULL"), nullable=True),
        sa.Column("specialty", sa.String(length=120), nullable=False),
        sa.Column("target_facility", sa.String(length=255), nullable=True),
        sa.Column("target_clinician", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("clinical_summary", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(length=20), nullable=False, server_default=sa.text("'Routine'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'Pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_referrals_patient_id", "referrals", ["patient_id"])
    op.create_index("ix_referrals_referred_by", "referrals", ["referred_by"])
    op.create_index("ix_referrals_record_id", "referrals", ["record_id"])
    op.create_index("ix_referrals_status", "referrals", ["status"])
    op.create_index("ix_referrals_created_at", "referrals", ["created_at"])
    op.create_index("idx_referral_patient_status", "referrals", ["patient_id", "status"])

    # New permission for managing referrals + grant to roles that already
    # write clinical data.
    op.execute(
        """
        INSERT INTO permissions (codename, description)
        SELECT 'referrals:manage', 'Create and update specialist referrals'
        WHERE NOT EXISTS (
            SELECT 1 FROM permissions WHERE codename = 'referrals:manage'
        );
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r CROSS JOIN permissions p
        WHERE p.codename = 'referrals:manage'
          AND r.name IN ('Admin', 'Doctor')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
          );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename = 'referrals:manage');"
    )
    op.execute("DELETE FROM permissions WHERE codename = 'referrals:manage';")
    op.drop_index("idx_referral_patient_status", table_name="referrals")
    op.drop_index("ix_referrals_created_at", table_name="referrals")
    op.drop_index("ix_referrals_status", table_name="referrals")
    op.drop_index("ix_referrals_record_id", table_name="referrals")
    op.drop_index("ix_referrals_referred_by", table_name="referrals")
    op.drop_index("ix_referrals_patient_id", table_name="referrals")
    op.drop_table("referrals")
