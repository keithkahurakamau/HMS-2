"""
Single helper for emitting persistent + real-time notifications together.

Server code calls `notify(...)` instead of touching the WebSocket layer or the
DB directly. The helper writes a Notification row and (best-effort) publishes
a WebSocket message so the bell + toast update live without a refresh.
"""
import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.core.websocket import manager

logger = logging.getLogger(__name__)


def notify(
    db: Session,
    *,
    user_id: int,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category: str = "info",
    flush: bool = True,
) -> Notification:
    """
    Persists a notification and pushes a real-time fan-out message.

    The caller commits the surrounding transaction. If `flush=True` (default)
    the row is flushed so the notification_id is available on the returned
    object.
    """
    n = Notification(
        user_id=user_id,
        category=category,
        title=title,
        body=body,
        link=link,
    )
    db.add(n)
    if flush:
        db.flush()

    payload = {
        "type": "notification",
        "notification_id": n.notification_id,
        "category": category,
        "title": title,
        "body": body,
        "link": link,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }

    # Real-time fan-out is best-effort — never block the write path.
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(manager.send_personal_message(payload, user_id))
            else:
                loop.run_until_complete(manager.send_personal_message(payload, user_id))
        except RuntimeError:
            asyncio.run(manager.send_personal_message(payload, user_id))
    except Exception as exc:
        logger.warning("notify(): WebSocket fan-out failed for user %s: %s", user_id, exc)

    return n
