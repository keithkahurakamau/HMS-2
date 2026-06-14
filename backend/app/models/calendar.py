from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


class CalendarEvent(Base):
    """A staff member's personal calendar event — leave, meetings, reminders,
    on-call blocks, anything that isn't a patient appointment.

    Strictly user-scoped: every row belongs to the user who created it and is
    only ever read/written by that user. The shared calendar view overlays
    these on top of the appointments feed so a clinician sees one timeline.
    """
    __tablename__ = "calendar_events"

    event_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)

    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    # Free-text colour/category tag the UI maps to a swatch (e.g. "leave",
    # "meeting", "personal"). Kept loose so we don't migrate for a new tag.
    category = Column(String(40), nullable=False, default="personal")

    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    # Nullable end: a point-in-time reminder has no end. All-day events span
    # the calendar day and ignore the time component in the UI.
    end_at = Column(DateTime(timezone=True), nullable=True)
    all_day = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User")

    __table_args__ = (
        Index("idx_calendar_user_start", "user_id", "start_at"),
    )
