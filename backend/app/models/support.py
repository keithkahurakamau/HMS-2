"""Platform-level support tickets.

Tenants raise tickets to the MediFleet platform team. Tickets live in the
master ``hms_master`` database (cross-tenant) so the superadmin console can
see them all in one inbox without iterating every tenant DB.

A tenant Admin submits a ticket through ``/api/support/``; the submitter's
identity (email, full_name, tenant_id) is captured at creation time so the
record stays useful even if the staff account is later deleted on the
tenant side.

Replies use a thread of ``SupportMessage`` rows; ``author_kind`` tells the
UI whether a message came from the tenant ("staff") or the platform team
("platform").
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.config.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    ticket_id = Column(Integer, primary_key=True)

    # Who raised it
    tenant_id = Column(Integer, nullable=False, index=True)        # NOT a hard FK — master DB only
    tenant_name = Column(String(255), nullable=False)
    submitter_email = Column(String(255), nullable=False)
    submitter_name = Column(String(255), nullable=False)
    submitter_user_id = Column(Integer, nullable=True)             # tenant-DB user_id, informational

    # What it's about
    subject = Column(String(200), nullable=False)
    category = Column(String(40), nullable=False, server_default="Other")
    # Billing | Bug | Feature | Account | Onboarding | Other
    priority = Column(String(20), nullable=False, server_default="Normal")
    # Low | Normal | High | Urgent
    status = Column(String(40), nullable=False, server_default="Open", index=True)
    # Open | In Progress | Waiting on Customer | Resolved | Closed

    # Routing
    assigned_to_admin_id = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    first_response_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    messages = relationship(
        "SupportMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at",
    )

    __table_args__ = (
        Index("idx_support_status_created", "status", "created_at"),
        Index("idx_support_tenant_status", "tenant_id", "status"),
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

    message_id = Column(Integer, primary_key=True)
    ticket_id = Column(
        Integer,
        ForeignKey("support_tickets.ticket_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    author_kind = Column(String(20), nullable=False)               # staff | platform
    author_name = Column(String(255), nullable=False)
    author_id = Column(Integer, nullable=True)                     # staff: tenant user_id; platform: superadmin admin_id
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    ticket = relationship("SupportTicket", back_populates="messages")
