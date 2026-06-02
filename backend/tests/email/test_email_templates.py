"""Unit tests for email template rendering (no DB, no network)."""
from __future__ import annotations

from app.services.email_templates import render_password_reset, render_staff_invite

RESET_URL = "https://app.medifleet.app/reset-password?token=ABC123&tenant=demo"
INVITE_URL = "https://app.medifleet.app/reset-password?token=XYZ789&tenant=demo"
# In HTML the ampersand is escaped (&amp;); plaintext keeps the raw URL.
RESET_URL_HTML = RESET_URL.replace("&", "&amp;")
INVITE_URL_HTML = INVITE_URL.replace("&", "&amp;")


def test_password_reset_returns_subject_html_text():
    subject, html, text = render_password_reset(
        reset_url=RESET_URL, recipient_name="Dr Jane", hospital_name="Mayo Clinic",
    )
    assert "reset" in subject.lower()
    assert RESET_URL_HTML in html
    assert RESET_URL in text
    assert "Mayo Clinic" in html
    assert "Dr Jane" in html
    assert "60 minutes" in html  # default expiry advertised


def test_password_reset_respects_custom_expiry():
    _, html, text = render_password_reset(reset_url=RESET_URL, expires_minutes=30)
    assert "30 minutes" in html
    assert "30 minutes" in text


def test_password_reset_escapes_html_in_user_values():
    _, html, _ = render_password_reset(
        reset_url=RESET_URL, recipient_name="<script>alert(1)</script>",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_staff_invite_returns_subject_html_text():
    subject, html, text = render_staff_invite(
        invite_url=INVITE_URL, recipient_name="Sam", hospital_name="Mayo Clinic",
        inviter_name="Admin Ann",
    )
    assert "Mayo Clinic" in subject
    assert INVITE_URL_HTML in html
    assert INVITE_URL in text
    assert "Sam" in html
    assert "Admin Ann" in html


def test_staff_invite_handles_missing_optional_fields():
    # No recipient/hospital/inviter — should still render coherent copy.
    subject, html, text = render_staff_invite(invite_url=INVITE_URL)
    assert INVITE_URL_HTML in html and INVITE_URL in text
    assert "your organization" in html.lower()
