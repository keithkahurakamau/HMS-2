"""Flow tests for process_inbound against an in-memory SQLite DB.

We create only the two support tables (not the whole metadata, which has
Postgres-specific types), seed a 'known contact', and exercise the gate,
new-ticket creation, reply threading, and dedupe.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.master import SuperAdmin
from app.models.support import SupportMessage, SupportTicket
from app.services import support_inbound as si


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    # support_tickets.assigned_to_admin_id FKs into superadmins — create it first.
    SuperAdmin.__table__.create(engine)
    SupportTicket.__table__.create(engine)
    SupportMessage.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    # Seed a known contact: a tenant admin who raised a ticket in-app.
    session.add(SupportTicket(
        tenant_id=7, tenant_name="Mayo Clinic",
        submitter_email="jane@mayo.com", submitter_name="Jane Admin",
        submitter_user_id=42, origin="app", subject="Old ticket",
        category="Other", priority="Normal", status="Resolved",
    ))
    session.commit()
    yield session
    session.close()


def _payload(**kw):
    base = {
        "from": "Jane Admin <jane@mayo.com>",
        "to": ["support@medifleet.app"],
        "subject": "New problem",
        "text": "Something broke",
        "message_id": "<msg-1@mail.com>",
        "attachments": [],
    }
    base.update(kw)
    return base


def test_unknown_sender_rejected(db):
    res = si.process_inbound(db, _payload(**{"from": "stranger@nope.com"}))
    assert res.action == "rejected"
    assert db.query(SupportTicket).count() == 1  # nothing created


def test_known_sender_creates_ticket_with_tenant_attribution(db):
    res = si.process_inbound(db, _payload(to=["finance@medifleet.app"]))
    assert res.action == "created"
    t = db.query(SupportTicket).filter(SupportTicket.ticket_id == res.ticket_id).one()
    assert t.origin == "email"
    assert t.category == "Billing"          # finance@ → Billing
    assert t.tenant_id == 7                  # inherited from the known contact
    assert t.tenant_name == "Mayo Clinic"
    msg = db.query(SupportMessage).filter(SupportMessage.ticket_id == t.ticket_id).one()
    assert msg.author_kind == "customer" and msg.source == "email"
    assert msg.external_message_id == "<msg-1@mail.com>"


def test_reply_threads_into_existing_ticket_and_reopens(db):
    seed = db.query(SupportTicket).first()  # status Resolved, jane@mayo.com
    res = si.process_inbound(db, _payload(
        subject=f"Re: [#MF-{seed.ticket_id:06d}] Old ticket",
        message_id="<reply-1@mail.com>",
    ))
    assert res.action == "appended"
    assert res.ticket_id == seed.ticket_id
    db.refresh(seed)
    assert seed.status == "Open"            # Resolved → reopened by customer reply
    assert db.query(SupportMessage).filter(SupportMessage.ticket_id == seed.ticket_id).count() == 1


def test_reply_with_wrong_sender_does_not_thread(db):
    seed = db.query(SupportTicket).first()
    # Unknown sender referencing a real ticket → must not append, must reject.
    res = si.process_inbound(db, _payload(**{
        "from": "imposter@evil.com",
        "subject": f"Re: [#MF-{seed.ticket_id:06d}] Old ticket",
        "message_id": "<reply-2@mail.com>",
    }))
    assert res.action == "rejected"


def test_duplicate_message_id_is_ignored(db):
    first = si.process_inbound(db, _payload(message_id="<dup@mail.com>"))
    assert first.action == "created"
    again = si.process_inbound(db, _payload(message_id="<dup@mail.com>", subject="resent"))
    assert again.action == "duplicate"
    assert again.ticket_id == first.ticket_id
