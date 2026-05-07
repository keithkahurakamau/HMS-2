"""
KDPA Section 43 — Breach notification within 72 hours.
A BreachIncident is a structured record of a suspected/confirmed data breach.
The schema captures everything required for the Office of the Data Protection
Commissioner notification: nature, affected categories, likely consequences,
and the mitigation steps taken.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.config.database import Base


class BreachIncident(Base):
    __tablename__ = "breach_incidents"

    incident_id = Column(Integer, primary_key=True)

    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    reported_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    severity = Column(String(20), nullable=False, default="Medium")  # Low, Medium, High, Critical
    nature = Column(String(100), nullable=False)  # e.g., "Unauthorized access", "Loss of device", "Phishing"
    description = Column(Text, nullable=False)

    # KDPA S.43(2)(a): nature of breach + affected categories
    affected_categories = Column(JSONB, nullable=True)  # ["patients", "staff", "clinical_records"]
    estimated_records_affected = Column(Integer, nullable=True)
    affected_patient_ids = Column(JSONB, nullable=True)  # list[int] when known

    # KDPA S.43(2)(c): likely consequences
    likely_consequences = Column(Text, nullable=True)
    # KDPA S.43(2)(d): measures taken or proposed
    mitigation_steps = Column(Text, nullable=True)

    # ODPC notification tracking
    odpc_notified = Column(Boolean, default=False, nullable=False)
    odpc_notified_at = Column(DateTime(timezone=True), nullable=True)
    odpc_reference = Column(String(100), nullable=True)

    # Patient notification tracking
    patients_notified = Column(Boolean, default=False, nullable=False)
    patients_notified_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(30), default="Open", nullable=False)  # Open, Investigating, Contained, Closed
    closed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_breach_status_detected", "status", "detected_at"),
    )
