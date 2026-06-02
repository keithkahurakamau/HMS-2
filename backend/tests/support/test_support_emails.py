"""Unit tests for outbound support-ticket email helpers (no DB, no network)."""
from __future__ import annotations

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.services import support_emails as se
from app.services.email_service import email_service


def test_ticket_ref_format():
    assert se.ticket_ref(123) == "#MF-000123"


def test_ticket_reply_address_uses_domain(monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_INBOUND_DOMAIN", "medifleet.app")
    assert se.ticket_reply_address(123) == "support+ticket-123@medifleet.app"


def test_desk_for_category():
    assert se.desk_for_category("Billing") == "finance"
    assert se.desk_for_category("Bug") == "technical"
    assert se.desk_for_category("Feature") == "technical"
    assert se.desk_for_category("Account") == "support"
    assert se.desk_for_category(None) == "support"


def test_send_ticket_reply_queues_task_with_desk_sender_and_reply_to(monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_INBOUND_DOMAIN", "medifleet.app")
    monkeypatch.setattr(settings, "EMAIL_FROM_FINANCE", "finance@medifleet.app")
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@medifleet.app")
    bt = BackgroundTasks()
    se.send_ticket_reply_email(
        bt, ticket_id=123, to="jane@mayo.com",
        ticket_subject="Invoice question", reply_body="Here's your answer.",
        category="Billing", recipient_name="Jane",
    )
    assert len(bt.tasks) == 1
    task = bt.tasks[0]
    assert task.func == email_service.send
    assert task.kwargs["to"] == "jane@mayo.com"
    assert task.kwargs["subject"] == "[#MF-000123] Invoice question"
    assert task.kwargs["from_addr"] == "finance@medifleet.app"     # Billing → finance desk
    assert task.kwargs["reply_to"] == "support+ticket-123@medifleet.app"
    # Body is HTML-escaped (apostrophe → &#x27;); check on the plaintext part.
    assert "Here's your answer." in task.kwargs["text"]


def test_send_ticket_reply_falls_back_to_default_sender(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM_SUPPORT", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@medifleet.app")
    bt = BackgroundTasks()
    se.send_ticket_reply_email(
        bt, ticket_id=5, to="x@y.com", ticket_subject="Hi",
        reply_body="hello", category="Account",
    )
    assert bt.tasks[0].kwargs["from_addr"] == "noreply@medifleet.app"
