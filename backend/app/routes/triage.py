from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from typing import Optional

from app.config.database import get_db
from app.models.clinical import PatientQueue, TriageRecord
from app.models.patient import Patient
from app.schemas.triage import TriageCreate, TriageResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit
from app.routes.patients import _canonical_department

router = APIRouter(prefix="/api/triage", tags=["Triage"])


def _clamp_acuity(value: Optional[int]) -> int:
    """Acuity is a 1–5 scale (1=Emergency). Clamp defensively so a stray UI
    value never sorts a patient out of the queue ordering."""
    try:
        return max(1, min(5, int(value if value is not None else 3)))
    except (TypeError, ValueError):
        return 3


# ==========================================
# 1. TRIAGE QUEUE (Nurse worklist)
# ==========================================
@router.get("/queue", dependencies=[Depends(RequirePermission("triage:read"))])
def get_triage_queue(db: Session = Depends(get_db)):
    """Patients waiting to be triaged.

    These are queue rows the front desk routed to ``department='Triage'`` and
    that haven't been worked yet. Ordered by acuity then arrival so the nurse
    works the most urgent walk-ins first.
    """
    rows = db.query(
        PatientQueue.queue_id,
        PatientQueue.acuity_level,
        PatientQueue.status,
        func.to_char(PatientQueue.joined_at, 'HH12:MI AM').label('joined_time'),
        Patient.patient_id,
        Patient.surname,
        Patient.other_names,
        Patient.outpatient_no,
        Patient.date_of_birth,
        Patient.sex,
        Patient.allergies,
    ).join(
        Patient, PatientQueue.patient_id == Patient.patient_id
    ).filter(
        PatientQueue.department == "Triage",
        PatientQueue.status.in_(["Waiting", "In Progress"]),
    ).order_by(
        PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc()
    ).all()

    out = []
    for q in rows:
        age = (datetime.now().date() - q.date_of_birth).days // 365 if q.date_of_birth else 0
        out.append({
            "queue_id": q.queue_id,
            "patient_id": q.patient_id,
            "outpatient_no": q.outpatient_no,
            "patient_name": f"{q.other_names} {q.surname}",
            "age": age,
            "gender": "M" if q.sex == "Male" else "F",
            "joined_time": q.joined_time,
            "status": q.status,
            "allergies": q.allergies or "None",
        })
    return out


# ==========================================
# 2. SUBMIT TRIAGE (record vitals + route on)
# ==========================================
@router.post("/submit", dependencies=[Depends(RequirePermission("triage:write"))])
def submit_triage(
    payload: TriageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Nurse records triage vitals, closes the Triage queue row, and re-queues
    the patient into their disposition department (default: the doctor's
    Consultation queue) carrying the nurse-assessed acuity.

    The whole point: the Clinical Desk reads the latest triage row back for
    this patient and prefills vitals, so the doctor never re-keys them.
    """
    try:
        data = payload.model_dump()
        queue_id = data.pop("queue_id", None)
        disposition = _canonical_department(data.get("disposition") or "Consultation")
        data["disposition"] = disposition
        data["acuity_level"] = _clamp_acuity(data.get("acuity_level"))

        patient = db.query(Patient).filter(Patient.patient_id == data["patient_id"]).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found.")

        # Derive BMI server-side if the nurse gave weight + height but the UI
        # didn't compute it — keeps the stored value trustworthy.
        if data.get("calculated_bmi") is None and data.get("weight_kg") and data.get("height_cm"):
            h = float(data["height_cm"]) / 100.0
            if h > 0:
                data["calculated_bmi"] = round(float(data["weight_kg"]) / (h * h), 1)

        record = TriageRecord(**data, nurse_id=current_user["user_id"])
        db.add(record)
        db.flush()

        # Close out the Triage queue row this assessment belongs to.
        if queue_id:
            triage_entry = db.query(PatientQueue).filter(PatientQueue.queue_id == queue_id).first()
            if triage_entry and triage_entry.department == "Triage":
                triage_entry.status = "Completed"
                triage_entry.completed_at = datetime.now(timezone.utc)
                triage_entry.acuity_level = data["acuity_level"]

        # Route the patient onward. Don't double-queue: if they're already
        # active in the disposition department, just refresh that row's acuity
        # so the nurse's assessment still takes effect on the doctor's sort.
        existing = db.query(PatientQueue).filter(
            PatientQueue.patient_id == patient.patient_id,
            PatientQueue.department == disposition,
            PatientQueue.status.in_(["Waiting", "In Progress", "In Consultation"]),
        ).first()
        if existing:
            existing.acuity_level = data["acuity_level"]
            next_queue_id = existing.queue_id
        else:
            next_queue = PatientQueue(
                patient_id=patient.patient_id,
                department=disposition,
                acuity_level=data["acuity_level"],
                status="Waiting",
                notes=data.get("chief_complaint"),
            )
            db.add(next_queue)
            db.flush()
            next_queue_id = next_queue.queue_id

        log_audit(
            db, current_user["user_id"], "CREATE", "TriageRecord", str(record.triage_id),
            None, data, request.client.host if request.client else None,
        )
        db.commit()
        db.refresh(record)
        return {
            "message": f"Triage saved. Patient routed to {disposition}.",
            "triage_id": record.triage_id,
            "queue_id": next_queue_id,
            "disposition": disposition,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save triage: {str(e)}")


# ==========================================
# 3. LATEST TRIAGE (Clinical Desk prefill)
# ==========================================
@router.get(
    "/patients/{patient_id}/latest",
    response_model=Optional[TriageResponse],
    dependencies=[Depends(RequirePermission("triage:read"))],
)
def get_latest_triage(patient_id: int, db: Session = Depends(get_db)):
    """Most recent triage row for a patient, or null if never triaged.

    The Clinical Desk calls this on patient-select to prefill vitals.
    """
    return (
        db.query(TriageRecord)
        .filter(TriageRecord.patient_id == patient_id)
        .order_by(TriageRecord.created_at.desc())
        .first()
    )
