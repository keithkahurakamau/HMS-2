"""Unit tests for auth email dispatch helpers (no DB, no network)."""
from __future__ import annotations

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.services import auth_emails
from app.services.email_service import email_service


def test_reset_link_includes_tenant_and_encodes(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.medifleet.app")
    link = auth_emails._reset_link("a b&c", "tenant one")
    assert link.startswith("https://app.medifleet.app/reset-password?token=")
    assert "a%20b%26c" in link        # token url-encoded
    assert "&tenant=tenant%20one" in link


def test_reset_link_omits_tenant_when_none(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.medifleet.app")
    link = auth_emails._reset_link("tok", None)
    assert "tenant=" not in link
    assert link.endswith("/reset-password?token=tok")


def test_send_password_reset_email_queues_background_task(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.medifleet.app")
    bt = BackgroundTasks()
    auth_emails.send_password_reset_email(
        bt, to="user@example.com", raw_token="TOK", tenant_id="demo",
        recipient_name="Jane",
    )
    assert len(bt.tasks) == 1
    task = bt.tasks[0]
    assert task.func == email_service.send
    assert task.kwargs["to"] == "user@example.com"
    assert "reset" in task.kwargs["subject"].lower()
    assert "TOK" in task.kwargs["html"]
    assert "tenant=demo" in task.kwargs["html"]


def test_send_staff_invite_email_queues_background_task(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_BASE_URL", "https://app.medifleet.app")
    bt = BackgroundTasks()
    auth_emails.send_staff_invite_email(
        bt, to="new@example.com", raw_token="INV", tenant_id="demo",
        recipient_name="Sam", hospital_name="Mayo Clinic", inviter_name="Ann",
    )
    assert len(bt.tasks) == 1
    task = bt.tasks[0]
    assert task.func == email_service.send
    assert task.kwargs["to"] == "new@example.com"
    assert "Mayo Clinic" in task.kwargs["subject"]
    assert "INV" in task.kwargs["html"]
