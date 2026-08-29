"""Operator-side receivables: what each hospital owes MediFleet, and what
has been received against it.

These four tables live in the MASTER database only. Tenant databases never
see them: a hospital does not need to know how the platform bills it.

Balance and ageing are deliberately NOT columns. They are derived from the
payment rows, because a stored total is a second source of truth that
drifts the first time a payment is corrected.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
    Text, UniqueConstraint, func,
)

from app.config.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), unique=True, nullable=False, index=True)
    plan = Column(String(20), nullable=False, default="standard")
    # The agreed price, copied onto each invoice at issue time. Stored rather
    # than read from TIER_PRICING so a negotiated rate survives a change to
    # the public price list, and so an invoice can always be explained.
    price_kes = Column(Numeric(12, 2), nullable=False, default=0)
    cycle = Column(String(10), nullable=False, default="monthly")
    status = Column(String(20), nullable=False, default="active")
    started_on = Column(Date, nullable=False)
    # The idempotency key for generation: an invoice is raised only when this
    # date has arrived, and the date advances as part of the same transaction.
    next_invoice_on = Column(Date, nullable=False)
    reminders_paused = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SubscriptionInvoice(Base):
    __tablename__ = "subscription_invoices"
    __table_args__ = (
        # The guard that makes generation safe to run repeatedly.
        UniqueConstraint("subscription_id", "period_start", name="uq_invoice_period"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    number = Column(String(20), unique=True, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    amount_kes = Column(Numeric(12, 2), nullable=False)
    issued_on = Column(Date, nullable=False)
    due_on = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    void_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("subscription_invoices.id"), nullable=False, index=True)
    # Set when an M-Pesa receipt settled this. Null for manual entries.
    platform_transaction_id = Column(Integer, nullable=True)
    amount_kes = Column(Numeric(12, 2), nullable=False)
    paid_on = Column(Date, nullable=False)
    # A waiver is a payment, not a deletion: the invoice closes and the
    # write-off stays visible and attributable.
    method = Column(String(20), nullable=False, default="mpesa")
    recorded_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DunningEvent(Base):
    __tablename__ = "dunning_events"
    __table_args__ = (
        # Stops a hospital being reminded twice for the same milestone,
        # however often the job runs.
        UniqueConstraint("invoice_id", "day_offset", name="uq_dunning_milestone"),
    )

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("subscription_invoices.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    day_offset = Column(Integer, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    recipients = Column(Integer, nullable=False, default=0)
