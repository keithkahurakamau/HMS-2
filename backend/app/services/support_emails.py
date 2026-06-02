"""
Outbound support-ticket email (EMAIL-002 / EMAIL-003).

When the platform team replies to a ticket in the superadmin inbox, we email
the client so they can read it on any device and reply by email. Threading is
carried by:
  • a ``[#MF-000123]`` token in the subject, and
  • a per-ticket Reply-To ``support+ticket-123@<domain>``,
both of which the inbound webhook parses to route the client's reply back to
the same ticket.

The "from" desk is chosen by ticket category so billing replies come from
finance@ and technical replies from technical@ (falling back to EMAIL_FROM).
"""
from __future__ import annotations

from fastapi import BackgroundTasks

from app.config.settings import settings
from app.services.email_service import email_service
from app.services.email_templates import render_ticket_reply

# Ticket category → sender desk. Mirrors support_inbound.DESK_CATEGORY.
_CATEGORY_DESK = {
    "Billing": "finance",
    "Bug": "technical",
    "Feature": "technical",
    "Account": "support",
    "Onboarding": "support",
    "Other": "support",
}


def ticket_ref(ticket_id: int) -> str:
    """Human/threading reference, e.g. '#MF-000123'."""
    return f"#MF-{ticket_id:06d}"


def ticket_reply_address(ticket_id: int) -> str:
    """Per-ticket Reply-To, e.g. 'support+ticket-123@medifleet.app'."""
    return f"support+ticket-{ticket_id}@{settings.SUPPORT_INBOUND_DOMAIN}"


def desk_for_category(category: str | None) -> str:
    return _CATEGORY_DESK.get(category or "", "support")


def send_ticket_reply_email(
    background_tasks: BackgroundTasks,
    *,
    ticket_id: int,
    to: str,
    ticket_subject: str,
    reply_body: str,
    category: str | None = None,
    recipient_name: str | None = None,
) -> None:
    """Queue the client-facing email for a platform reply to a ticket."""
    desk = desk_for_category(category)
    subject, html, text = render_ticket_reply(
        ticket_ref=ticket_ref(ticket_id),
        ticket_subject=ticket_subject,
        reply_body=reply_body,
        recipient_name=recipient_name,
    )
    background_tasks.add_task(
        email_service.send,
        to=to,
        subject=subject,
        html=html,
        text=text,
        from_addr=settings.email_from_for(desk),
        reply_to=ticket_reply_address(ticket_id),
    )
