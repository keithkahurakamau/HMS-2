"""
Persistent in-app notifications.

Toast popups (react-hot-toast) are ephemeral. This table backs an inbox so a
user who was offline when an event fired can still see "lab result is ready"
when they next log in. Mark-as-read state is per-recipient.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.sql import func
from app.config.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)

    # category lets the UI render an icon and color (info / success / warning / critical)
    category = Column(String(20), default="info", nullable=False)
    # Short, single-line label
    title = Column(String(255), nullable=False)
    # Optional long-form body
    body = Column(Text, nullable=True)
    # Optional in-app deep link (e.g. "/app/laboratory?test_id=42")
    link = Column(String(255), nullable=True)

    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("idx_notification_user_unread", "user_id", "is_read", "created_at"),
    )
