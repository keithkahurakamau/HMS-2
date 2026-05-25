"""Cheque register — handles both incoming and outgoing cheques.

Incoming (cheques the hospital RECEIVES from insurers, employers, patients):
    Received → Deposited → Cleared          ↘
                         → Bounced           → posts a Payment against
                                              the linked invoice if any
             → Cancelled (any time before clearance)

Outgoing (cheques the hospital ISSUES to suppliers, staff, refunds):
    Issued → Dispatched → Cleared            ↘
                        → Returned            → reverses the supplier
                                              AP posting if any
            → Stopped     (stop-payment instruction sent to our bank)
            → Cancelled   (cheque physically destroyed before dispatch)

The two flows share the same table because finance teams reconcile them
against the same bank statement — a single Cheque Register page filtered
by direction matches how the books are kept. The `direction` column is
indexed alongside `status` so the queue queries stay snappy at thousands
of rows per direction.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Numeric, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base


class Cheque(Base):
    __tablename__ = "cheques"

    cheque_id = Column(Integer, primary_key=True)

    # Direction — 'incoming' (hospital receives) or 'outgoing' (hospital issues).
    # Indexed because every Cheque Register view filters on it.
    direction = Column(String(20), nullable=False, server_default="incoming", index=True)

    # Cheque identity
    cheque_number = Column(String(60), index=True, nullable=False)
    bank_name = Column(String(120), nullable=False)
    bank_branch = Column(String(120), nullable=True)

    # Counterparty — split into drawer (incoming) and payee (outgoing) so
    # the front-desk form stays unambiguous. For incoming, drawer_* is
    # required and payee_* stays null. For outgoing, payee_* is required
    # and drawer_* is left blank (the hospital is the implicit drawer).
    drawer_name = Column(String(255), nullable=True)              # incoming: issuer (insurer/employer/individual)
    drawer_type = Column(String(40), nullable=True)               # Insurance | Employer | Patient | Government | Other
    payee_name = Column(String(255), nullable=True)               # outgoing: recipient (supplier/staff/refund target)
    payee_type = Column(String(40), nullable=True)                # Supplier | Staff | Refund | Government | Other

    # Money
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, server_default="KES")

    # Dates — both legs of the lifecycle live here. The migration backfills
    # date_received to created_at for legacy rows so SELECTs ordered by
    # received-date keep working.
    date_on_cheque = Column(Date, nullable=True)                  # Cheque face date — postdated handling
    date_received = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    date_issued = Column(DateTime(timezone=True), nullable=True)  # outgoing: when WE wrote the cheque
    dispatch_date = Column(DateTime(timezone=True), nullable=True)  # outgoing: when it left our office
    deposit_date = Column(DateTime(timezone=True), nullable=True)
    deposit_account = Column(String(120), nullable=True)
    clearance_date = Column(DateTime(timezone=True), nullable=True)

    # Lifecycle — status set is direction-aware:
    #   incoming: Received | Deposited | Cleared | Bounced  | Cancelled
    #   outgoing: Issued   | Dispatched| Cleared | Returned | Stopped | Cancelled
    status = Column(String(30), nullable=False, server_default="Received", index=True)
    bounce_reason = Column(String(255), nullable=True)             # incoming-only
    return_reason = Column(String(255), nullable=True)             # outgoing-only
    stop_reason = Column(String(255), nullable=True)               # outgoing-only
    cancel_reason = Column(String(255), nullable=True)             # both directions

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
        # that combo as a soft-unique hint so duplicate-entries surface fast.
        Index("idx_cheque_drawer_bank_number", "drawer_name", "bank_name", "cheque_number", unique=False),
        # Most queries filter by direction + status (e.g. outgoing+Issued
        # for the dispatch queue); compound index keeps them index-only.
        Index("idx_cheque_dir_status", "direction", "status"),
        Index("idx_cheque_status_received", "status", "date_received"),
    )
