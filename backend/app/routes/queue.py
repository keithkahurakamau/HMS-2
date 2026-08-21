from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, date as date_cls, timedelta
from collections import defaultdict

from app.config.database import get_db
from app.models.clinical import PatientQueue
from app.models.patient import Patient
from app.models.user import User
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


def _scheme_of(patient: Patient) -> str:
    """Display label for a patient's payment scheme — the insurance provider on
    file, or 'Cash' when they have none."""
    return (patient.insurance_provider or "").strip() or "Cash"


@router.get("/live", dependencies=[Depends(RequirePermission("patients:read"))])
def get_live_queue(db: Session = Depends(get_db)):
    """Live board of every patient currently on a queue across ALL departments.

    Each row carries Q.No (queue_id), patient + payment scheme, the timestamp
    they joined, and the from→to "rooms" (departments): `to_department` is where
    they're waiting now, `from_department` is the stop they were routed in from
    (their most recent completed stop before this one, or null for a fresh
    arrival). Duration is derived client-side from `joined_at` so it can tick
    live. Ordered by acuity then wait time — sickest / longest-waiting first.
    """
    active = (
        db.query(PatientQueue, Patient)
        .join(Patient, PatientQueue.patient_id == Patient.patient_id)
        .filter(~PatientQueue.status.in_(TERMINAL_QUEUE_STATUSES))
        .order_by(PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc())
        .all()
    )
    patient_ids = {q.patient_id for q, _ in active}

    # Batch the "where did they come from" lookup: every completed stop for the
    # patients on the board, newest-first, grouped per patient.
    completed_by_patient: dict[int, list[PatientQueue]] = defaultdict(list)
    staff_ids: set[int] = {q.assigned_to for q, _ in active if q.assigned_to}
    if patient_ids:
        completed = (
            db.query(PatientQueue)
            .filter(
                PatientQueue.patient_id.in_(patient_ids),
                PatientQueue.status == "Completed",
                PatientQueue.completed_at.isnot(None),
            )
            .order_by(PatientQueue.completed_at.desc())
            .all()
        )
        for r in completed:
            completed_by_patient[r.patient_id].append(r)
    staff = (
        {u.user_id: u.full_name for u in db.query(User).filter(User.user_id.in_(staff_ids)).all()}
        if staff_ids else {}
    )

    result = []
    for q, p in active:
        # The stop they came from = most recent completed stop at/before this
        # one's joined_at.
        frm = None
        for r in completed_by_patient.get(p.patient_id, []):
            if r.completed_at and q.joined_at and r.completed_at <= q.joined_at:
                frm = r.department
                break
        result.append({
            "queue_id": q.queue_id,
            "patient_id": p.patient_id,
            "patient_name": f"{p.other_names} {p.surname}",
            "outpatient_no": p.outpatient_no,
            "scheme": _scheme_of(p),
            "from_department": frm,
            "to_department": q.department,
            "department": q.department,
            "acuity_level": q.acuity_level,
            "status": q.status,
            "joined_at": q.joined_at.isoformat() if q.joined_at else None,
            "assigned_to": staff.get(q.assigned_to),
        })
    return result


@router.get("/day", dependencies=[Depends(RequirePermission("patients:read"))])
def get_queue_day(
    date: Optional[str] = Query(None, description="Day to report, YYYY-MM-DD (defaults to today)"),
    from_ts: Optional[str] = Query(None, alias="from", description="ISO start of a custom window (overrides date)"),
    to_ts: Optional[str] = Query(None, alias="to", description="ISO end of a custom window (overrides date)"),
    db: Session = Depends(get_db),
):
    """Patients dealt with — and their movement footprints — for a given day.

    Groups every queue stop in the window by patient into an ordered trail:
    each stop is a room (department) with in/out times, the time spent, its
    status, and who handled it. `dealt_with` marks patients who completed at
    least one stop. A custom `from`/`to` window overrides `date` for a finer
    time-stretch.
    """
    # Resolve the reporting window.
    if from_ts or to_ts:
        try:
            start = datetime.fromisoformat(from_ts) if from_ts else datetime.now(timezone.utc) - timedelta(days=1)
            end = datetime.fromisoformat(to_ts) if to_ts else datetime.now(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="from/to must be ISO-8601 datetimes.")
    else:
        if date:
            try:
                d = date_cls.fromisoformat(date)
            except ValueError:
                raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")
        else:
            d = datetime.now(timezone.utc).date()
        start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)

    rows = (
        db.query(PatientQueue, Patient)
        .join(Patient, PatientQueue.patient_id == Patient.patient_id)
        .filter(PatientQueue.joined_at >= start, PatientQueue.joined_at < end)
        .order_by(Patient.patient_id.asc(), PatientQueue.joined_at.asc())
        .all()
    )

    staff_ids = {q.assigned_to for q, _ in rows if q.assigned_to}
    staff = (
        {u.user_id: u.full_name for u in db.query(User).filter(User.user_id.in_(staff_ids)).all()}
        if staff_ids else {}
    )
    now = datetime.now(timezone.utc)

    grouped: dict[int, dict] = {}
    for q, p in rows:
        g = grouped.get(p.patient_id)
        if g is None:
            g = grouped[p.patient_id] = {
                "patient_id": p.patient_id,
                "patient_name": f"{p.other_names} {p.surname}",
                "outpatient_no": p.outpatient_no,
                "scheme": _scheme_of(p),
                "footprint": [],
                "dealt_with": False,
                "still_active": False,
            }
        end_ts = q.completed_at or (now if q.status not in TERMINAL_QUEUE_STATUSES else None)
        duration = int((end_ts - q.joined_at).total_seconds()) if (end_ts and q.joined_at) else None
        g["footprint"].append({
            "queue_id": q.queue_id,
            "department": q.department,
            "status": q.status,
            "joined_at": q.joined_at.isoformat() if q.joined_at else None,
            "completed_at": q.completed_at.isoformat() if q.completed_at else None,
            "duration_seconds": duration,
            "handled_by": staff.get(q.assigned_to),
        })
        if q.status == "Completed":
            g["dealt_with"] = True
        if q.status in ACTIVE_QUEUE_STATUSES:
            g["still_active"] = True

    patients = list(grouped.values())
    for g in patients:
        fp = g["footprint"]
        g["stops"] = len(fp)
        g["departments"] = list(dict.fromkeys(s["department"] for s in fp))
        g["first_seen"] = fp[0]["joined_at"] if fp else None
        g["last_seen"] = (fp[-1]["completed_at"] or fp[-1]["joined_at"]) if fp else None

    # Sort: patients seen most recently first.
    patients.sort(key=lambda g: g["first_seen"] or "", reverse=True)
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "total_patients": len(patients),
        "dealt_with": sum(1 for g in patients if g["dealt_with"]),
        "still_active": sum(1 for g in patients if g["still_active"]),
        "patients": patients,
    }


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
