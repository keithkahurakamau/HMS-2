"""
Inbound support email → Support Inbox (EMAIL-003).

A mail provider (Resend Inbound) receives mail at support@ / finance@ /
technical@<domain> and POSTs the parsed message to
``/api/public/support/inbound``. This module turns that payload into
``SupportTicket`` / ``SupportMessage`` rows in the master DB.

Policy decisions (per product):
  • **Drop attachments** — we never store file content; only a one-line note
    of what was dropped is appended to the message body.
  • **Restrict to known contacts** — we only accept mail from a sender whose
    address already exists as ``submitter_email`` on some ticket (i.e. they
    raised a ticket in-product first, or are replying to one). Unknown senders
    are rejected. This avoids cross-tenant email scans and blocks cold spam.

The pure helpers (signature, desk/category, threading, body) are DB-free and
unit-tested directly; ``process_inbound`` is the thin DB orchestrator.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Optional

from sqlalchemy.orm import Session

from app.models.support import SupportMessage, SupportTicket

logger = logging.getLogger(__name__)

# Recipient local-part → support desk → ticket category.
DESK_CATEGORY = {
    "support": "Account",
    "finance": "Billing",
    "technical": "Bug",
}
DEFAULT_CATEGORY = "Other"

TERMINAL_STATUSES = {"Resolved", "Closed"}

# Outbound subject token, e.g. "[#MF-000123]". Parsed back on reply.
_SUBJECT_REF = re.compile(r"\[#MF-0*(\d+)\]")
# Plus-addressed reply target, e.g. "support+ticket-123@medifleet.app".
_PLUS_REF = re.compile(r"\+ticket-(\d+)@", re.IGNORECASE)


@dataclass
class InboundResult:
    action: str                     # "created" | "appended" | "duplicate" | "rejected"
    reason: str = ""
    ticket_id: Optional[int] = None


# ── Pure helpers (DB-free) ─────────────────────────────────────────────────
# Webhook signature verification lives in app.services.webhook_security
# (Svix scheme — Resend signs with whsec_ secrets).


def _local_part(addr: str) -> str:
    _, email = parseaddr(addr or "")
    return (email.split("@", 1)[0] if "@" in email else email).lower()


def resolve_desk(to_addresses: list[str]) -> str:
    """Which desk an inbound message was addressed to. Strips any +tag."""
    for addr in to_addresses or []:
        local = _local_part(addr).split("+", 1)[0]
        if local in DESK_CATEGORY:
            return local
    return "support"


def desk_to_category(desk: str) -> str:
    return DESK_CATEGORY.get(desk, DEFAULT_CATEGORY)


def extract_ticket_id(to_addresses: list[str], subject: str) -> Optional[int]:
    """Find the ticket this message replies to: plus-address first, then subject token."""
    for addr in to_addresses or []:
        m = _PLUS_REF.search(addr or "")
        if m:
            return int(m.group(1))
    m = _SUBJECT_REF.search(subject or "")
    return int(m.group(1)) if m else None


def parse_from(from_header: str) -> tuple[str, str]:
    """Return (email_lower, display_name). Name falls back to the local part."""
    name, email = parseaddr(from_header or "")
    email = email.strip().lower()
    return email, (name.strip() or (email.split("@", 1)[0] if email else "Unknown"))


def build_body(text: str | None, html: str | None, attachments: list | None) -> str:
    """Assemble the stored message body. Prefer plaintext; drop attachments,
    leaving only a note of what was stripped."""
    body = (text or "").strip()
    if not body and html:
        body = _strip_html(html)
    body = body or "(no text content)"
    names = [a.get("filename") or "file" for a in (attachments or []) if isinstance(a, dict)]
    if names:
        body += f"\n\n[{len(names)} attachment(s) dropped: {', '.join(names)}]"
    return body


def _strip_html(html: str) -> str:
    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|h[1-6]|tr)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


# ── DB orchestration ────────────────────────────────────────────────────────
def _known_contact_ticket(db: Session, sender_email: str) -> Optional[SupportTicket]:
    """Most recent ticket whose submitter matches the sender — our definition
    of a 'known contact'. Returns None if the sender has never raised a ticket."""
    if not sender_email:
        return None
    return (
        db.query(SupportTicket)
        .filter(SupportTicket.submitter_email == sender_email)
        .order_by(SupportTicket.created_at.desc())
        .first()
    )


def process_inbound(db: Session, payload: dict) -> InboundResult:
    """Persist one inbound email as a ticket or a reply. Idempotent on Message-ID."""
    sender_email, sender_name = parse_from(payload.get("from", ""))
    to_addresses = payload.get("to") or []
    subject = (payload.get("subject") or "").strip() or "(no subject)"
    message_id = (payload.get("message_id") or "").strip() or None

    # 1) Dedupe webhook retries on the provider Message-ID.
    if message_id:
        dup = (
            db.query(SupportMessage)
            .filter(SupportMessage.external_message_id == message_id)
            .first()
        )
        if dup:
            return InboundResult("duplicate", "message already processed", dup.ticket_id)

    body = build_body(payload.get("text"), payload.get("html"), payload.get("attachments"))

    # 2) Threading — is this a reply to an existing ticket?
    ticket_id = extract_ticket_id(to_addresses, subject)
    if ticket_id is not None:
        ticket = db.query(SupportTicket).filter(SupportTicket.ticket_id == ticket_id).first()
        # Known-contact gate for replies: sender must own the ticket.
        if ticket and ticket.submitter_email == sender_email:
            return _append_reply(db, ticket, sender_name, sender_email, body, message_id)
        # Ref present but no match / wrong sender → fall through to the gate.

    # 3) Known-contact gate for new tickets.
    prior = _known_contact_ticket(db, sender_email)
    if prior is None:
        logger.info("[inbound] rejected unknown sender %r (subject=%r)", sender_email, subject)
        return InboundResult("rejected", "unknown sender — not an existing contact")

    # 4) New ticket, attributed to the contact's most recent tenant.
    desk = resolve_desk(to_addresses)
    ticket = SupportTicket(
        tenant_id=prior.tenant_id,
        tenant_name=prior.tenant_name,
        submitter_email=sender_email,
        submitter_name=sender_name or prior.submitter_name,
        submitter_user_id=prior.submitter_user_id,
        origin="email",
        subject=subject[:200],
        category=desk_to_category(desk),
        priority="Normal",
        status="Open",
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(
        ticket_id=ticket.ticket_id,
        author_kind="customer",
        author_name=sender_name,
        source="email",
        external_message_id=message_id,
        from_email=sender_email,
        from_name=sender_name,
        body=body,
    ))
    db.commit()
    logger.info("[inbound] created ticket #%s from %r via %s desk", ticket.ticket_id, sender_email, desk)
    return InboundResult("created", "new ticket", ticket.ticket_id)


def _append_reply(db, ticket, sender_name, sender_email, body, message_id) -> InboundResult:
    db.add(SupportMessage(
        ticket_id=ticket.ticket_id,
        author_kind="customer",
        author_name=sender_name,
        source="email",
        external_message_id=message_id,
        from_email=sender_email,
        from_name=sender_name,
        body=body,
    ))
    # Customer replied — pull it back into the active queue.
    if ticket.status in TERMINAL_STATUSES or ticket.status == "Waiting on Customer":
        ticket.status = "Open"
    db.commit()
    logger.info("[inbound] appended reply to ticket #%s from %r", ticket.ticket_id, sender_email)
    return InboundResult("appended", "reply added", ticket.ticket_id)
