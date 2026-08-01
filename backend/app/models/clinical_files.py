"""Clinical file attachments — documents/images a clinician attaches to a
patient (and optionally a specific encounter). Stored as a base64 data URL in
the row, mirroring the branding-upload pattern, so no external object storage is
needed. Size is capped at the route (~2 MB binary) to keep tenant DBs sane.
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func

from app.config.database import Base


class ClinicalFile(Base):
    __tablename__ = "clinical_files"

    file_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    # Optional link to the encounter it was attached during.
    record_id = Column(Integer, ForeignKey("medical_records.record_id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    mime = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    data = Column(Text, nullable=False)  # base64 data URL
    uploaded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
