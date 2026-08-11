"""Clinical-desk extras — the Doctor's-panel outputs HMS-2 was missing:
sick notes, optical prescriptions, external (out-of-facility) requests, and
configurable order sets (named bundles of lab/radiology/drug orders).

All belong to the clinical module (RBAC clinical:read/write) and hang off a
patient. Order sets are tenant config (like checklists), applied at the point
of care to pre-fill the doctor's orders.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class SickNote(Base):
    __tablename__ = "sick_notes"

    sick_note_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    diagnosis = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, nullable=True)
    recommendation = Column(Text, nullable=True)
    fit_for_duty = Column(Boolean, nullable=False, default=False)
    issued_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OpticalPrescription(Base):
    __tablename__ = "optical_prescriptions"

    optical_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    right_sphere = Column(String(12), nullable=True)
    right_cylinder = Column(String(12), nullable=True)
    right_axis = Column(String(12), nullable=True)
    right_add = Column(String(12), nullable=True)
    left_sphere = Column(String(12), nullable=True)
    left_cylinder = Column(String(12), nullable=True)
    left_axis = Column(String(12), nullable=True)
    left_add = Column(String(12), nullable=True)
    pd = Column(String(12), nullable=True)  # pupillary distance
    notes = Column(Text, nullable=True)
    issued_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExternalRequest(Base):
    __tablename__ = "external_requests"

    request_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    facility = Column(String(160), nullable=True)
    # Lab | Radiology | Referral | Other
    request_type = Column(String(40), nullable=False)
    details = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    issued_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrderSet(Base):
    __tablename__ = "order_sets"

    order_set_id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    items = relationship("OrderSetItem", backref="order_set", cascade="all, delete-orphan")


class OrderSetItem(Base):
    __tablename__ = "order_set_items"

    item_id = Column(Integer, primary_key=True)
    order_set_id = Column(Integer, ForeignKey("order_sets.order_set_id", ondelete="CASCADE"), nullable=False, index=True)
    # Lab | Radiology | Drug
    item_type = Column(String(20), nullable=False)
    name = Column(String(160), nullable=False)
    ref_code = Column(String(60), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
