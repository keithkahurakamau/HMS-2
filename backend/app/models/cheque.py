"""Cheque register.

Tracks every cheque (cash, insurance, employer, NHIF top-up) the hospital
receives through its lifecycle:

    Received → Deposited → Cleared        ↘
                          → Bounced        → posts a Payment against the
                                            linked invoice if applicable
              → Cancelled (any time before clearance)

This is independent from M-Pesa/Cash because cheques carry their own
operational risk (bouncing, deposit lag) and finance teams typically maintain
a separate ledger of "cheques in transit".
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Numeric, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base


class Cheque(Base):
    __tablename__ = "cheques"

    cheque_id = Column(Integer, primary_key=True)

    # Cheque identity
    cheque_number = Column(String(60), index=True, nullable=False)
    drawer_name = Column(String(255), nullable=False)             # Issuer (insurance co, employer, individual)
    drawer_type = Column(String(40), nullable=False, server_default="Other")  # Insurance | Employer | Patient | Government | Other
    bank_name = Column(String(120), nullable=False)
    bank_branch = Column(String(120), nullable=True)

    # Money
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, server_default="KES")

    # Dates
    date_on_cheque = Column(Date, nullable=True)                  # Cheque face date — postdated handling
    date_received = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    deposit_date = Column(DateTime(timezone=True), nullable=True)
    deposit_account = Column(String(120), nullable=True)
    clearance_date = Column(DateTime(timezone=True), nullable=True)

    # Lifecycle
    status = Column(String(30), nullable=False, server_default="Received", index=True)
    # Received | Deposited | Cleared | Bounced | Cancelled
    bounce_reason = Column(String(255), nullable=True)
    cancel_reason = Column(String(255), nullable=True)

    # Links — both optional. A cheque might cover one invoice, multiple, or
    # be unallocated until the finance team posts it.
    invoice_id = Column(Integer, ForeignKey("invoices.invoice_id", ondelete="SET NULL"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True, index=True)

    # Audit
    received_by = Column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    last_updated_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    invoice = relationship("Invoice", foreign_keys=[invoice_id])
    patient = relationship("Patient", foreign_keys=[patient_id])

    __table_args__ = (
        # A drawer rarely re-uses a cheque number from the same bank — treat
        # that combo as unique so duplicate-entries surface fast.
        Index("idx_cheque_drawer_bank_number", "drawer_name", "bank_name", "cheque_number", unique=False),
        Index("idx_cheque_status_received", "status", "date_received"),
    )
