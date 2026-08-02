"""DoctorV2: clinical_files attachments table + medical_records.assessment_plan

Revision ID: a1b2c3d4e5f6
Revises: f3c73d2e5a91
Create Date: 2026-08-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3c73d2e5a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clinical_files",
        sa.Column("file_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_id", sa.Integer(), sa.ForeignKey("medical_records.record_id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinical_files_patient_id", "clinical_files", ["patient_id"])

    op.add_column("medical_records", sa.Column("assessment_plan", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_records", "assessment_plan")
    op.drop_index("ix_clinical_files_patient_id", table_name="clinical_files")
    op.drop_table("clinical_files")
