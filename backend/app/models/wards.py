from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class Ward(Base):
    __tablename__ = "wards"
    ward_id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    capacity = Column(Integer, nullable=False)
    
    # Relationship to beds
    beds = relationship("Bed", backref="ward")

class Bed(Base):
    __tablename__ = "beds"
    bed_id = Column(Integer, primary_key=True)
    ward_id = Column(Integer, ForeignKey("wards.ward_id"), nullable=False)
    bed_number = Column(String(50), unique=True, nullable=False)
    
    # Available, Occupied, Maintenance, Cleaning
    status = Column(String(50), default="Available", index=True) 

class AdmissionRecord(Base):
    """Tracks a patient's stay in the hospital from start to finish."""
    __tablename__ = "admission_records"
    
    admission_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    bed_id = Column(Integer, ForeignKey("beds.bed_id"), index=True, nullable=False)
    admitting_doctor_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    
    primary_diagnosis = Column(String(255), nullable=False)
    status = Column(String(50), default="Active", index=True) # Active, Discharged
    
    admitted_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    discharged_at = Column(DateTime(timezone=True), nullable=True)
    discharge_notes = Column(String, nullable=True)