"""
Medical History Module - Models
Compliant with: Kenya Data Protection Act 2019 (KDPA), 
Health Act 2017, and the right to privacy under Article 31 of the Constitution of Kenya.

Key Principles Applied:
  - Data Minimisation: Only clinically necessary fields captured.
  - Purpose Limitation: Data collected exclusively for treatment.
  - Access Control: RBAC enforced at the API layer (see routes/medical_history.py).
  - Full Audit Trail: All CREATE/UPDATE/DELETE operations logged in audit_logs table.
  - Consent: Patient consent timestamp and method recorded at point of data collection.
  - Data Integrity: Immutable record_id + created_at prevents tampering.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base


class ConsentRecord(Base):
    """
    KDPA Section 30 / Health Act 2017 - Informed Consent.
    Records that a patient has been informed of their rights regarding their
    medical data, and has consented to its collection and processing.
    """
    __tablename__ = "consent_records"

    consent_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False, index=True)
    recorded_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # What specifically the patient consented to
    consent_type = Column(String(100), nullable=False)  # e.g., "Treatment", "Data Sharing", "Research"
    consent_given = Column(Boolean, default=True, nullable=False)
    
    # Method by which consent was given (Written signature, Verbal, Guardian)
    consent_method = Column(String(100), default="Written", nullable=False)
    # Any specific notes (e.g., "Patient is a minor, consent given by parent John Doe ID:29384756")
    notes = Column(Text, nullable=True)
    
    # For research consent, specify the expiry date (KDPA: time-limited consent)
    consent_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    consented_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    patient = relationship("Patient", backref="consents")
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        Index('idx_consent_patient_type', 'patient_id', 'consent_type'),
    )


class MedicalHistoryEntry(Base):
    """
    The canonical, structured Medical History for a patient.
    This is the 'permanent record' that grows over time with every clinical encounter.
    It is distinct from a MedicalRecord (which is a single visit's SOAP note).
    
    Equivalent to: the 'Folder' held at a patient's regular clinic.
    """
    __tablename__ = "medical_history_entries"

    entry_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False, index=True)
    record_id = Column(Integer, ForeignKey("medical_records.record_id"), nullable=True, index=True)  # Links to a specific visit
    recorded_by = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    
    # Classification of entry
    entry_type = Column(String(50), nullable=False, index=True)
    # Valid types:
    # "SURGICAL_HISTORY"      - Past surgeries and procedures
    # "FAMILY_HISTORY"        - Heritable conditions in blood relatives
    # "SOCIAL_HISTORY"        - Smoking, alcohol, drug use, occupation risk
    # "IMMUNIZATION"          - Vaccine records
    # "ALLERGY"               - Detailed allergy reactions (extends Patient.allergies baseline)
    # "CHRONIC_CONDITION"     - Ongoing long-term diseases (extends Patient.chronic_conditions)
    # "PAST_MEDICAL_EVENT"    - Previous major illnesses (e.g., Malaria, Typhoid, TB)
    # "OBSTETRIC_HISTORY"     - Pregnancies, deliveries, complications (Female patients)
    # "MENTAL_HEALTH"         - Psychiatric diagnoses, therapy history
    
    title = Column(String(255), nullable=False)   # e.g., "Appendectomy", "Penicillin Reaction (Anaphylaxis)"
    description = Column(Text, nullable=False)     # Full detailed narrative
    
    # Date of the event (not the date of recording)
    event_date = Column(String(50), nullable=True)     # Stored as string for flexibility (e.g., "2019", "March 2020")
    severity = Column(String(50), nullable=True)       # Mild, Moderate, Severe, Life-threatening
    status = Column(String(50), default="Active")      # Active, Resolved, Managed, Remission
    
    # Structured extension data (e.g., allergy reaction details, vaccination batch no.)
    extra_data = Column(JSONB, nullable=True)

    # KDPA: Is this entry considered 'Sensitive' data (Mental Health, Obstetric, HIV)?
    # Sensitive data can only be accessed by authorised clinical staff.
    is_sensitive = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    patient = relationship("Patient", backref="history_entries")
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        Index('idx_history_patient_type', 'patient_id', 'entry_type'),
        Index('idx_history_patient_sensitive', 'patient_id', 'is_sensitive'),
    )


class DataAccessLog(Base):
    """
    KDPA Section 26 & 41 - Right to Access & Data Security.
    Logs every time a clinician VIEWS a patient's full medical history.
    This is separate from the audit_logs table (which tracks writes).
    This table tracks READ access to sensitive records.
    """
    __tablename__ = "data_access_logs"

    log_id = Column(Integer, primary_key=True)
    accessed_by = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False, index=True)
    
    access_reason = Column(String(255), nullable=True)  # "Routine Consultation", "Emergency Access"
    ip_address = Column(String(45), nullable=True)
    accessed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index('idx_access_log_patient', 'patient_id', 'accessed_at'),
    )
