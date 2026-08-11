"""Add dialysis / renal module tables + permissions

Revision ID: d1a15c0b7e42
Revises: c4f1a2b8d6e3
Create Date: 2026-07-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a15c0b7e42"
down_revision: Union[str, Sequence[str], None] = "c4f1a2b8d6e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── A · Unit setup ──────────────────────────────────────────────────────
    op.create_table(
        "dialysis_checklists",
        sa.Column("checklist_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "dialysis_machines",
        sa.Column("machine_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("station", sa.String(40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_serviced", sa.Date(), nullable=True),
        sa.Column("hours_run", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── B · Patient renal profile ───────────────────────────────────────────
    op.create_table(
        "vascular_accesses",
        sa.Column("access_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("site", sa.String(80), nullable=True),
        sa.Column("created_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("last_assessed", sa.Date(), nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vascular_accesses_patient_id", "vascular_accesses", ["patient_id"])
    op.create_index("ix_vascular_accesses_status", "vascular_accesses", ["status"])

    op.create_table(
        "dialysis_schedules",
        sa.Column("schedule_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("pattern", sa.String(20), nullable=False),
        sa.Column("shift", sa.String(20), nullable=True),
        sa.Column("sessions_per_week", sa.Integer(), nullable=True),
        sa.Column("preferred_machine_id", sa.Integer(), sa.ForeignKey("dialysis_machines.machine_id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_dry_weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_schedules_patient_id", "dialysis_schedules", ["patient_id"])
    op.create_index("ix_dialysis_schedules_status", "dialysis_schedules", ["status"])

    # ── C · The session ─────────────────────────────────────────────────────
    op.create_table(
        "dialysis_orders",
        sa.Column("order_id", sa.Integer(), primary_key=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False),
        sa.Column("treatment_no", sa.Integer(), nullable=True),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("dialysis_schedules.schedule_id", ondelete="SET NULL"), nullable=True),
        sa.Column("vascular_access_id", sa.Integer(), sa.ForeignKey("vascular_accesses.access_id", ondelete="SET NULL"), nullable=True),
        sa.Column("machine_id", sa.Integer(), sa.ForeignKey("dialysis_machines.machine_id", ondelete="SET NULL"), nullable=True),
        sa.Column("nephrologist_id", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("ordered_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("screening_date", sa.Date(), nullable=True),
        sa.Column("hiv_hbv_status", sa.String(20), nullable=True),
        sa.Column("blood_group", sa.String(8), nullable=True),
        sa.Column("dialyzer", sa.String(60), nullable=True),
        sa.Column("membrane_type", sa.String(60), nullable=True),
        sa.Column("priming", sa.String(60), nullable=True),
        sa.Column("k_bath", sa.String(20), nullable=True),
        sa.Column("dialysate_calcium", sa.String(20), nullable=True),
        sa.Column("dialysate_bicarbonate", sa.String(20), nullable=True),
        sa.Column("dialysate_sodium", sa.String(20), nullable=True),
        sa.Column("dialysate_temp_c", sa.Numeric(3, 1), nullable=True),
        sa.Column("blood_flow_target", sa.Integer(), nullable=True),
        sa.Column("dialysate_flow_target", sa.Integer(), nullable=True),
        sa.Column("treatment_time_min", sa.Integer(), nullable=True),
        sa.Column("anticoag_type", sa.String(20), nullable=True),
        sa.Column("heparin_loading_dose", sa.String(40), nullable=True),
        sa.Column("heparin_maintenance_dose", sa.String(40), nullable=True),
        sa.Column("heparin_stop_time", sa.String(20), nullable=True),
        sa.Column("pre_weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("dry_weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("post_weight_kg", sa.Numeric(5, 1), nullable=True),
        sa.Column("target_uf_ml", sa.Integer(), nullable=True),
        sa.Column("intake_ml", sa.Integer(), nullable=True),
        sa.Column("fluid_removal_goal_ml", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'Ordered'")),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_orders_patient_id", "dialysis_orders", ["patient_id"])
    op.create_index("ix_dialysis_orders_status", "dialysis_orders", ["status"])
    op.create_index(
        "uq_dialysis_active_per_patient", "dialysis_orders", ["patient_id"],
        unique=True, postgresql_where=sa.text("status NOT IN ('Completed','Cancelled')"),
    )

    # ── D · Intra- & post-session ───────────────────────────────────────────
    op.create_table(
        "dialysis_observations",
        sa.Column("obs_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("bp_systolic", sa.Integer(), nullable=True),
        sa.Column("bp_diastolic", sa.Integer(), nullable=True),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("venous_pressure", sa.Integer(), nullable=True),
        sa.Column("arterial_pressure", sa.Integer(), nullable=True),
        sa.Column("tmp", sa.Integer(), nullable=True),
        sa.Column("conductivity", sa.Numeric(4, 1), nullable=True),
        sa.Column("blood_flow_rate", sa.Integer(), nullable=True),
        sa.Column("dialysate_flow_rate", sa.Integer(), nullable=True),
        sa.Column("uf_volume_ml", sa.Integer(), nullable=True),
        sa.Column("blood_volume_processed_l", sa.Numeric(5, 1), nullable=True),
        sa.Column("temperature_c", sa.Numeric(3, 1), nullable=True),
        sa.Column("heparin_note", sa.String(255), nullable=True),
        sa.Column("corrects_obs_id", sa.Integer(), sa.ForeignKey("dialysis_observations.obs_id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_observations_order_id", "dialysis_observations", ["order_id"])

    op.create_table(
        "dialysis_complications",
        sa.Column("complication_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("intervention", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_complications_order_id", "dialysis_complications", ["order_id"])

    op.create_table(
        "dialysis_adequacy",
        sa.Column("adequacy_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("pre_urea", sa.Numeric(6, 2), nullable=True),
        sa.Column("post_urea", sa.Numeric(6, 2), nullable=True),
        sa.Column("pre_creatinine", sa.Numeric(6, 2), nullable=True),
        sa.Column("post_creatinine", sa.Numeric(6, 2), nullable=True),
        sa.Column("pre_potassium", sa.Numeric(4, 2), nullable=True),
        sa.Column("post_potassium", sa.Numeric(4, 2), nullable=True),
        sa.Column("pre_hb", sa.Numeric(4, 1), nullable=True),
        sa.Column("ultrafiltration_actual_ml", sa.Integer(), nullable=True),
        sa.Column("session_duration_min", sa.Integer(), nullable=True),
        sa.Column("urr", sa.Numeric(4, 1), nullable=True),
        sa.Column("kt_v", sa.Numeric(4, 2), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_dialysis_adequacy_order_id", "dialysis_adequacy", ["order_id"], unique=True)

    op.create_table(
        "dialysis_consumables",
        sa.Column("consumable_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.item_id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_name", sa.String(120), nullable=True),
        sa.Column("qty", sa.Numeric(6, 2), nullable=True),
        sa.Column("dialyzer_reuse_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_consumables_order_id", "dialysis_consumables", ["order_id"])

    op.create_table(
        "dialysis_checklist_runs",
        sa.Column("run_id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("checklist_id", sa.Integer(), sa.ForeignKey("dialysis_checklists.checklist_id", ondelete="SET NULL"), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("checked_by", sa.Integer(), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dialysis_checklist_runs_order_id", "dialysis_checklist_runs", ["order_id"])

    # Permissions + base role grants (mirrors the maternity revision).
    for codename, description in (
        ("dialysis:read", "View dialysis orders, observations, and adequacy"),
        ("dialysis:manage", "Order dialysis, record observations/adequacy, manage checklists"),
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
        "(SELECT permission_id FROM permissions WHERE codename IN ('dialysis:read', 'dialysis:manage'));"
    )
    op.execute("DELETE FROM permissions WHERE codename IN ('dialysis:read', 'dialysis:manage');")
    for table in (
        "dialysis_checklist_runs", "dialysis_consumables", "dialysis_adequacy",
        "dialysis_complications", "dialysis_observations", "dialysis_orders",
        "dialysis_schedules", "vascular_accesses", "dialysis_machines",
        "dialysis_checklists",
    ):
        op.drop_table(table)
