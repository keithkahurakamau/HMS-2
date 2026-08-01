"""Add clinical-desk extras: sick notes, optical prescriptions, external
requests, order sets + items

Revision ID: f3c73d2e5a91
Revises: e2b62c1d9f34
Create Date: 2026-07-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c73d2e5a91"
down_revision: Union[str, Sequence[str], None] = "e2b62c1d9f34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sick_notes",
        sa.Column("sick_note_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("diagnosis", sa.String(255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("fit_for_duty", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sick_notes_patient_id", "sick_notes", ["patient_id"])

    op.create_table(
        "optical_prescriptions",
        sa.Column("optical_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_sphere", sa.String(12), nullable=True),
        sa.Column("right_cylinder", sa.String(12), nullable=True),
        sa.Column("right_axis", sa.String(12), nullable=True),
        sa.Column("right_add", sa.String(12), nullable=True),
        sa.Column("left_sphere", sa.String(12), nullable=True),
        sa.Column("left_cylinder", sa.String(12), nullable=True),
        sa.Column("left_axis", sa.String(12), nullable=True),
        sa.Column("left_add", sa.String(12), nullable=True),
        sa.Column("pd", sa.String(12), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_optical_prescriptions_patient_id", "optical_prescriptions", ["patient_id"])

    op.create_table(
        "external_requests",
        sa.Column("request_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility", sa.String(160), nullable=True),
        sa.Column("request_type", sa.String(40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_external_requests_patient_id", "external_requests", ["patient_id"])

    op.create_table(
        "order_sets",
        sa.Column("order_set_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "order_set_items",
        sa.Column("item_id", sa.Integer(), primary_key=True),
        sa.Column("order_set_id", sa.Integer(), sa.ForeignKey("order_sets.order_set_id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("ref_code", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_order_set_items_order_set_id", "order_set_items", ["order_set_id"])


def downgrade() -> None:
    for table in ("order_set_items", "order_sets", "external_requests",
                  "optical_prescriptions", "sick_notes"):
        op.drop_table(table)
