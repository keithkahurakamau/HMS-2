"""
Email delivery service (EMAIL-001).

Provider-agnostic by design. The :class:`EmailService` builds a standard
``EmailMessage`` and hands it to a pluggable :class:`EmailBackend`:

  * :class:`SMTPBackend`    — talks SMTP to any relay (Gmail, Mailgun, Resend,
                              AWS SES; they all expose an SMTP endpoint).
  * :class:`ConsoleBackend` — logs the rendered message instead of sending.
                              Used whenever ``EMAIL_ENABLED`` is false so local
                              development and CI never try to reach a real MTA.

Swapping to an HTTP-API provider later (e.g. a ``ResendBackend``) is purely
additive: implement :meth:`EmailBackend.send` and select it in
``_build_backend`` — no caller changes.

Sends are synchronous (stdlib ``smtplib``, zero extra dependencies). Callers
should dispatch through FastAPI ``BackgroundTasks`` so a slow MTA never blocks
the HTTP response. ``send`` never raises into the request path: delivery
failures are logged and swallowed (an email is best-effort, not transactional).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import formataddr

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmailBackend(ABC):
    """Transport contract. Implementations deliver a fully-built message."""

    @abstractmethod
    def send(self, message: EmailMessage) -> None:  # pragma: no cover - interface
        ...


class ConsoleBackend(EmailBackend):
    """Dev/CI backend — logs the message instead of sending it."""

    def send(self, message: EmailMessage) -> None:
        body = ""
        # Prefer the plaintext alternative for readable logs.
        if message.is_multipart():
            for part in message.iter_parts():
                if part.get_content_type() == "text/plain":
                    body = part.get_content()
                    break
        else:
            body = message.get_content()
        logger.info(
            "[email:console] EMAIL_ENABLED is false — not sending.\n"
            "  To:      %s\n  From:    %s\n  Subject: %s\n  Body:\n%s",
            message["To"], message["From"], message["Subject"], body,
        )


class SMTPBackend(EmailBackend):
    """Sends via SMTP. Supports STARTTLS (587) and implicit SSL (465)."""

    def send(self, message: EmailMessage) -> None:
        host = settings.SMTP_HOST
        port = settings.SMTP_PORT
        timeout = settings.SMTP_TIMEOUT_SECONDS

        if settings.SMTP_USE_SSL:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
                self._login_and_send(server, message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                if settings.SMTP_USE_TLS:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                self._login_and_send(server, message)

    @staticmethod
    def _login_and_send(server: smtplib.SMTP, message: EmailMessage) -> None:
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.smtp_password)
        server.send_message(message)


def _build_backend() -> EmailBackend:
    """Select the active backend from configuration.

    Falls back to ConsoleBackend (rather than raising) when email is enabled
    but SMTP_HOST is missing, so a half-configured prod deploy degrades to
    "logged, not sent" instead of 500-ing every reset request.
    """
    if not settings.EMAIL_ENABLED:
        return ConsoleBackend()
    if not settings.SMTP_HOST:
        logger.warning("EMAIL_ENABLED is true but SMTP_HOST is unset — falling back to console backend.")
        return ConsoleBackend()
    return SMTPBackend()


class EmailService:
    """Builds and dispatches emails. Construct once; reuse the module singleton."""

    def __init__(self, backend: EmailBackend | None = None):
        self._backend = backend or _build_backend()

    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> bool:
        """Best-effort send. Returns True on success, False on failure.

        Never raises — callers run this in a background task and an email
        failure must not surface as a request error or roll anything back.
        """
        from_addr = settings.EMAIL_FROM or settings.SMTP_USER
        if not from_addr:
            logger.error("[email] no EMAIL_FROM / SMTP_USER configured — cannot send '%s' to %s", subject, to)
            return False

        message = EmailMessage()
        message["From"] = formataddr((settings.EMAIL_FROM_NAME, from_addr))
        message["To"] = to
        message["Subject"] = subject
        # Route client replies to the support inbox when configured.
        if settings.EMAIL_REPLY_TO:
            message["Reply-To"] = settings.EMAIL_REPLY_TO
        # Plaintext is the required fallback; HTML is the alternative.
        message.set_content(text or _strip_html(html))
        message.add_alternative(html, subtype="html")

        try:
            self._backend.send(message)
            logger.info("[email] sent '%s' to %s via %s", subject, to, type(self._backend).__name__)
            return True
        except Exception:  # noqa: BLE001 - email is best-effort, never fatal
            logger.exception("[email] failed to send '%s' to %s", subject, to)
            return False


def _strip_html(html: str) -> str:
    """Crude HTML→text fallback for clients that won't render HTML."""
    import re

    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|h[1-6]|tr)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse runs of blank lines and trim each line.
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln) or html


# Module singleton. Backend is resolved at import time from settings; tests can
# inject a fake backend via EmailService(backend=...).
email_service = EmailService()
