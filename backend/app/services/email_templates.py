"""
Transactional email templates (EMAIL-001).

Plain Python string templates — no Jinja dependency. Each renderer returns a
``(subject, html, text)`` tuple ready to hand to ``email_service.send``.

Single-platform-sender model: the From address is the platform's, and the
hospital's name appears *inside* the body for branding. When per-tenant senders
arrive later, only the From address changes — these templates are unaffected.

All caller-supplied values are HTML-escaped (``_e``) to prevent injection into
the HTML alternative.
"""
from __future__ import annotations

import html
from typing import Tuple

# Inline styles only — email clients strip <style> blocks and don't load
# external CSS. Keep the palette muted and the layout single-column.
_BRAND = "#0f766e"   # teal-700, matches the app
_INK = "#1f2937"     # slate-800
_MUTED = "#6b7280"   # gray-500


def _e(value: str | None) -> str:
    return html.escape(value or "")


def _layout(*, heading: str, body_html: str, footer: str = "") -> str:
    """Wrap inner content in the shared responsive shell."""
    footer_html = (
        f'<p style="margin:24px 0 0;font-size:12px;line-height:18px;color:{_MUTED};">{footer}</p>'
        if footer else ""
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
        <tr><td style="background:{_BRAND};padding:20px 28px;">
          <span style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:18px;font-weight:700;letter-spacing:0.3px;">MediFleet</span>
        </td></tr>
        <tr><td style="padding:28px;font-family:Arial,Helvetica,sans-serif;color:{_INK};">
          <h1 style="margin:0 0 16px;font-size:20px;line-height:28px;color:{_INK};">{heading}</h1>
          {body_html}
          {footer_html}
        </td></tr>
      </table>
      <p style="max-width:520px;margin:16px auto 0;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:16px;color:{_MUTED};text-align:center;">
        This is an automated message from MediFleet. Please do not reply to this email.
      </p>
    </td></tr>
  </table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">'
        f'<tr><td style="border-radius:8px;background:{_BRAND};">'
        f'<a href="{_e(url)}" style="display:inline-block;padding:12px 24px;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">{_e(label)}</a>'
        f"</td></tr></table>"
    )


def render_password_reset(
    *, reset_url: str, recipient_name: str | None = None,
    hospital_name: str | None = None, expires_minutes: int = 60,
) -> Tuple[str, str, str]:
    greeting = f"Hi {_e(recipient_name)}," if recipient_name else "Hello,"
    org = f" for <strong>{_e(hospital_name)}</strong>" if hospital_name else ""
    org_text = f" for {hospital_name}" if hospital_name else ""

    subject = "Reset your MediFleet password"
    body_html = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:22px;">{greeting}</p>'
        f'<p style="margin:0 0 8px;font-size:15px;line-height:22px;">'
        f"We received a request to reset the password on your MediFleet account{org}. "
        f"Click the button below to choose a new one.</p>"
        f"{_button(reset_url, 'Reset password')}"
        f'<p style="margin:0;font-size:13px;line-height:20px;color:{_MUTED};">'
        f"This link expires in {expires_minutes} minutes. If you didn't request a password "
        f"reset, you can safely ignore this email — your password won't change.</p>"
    )
    footer = (
        "If the button doesn't work, copy and paste this URL into your browser:<br>"
        f'<a href="{_e(reset_url)}" style="color:{_BRAND};word-break:break-all;">{_e(reset_url)}</a>'
    )
    html_out = _layout(heading="Password reset request", body_html=body_html, footer=footer)
    text_out = (
        f"{recipient_name + ',' if recipient_name else 'Hello,'}\n\n"
        f"We received a request to reset the password on your MediFleet account{org_text}.\n"
        f"Open this link to choose a new password (expires in {expires_minutes} minutes):\n\n"
        f"{reset_url}\n\n"
        "If you didn't request this, ignore this email — your password won't change.\n"
    )
    return subject, html_out, text_out


