"""The Daraja event log: one row per interaction with Safaricom, whatever
its outcome.

Tenant table, like mpesa.py's MpesaConfig/MpesaTransaction/MpesaRefund, the
opposite of platform_mpesa.py: this records a hospital's own till traffic,
so it lives one database per tenant, never in the master DB. It therefore
belongs in scripts/migrate_all_tenants.py's `from app.models import (...)`
block, which feeds the unfiltered `Base.metadata.create_all()` run against
every tenant engine.

Why this table exists at all: application logs answer "what did the code
do", which is not the question a cashier standing at a counter is asking.
That question is "what happened to THIS payment", and it needs an answer
that survives past whatever log retention window ops configured, is
queryable by receipt or phone, and is safe to put in front of hospital
staff in a browser. See app/services/daraja/events.py for the redaction
that makes the last part true, and its own module docstring for why that
redaction is an allowlist, never a denylist.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.config.database import Base


class MpesaEvent(Base):
    """Append-only. Nothing here is ever updated after insert; a later
    development in the same payment's life (a callback after a push, a
    reconciliation resolution after a stuck row) is always a NEW row, not
    an edit of an old one, so the log itself is never rewritten under a
    human who is mid-read of it.
    """

    __tablename__ = "mpesa_events"
    id = Column(Integer, primary_key=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Which Daraja operation this is: 'stk_push', 'stk_query', 'stk_callback',
    # 'c2b_validation', 'c2b_confirmation', 'b2c_request', 'b2c_result',
    # 'b2c_timeout', 'transaction_status', 'balance', 'url_registration',
    # 'reconciliation'. A free string, not an enum: Daraja grows new flows
    # faster than a migration should have to chase them.
    flow = Column(String(40), nullable=False, index=True)

    # 'outbound': we called Safaricom. 'inbound': Safaricom called us.
    direction = Column(String(10), nullable=False)

    # 'success', 'failure' (Safaricom answered and said no), 'error' (we
    # could not even complete the call: a timeout, a breaker trip, a 5xx),
    # 'quarantined' (a cross-check refused to settle), 'rejected' (a C2B
    # validation decline).
    outcome = Column(String(20), nullable=False, index=True)

    http_status = Column(Integer, nullable=True)
    daraja_result_code = Column(String(20), nullable=True)
    daraja_result_desc = Column(String(255), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error_detail = Column(Text, nullable=True)

    # Correlation handles: whichever of these apply to this flow are set,
    # the rest stay NULL. Each indexed so a human can jump straight from a
    # transaction, a refund, a till, or a receipt to every event that
    # touched it.
    mpesa_transaction_id = Column(Integer, nullable=True, index=True)
    mpesa_refund_id = Column(Integer, nullable=True, index=True)
    mpesa_config_id = Column(Integer, nullable=True, index=True)
    checkout_request_id = Column(String(100), nullable=True, index=True)
    conversation_id = Column(String(64), nullable=True, index=True)
    receipt_number = Column(String(50), nullable=True, index=True)

    # Redacted (see app/services/daraja/events.py's redact_payload) JSON,
    # stored as text rather than a JSON column: this table is written from
    # inside flows that must never fail because of it (see record_event),
    # and a plain string column has no type-coercion surface of its own to
    # add a new way for that write to raise.
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
