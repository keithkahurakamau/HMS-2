"""Add theatre / surgery module tables + permissions

Revision ID: e2b62c1d9f34
Revises: d1a15c0b7e42
Create Date: 2026-07-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b62c1d9f34"
down_revision: Union[str, Sequence[str], None] = "d1a15c0b7e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "theatre_rooms",
        sa.Column("room_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "surgical_checklists",
        sa.Column("checklist_id", sa.Integer(), primary_key=True),
        sa.Column("phase", sa.String(12), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surgical_checklists_phase", "surgical_checklists", ["phase"])

    op.create_table(
        "surgical_cases",
        sa.Column("case_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("admission_id", sa.Integer(), sa.ForeignKey("admission_records.admission_id", ondelete="SET NULL"), nullable=True),
        sa.Column("theatre_room_id", sa.Integer(), sa.ForeignKey("theatre_rooms.room_id", ondelete="SET NULL"), nullable=True),
        sa.Column("primary_surgeon_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("anaesthetist_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("procedure_name", sa.String(200), nullable=False),
        sa.Column("procedure_code", sa.String(40), nullable=True),
        sa.Column("diagnosis", sa.String(255), nullable=True),
        sa.Column("priority", sa.String(12), nullable=False, server_default=sa.text("'Elective'")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default=sa.text("'Scheduled'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surgical_cases_patient_id", "surgical_cases", ["patient_id"])
    op.create_index("ix_surgical_cases_status", "surgical_cases", ["status"])

    op.create_table(
        "surgical_checklist_runs",
        sa.Column("run_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("checklist_id", sa.Integer(), sa.ForeignKey("surgical_checklists.checklist_id", ondelete="SET NULL"), nullable=True),
        sa.Column("phase", sa.String(12), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("checked_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surgical_checklist_runs_case_id", "surgical_checklist_runs", ["case_id"])

    op.create_table(
        "operative_notes",
        sa.Column("note_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("procedure_performed", sa.Text(), nullable=True),
        sa.Column("technique", sa.Text(), nullable=True),
        sa.Column("closure", sa.String(255), nullable=True),
        sa.Column("blood_loss_ml", sa.Integer(), nullable=True),
        sa.Column("specimens", sa.String(255), nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        sa.Column("estimated_duration_min", sa.Integer(), nullable=True),
        sa.Column("surgeon_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_operative_notes_case_id", "operative_notes", ["case_id"], unique=True)

    op.create_table(
        "anaesthesia_records",
        sa.Column("anaesthesia_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("asa_grade", sa.String(4), nullable=True),
        sa.Column("agents", sa.String(255), nullable=True),
        sa.Column("airway", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("anaesthetist_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_anaesthesia_records_case_id", "anaesthesia_records", ["case_id"], unique=True)

    op.create_table(
        "surgical_team_members",
        sa.Column("member_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surgical_team_members_case_id", "surgical_team_members", ["case_id"])

    op.create_table(
        "surgical_consumables",
        sa.Column("consumable_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.item_id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_name", sa.String(120), nullable=True),
        sa.Column("qty", sa.Numeric(6, 2), nullable=True),
        sa.Column("is_implant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("serial_no", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_surgical_consumables_case_id", "surgical_consumables", ["case_id"])

    op.create_table(
        "recovery_observations",
        sa.Column("obs_id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("spo2", sa.Integer(), nullable=True),
        sa.Column("temperature_c", sa.Numeric(3, 1), nullable=True),
        sa.Column("pain_score", sa.Integer(), nullable=True),
        sa.Column("consciousness", sa.String(4), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("corrects_obs_id", sa.Integer(), sa.ForeignKey("recovery_observations.obs_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recovery_observations_case_id", "recovery_observations", ["case_id"])

    for codename, description in (
        ("theatre:read", "View theatre cases, checklists, operative notes"),
        ("theatre:manage", "Schedule/run theatre cases, checklists, operative notes, anaesthesia"),
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
        "(SELECT permission_id FROM permissions WHERE codename IN ('theatre:read', 'theatre:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('theatre:read', 'theatre:manage');")
    for table in (
        "recovery_observations", "surgical_consumables", "surgical_team_members",
        "anaesthesia_records", "operative_notes", "surgical_checklist_runs",
        "surgical_cases", "surgical_checklists", "theatre_rooms",
    ):
        op.drop_table(table)
