from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class Appointment(Base):
    __tablename__ = "appointments"
    appointment_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)
    appointment_date = Column(DateTime(timezone=True), index=True, nullable=False)
    status = Column(String(50), default="Scheduled", index=True) # Scheduled/Confirmed/Completed/Cancelled/No-Show
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    patient = relationship("Patient")
    doctor = relationship("User")

class PatientQueue(Base):
    __tablename__ = "patient_queue"
    queue_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    department = Column(String(50), nullable=False) 
    acuity_level = Column(Integer, default=3) # 1=Emergency, 2=Urgent, 3=Standard
    status = Column(String(50), default="Waiting", nullable=False) 
    notes = Column(String, nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    patient = relationship("Patient")
    assigned_user = relationship("User")

    __table_args__ = (
        Index('idx_queue_dept_status', 'department', 'status'),
    )

class TriageRecord(Base):
    """Nurse-captured triage assessment taken *before* the doctor sees the
    patient. Recording vitals + an acuity score here means the doctor's
    encounter form arrives pre-filled, so the clinical desk doesn't re-key
    the same numbers — that's the whole point of the module.

    A triage row is immutable history: each visit's triage is its own row,
    and the Clinical Desk prefills from the most recent one for the patient.
    """
    __tablename__ = "triage_records"
    triage_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    # The Triage queue row this assessment closed out. Nullable because a nurse
    # can triage a walk-in that was never formally queued.
    queue_id = Column(Integer, ForeignKey("patient_queue.queue_id"), index=True, nullable=True)
    nurse_id = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)

    # Vitals — mirror MedicalRecord's column names so the Clinical Desk can
    # copy them across field-for-field without a translation layer.
    blood_pressure = Column(String(20), nullable=True)  # e.g. "120/80"
    heart_rate = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    spo2 = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    calculated_bmi = Column(Float, nullable=True)
    pain_score = Column(Integer, nullable=True)       # 0–10 numeric pain scale
    blood_glucose = Column(Float, nullable=True)      # mmol/L (RBS at the bedside)

    # Triage assessment
    chief_complaint = Column(String, nullable=True)
    acuity_level = Column(Integer, default=3)  # 1=Emergency … 5=Non-urgent
    triage_notes = Column(String, nullable=True)
    # Department the nurse is routing the patient to next (canonical name).
    disposition = Column(String(50), default="Consultation")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    patient = relationship("Patient")
    nurse = relationship("User")

    __table_args__ = (
        Index('idx_triage_patient_time', 'patient_id', 'created_at'),
    )

class MedicalRecord(Base):
    __tablename__ = "medical_records"
    record_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)
    
    # Workflow Status
    record_status = Column(String(50), default="Draft", index=True) # Draft/Billed/Pharmacy/Completed
    
    # Vitals
    blood_pressure = Column(String(20), nullable=True) # e.g. "120/80"
    heart_rate = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    spo2 = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    calculated_bmi = Column(Float, nullable=True)
    
    # Clinical Data (SOAP)
    chief_complaint = Column(String, nullable=True)
    history_of_present_illness = Column(String, nullable=True)
    review_of_systems = Column(JSON, nullable=True) # Stores dictionary of system checks
    physical_examination = Column(String, nullable=True)
    
    # Diagnosis & Plan
    icd10_code = Column(String(255), index=True, nullable=True)
    diagnosis = Column(String, nullable=True)
    treatment_plan = Column(String, nullable=True)
    prescription_notes = Column(String, nullable=True)
    internal_notes = Column(String, nullable=True)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient")
    doctor = relationship("User")