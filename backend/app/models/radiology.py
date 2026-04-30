from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base

class RadiologyRequest(Base):
    __tablename__ = "radiology_requests"

    request_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False)
    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    exam_type = Column(String(100), nullable=False) # e.g., X-Ray, MRI, Ultrasound
    clinical_notes = Column(Text, nullable=True)
    status = Column(String(50), default="Pending") # Pending, In Progress, Completed, Cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    patient = relationship("Patient", backref="radiology_requests")
    doctor = relationship("User", foreign_keys=[requested_by])
    result = relationship("RadiologyResult", back_populates="request", uselist=False)

class RadiologyResult(Base):
    __tablename__ = "radiology_results"

    result_id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("radiology_requests.request_id"), unique=True, nullable=False)
    performed_by = Column(Integer, ForeignKey("users.user_id"), nullable=False) # The radiologist
    findings = Column(Text, nullable=False)
    conclusion = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True) # S3 or local path to DICOM/image
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    request = relationship("RadiologyRequest", back_populates="result")
    radiologist = relationship("User", foreign_keys=[performed_by])
