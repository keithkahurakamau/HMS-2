"""Dialysis / renal module: unit setup (checklists, machines), patient renal
profile (vascular access, recurring schedule), per-session orders with renal
prescription + anticoagulation, append-only intradialytic observations,
complications, adequacy (URR + Kt/V), consumables, and checklist runs.

A dialysis *order* is one haemodialysis session. A patient may have at most one
*live* (non-terminal) session at a time — enforced by a partial unique index,
same convention as maternity's active-episode guard. Observations are
append-only: corrections are new rows pointing at the row they supersede via
`corrects_obs_id` (mirrors the partograph pattern).
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.config.database import Base


# ── A · Unit setup ──────────────────────────────────────────────────────────
class DialysisChecklist(Base):
    __tablename__ = "dialysis_checklists"

    checklist_id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DialysisMachine(Base):
    __tablename__ = "dialysis_machines"

    machine_id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    model = Column(String(80), nullable=True)
    station = Column(String(40), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    last_serviced = Column(Date, nullable=True)
    hours_run = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── B · Patient renal profile (longitudinal) ────────────────────────────────
class VascularAccess(Base):
    __tablename__ = "vascular_accesses"

    access_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    # AVF | AVG | Tunneled-cath | Non-tunneled-cath | Permcath
    type = Column(String(30), nullable=False)
    site = Column(String(80), nullable=True)
    created_date = Column(Date, nullable=True)
    # Active | Maturing | Failed | Infected | Removed
    status = Column(String(20), nullable=False, default="Active", index=True)
    last_assessed = Column(Date, nullable=True)
    complications = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DialysisSchedule(Base):
    __tablename__ = "dialysis_schedules"

    schedule_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    # MWF | TTS | Daily | Custom
    pattern = Column(String(20), nullable=False)
    # Morning | Afternoon | Evening
    shift = Column(String(20), nullable=True)
    sessions_per_week = Column(Integer, nullable=True)
    preferred_machine_id = Column(Integer, ForeignKey("dialysis_machines.machine_id", ondelete="SET NULL"), nullable=True)
    target_dry_weight_kg = Column(Numeric(5, 1), nullable=True)
    start_date = Column(Date, nullable=True)
    # Active | Paused | Ended
    status = Column(String(20), nullable=False, default="Active", index=True)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── C · The session ─────────────────────────────────────────────────────────
class DialysisOrder(Base):
    __tablename__ = "dialysis_orders"

    order_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    treatment_no = Column(Integer, nullable=True)
    schedule_id = Column(Integer, ForeignKey("dialysis_schedules.schedule_id", ondelete="SET NULL"), nullable=True)
    vascular_access_id = Column(Integer, ForeignKey("vascular_accesses.access_id", ondelete="SET NULL"), nullable=True)
    machine_id = Column(Integer, ForeignKey("dialysis_machines.machine_id", ondelete="SET NULL"), nullable=True)
    nephrologist_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    ordered_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    screening_date = Column(Date, nullable=True)
    hiv_hbv_status = Column(String(20), nullable=True)
    blood_group = Column(String(8), nullable=True)

    # Prescription
    dialyzer = Column(String(60), nullable=True)
    membrane_type = Column(String(60), nullable=True)
    priming = Column(String(60), nullable=True)
    k_bath = Column(String(20), nullable=True)
    dialysate_calcium = Column(String(20), nullable=True)
    dialysate_bicarbonate = Column(String(20), nullable=True)
    dialysate_sodium = Column(String(20), nullable=True)
    dialysate_temp_c = Column(Numeric(3, 1), nullable=True)
    blood_flow_target = Column(Integer, nullable=True)
    dialysate_flow_target = Column(Integer, nullable=True)
    treatment_time_min = Column(Integer, nullable=True)

    # Anticoagulation — Heparin | Heparin-free | LMWH
    anticoag_type = Column(String(20), nullable=True)
    heparin_loading_dose = Column(String(40), nullable=True)
    heparin_maintenance_dose = Column(String(40), nullable=True)
    heparin_stop_time = Column(String(20), nullable=True)

    # Fluid
    pre_weight_kg = Column(Numeric(5, 1), nullable=True)
    dry_weight_kg = Column(Numeric(5, 1), nullable=True)
    post_weight_kg = Column(Numeric(5, 1), nullable=True)
    target_uf_ml = Column(Integer, nullable=True)
    intake_ml = Column(Integer, nullable=True)
    fluid_removal_goal_ml = Column(Integer, nullable=True)

    # State machine — Ordered | Connected | Disconnected | Completed | Cancelled
    status = Column(String(20), nullable=False, default="Ordered", index=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    patient = relationship("Patient")
    observations = relationship("DialysisObservation", backref="order", cascade="all, delete-orphan")
    complications = relationship("DialysisComplication", backref="order", cascade="all, delete-orphan")
    adequacy = relationship("DialysisAdequacy", backref="order", uselist=False, cascade="all, delete-orphan")
    consumables = relationship("DialysisConsumable", backref="order", cascade="all, delete-orphan")
    checklist_runs = relationship("DialysisChecklistRun", backref="order", cascade="all, delete-orphan")

    __table_args__ = (
        # One live (non-terminal) session per patient. Enforced in Postgres via
        # the partial unique index created in the alembic revision; declared
        # here for create_all parity on fresh bootstraps.
        Index(
            "uq_dialysis_active_per_patient",
            "patient_id",
            unique=True,
            postgresql_where=text("status NOT IN ('Completed','Cancelled')"),
        ),
    )


# ── D · Intra- & post-session ───────────────────────────────────────────────
class DialysisObservation(Base):
    """Append-only. No UPDATE/DELETE endpoints; corrections are new rows
    pointing at the superseded row via corrects_obs_id."""
    __tablename__ = "dialysis_observations"

    obs_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    pulse = Column(Integer, nullable=True)
    venous_pressure = Column(Integer, nullable=True)
    arterial_pressure = Column(Integer, nullable=True)
    tmp = Column(Integer, nullable=True)
    conductivity = Column(Numeric(4, 1), nullable=True)
    blood_flow_rate = Column(Integer, nullable=True)
    dialysate_flow_rate = Column(Integer, nullable=True)
    uf_volume_ml = Column(Integer, nullable=True)
    blood_volume_processed_l = Column(Numeric(5, 1), nullable=True)
    temperature_c = Column(Numeric(3, 1), nullable=True)
    heparin_note = Column(String(255), nullable=True)
    corrects_obs_id = Column(Integer, ForeignKey("dialysis_observations.obs_id", ondelete="SET NULL"), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DialysisComplication(Base):
    __tablename__ = "dialysis_complications"

    complication_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Hypotension|Cramps|Nausea|Vomiting|Clotting|Bleeding|Chest-pain|Fever|Disequilibrium
    type = Column(String(30), nullable=False)
    intervention = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DialysisAdequacy(Base):
    __tablename__ = "dialysis_adequacy"

    adequacy_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    pre_urea = Column(Numeric(6, 2), nullable=True)
    post_urea = Column(Numeric(6, 2), nullable=True)
    pre_creatinine = Column(Numeric(6, 2), nullable=True)
    post_creatinine = Column(Numeric(6, 2), nullable=True)
    pre_potassium = Column(Numeric(4, 2), nullable=True)
    post_potassium = Column(Numeric(4, 2), nullable=True)
    pre_hb = Column(Numeric(4, 1), nullable=True)
    ultrafiltration_actual_ml = Column(Integer, nullable=True)
    session_duration_min = Column(Integer, nullable=True)
    urr = Column(Numeric(4, 1), nullable=True)      # computed
    kt_v = Column(Numeric(4, 2), nullable=True)     # computed
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)


class DialysisConsumable(Base):
    __tablename__ = "dialysis_consumables"

    consumable_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String(120), nullable=True)
    qty = Column(Numeric(6, 2), nullable=True)
    dialyzer_reuse_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DialysisChecklistRun(Base):
    __tablename__ = "dialysis_checklist_runs"

    run_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("dialysis_orders.order_id", ondelete="CASCADE"), nullable=False, index=True)
    checklist_id = Column(Integer, ForeignKey("dialysis_checklists.checklist_id", ondelete="SET NULL"), nullable=True)
    passed = Column(Boolean, nullable=False, default=False)
    note = Column(String(255), nullable=True)
    checked_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
