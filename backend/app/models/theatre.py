"""Theatre / surgery module: theatre rooms, the WHO Surgical Safety Checklist
(SignIn/TimeOut/SignOut), surgical cases with a state machine, operative notes,
anaesthesia records, surgical team, consumables/implants, and post-op recovery
observations.

A surgical *case* is one operating-theatre episode. Recovery observations are
append-only: corrections are new rows pointing at the superseded row via
`corrects_obs_id` (mirrors the dialysis / partograph pattern). The WHO checklist
is modelled as configurable phase-tagged items plus per-case runs.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


# ── A · Config ──────────────────────────────────────────────────────────────
class TheatreRoom(Base):
    __tablename__ = "theatre_rooms"

    room_id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SurgicalChecklist(Base):
    __tablename__ = "surgical_checklists"

    checklist_id = Column(Integer, primary_key=True)
    # SignIn | TimeOut | SignOut
    phase = Column(String(12), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── B · The case ────────────────────────────────────────────────────────────
class SurgicalCase(Base):
    __tablename__ = "surgical_cases"

    case_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    admission_id = Column(Integer, ForeignKey("admission_records.admission_id", ondelete="SET NULL"), nullable=True)
    theatre_room_id = Column(Integer, ForeignKey("theatre_rooms.room_id", ondelete="SET NULL"), nullable=True)
    primary_surgeon_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    anaesthetist_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    procedure_name = Column(String(200), nullable=False)
    procedure_code = Column(String(40), nullable=True)
    diagnosis = Column(String(255), nullable=True)
    # Elective | Emergency
    priority = Column(String(12), nullable=False, default="Elective")
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    # Scheduled | InTheatre | Recovery | Completed | Cancelled
    status = Column(String(12), nullable=False, default="Scheduled", index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    patient = relationship("Patient")
    checklist_runs = relationship("SurgicalChecklistRun", backref="case", cascade="all, delete-orphan")
    operative_note = relationship("OperativeNote", backref="case", uselist=False, cascade="all, delete-orphan")
    anaesthesia = relationship("AnaesthesiaRecord", backref="case", uselist=False, cascade="all, delete-orphan")
    team_members = relationship("SurgicalTeamMember", backref="case", cascade="all, delete-orphan")
    consumables = relationship("SurgicalConsumable", backref="case", cascade="all, delete-orphan")
    recovery_observations = relationship("RecoveryObservation", backref="case", cascade="all, delete-orphan")


# ── C · Safety checklist runs ───────────────────────────────────────────────
class SurgicalChecklistRun(Base):
    __tablename__ = "surgical_checklist_runs"

    run_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    checklist_id = Column(Integer, ForeignKey("surgical_checklists.checklist_id", ondelete="SET NULL"), nullable=True)
    phase = Column(String(12), nullable=False)
    checked = Column(Boolean, nullable=False, default=False)
    note = Column(String(255), nullable=True)
    checked_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── D · Operative & anaesthesia (1:1 per case) ──────────────────────────────
class OperativeNote(Base):
    __tablename__ = "operative_notes"

    note_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    findings = Column(Text, nullable=True)
    procedure_performed = Column(Text, nullable=True)
    technique = Column(Text, nullable=True)
    closure = Column(String(255), nullable=True)
    blood_loss_ml = Column(Integer, nullable=True)
    specimens = Column(String(255), nullable=True)
    complications = Column(Text, nullable=True)
    estimated_duration_min = Column(Integer, nullable=True)
    surgeon_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AnaesthesiaRecord(Base):
    __tablename__ = "anaesthesia_records"

    anaesthesia_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    # GA | Spinal | Epidural | Local | Sedation
    type = Column(String(12), nullable=False)
    # I | II | III | IV | V
    asa_grade = Column(String(4), nullable=True)
    agents = Column(String(255), nullable=True)
    airway = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    anaesthetist_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ── E · Team ────────────────────────────────────────────────────────────────
class SurgicalTeamMember(Base):
    __tablename__ = "surgical_team_members"

    member_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    name = Column(String(120), nullable=True)
    # Surgeon | Assistant | Anaesthetist | Scrub-Nurse | Circulating-Nurse | Perfusionist
    role = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── F · Materials ───────────────────────────────────────────────────────────
class SurgicalConsumable(Base):
    __tablename__ = "surgical_consumables"

    consumable_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String(120), nullable=True)
    qty = Column(Numeric(6, 2), nullable=True)
    is_implant = Column(Boolean, nullable=False, default=False)
    serial_no = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── G · Recovery (append-only) ──────────────────────────────────────────────
class RecoveryObservation(Base):
    __tablename__ = "recovery_observations"

    obs_id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("surgical_cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    pulse = Column(Integer, nullable=True)
    spo2 = Column(Integer, nullable=True)
    temperature_c = Column(Numeric(3, 1), nullable=True)
    pain_score = Column(Integer, nullable=True)  # 0-10
    consciousness = Column(String(4), nullable=True)  # AVPU
    notes = Column(String(255), nullable=True)
    corrects_obs_id = Column(Integer, ForeignKey("recovery_observations.obs_id", ondelete="SET NULL"), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
