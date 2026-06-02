"""
Auth-related email dispatch (EMAIL-001).

Ties together: a reset/invite token → a tenant-aware frontend link → the
rendered template → a background send. Routes call these helpers so the
link-building and tenant-routing rules live in exactly one place.

Multi-tenant note: password-reset / invite tokens are stored in the *tenant*
database, so the emailed link MUST carry the tenant id. Without it the
frontend would post to the wrong (or default) tenant DB and the token lookup
would fail. We append ``?tenant=<id>`` and the ResetPassword page restores it
into the X-Tenant-ID header before calling /auth/reset-password.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.services.email_service import email_service
from app.services.email_templates import render_password_reset, render_staff_invite

# Token lifetime advertised to recipients. Mirrors RESET_TOKEN_TTL_MINUTES in
# app.auth.auth (kept independent to avoid a route→service import cycle).
RESET_TOKEN_TTL_MINUTES = 60


def _reset_link(raw_token: str, tenant_id: str | None) -> str:
    base = settings.frontend_base_url
    url = f"{base}/reset-password?token={quote(raw_token, safe='')}"
    if tenant_id:
        url += f"&tenant={quote(tenant_id, safe='')}"
    return url


def send_password_reset_email(
    background_tasks: BackgroundTasks,
    *,
    to: str,
    raw_token: str,
    tenant_id: str | None,
    recipient_name: str | None = None,
    hospital_name: str | None = None,
) -> None:
    """Queue a password-reset email. Returns immediately; sends after response."""
    link = _reset_link(raw_token, tenant_id)
    subject, html, text = render_password_reset(
        reset_url=link,
        recipient_name=recipient_name,
        hospital_name=hospital_name,
        expires_minutes=RESET_TOKEN_TTL_MINUTES,
    )
    background_tasks.add_task(email_service.send, to=to, subject=subject, html=html, text=text)


def send_staff_invite_email(
    background_tasks: BackgroundTasks,
    *,
    to: str,
    raw_token: str,
    tenant_id: str | None,
    recipient_name: str | None = None,
    hospital_name: str | None = None,
    inviter_name: str | None = None,
) -> None:
    """Queue a staff-invite (set-password) email. Reuses the reset-token rail."""
    link = _reset_link(raw_token, tenant_id)
    subject, html, text = render_staff_invite(
        invite_url=link,
        recipient_name=recipient_name,
        hospital_name=hospital_name,
        inviter_name=inviter_name,
        expires_minutes=RESET_TOKEN_TTL_MINUTES,
    )
    background_tasks.add_task(email_service.send, to=to, subject=subject, html=html, text=text)
