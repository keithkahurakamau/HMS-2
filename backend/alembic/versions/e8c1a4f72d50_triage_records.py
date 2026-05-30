"""Triage module — nurse-captured vitals before the clinical desk

Revision ID: e8c1a4f72d50
Revises: d7a1f9c34b85
Create Date: 2026-05-30 09:00:00.000000

1 new tenant table:
- triage_records   (vitals + acuity recorded by a nurse, prefills the
                    doctor's encounter form)

Permissions (triage:read / triage:write) and the Nurse/Doctor grants are
reconciled idempotently on boot by
tenant_provisioning.backfill_admin_permissions, so this migration only
manages the table.

Idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8c1a4f72d50"
down_revision: Union[str, Sequence[str], None] = "d7a1f9c34b85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _missing(inspector, name: str) -> bool:
    return name not in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _missing(inspector, "triage_records"):
        op.create_table(
            "triage_records",
            sa.Column("triage_id", sa.Integer(), primary_key=True),
            sa.Column("patient_id", sa.Integer(),
                      sa.ForeignKey("patients.patient_id"), nullable=False),
            sa.Column("queue_id", sa.Integer(),
                      sa.ForeignKey("patient_queue.queue_id"), nullable=True),
            sa.Column("nurse_id", sa.Integer(),
                      sa.ForeignKey("users.user_id"), nullable=False),
            # Vitals
            sa.Column("blood_pressure", sa.String(length=20), nullable=True),
            sa.Column("heart_rate", sa.Integer(), nullable=True),
            sa.Column("respiratory_rate", sa.Integer(), nullable=True),
            sa.Column("temperature", sa.Float(), nullable=True),
            sa.Column("spo2", sa.Integer(), nullable=True),
            sa.Column("weight_kg", sa.Float(), nullable=True),
            sa.Column("height_cm", sa.Float(), nullable=True),
            sa.Column("calculated_bmi", sa.Float(), nullable=True),
            sa.Column("pain_score", sa.Integer(), nullable=True),
            sa.Column("blood_glucose", sa.Float(), nullable=True),
            # Assessment
            sa.Column("chief_complaint", sa.String(), nullable=True),
            sa.Column("acuity_level", sa.Integer(), nullable=True, server_default="3"),
            sa.Column("triage_notes", sa.String(), nullable=True),
            sa.Column("disposition", sa.String(length=50), nullable=True,
                      server_default="Consultation"),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
        )
        op.create_index("ix_triage_records_patient_id", "triage_records", ["patient_id"])
        op.create_index("ix_triage_records_queue_id", "triage_records", ["queue_id"])
        op.create_index("ix_triage_records_nurse_id", "triage_records", ["nurse_id"])
        op.create_index("ix_triage_records_created_at", "triage_records", ["created_at"])
        op.create_index(
            "idx_triage_patient_time", "triage_records", ["patient_id", "created_at"]
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS triage_records CASCADE;")
