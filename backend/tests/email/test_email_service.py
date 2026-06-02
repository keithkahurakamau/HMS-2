"""Unit tests for EmailService and backend selection (no DB, no network)."""
from __future__ import annotations

from email.message import EmailMessage

import pytest

from app.config.settings import settings
from app.services.email_service import (
    ConsoleBackend,
    EmailBackend,
    EmailService,
    SMTPBackend,
    _build_backend,
    _strip_html,
)


class FakeBackend(EmailBackend):
    """Records the message instead of sending it."""

    def __init__(self, raise_exc: Exception | None = None):
        self.sent: list[EmailMessage] = []
        self._raise = raise_exc

    def send(self, message: EmailMessage) -> None:
        if self._raise:
            raise self._raise
        self.sent.append(message)


@pytest.fixture
def from_configured(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@medifleet.app")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "MediFleet")
    monkeypatch.setattr(settings, "EMAIL_REPLY_TO", "")


def _get_part(message: EmailMessage, content_type: str) -> str:
    for part in message.iter_parts():
        if part.get_content_type() == content_type:
            return part.get_content()
    raise AssertionError(f"no {content_type} part found")


def test_send_builds_multipart_message(from_configured):
    backend = FakeBackend()
    ok = EmailService(backend=backend).send(
        to="user@example.com", subject="Hi", html="<p>Hello</p>", text="Hello",
    )
    assert ok is True
    assert len(backend.sent) == 1
    msg = backend.sent[0]
    assert msg["To"] == "user@example.com"
    assert msg["Subject"] == "Hi"
    assert "noreply@medifleet.app" in msg["From"]
    assert "MediFleet" in msg["From"]
    assert _get_part(msg, "text/plain").strip() == "Hello"
    assert "<p>Hello</p>" in _get_part(msg, "text/html")


def test_plaintext_derived_from_html_when_text_omitted(from_configured):
    backend = FakeBackend()
    EmailService(backend=backend).send(
        to="u@e.com", subject="S", html="<p>Line one</p><p>Line two</p>",
    )
    plain = _get_part(backend.sent[0], "text/plain")
    assert "Line one" in plain and "Line two" in plain
    assert "<p>" not in plain


def test_reply_to_set_when_configured(monkeypatch, from_configured):
    monkeypatch.setattr(settings, "EMAIL_REPLY_TO", "support@medifleet.app")
    backend = FakeBackend()
    EmailService(backend=backend).send(to="u@e.com", subject="S", html="<p>x</p>")
    assert backend.sent[0]["Reply-To"] == "support@medifleet.app"


def test_reply_to_absent_when_unset(from_configured):
    backend = FakeBackend()
    EmailService(backend=backend).send(to="u@e.com", subject="S", html="<p>x</p>")
    assert backend.sent[0]["Reply-To"] is None


def test_send_returns_false_without_from(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_FROM", "")
    monkeypatch.setattr(settings, "SMTP_USER", "")
    backend = FakeBackend()
    ok = EmailService(backend=backend).send(to="u@e.com", subject="S", html="<p>x</p>")
    assert ok is False
    assert backend.sent == []  # never attempted


def test_send_swallows_backend_errors(from_configured):
    backend = FakeBackend(raise_exc=RuntimeError("smtp down"))
    # Must not raise — email is best-effort.
    ok = EmailService(backend=backend).send(to="u@e.com", subject="S", html="<p>x</p>")
    assert ok is False


def test_build_backend_console_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    assert isinstance(_build_backend(), ConsoleBackend)


def test_build_backend_console_when_enabled_but_no_host(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert isinstance(_build_backend(), ConsoleBackend)


def test_build_backend_smtp_when_enabled_and_host_set(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    assert isinstance(_build_backend(), SMTPBackend)


def test_console_backend_does_not_raise(from_configured):
    # ConsoleBackend just logs; ensure a full send path stays green.
    ok = EmailService(backend=ConsoleBackend()).send(
        to="u@e.com", subject="S", html="<p>x</p>",
    )
    assert ok is True


def test_strip_html_collapses_markup():
    out = _strip_html("<p>Hello<br>World</p><div>Done</div>")
    assert out.splitlines() == ["Hello", "World", "Done"]
