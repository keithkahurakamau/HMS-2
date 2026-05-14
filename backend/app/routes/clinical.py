from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timezone

from app.config.database import get_db
from app.models.clinical import PatientQueue, MedicalRecord, Appointment
from app.models.patient import Patient
from app.models.user import User
from app.schemas.clinical import MedicalRecordCreate, MedicalRecordResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit
from app.utils.consent import require_active_consent

router = APIRouter(prefix="/api/clinical", tags=["Clinical Desk"])

# ==========================================
# 1. DOCTOR'S WORKSPACE & QUEUE
# ==========================================
@router.get("/queue")
def get_clinical_queue(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Fetches the active Consultation queue for the logged-in doctor.

    Returns rows that are either:
      * already assigned to this doctor (their personal worklist), or
      * unassigned (claimable — any doctor can pick them up).

    Filtering by ``department='Consultation'`` is intentional: patients
    routed from the front desk land in this department by name, and we
    don't want lab/pharmacy queue rows leaking into the clinical worklist.
    """
    from sqlalchemy import or_

    active_queue = db.query(
        PatientQueue.queue_id,
        PatientQueue.acuity_level,
        PatientQueue.status,
        PatientQueue.assigned_to,
        func.to_char(PatientQueue.joined_at, 'HH12:MI AM').label('triage_time'),
        Patient.patient_id,
        Patient.surname,
        Patient.other_names,
        Patient.outpatient_no,
        Patient.date_of_birth,
        Patient.sex,
        Patient.allergies
    ).join(
        Patient, PatientQueue.patient_id == Patient.patient_id
    ).filter(
        PatientQueue.status.in_(["Waiting", "In Progress", "In Consultation"]),
        PatientQueue.department == "Consultation",
        or_(
            PatientQueue.assigned_to == current_user["user_id"],
            PatientQueue.assigned_to.is_(None),
        ),
    ).order_by(PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc()).all()

    formatted_queue = []
    for q in active_queue:
        age = (datetime.now().date() - q.date_of_birth).days // 365 if q.date_of_birth else 0
        priority = "Normal"
        if q.acuity_level == 1: priority = "Critical"
        elif q.acuity_level == 2: priority = "High"

        formatted_queue.append({
            "queue_id": q.queue_id,
            "patient_id": q.patient_id,
            "outpatient_no": q.outpatient_no,
            "patient_name": f"{q.other_names} {q.surname}",
            "age": age,
            "gender": "M" if q.sex == "Male" else "F",
            "triage_time": q.triage_time,
            "status": q.status,
            "priority": priority,
            "allergies": q.allergies or "None",
            "assigned_to": q.assigned_to,
            "unclaimed": q.assigned_to is None,
        })

    return formatted_queue

# ==========================================
# 2. MEDICAL RECORD (SOAP) SUBMISSION
# ==========================================
@router.post("/submit", dependencies=[Depends(RequirePermission("clinical:write"))])
def submit_consultation(record_in: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Saves vitals, SOAP notes, and updates the patient's queue status."""
    try:
        # Extract queue_id as it doesn't belong in the MedicalRecord table
        queue_id = record_in.pop("queue_id", None)

        # KDPA S.30: cannot record clinical findings without active patient consent.
        patient_id = record_in.get("patient_id")
        if patient_id is not None:
            require_active_consent(db, patient_id, consent_type="Treatment")

        # Create the record using the remaining dictionary items
        new_record = MedicalRecord(**record_in, doctor_id=current_user["user_id"])
        db.add(new_record)
        db.flush() 

        # Handle Queue Status dynamically based on doctor's action.
        # An unclaimed row gets claimed here — by saving anything against
        # this queue entry the doctor is implicitly taking ownership, so
        # the row disappears from other doctors' queues and persists in
        # theirs.
        if queue_id:
            queue_entry = db.query(PatientQueue).filter(PatientQueue.queue_id == queue_id).first()
            if queue_entry:
                if queue_entry.assigned_to is None:
                    queue_entry.assigned_to = current_user["user_id"]
                if record_in.get("record_status") == "Draft":
                    queue_entry.status = "In Consultation"
                else:
                    # Billed, Pharmacy, or Completed removes them from the active waiting queue
                    queue_entry.status = "Completed"
                    queue_entry.completed_at = datetime.now(timezone.utc)

        # Log the action to the Immutable Audit Ledger
        log_audit(db, current_user["user_id"], "CREATE", "MedicalRecord", str(new_record.record_id), None, record_in, request.client.host)
        
        db.commit()
        return {"message": "Record saved successfully."}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save clinical record: {str(e)}")

# ==========================================
# 3. PATIENT HISTORY
# ==========================================
@router.get("/records/{patient_id}", response_model=List[MedicalRecordResponse], dependencies=[Depends(RequirePermission("patients:read"))])
def get_patient_history(patient_id: int, db: Session = Depends(get_db)):
    """Fetches all past medical records for a specific patient."""
    return db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(MedicalRecord.created_at.desc()).all()


# ==========================================
# 4. PHARMACY ROUTING
# ==========================================
@router.get("/prescriptions/pending")
def get_pending_prescriptions(db: Session = Depends(get_db)):
    """Fetches all Medical Records that have been routed to the Pharmacy."""
    
    pending_records = db.query(
        MedicalRecord.record_id,
        MedicalRecord.treatment_plan,
        MedicalRecord.created_at,
        Patient.patient_id,
        Patient.surname,
        Patient.other_names,
        Patient.outpatient_no,
        User.full_name.label("doctor_name"),
        Patient.allergies
    ).join(
        Patient, MedicalRecord.patient_id == Patient.patient_id
    ).join(
        User, MedicalRecord.doctor_id == User.user_id
    ).filter(
        MedicalRecord.record_status == "Pharmacy" # Only show records routed to Pharmacy
    ).all()

    formatted_prescriptions = []
    for r in pending_records:
        formatted_prescriptions.append({
            "id": f"RX-{r.record_id}", 
            "record_id": r.record_id,
            "patient_id": r.patient_id,
            "patient": f"{r.other_names} {r.surname}",
            "op_no": r.outpatient_no,
            "doctor": f"Dr. {r.doctor_name}",
            "time": r.created_at.strftime('%I:%M %p'),
            "priority": "Normal",
            "allergies": r.allergies,
            "prescriptions": [
                {
                    "drug": r.treatment_plan or "See Doctor Notes",
                    "dosage": "As prescribed",
                    "frequency": "As prescribed",
                    "duration": "As prescribed"
                }
            ]
        })

    return formatted_prescriptions


# ==========================================
# 5. RETURN PRESCRIPTION TO DOCTOR
# ==========================================
from pydantic import BaseModel as _BM


class ReturnPrescriptionRequest(_BM):
    reason: str


@router.post("/prescriptions/{record_id}/return", dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def return_prescription(
    record_id: int,
    payload: ReturnPrescriptionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Pharmacist sends a prescription back to the doctor for clarification."""
    record = db.query(MedicalRecord).filter(MedicalRecord.record_id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Prescription not found.")
    if record.record_status != "Pharmacy":
        raise HTTPException(status_code=400, detail="Only pharmacy-routed prescriptions can be returned.")

    record.record_status = "Returned"
    record.internal_notes = (record.internal_notes or "") + f"\nRETURNED BY PHARMACY ({datetime.now(timezone.utc).isoformat()}): {payload.reason}"

    log_audit(
        db, current_user["user_id"], "UPDATE", "MedicalRecord", str(record_id),
        {"record_status": "Pharmacy"}, {"record_status": "Returned", "reason": payload.reason},
        request.client.host if request.client else None,
    )
    db.commit()
    return {"message": "Prescription returned to doctor.", "record_id": record_id}


# ==========================================
# 6. VITALS TREND
# ==========================================
@router.get("/patients/{patient_id}/vitals-history", dependencies=[Depends(RequirePermission("clinical:read"))])
def get_vitals_history(
    patient_id: int,
    db: Session = Depends(get_db),
    limit: int = 20,
):
    """Past vitals readings, oldest first, suitable for plotting a trend line.

    Pulls from `medical_records` (every consultation captures vitals). Records
    where every vitals field is null are skipped — they're typically early
    drafts where the doctor hadn't filled them in yet.
    """
    records = (
        db.query(MedicalRecord)
        .filter(MedicalRecord.patient_id == patient_id)
        .order_by(MedicalRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    out = []
    for r in records:
        if all(v is None for v in (
            r.blood_pressure, r.heart_rate, r.respiratory_rate,
            r.temperature, r.spo2, r.weight_kg, r.height_cm,
        )):
            continue
        out.append({
            "record_id": r.record_id,
            "recorded_at": r.created_at.isoformat() if r.created_at else None,
            "blood_pressure": r.blood_pressure,
            "heart_rate": r.heart_rate,
            "respiratory_rate": r.respiratory_rate,
            "temperature": r.temperature,
            "spo2": r.spo2,
            "weight_kg": r.weight_kg,
            "height_cm": r.height_cm,
            "bmi": r.calculated_bmi,
        })

    # Reverse to oldest-first so the UI can plot left-to-right naturally.
    out.reverse()
    return out