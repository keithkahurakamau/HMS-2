from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from app.config.database import get_db
from app.models.clinical import PatientQueue
from app.models.patient import Patient
from app.schemas.queue import (
    QueueCreate, QueueResponse, QueueEndOfDay, QueueCheckoutResult, QueueCancel,
    CloseVisitResult,
)
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit
from app.utils.notify import notify_permission
from app.routes.patients import _canonical_department

router = APIRouter(prefix="/api/queue", tags=["Triage Queue"])

# Statuses that mean a patient is still actively in the queue (i.e. not yet
# Completed). Mirrors the set the clinical desk and patient-routing use.
ACTIVE_QUEUE_STATUSES = ["Waiting", "In Progress", "In Consultation"]

# Both terminal statuses — patients removed from the active view.
TERMINAL_QUEUE_STATUSES = ["Completed", "Cancelled"]

@router.post("/", response_model=QueueResponse, dependencies=[Depends(RequirePermission("patients:write"))])
def add_to_queue(queue_in: QueueCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    payload = queue_in.model_dump()
    payload["department"] = _canonical_department(payload["department"])
    payload["acuity_level"] = max(1, min(5, int(payload.get("acuity_level") or 3)))

    new_queue = PatientQueue(**payload)
    db.add(new_queue)
    db.flush()

    log_audit(
        db, current_user["user_id"], "CREATE", "Queue", new_queue.queue_id,
        None, payload,
        request.client.host if request.client else None,
    )

    # Tell the doctors a patient is waiting — the front desk queues the
    # patient, but it's the clinical side that needs to react.
    if payload["department"] == "Consultation":
        from app.models.patient import Patient
        patient = db.query(Patient).filter(Patient.patient_id == payload["patient_id"]).first()
        patient_name = f"{patient.other_names} {patient.surname}" if patient else "A patient"
        acuity = payload["acuity_level"]
        notify_permission(
            db, "clinical:write",
            title="Patient waiting in the consultation queue",
            body=f"{patient_name} · acuity {acuity}",
            link="/app/clinical",
            category="critical" if acuity == 1 else ("warning" if acuity == 2 else "info"),
            exclude_user_id=current_user["user_id"],
        )

    db.commit()
    db.refresh(new_queue)
    return new_queue

@router.get("/", response_model=List[QueueResponse], dependencies=[Depends(RequirePermission("patients:read"))])
def get_active_queue(department: Optional[str] = None, db: Session = Depends(get_db)):
    query = (
        db.query(PatientQueue, Patient)
        .join(Patient, PatientQueue.patient_id == Patient.patient_id)
        .filter(~PatientQueue.status.in_(TERMINAL_QUEUE_STATUSES))
    )
    if department:
        query = query.filter(PatientQueue.department == department)
    rows = query.order_by(PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc()).all()
    result = []
    for queue_entry, patient in rows:
        entry_dict = {c.name: getattr(queue_entry, c.name) for c in PatientQueue.__table__.columns}
        entry_dict["patient_name"] = f"{patient.other_names} {patient.surname}"
        result.append(entry_dict)
    return result


@router.patch(
    "/{queue_id}/checkout",
    response_model=QueueResponse,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def checkout_from_queue(
    queue_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Remove a single patient from the active queue.

    Soft-completes the entry (status → Completed, stamps completed_at) rather
    than deleting it, so the visit stays in history/analytics. Used for the
    per-row "remove from queue" action when a patient leaves without being
    seen."""
    entry = db.query(PatientQueue).filter(PatientQueue.queue_id == queue_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    if entry.status != "Completed":
        old = {"status": entry.status}
        entry.status = "Completed"
        entry.completed_at = datetime.now(timezone.utc)
        log_audit(
            db, current_user["user_id"], "UPDATE", "Queue", entry.queue_id,
            old, {"status": "Completed"},
            request.client.host if request.client else None,
        )
        db.commit()
        db.refresh(entry)
    return entry


@router.patch(
    "/{queue_id}/cancel",
    response_model=QueueResponse,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def cancel_from_queue(
    queue_id: int,
    payload: QueueCancel,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a patient who left without being seen.

    Distinct from checkout (Completed = seen & done): Cancelled means the
    patient never received the service. Soft-terminal so analytics can tell
    them apart and history retains the visit."""
    entry = db.query(PatientQueue).filter(PatientQueue.queue_id == queue_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    if entry.status not in TERMINAL_QUEUE_STATUSES:
        old = {"status": entry.status}
        entry.status = "Cancelled"
        entry.completed_at = datetime.now(timezone.utc)
        if payload.reason:
            entry.notes = ((entry.notes + " | ") if entry.notes else "") + f"Cancelled: {payload.reason}"
        log_audit(
            db, current_user["user_id"], "UPDATE", "Queue", entry.queue_id,
            old, {"status": "Cancelled", "reason": payload.reason},
            request.client.host if request.client else None,
        )
        db.commit()
        db.refresh(entry)
    return entry


@router.post(
    "/end-of-day",
    response_model=QueueCheckoutResult,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def end_of_day_checkout(
    payload: QueueEndOfDay,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Clear the queue at the end of the clinic day.

    Soft-completes every still-active queue entry (optionally scoped to one
    department, e.g. the doctor closing the Consultation clinic) so leftover
    patients who were never seen don't carry over to tomorrow's queue."""
    query = db.query(PatientQueue).filter(
        PatientQueue.status.in_(ACTIVE_QUEUE_STATUSES)
    )
    department = None
    if payload.department:
        department = _canonical_department(payload.department)
        query = query.filter(PatientQueue.department == department)

    entries = query.all()
    now = datetime.now(timezone.utc)
    for entry in entries:
        entry.status = "Completed"
        entry.completed_at = now

    log_audit(
        db, current_user["user_id"], "UPDATE", "Queue", "end-of-day",
        {"active_count": len(entries), "department": department or "ALL"},
        {"status": "Completed"},
        request.client.host if request.client else None,
    )
    db.commit()
    return QueueCheckoutResult(checked_out=len(entries), department=department)


@router.post(
    "/patients/{patient_id}/close-visit",
    response_model=CloseVisitResult,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def close_visit(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Close a patient's current visit by soft-completing every active queue
    row they have, so the next registration/queue starts a clean visit.
    Backs the 'Clear previous visit / start new visit' control on the chart."""
    rows = db.query(PatientQueue).filter(
        PatientQueue.patient_id == patient_id,
        PatientQueue.status.in_(ACTIVE_QUEUE_STATUSES),
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = "Completed"
        row.completed_at = now
    log_audit(
        db, current_user["user_id"], "UPDATE", "Queue", f"close-visit:{patient_id}",
        {"active_count": len(rows)}, {"status": "Completed"},
        request.client.host if request.client else None,
    )
    db.commit()
    return CloseVisitResult(closed=len(rows))
