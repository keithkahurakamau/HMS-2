from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base

class Invoice(Base):
    __tablename__ = "invoices"
    invoice_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.appointment_id"), index=True, nullable=True)
    
    total_amount = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), default=0)
    status = Column(String(50), default="Pending", index=True) # Pending/Paid/Partially Paid/Cancelled/Pending M-Pesa
    payment_method = Column(String(50), nullable=True) # Cash/M-Pesa/Card
    
    billing_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_by = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)

    items = relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")
    patient = relationship("Patient", backref="invoices")

    __table_args__ = (Index('idx_invoice_status_date', 'status', 'billing_date'),)

class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True, nullable=False)
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    item_type = Column(String(50), nullable=False) # Laboratory/Pharmacy/Consultation/Procedure
    reference_id = Column(Integer, nullable=True) # Links to specific test/drug

class Payment(Base):
    __tablename__ = "payments"
    payment_id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id", ondelete="CASCADE"), index=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)
    transaction_reference = Column(String(100), unique=True, index=True, nullable=True) # M-Pesa Receipt No
    payment_date = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key = Column(String(36), primary_key=True) # UUID string
    response_body = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())