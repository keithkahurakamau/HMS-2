from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base


class RadiologyExamCatalog(Base):
    """The hospital's directory of imaging exams it actually performs.

    Each catalog row captures modality + body part + default findings template
    + price + flags. The Radiology UI is rendered straight from this table so
    operators can add a new imaging service without a code change.
    """
    __tablename__ = "radiology_exam_catalog"

    catalog_id = Column(Integer, primary_key=True, index=True)
    exam_name = Column(String(200), unique=True, index=True, nullable=False)
    modality = Column(String(50), nullable=False)         # X-Ray, CT, MRI, Ultrasound, Mammography…
    body_part = Column(String(120), nullable=True)        # Chest, Abdomen, Right Knee…
    description = Column(Text, nullable=True)

    base_price = Column(Numeric(10, 2), nullable=False, server_default="0")
    requires_prep = Column(Boolean, default=False, nullable=False)   # fasting, contrast prep
    requires_contrast = Column(Boolean, default=False, nullable=False)
    default_findings_template = Column(Text, nullable=True)         # pre-populated boilerplate
    default_impression_template = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class RadiologyRequest(Base):
    __tablename__ = "radiology_requests"

    request_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False)
    requested_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    # Link to catalog when known; free-text exam_type stays for backward
    # compatibility / ad-hoc requests.
    catalog_id = Column(
        Integer,
        ForeignKey("radiology_exam_catalog.catalog_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    exam_type = Column(String(100), nullable=False)
    clinical_notes = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, server_default="Routine")
    billed_price = Column(Numeric(10, 2), nullable=True)

    status = Column(String(50), default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    patient = relationship("Patient", backref="radiology_requests")
    doctor = relationship("User", foreign_keys=[requested_by])
    result = relationship("RadiologyResult", back_populates="request", uselist=False)
    catalog = relationship("RadiologyExamCatalog")


class RadiologyResult(Base):
    __tablename__ = "radiology_results"

    result_id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("radiology_requests.request_id"), unique=True, nullable=False)
    performed_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    findings = Column(Text, nullable=False)
    conclusion = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True)
    contrast_used = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    request = relationship("RadiologyRequest", back_populates="result")
    radiologist = relationship("User", foreign_keys=[performed_by])
