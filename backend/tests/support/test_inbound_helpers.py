"""Unit tests for the pure inbound-email helpers (no DB, no network)."""
from __future__ import annotations

import hashlib
import hmac

from app.services import support_inbound as si


# ── signature ───────────────────────────────────────────────────────────────
def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_valid():
    body, secret = b'{"a":1}', "s3cret"
    assert si.verify_signature(body, _sign(body, secret), secret) is True
    assert si.verify_signature(body, "sha256=" + _sign(body, secret), secret) is True


def test_verify_signature_rejects_tampered_or_empty():
    body, secret = b'{"a":1}', "s3cret"
    assert si.verify_signature(body, _sign(b'{"a":2}', secret), secret) is False
    assert si.verify_signature(body, "", secret) is False
    assert si.verify_signature(body, _sign(body, secret), "") is False


# ── desk / category ───────────────────────────────────────────────────────────
def test_resolve_desk_from_recipient():
    assert si.resolve_desk(["finance@medifleet.app"]) == "finance"
    assert si.resolve_desk(["Technical <technical@medifleet.app>"]) == "technical"
    assert si.resolve_desk(["support+ticket-5@medifleet.app"]) == "support"
    assert si.resolve_desk(["random@medifleet.app"]) == "support"  # default
    assert si.resolve_desk([]) == "support"


def test_desk_to_category():
    assert si.desk_to_category("finance") == "Billing"
    assert si.desk_to_category("technical") == "Bug"
    assert si.desk_to_category("support") == "Account"
    assert si.desk_to_category("unknown") == "Other"


# ── threading ──────────────────────────────────────────────────────────────────
def test_extract_ticket_id_from_plus_address():
    assert si.extract_ticket_id(["support+ticket-123@medifleet.app"], "anything") == 123


def test_extract_ticket_id_from_subject_token():
    assert si.extract_ticket_id(["support@medifleet.app"], "Re: [#MF-000077] Help") == 77


def test_extract_ticket_id_plus_takes_precedence():
    assert si.extract_ticket_id(["support+ticket-9@medifleet.app"], "[#MF-000077]") == 9


def test_extract_ticket_id_none_when_absent():
    assert si.extract_ticket_id(["support@medifleet.app"], "No ref here") is None


# ── from parsing ───────────────────────────────────────────────────────────────
def test_parse_from_name_and_email():
    assert si.parse_from("Jane Client <Jane@Example.com>") == ("jane@example.com", "Jane Client")


def test_parse_from_bare_email_falls_back_to_local_part():
    assert si.parse_from("bob@example.com") == ("bob@example.com", "bob")


# ── body / attachments ──────────────────────────────────────────────────────────
def test_build_body_prefers_text_and_drops_attachments():
    body = si.build_body(
        "Hello there", "<p>ignored</p>",
        [{"filename": "scan.pdf"}, {"filename": "x.png"}],
    )
    assert body.startswith("Hello there")
    assert "2 attachment(s) dropped: scan.pdf, x.png" in body


def test_build_body_falls_back_to_html_then_placeholder():
    assert "Hello" in si.build_body(None, "<p>Hello</p>", None)
    assert si.build_body(None, None, None) == "(no text content)"
