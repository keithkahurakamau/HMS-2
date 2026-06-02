"""Unit + flow tests for outbound email event processing (EMAIL-004)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.email_events import EmailEvent, EmailSuppression
from app.services import email_suppression as es


# ── pure parsing / classification (DB-free) ──────────────────────────────────
def test_parse_event_bounce():
    ev = es.parse_event({
        "type": "email.bounced",
        "data": {"to": ["Bouncer@Example.com"], "email_id": "e1",
                 "bounce": {"message": "mailbox full"}},
    })
    assert ev.event_type == "email.bounced"
    assert ev.email == "bouncer@example.com"     # lowercased
    assert ev.message_id == "e1"
    assert ev.reason == "mailbox full"


def test_parse_event_delivered_no_reason():
    ev = es.parse_event({"type": "email.delivered", "data": {"to": "a@b.com", "email_id": "e2"}})
    assert ev.event_type == "email.delivered"
    assert ev.email == "a@b.com"
    assert ev.reason is None


def test_parse_event_handles_missing_type():
    ev = es.parse_event({"data": {"to": ["x@y.com"]}})
    assert ev.event_type == ""


def test_suppression_reason():
    assert es.suppression_reason("email.bounced") == "bounced"
    assert es.suppression_reason("email.complained") == "complained"
    assert es.suppression_reason("email.delivered") is None
    assert es.suppression_reason("email.opened") is None


# ── flow against in-memory SQLite ─────────────────────────────────────────────
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    EmailEvent.__table__.create(engine)
    EmailSuppression.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_process_bounce_records_event_and_suppresses(db):
    out = es.process_event(db, {"type": "email.bounced",
                                "data": {"to": ["dead@inbox.com"], "email_id": "m1",
                                         "bounce": {"message": "no such user"}}})
    assert out["recorded"] and out["suppressed"]
    assert db.query(EmailEvent).count() == 1
    sup = db.query(EmailSuppression).filter(EmailSuppression.email == "dead@inbox.com").one()
    assert sup.reason == "bounced"


def test_process_complaint_suppresses(db):
    out = es.process_event(db, {"type": "email.complained", "data": {"to": ["spam@flag.com"]}})
    assert out["suppressed"]
    assert db.query(EmailSuppression).filter(EmailSuppression.reason == "complained").count() == 1


def test_process_delivered_records_but_does_not_suppress(db):
    out = es.process_event(db, {"type": "email.delivered", "data": {"to": ["ok@inbox.com"]}})
    assert out["recorded"] and not out["suppressed"]
    assert db.query(EmailSuppression).count() == 0
    assert db.query(EmailEvent).count() == 1


def test_repeat_bounce_does_not_duplicate_suppression(db):
    payload = {"type": "email.bounced", "data": {"to": ["dead@inbox.com"]}}
    es.process_event(db, payload)
    es.process_event(db, payload)
    assert db.query(EmailSuppression).filter(EmailSuppression.email == "dead@inbox.com").count() == 1
    assert db.query(EmailEvent).count() == 2  # both events still logged
