"""External / specialist referrals.

Captured at consultation time by the attending doctor when the patient needs
care this facility cannot deliver — onward to a specialist, a higher-level
hospital, or another department within the same facility.

Status flow:
    Pending  → an external referral letter is queued / printable
    Sent     → letter has been delivered to the receiving facility
    Accepted → receiving facility confirmed the appointment
    Completed→ patient was seen + outcome captured
    Cancelled→ withdrawn by the doctor or declined externally
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.config.database import Base


class Referral(Base):
    __tablename__ = "referrals"

    referral_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    referred_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    record_id = Column(Integer, ForeignKey("medical_records.record_id", ondelete="SET NULL"), nullable=True, index=True)

    # What kind of care the patient needs
    specialty = Column(String(120), nullable=False)
    target_facility = Column(String(255), nullable=True)
    target_clinician = Column(String(255), nullable=True)

    # Why the doctor is referring
    reason = Column(Text, nullable=False)
    clinical_summary = Column(Text, nullable=True)

    urgency = Column(String(20), nullable=False, default="Routine")  # Routine | Urgent | Emergency
    status = Column(String(20), nullable=False, default="Pending", index=True)

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient")
    doctor = relationship("User", foreign_keys=[referred_by])

    __table_args__ = (
        Index("idx_referral_patient_status", "patient_id", "status"),
    )
