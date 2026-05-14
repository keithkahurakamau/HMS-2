from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from pydantic import BaseModel
from typing import List
from datetime import datetime

from app.config.database import get_db
from app.models.patient import Patient
from app.models.clinical import MedicalRecord, Appointment, PatientQueue
from app.models.laboratory import LabTest
from app.core.dependencies import get_current_user, RequirePermission
from app.core.limiter import limiter
from app.core import cache
from app.utils.audit import log_audit
from app.models.billing import Invoice, InvoiceItem

# Cache prefixes for entries this router writes to. Mutations clear the
# relevant tenant's dashboard rollups so the next read recomputes.
_ANALYTICS_DASHBOARD = "analytics:dashboard"


def _bust_dashboard(request: Request) -> None:
    tenant = request.headers.get("X-Tenant-ID") if request else None
    cache.invalidate_prefix(_ANALYTICS_DASHBOARD, tenant=tenant)

router = APIRouter(prefix="/api/patients", tags=["Patient Registry"])

def generate_op_number(db: Session) -> str:
    """Generates a sequential Outpatient Number like OP-2026-0045"""
    current_year = datetime.now().year
    prefix = f"OP-{current_year}-"
    
    latest_patient = db.query(Patient).filter(
        Patient.outpatient_no.like(f"{prefix}%")
    ).order_by(desc(Patient.patient_id)).first()

    if latest_patient:
        last_number = int(latest_patient.outpatient_no.split("-")[-1])
        new_number = last_number + 1
    else:
        new_number = 1

    return f"{prefix}{new_number:04d}"

# ==========================================
# 1. SEARCH & LIST PATIENTS
# ==========================================
@router.get("/", dependencies=[Depends(RequirePermission("patients:read"))])
@limiter.limit("60/minute")
def get_patients(request: Request, search: str = Query("", description="Search by name, ID, OP number, or phone"), skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Patient).filter(Patient.is_active == True) 
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Patient.outpatient_no.ilike(search_term),
                Patient.surname.ilike(search_term),
                Patient.other_names.ilike(search_term),
                Patient.id_number.ilike(search_term),
                Patient.telephone_1.ilike(search_term)
            )
        )
    return query.order_by(desc(Patient.registered_on)).offset(skip).limit(limit).all()

