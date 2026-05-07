from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification import Notification


router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


def _serialize(n: Notification) -> dict:
    return {
        "notification_id": n.notification_id,
        "category": n.category,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "is_read": n.is_read,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/")
def list_my_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    only_unread: bool = Query(False),
    limit: int = Query(50, le=200),
):
    q = db.query(Notification).filter(Notification.user_id == current_user["user_id"])
    if only_unread:
        q = q.filter(Notification.is_read.is_(False))
    notifications = q.order_by(Notification.created_at.desc()).limit(limit).all()

    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user["user_id"], Notification.is_read.is_(False))
        .count()
    )

    return {
        "notifications": [_serialize(n) for n in notifications],
        "unread_count": unread_count,
    }


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    n = (
        db.query(Notification)
        .filter(
            Notification.notification_id == notification_id,
            Notification.user_id == current_user["user_id"],
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return _serialize(n)


@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    affected = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user["user_id"],
            Notification.is_read.is_(False),
        )
        .update({"is_read": True, "read_at": now})
    )
    db.commit()
    return {"marked_read": affected}
