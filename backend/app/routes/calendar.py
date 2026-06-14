"""Personal calendar events — user-scoped CRUD.

Every endpoint is bound to the logged-in user: a staff member only ever
sees and edits their own events. No extra permission gate is needed beyond
authentication — a personal calendar isn't a module-gated feature, it's a
property of having an account. The shared appointments calendar overlays
these client-side.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user
from app.models.calendar import CalendarEvent


router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

VALID_CATEGORIES = {"personal", "leave", "meeting", "on-call", "reminder", "other"}


class CalendarEventCreate(BaseModel):
    title: str
    notes: Optional[str] = None
    category: str = "personal"
    start_at: datetime
    end_at: Optional[datetime] = None
    all_day: bool = False

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Title is required.")
        return v[:200]

    @field_validator("category")
    @classmethod
    def _category_known(cls, v: str) -> str:
        v = (v or "personal").strip().lower()
        return v if v in VALID_CATEGORIES else "personal"


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    category: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    all_day: Optional[bool] = None


def _serialize(e: CalendarEvent) -> dict:
    return {
        "event_id": e.event_id,
        "title": e.title,
        "notes": e.notes,
        "category": e.category,
        "start_at": e.start_at.isoformat() if e.start_at else None,
        "end_at": e.end_at.isoformat() if e.end_at else None,
        "all_day": e.all_day,
    }


def _validate_range(start: Optional[datetime], end: Optional[datetime]) -> None:
    if start and end and end < start:
        raise HTTPException(status_code=400, detail="End time cannot be before the start time.")


@router.get("/events")
def list_events(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    """The caller's own events, optionally bounded by a date window so the
    calendar can fetch just the month in view."""
    q = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user["user_id"])
    if date_from is not None:
        # An event is in-window if it ends on/after the window start (use the
        # start as the fallback end for point-in-time events).
        q = q.filter((CalendarEvent.end_at >= date_from) | (CalendarEvent.start_at >= date_from))
    if date_to is not None:
        q = q.filter(CalendarEvent.start_at <= date_to)
    events = q.order_by(CalendarEvent.start_at.asc()).all()
    return [_serialize(e) for e in events]


@router.post("/events")
def create_event(
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _validate_range(payload.start_at, payload.end_at)
    event = CalendarEvent(
        user_id=current_user["user_id"],
        title=payload.title,
        notes=payload.notes,
        category=payload.category,
        start_at=payload.start_at,
        end_at=payload.end_at,
        all_day=payload.all_day,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _serialize(event)


def _owned_event(db: Session, event_id: int, user_id: int) -> CalendarEvent:
    event = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.event_id == event_id, CalendarEvent.user_id == user_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


@router.patch("/events/{event_id}")
def update_event(
    event_id: int,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    event = _owned_event(db, event_id, current_user["user_id"])
    data = payload.model_dump(exclude_unset=True)

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        event.title = title[:200]
    if "notes" in data:
        event.notes = data["notes"]
    if "category" in data:
        cat = (data["category"] or "personal").strip().lower()
        event.category = cat if cat in VALID_CATEGORIES else "personal"
    if "start_at" in data:
        event.start_at = data["start_at"]
    if "end_at" in data:
        event.end_at = data["end_at"]
    if "all_day" in data:
        event.all_day = data["all_day"]

    _validate_range(event.start_at, event.end_at)
    db.commit()
    db.refresh(event)
    return _serialize(event)


@router.delete("/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    event = _owned_event(db, event_id, current_user["user_id"])
    db.delete(event)
    db.commit()
    return {"message": "Event deleted.", "event_id": event_id}