# ==========================================
# 2. GET PATIENT BY ID
# ==========================================
@router.get("/{patient_id}", dependencies=[Depends(RequirePermission("patients:read"))])
def get_patient_by_id(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

# ==========================================
# 3. REGISTER NEW PATIENT
# ==========================================
@router.post("/", dependencies=[Depends(RequirePermission("patients:write"))])
def register_patient(patient_data: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        # Collapse "" → None for fields that have unique indexes (or are
        # indexed and compared by ==) so two blank submissions don't collide.
        # Same defensive pattern as the users.license_number fix.
        for k in ("id_number", "telephone_2", "email", "reference_number"):
            if isinstance(patient_data.get(k), str) and not patient_data[k].strip():
                patient_data[k] = None

        existing_patient = db.query(Patient).filter(
            or_(
                Patient.telephone_1 == patient_data.get("telephone_1"),
                (Patient.id_number == patient_data.get("id_number")) & (Patient.id_number.isnot(None))
            )
        ).first()
        
        if existing_patient:
            raise HTTPException(status_code=400, detail="A patient with this Phone Number or ID already exists.")

        op_number = generate_op_number(db)
        
        new_patient = Patient(
            outpatient_no=op_number,
            surname=patient_data.get("surname"),
            other_names=patient_data.get("other_names"),
            sex=patient_data.get("sex"),
            date_of_birth=patient_data.get("date_of_birth"),
            marital_status=patient_data.get("marital_status"),
            religion=patient_data.get("religion"),
            primary_language=patient_data.get("primary_language"),
            blood_group=patient_data.get("blood_group"),
            allergies=patient_data.get("allergies"),
            chronic_conditions=patient_data.get("chronic_conditions"),
            id_type=patient_data.get("id_type"),
            id_number=patient_data.get("id_number"),
            nationality=patient_data.get("nationality"),
            telephone_1=patient_data.get("telephone_1"),
            telephone_2=patient_data.get("telephone_2"),
            email=patient_data.get("email"),
            postal_address=patient_data.get("postal_address"),
            postal_code=patient_data.get("postal_code"),
            residence=patient_data.get("residence"),
            town=patient_data.get("town"),
            occupation=patient_data.get("occupation"),
            employer_name=patient_data.get("employer_name"),
            reference_number=patient_data.get("reference_number"),
            nok_name=patient_data.get("nok_name"),
            nok_relationship=patient_data.get("nok_relationship"),
            nok_contact=patient_data.get("nok_contact"),
            notes=patient_data.get("notes"),
            registered_by=current_user["user_id"]
        )
        
        db.add(new_patient)
        db.flush()
        
        log_audit(
            db=db, user_id=current_user["user_id"], action="CREATE", 
            entity_type="Patient", entity_id=op_number, 
            old_value=None, new_value={"name": f"{new_patient.other_names} {new_patient.surname}"}, 
            ip_address=request.client.host
        )
        
        db.commit()
        db.refresh(new_patient)
        _bust_dashboard(request)
        return new_patient

    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"Failed to register patient: {str(e)}")

# ==========================================
# 4. UPDATE PATIENT
# ==========================================
@router.put("/{patient_id}", dependencies=[Depends(RequirePermission("patients:write"))])
def update_patient(patient_id: int, patient_data: dict, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    old_data = {key: getattr(patient, key) for key in patient_data.keys() if hasattr(patient, key)}
    
    for key, value in patient_data.items():
        if hasattr(patient, key):
            setattr(patient, key, value)
            
    log_audit(
        db=db, user_id=current_user["user_id"], action="UPDATE", 
        entity_type="Patient", entity_id=str(patient.patient_id), 
        old_value=old_data, new_value=patient_data, 
        ip_address=request.client.host
    )
    db.commit()
    db.refresh(patient)
    return patient

# ==========================================
# 5. DEACTIVATE (SOFT DELETE) PATIENT
# ==========================================
@router.delete("/{patient_id}", dependencies=[Depends(RequirePermission("patients:write"))])
def delete_patient(patient_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    patient.is_active = False

    log_audit(
        db=db, user_id=current_user["user_id"], action="DELETE",
        entity_type="Patient", entity_id=str(patient.patient_id),
        old_value={"is_active": True}, new_value={"is_active": False},
        ip_address=request.client.host
    )
    db.commit()
    _bust_dashboard(request)
    return {"message": "Patient successfully deactivated."}

# ==========================================
# 6. GET COMPREHENSIVE HISTORY
# ==========================================
@router.get("/{patient_id}/history", dependencies=[Depends(RequirePermission("patients:read"))])
def get_patient_history(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    records = db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).all()
    labs = db.query(LabTest).filter(LabTest.patient_id == patient_id).all()
    appointments = db.query(Appointment).filter(Appointment.patient_id == patient_id).all()

    return {
        "demographics": {
            "name": f"{patient.surname}, {patient.other_names}",
            "opd": patient.outpatient_no,
            "blood_group": patient.blood_group or "Unknown",
            "allergies": patient.allergies or "None recorded",
            "chronic_conditions": patient.chronic_conditions or "None recorded"
        },
        "clinical_records": records,
        "lab_tests": labs,
        "appointments": appointments
    }


# ==========================================
# 6b. ACTIVE PATIENT NAVIGATION ACCESS LOG
# ==========================================
class AccessLogPayload(BaseModel):
    """Lightweight body the frontend posts when the active patient bar
    follows a user across modules. Both fields are optional — the endpoint
    falls back to defaults if the UI doesn't supply them."""
    module: str | None = None  # e.g. "Clinical Desk", "Pharmacy", "Laboratory"
    reason: str | None = None  # operator-supplied free-text reason


@router.post("/{patient_id}/access", dependencies=[Depends(RequirePermission("patients:read"))])
def log_patient_access(
    patient_id: int,
    payload: AccessLogPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Record that the current user navigated to a module while a patient
    was the active context. Underpins the KDPA S.26 audit trail for who
    looked at whose records and when — even when the navigation didn't
    open the full chart.

    This is a cheap, high-frequency endpoint. We do NOT validate the
    patient exists with a SELECT here (one extra round-trip per nav is too
    chatty); the FK constraint on data_access_logs.patient_id will reject
    a bad id without spending application time.
    """
    from app.models.medical_history import DataAccessLog

    reason = (payload.module or payload.reason or "Active patient navigation")[:255]
    log = DataAccessLog(
        accessed_by=current_user["user_id"],
        patient_id=patient_id,
        access_reason=reason,
        ip_address=(request.client.host if request.client else None),
    )
    db.add(log)
    db.commit()
    return {"ok": True}

# ==========================================
# 7. ROUTE PATIENT TO QUEUE
# ==========================================
# Canonical department names used by analytics rollups (analytics.py),
# per-module queue endpoints (clinical/queue, laboratory/queue, etc.) and the
# Command Center breakdown. Anything outside this set is silently ignored by
# downstream consumers — a patient routed to "Clinical Desk" never shows up
# on the Command Center because the analytics filter looks for
# "Consultation". The map below normalises the friendly UI labels the front
# desk picks from to the canonical names. Adding a new module? Extend this
# map AND wire it through analytics.py + the per-module queue endpoint.
_DEPARTMENT_ALIASES = {
    # UI label → canonical name used everywhere else
    "clinical desk":      "Consultation",
    "clinical":           "Consultation",
    "consultation":       "Consultation",
    "triage":             "Triage",
    "laboratory":         "Laboratory",
    "lab":                "Laboratory",
    "radiology":          "Radiology",
    "imaging":            "Radiology",
    "pharmacy":           "Pharmacy",
    "billing":            "Billing",
    "cashier":            "Billing",
    "wards":              "Wards",
    "ward":               "Wards",
    "admissions":         "Wards",
}
CANONICAL_DEPARTMENTS = frozenset({
    "Triage", "Consultation", "Laboratory", "Radiology",
    "Pharmacy", "Billing", "Wards",
})


def _canonical_department(label: str) -> str:
    """Resolve a UI department label to its canonical name. Raises 400 when
    the caller picks something not in the catalogue."""
    if not label:
        raise HTTPException(status_code=400, detail="Department is required.")
    key = label.strip().lower()
    resolved = _DEPARTMENT_ALIASES.get(key)
    if resolved is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown department '{label}'. Allowed: "
                f"{', '.join(sorted(CANONICAL_DEPARTMENTS))}."
            ),
        )
    return resolved


class QueueRequest(BaseModel):
    department: str
    acuity_level: int = 3
    # When set, the patient is assigned directly to this specific staff
    # member. Otherwise the row lands in the unclaimed pool and the first
    # available clinician picks it up. The latter is the legacy behaviour.
    assigned_to: int | None = None


@router.get("/staff", dependencies=[Depends(RequirePermission("patients:write"))])
def list_staff_by_role(role: str = "", db: Session = Depends(get_db)):
    """Active staff members filtered by role name.

    Used by the front-desk routing picker so the receptionist can pick
    *which* doctor / lab tech / radiologist the patient should land with.
    Empty role returns every active user.

    Available with patients:write so receptionists and clinical staff can
    populate the picker without needing users:manage.
    """
    from app.models.user import User, Role
    q = (
        db.query(User)
          .join(Role, User.role_id == Role.role_id)
          .filter(User.is_active == True)
    )
    if role:
        q = q.filter(Role.name == role)
    rows = q.order_by(User.full_name.asc()).all()
    return [
        {
            "user_id":        u.user_id,
            "full_name":      u.full_name,
            "role":           u.role.name if u.role else None,
            "specialization": getattr(u, "specialization", None),
        }
        for u in rows
    ]


@router.post("/{patient_id}/route", dependencies=[Depends(RequirePermission("patients:write"))])
def route_patient(patient_id: int, request: QueueRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Route a registered patient onto a departmental queue.

    The frontend exposes friendly labels (e.g. "Clinical Desk"); we resolve
    them to the canonical name before persisting so analytics rollups and
    per-module queue pages line up.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    department = _canonical_department(request.department)
    acuity = max(1, min(5, int(request.acuity_level or 3)))

    # Idempotency: don't let a double-click create two waiting rows in the
    # same department. If one exists, return the existing queue_id so the
    # caller can navigate to it instead of erroring.
    existing = db.query(PatientQueue).filter(
        PatientQueue.patient_id == patient_id,
        PatientQueue.department == department,
        PatientQueue.status.in_(["Waiting", "In Progress", "In Consultation"]),
    ).first()

    if existing:
        return {
            "message": f"Patient is already active in the {existing.department} queue.",
            "queue_id": existing.queue_id,
            "department": existing.department,
            "status": existing.status,
            "already_queued": True,
        }

    # Validate the picked staff member exists + is active. We only check
    # presence (not role-vs-department fit) so the receptionist can route
    # to an unusual specialist when clinically appropriate.
    assigned_to = None
    if request.assigned_to is not None:
        from app.models.user import User
        candidate = db.query(User).filter(
            User.user_id == request.assigned_to,
            User.is_active == True,
        ).first()
        if not candidate:
            raise HTTPException(status_code=400, detail="Selected staff member not found or inactive.")
        assigned_to = candidate.user_id

    new_queue = PatientQueue(
        patient_id=patient_id,
        department=department,
        acuity_level=acuity,
        status="Waiting",
        assigned_to=assigned_to,
    )
    db.add(new_queue)
    db.commit()
    db.refresh(new_queue)

    log_audit(
        db=db, user_id=current_user["user_id"], action="ROUTE",
        entity_type="PatientQueue", entity_id=str(new_queue.queue_id),
        old_value=None,
        new_value={
            "patient_id": patient_id,
            "department": department,
            "acuity_level": acuity,
            "assigned_to": assigned_to,
        },
        ip_address=None,
    )
    db.commit()

    # Cache invalidation — the dashboard waiting count changes when a new
    # patient lands on a queue.
    cache.invalidate_prefix(_ANALYTICS_DASHBOARD, tenant=None)

    return {
        "message": f"Patient successfully routed to {department}.",
        "queue_id": new_queue.queue_id,
        "department": department,
        "status": new_queue.status,
        "already_queued": False,
    }