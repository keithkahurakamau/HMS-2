from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Float, JSON
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

    __table_args__ = (
        Index('idx_queue_dept_status', 'department', 'status'),
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