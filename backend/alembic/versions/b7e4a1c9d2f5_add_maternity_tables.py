"""Add maternity module tables + permissions

Revision ID: b7e4a1c9d2f5
Revises: c2d3e4f5a6b7
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e4a1c9d2f5"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pregnancy_episodes",
        sa.Column("episode_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("gravida", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("para", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lmp", sa.Date(), nullable=True),
        sa.Column("edd", sa.Date(), nullable=True),
        sa.Column("blood_group", sa.String(8), nullable=True),
        sa.Column("rhesus", sa.String(4), nullable=True),
        sa.Column("risk_flags", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pregnancy_episodes_patient_id", "pregnancy_episodes", ["patient_id"])
    op.create_index("ix_pregnancy_episodes_status", "pregnancy_episodes", ["status"])
    op.create_index(
        "uq_pregnancy_active_per_patient", "pregnancy_episodes", ["patient_id"],
        unique=True, postgresql_where=sa.text("status = 'Active'"),
    )

    op.create_table(
        "anc_visits",
        sa.Column("visit_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("gestation_weeks", sa.Integer(), nullable=True),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("fundal_height_cm", sa.Numeric(4, 1), nullable=True),
        sa.Column("fetal_heart_rate", sa.Integer(), nullable=True),
        sa.Column("urine_dip", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_anc_visits_episode_id", "anc_visits", ["episode_id"])

    op.create_table(
        "labor_admissions",
        sa.Column("labor_admission_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("admission_id", sa.Integer(), sa.ForeignKey("admission_records.admission_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("active_labor_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_labor_admissions_episode_id", "labor_admissions", ["episode_id"])

    op.create_table(
        "partograph_entries",
        sa.Column("entry_id", sa.Integer(), primary_key=True),
        sa.Column("labor_admission_id", sa.Integer(), sa.ForeignKey("labor_admissions.labor_admission_id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cervical_dilation_cm", sa.Numeric(3, 1), nullable=True),
        sa.Column("descent_fifths", sa.Integer(), nullable=True),
        sa.Column("contractions_per_10min", sa.Integer(), nullable=True),
        sa.Column("contraction_duration_sec", sa.Integer(), nullable=True),
        sa.Column("fetal_heart_rate", sa.Integer(), nullable=True),
        sa.Column("liquor", sa.String(4), nullable=True),
        sa.Column("moulding", sa.String(4), nullable=True),
        sa.Column("maternal_bp_systolic", sa.Integer(), nullable=True),
        sa.Column("maternal_bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("maternal_pulse", sa.Integer(), nullable=True),
        sa.Column("temperature_c", sa.Numeric(3, 1), nullable=True),
        sa.Column("drugs_note", sa.String(255), nullable=True),
        sa.Column("corrects_entry_id", sa.Integer(), sa.ForeignKey("partograph_entries.entry_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_partograph_entries_labor_admission_id", "partograph_entries", ["labor_admission_id"])

    op.create_table(
        "delivery_records",
        sa.Column("delivery_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("labor_admission_id", sa.Integer(), sa.ForeignKey("labor_admissions.labor_admission_id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("placenta_complete", sa.Boolean(), nullable=True),
        sa.Column("blood_loss_ml", sa.Integer(), nullable=True),
        sa.Column("perineum", sa.String(40), nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        sa.Column("mother_status", sa.String(20), nullable=False, server_default=sa.text("'Stable'")),
        sa.Column("conducted_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("assistant_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_delivery_records_episode_id", "delivery_records", ["episode_id"])

    op.create_table(
        "newborn_records",
        sa.Column("newborn_id", sa.Integer(), primary_key=True),
        sa.Column("delivery_id", sa.Integer(), sa.ForeignKey("delivery_records.delivery_id", ondelete="CASCADE"), nullable=False),
        sa.Column("birth_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sex", sa.String(10), nullable=False),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("apgar_1", sa.Integer(), nullable=True),
        sa.Column("apgar_5", sa.Integer(), nullable=True),
        sa.Column("apgar_10", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False, server_default=sa.text("'Live'")),
        sa.Column("resuscitated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("registered_patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_newborn_records_delivery_id", "newborn_records", ["delivery_id"])

    op.create_table(
        "pnc_visits",
        sa.Column("visit_id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False),
        sa.Column("newborn_id", sa.Integer(), sa.ForeignKey("newborn_records.newborn_id", ondelete="SET NULL"), nullable=True),
        sa.Column("visit_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("involution", sa.String(40), nullable=True),
        sa.Column("lochia", sa.String(40), nullable=True),
        sa.Column("feeding", sa.String(40), nullable=True),
        sa.Column("cord_status", sa.String(40), nullable=True),
        sa.Column("baby_weight_g", sa.Integer(), nullable=True),
        sa.Column("urine_dip", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnc_visits_episode_id", "pnc_visits", ["episode_id"])

    # Permissions + base role grants (mirrors e2c5b9314f78 referrals pattern).
    for codename, description in (
        ("maternity:read", "View maternity episodes, partographs, and deliveries"),
        ("maternity:manage", "Record ANC/PNC visits, partograph entries, and deliveries"),
    ):
        op.execute(
            f"""
            INSERT INTO permissions (codename, description)
            SELECT '{codename}', '{description}'
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE codename = '{codename}');
            """
        )
        op.execute(
            f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.role_id, p.permission_id
            FROM roles r CROSS JOIN permissions p
            WHERE p.codename = '{codename}'
              AND r.name IN ('Admin', 'Doctor', 'Nurse')
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
              );
            """
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT permission_id FROM permissions WHERE codename IN ('maternity:read', 'maternity:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('maternity:read', 'maternity:manage');")
    for table in ("pnc_visits", "newborn_records", "delivery_records",
                  "partograph_entries", "labor_admissions", "anc_visits",
                  "pregnancy_episodes"):
        op.drop_table(table)
