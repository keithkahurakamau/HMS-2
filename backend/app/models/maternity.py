"""Maternity module: pregnancy episodes, ANC/PNC visits, labor partograph,
deliveries, newborns.

A pregnancy is a first-class *episode* a patient can have at most one Active
of at a time (partial unique index). Labor rides a normal wards admission via
the thin `labor_admissions` link table — bed management and daily ward billing
stay in the wards module. Partograph entries are append-only: corrections are
new rows pointing at the row they supersede via `corrects_entry_id`.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class PregnancyEpisode(Base):
    __tablename__ = "pregnancy_episodes"

    episode_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    gravida = Column(Integer, nullable=False, default=1)
    para = Column(Integer, nullable=False, default=0)
    lmp = Column(Date, nullable=True)
    edd = Column(Date, nullable=True)
    blood_group = Column(String(8), nullable=True)
    rhesus = Column(String(4), nullable=True)
    risk_flags = Column(Text, nullable=True)
    # Active | Delivered | Closed | Transferred
    status = Column(String(20), nullable=False, default="Active", index=True)
    created_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    patient = relationship("Patient")
    anc_visits = relationship("AncVisit", backref="episode", cascade="all, delete-orphan")
    pnc_visits = relationship("PncVisit", backref="episode", cascade="all, delete-orphan")

    __table_args__ = (
        # One Active pregnancy per patient. Enforced in Postgres via the
        # partial unique index created in the alembic revision; declared here
        # for create_all parity on fresh bootstraps.
        Index(
            "uq_pregnancy_active_per_patient",
            "patient_id",
            unique=True,
            postgresql_where=(status == "Active"),
        ),
    )


class AncVisit(Base):
    __tablename__ = "anc_visits"

    visit_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    visit_number = Column(Integer, nullable=False, default=1)
    visit_date = Column(Date, nullable=False)
    gestation_weeks = Column(Integer, nullable=True)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    weight_kg = Column(Numeric(5, 1), nullable=True)
    fundal_height_cm = Column(Numeric(4, 1), nullable=True)
    fetal_heart_rate = Column(Integer, nullable=True)
    urine_dip = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LaborAdmission(Base):
    __tablename__ = "labor_admissions"

    labor_admission_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    admission_id = Column(Integer, ForeignKey("admission_records.admission_id", ondelete="CASCADE"), nullable=False, unique=True)
    # Partograph time zero: set when the first >= 4 cm entry lands, or manually.
    active_labor_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    episode = relationship("PregnancyEpisode", backref="labor_admissions")
    entries = relationship("PartographEntry", backref="labor_admission", cascade="all, delete-orphan")


class PartographEntry(Base):
    """Append-only. No UPDATE/DELETE endpoints exist; corrections are new
    rows pointing at the superseded row via corrects_entry_id."""
    __tablename__ = "partograph_entries"

    entry_id = Column(Integer, primary_key=True)
    labor_admission_id = Column(Integer, ForeignKey("labor_admissions.labor_admission_id", ondelete="CASCADE"), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cervical_dilation_cm = Column(Numeric(3, 1), nullable=True)
    descent_fifths = Column(Integer, nullable=True)
    contractions_per_10min = Column(Integer, nullable=True)
    contraction_duration_sec = Column(Integer, nullable=True)
    fetal_heart_rate = Column(Integer, nullable=True)
    liquor = Column(String(4), nullable=True)     # I / C / M1 / M2 / M3 / B
    moulding = Column(String(4), nullable=True)   # 0 / + / ++ / +++
    maternal_bp_systolic = Column(Integer, nullable=True)
    maternal_bp_diastolic = Column(Integer, nullable=True)
    maternal_pulse = Column(Integer, nullable=True)
    temperature_c = Column(Numeric(3, 1), nullable=True)
    drugs_note = Column(String(255), nullable=True)
    corrects_entry_id = Column(Integer, ForeignKey("partograph_entries.entry_id", ondelete="SET NULL"), nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeliveryRecord(Base):
    __tablename__ = "delivery_records"

    delivery_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    labor_admission_id = Column(Integer, ForeignKey("labor_admissions.labor_admission_id", ondelete="SET NULL"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=False)
    # SVD | Assisted | CSection | Breech
    mode = Column(String(20), nullable=False)
    placenta_complete = Column(Boolean, nullable=True)
    blood_loss_ml = Column(Integer, nullable=True)
    perineum = Column(String(40), nullable=True)
    complications = Column(Text, nullable=True)
    # Stable | Referred | Deceased
    mother_status = Column(String(20), nullable=False, default="Stable")
    conducted_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    assistant_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    episode = relationship("PregnancyEpisode", backref="deliveries")
    newborns = relationship("NewbornRecord", backref="delivery", cascade="all, delete-orphan")


class NewbornRecord(Base):
    __tablename__ = "newborn_records"

    newborn_id = Column(Integer, primary_key=True)
    delivery_id = Column(Integer, ForeignKey("delivery_records.delivery_id", ondelete="CASCADE"), nullable=False, index=True)
    birth_order = Column(Integer, nullable=False, default=1)
    sex = Column(String(10), nullable=False)
    weight_g = Column(Integer, nullable=True)
    apgar_1 = Column(Integer, nullable=True)
    apgar_5 = Column(Integer, nullable=True)
    apgar_10 = Column(Integer, nullable=True)
    # Live | FSB | MSB
    outcome = Column(String(10), nullable=False, default="Live")
    resuscitated = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    registered_patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PncVisit(Base):
    __tablename__ = "pnc_visits"

    visit_id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("pregnancy_episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    newborn_id = Column(Integer, ForeignKey("newborn_records.newborn_id", ondelete="SET NULL"), nullable=True)
    visit_number = Column(Integer, nullable=False, default=1)
    visit_date = Column(Date, nullable=False)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    weight_kg = Column(Numeric(5, 1), nullable=True)
    involution = Column(String(40), nullable=True)
    lochia = Column(String(40), nullable=True)
    feeding = Column(String(40), nullable=True)
    cord_status = Column(String(40), nullable=True)
    baby_weight_g = Column(Integer, nullable=True)
    urine_dip = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