def render_staff_invite(
    *, invite_url: str, recipient_name: str | None = None,
    hospital_name: str | None = None, inviter_name: str | None = None,
    expires_minutes: int = 60,
) -> Tuple[str, str, str]:
    greeting = f"Hi {_e(recipient_name)}," if recipient_name else "Hello,"
    org = _e(hospital_name) if hospital_name else "your organization"
    org_text = hospital_name if hospital_name else "your organization"
    inviter = f"{_e(inviter_name)} has" if inviter_name else "You've"
    inviter_text = f"{inviter_name} has" if inviter_name else "You've"

    subject = f"You've been invited to MediFleet — {org_text}"
    body_html = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:22px;">{greeting}</p>'
        f'<p style="margin:0 0 8px;font-size:15px;line-height:22px;">'
        f"{inviter} been invited to access <strong>{org}</strong> on MediFleet. "
        f"To get started, set your password using the button below.</p>"
        f"{_button(invite_url, 'Set your password')}"
        f'<p style="margin:0;font-size:13px;line-height:20px;color:{_MUTED};">'
        f"This invitation link expires in {expires_minutes} minutes. If you weren't "
        f"expecting this, you can ignore this email.</p>"
    )
    footer = (
        "If the button doesn't work, copy and paste this URL into your browser:<br>"
        f'<a href="{_e(invite_url)}" style="color:{_BRAND};word-break:break-all;">{_e(invite_url)}</a>'
    )
    html_out = _layout(heading="Welcome to MediFleet", body_html=body_html, footer=footer)
    text_out = (
        f"{recipient_name + ',' if recipient_name else 'Hello,'}\n\n"
        f"{inviter_text} been invited to access {org_text} on MediFleet.\n"
        f"Set your password using this link (expires in {expires_minutes} minutes):\n\n"
        f"{invite_url}\n\n"
        "If you weren't expecting this, ignore this email.\n"
    )
    return subject, html_out, text_out


def render_ticket_reply(
    *, ticket_ref: str, ticket_subject: str, reply_body: str,
    recipient_name: str | None = None,
) -> Tuple[str, str, str]:
    """Email sent to a client when the support team replies to their ticket.

    Subject carries the ``[#MF-000123]`` token so a client reply threads back
    to the same ticket via the inbound webhook.
    """
    greeting = f"Hi {_e(recipient_name)}," if recipient_name else "Hello,"
    subject = f"[{ticket_ref}] {ticket_subject}".strip()
    # Preserve the agent's line breaks in HTML.
    body_html_inner = _e(reply_body).replace("\n", "<br>")
    body_html = (
        f'<p style="margin:0 0 12px;font-size:15px;line-height:22px;">{greeting}</p>'
        f'<p style="margin:0 0 16px;font-size:15px;line-height:22px;">'
        f"Our support team replied to your request <strong>{_e(ticket_ref)}</strong>:</p>"
        f'<div style="margin:0 0 16px;padding:14px 16px;background:#f9fafb;border-left:3px solid {_BRAND};'
        f'font-size:15px;line-height:22px;color:{_INK};">{body_html_inner}</div>'
        f'<p style="margin:0;font-size:13px;line-height:20px;color:{_MUTED};">'
        "Just reply to this email to continue the conversation — your response is "
        "added to the same ticket.</p>"
    )
    html_out = _layout(heading="Reply from MediFleet Support", body_html=body_html)
    text_out = (
        f"{recipient_name + ',' if recipient_name else 'Hello,'}\n\n"
        f"Our support team replied to your request {ticket_ref}:\n\n"
        f"{reply_body}\n\n"
        "Just reply to this email to continue the conversation — your response is "
        "added to the same ticket.\n"
    )
    return subject, html_out, text_out


def render_contact_message(
    *, name: str, email: str, message: str,
    subject: str | None = None, company: str | None = None,
) -> Tuple[str, str, str]:
    """Internal notification email for a website contact-form submission.

    Sent to the support inbox; Reply-To is set to the visitor's address by the
    caller so the team can reply straight to the prospect.
    """
    line = (subject or "New website enquiry").strip()
    email_subject = f"[Contact] {line} — from {name}".strip()
    rows = [("Name", name), ("Email", email)]
    if company:
        rows.append(("Company", company))
    if subject:
        rows.append(("Subject", subject))
    rows_html = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;font-size:13px;color:{_MUTED};white-space:nowrap;">{_e(k)}</td>'
        f'<td style="padding:4px 0;font-size:14px;color:{_INK};">{_e(v)}</td></tr>'
        for k, v in rows
    )
    body_html = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 16px;">{rows_html}</table>'
        f'<div style="margin:0;padding:14px 16px;background:#f9fafb;border-left:3px solid {_BRAND};'
        f'font-size:15px;line-height:22px;color:{_INK};white-space:pre-wrap;">{_e(message)}</div>'
    )
    html_out = _layout(heading="New contact enquiry", body_html=body_html)
    text_out = (
        "New website contact enquiry\n\n"
        + "".join(f"{k}: {v}\n" for k, v in rows)
        + f"\nMessage:\n{message}\n"
    )
    return email_subject, html_out, text_out
