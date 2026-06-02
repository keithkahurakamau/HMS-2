"""
Outbound email delivery tracking (EMAIL-004).

Master-DB tables fed by the Resend *events* webhook:

  * ``EmailEvent``       — append-only audit of every delivery event
                           (sent / delivered / bounced / complained / …).
  * ``EmailSuppression`` — addresses we must stop emailing (hard bounce or
                           spam complaint). Protects sender reputation.

Both live in hms_master (platform-wide, not per tenant), mirroring the support
tables. Created via migrate_all_tenants MASTER_DB_PATCHES — Alembic only
targets tenant DBs.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func

from app.config.database import Base


class EmailEvent(Base):
    __tablename__ = "email_events"

    event_id = Column(Integer, primary_key=True)
    # Resend event type, e.g. email.sent / email.delivered / email.bounced /
    # email.complained / email.opened / email.clicked.
    event_type = Column(String(64), nullable=False, index=True)
    email = Column(String(255), nullable=True, index=True)        # recipient
    message_id = Column(String(255), nullable=True, index=True)   # provider id
    reason = Column(String(255), nullable=True)                   # bounce/complaint detail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("idx_email_events_type_created", "event_type", "created_at"),
    )


class EmailSuppression(Base):
    __tablename__ = "email_suppressions"

    email = Column(String(255), primary_key=True)                 # the suppressed address
    reason = Column(String(64), nullable=False)                   # bounced | complained
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
