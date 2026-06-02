"""
Outbound email event processing + suppression (EMAIL-004).

Consumes Resend *events* webhook payloads: records every event to ``email_events``
and, on a hard bounce or spam complaint, adds the recipient to
``email_suppressions`` so we stop emailing them (protects sender reputation).

Pure helpers (parse / classify) are DB-free and unit-tested; the DB functions
are thin. ``is_suppressed`` is deliberately defensive — it opens its own master
session and returns False on any error, so a send is never blocked by an
infra hiccup or a missing table (e.g. in tests/CI).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.email_events import EmailEvent, EmailSuppression

logger = logging.getLogger(__name__)

# Event types that mean "never email this address again".
_SUPPRESS = {
    "email.bounced": "bounced",
    "email.complained": "complained",
}


@dataclass
class ParsedEvent:
    event_type: str
    email: Optional[str]
    message_id: Optional[str]
    reason: Optional[str]


def parse_event(payload: dict) -> ParsedEvent:
    """Normalize a Resend event payload (defensive about shape)."""
    event_type = (payload.get("type") or payload.get("event") or "").strip()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

    to = data.get("to")
    if isinstance(to, list):
        email = (to[0] if to else None)
    else:
        email = to or data.get("email")
    if isinstance(email, dict):
        email = email.get("address") or email.get("email")
    email = (email or "").strip().lower() or None

    message_id = data.get("email_id") or data.get("message_id") or data.get("id")

    reason = None
    bounce = data.get("bounce")
    if isinstance(bounce, dict):
        reason = bounce.get("message") or bounce.get("subType") or bounce.get("type")
    reason = reason or data.get("reason")

    return ParsedEvent(event_type=event_type, email=email, message_id=message_id, reason=reason)


def suppression_reason(event_type: str) -> Optional[str]:
    """'bounced' | 'complained' for events that should suppress, else None."""
    return _SUPPRESS.get(event_type)


def process_event(db: Session, payload: dict) -> dict:
    """Record one event; suppress the recipient on bounce/complaint."""
    ev = parse_event(payload)
    if not ev.event_type:
        return {"recorded": False, "reason": "missing event type"}

    db.add(EmailEvent(
        event_type=ev.event_type, email=ev.email,
        message_id=ev.message_id, reason=(ev.reason or "")[:255] or None,
    ))

    suppressed = False
    reason = suppression_reason(ev.event_type)
    if reason and ev.email:
        existing = db.query(EmailSuppression).filter(EmailSuppression.email == ev.email).first()
        if not existing:
            db.add(EmailSuppression(email=ev.email, reason=reason, detail=ev.reason))
            suppressed = True
    db.commit()

    if suppressed:
        logger.info("[email-events] suppressed %s (%s)", ev.email, reason)
    return {"recorded": True, "event_type": ev.event_type, "suppressed": suppressed}


def is_suppressed(email: str) -> bool:
    """True if the address is on the suppression list. Never raises — returns
    False on any error so a send is never blocked by infra/missing table."""
    if not email:
        return False
    try:
        from app.config.database import MasterSessionLocal
        db = MasterSessionLocal()
        try:
            return db.query(EmailSuppression).filter(
                EmailSuppression.email == email.strip().lower()
            ).first() is not None
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - suppression must never break sending
        logger.debug("[email-events] suppression check failed for %s — allowing send", email, exc_info=True)
        return False
