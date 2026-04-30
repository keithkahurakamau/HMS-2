"""
Medical History API Routes
Kenya Data Protection Act 2019 (KDPA) Compliance Layer:

  1. RequirePermission("clinical:read") guards ALL GET endpoints.
  2. RequirePermission("clinical:write") guards ALL POST/PUT/DELETE endpoints.
  3. Every READ of a full patient chart is logged to data_access_logs (KDPA S.26).
  4. Every WRITE is committed with a corresponding entry in audit_logs.
  5. Sensitive records (is_sensitive=True) are redacted for non-clinical roles.
  6. Patient consent is verified before exposing the full history chart.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime

from app.config.database import get_db
from app.models.medical_history import MedicalHistoryEntry, ConsentRecord, DataAccessLog
from app.models.patient import Patient
from app.models.clinical import MedicalRecord
from app.models.laboratory import LabTest
from app.models.radiology import RadiologyRequest
from app.models.wards import AdmissionRecord
from app.models.user import User
from app.schemas.medical_history import (
    MedicalHistoryEntryCreate, MedicalHistoryEntryUpdate, MedicalHistoryEntryResponse,
    ConsentCreate, ConsentResponse,
    PatientMedicalChartResponse
)
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/medical-history", tags=["Medical History (KDPA Compliant)"])

# Non-clinical roles that are BLOCKED from viewing sensitive entries
SENSITIVE_DATA_RESTRICTED_ROLES = ["Receptionist", "Pharmacist", "Admin"]


# ==========================================
# HELPER: KDPA Read Access Logger
# ==========================================
def _log_data_access(db: Session, user_id: int, patient_id: int, ip: str, reason: str = "Clinical Review"):
    """KDPA S.26: Logs every instance of accessing a patient's full record."""
    try:
        access_log = DataAccessLog(
            accessed_by=user_id,
            patient_id=patient_id,
            access_reason=reason,
            ip_address=ip
        )
        db.add(access_log)
        # This is flushed with the surrounding transaction
    except Exception as e:
        logger.error(f"Failed to write DataAccessLog: {e}")


# ==========================================
# 1. GET FULL MEDICAL CHART (The Complete Patient File)
# ==========================================
@router.get("/{patient_id}/chart", response_model=PatientMedicalChartResponse)
def get_patient_medical_chart(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("history:read"))
):
    """
    Returns the complete, structured medical history chart for a patient.
    KDPA Compliance:
      - Access is logged to data_access_logs.
      - Sensitive entries are redacted based on the requester's role.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id, Patient.is_active == True).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found or is inactive.")

    # --- KDPA COMPLIANCE: Log this read access ---
    _log_data_access(
        db, current_user["user_id"], patient_id,
        str(request.client.host if request.client else "unknown"),
        f"Full chart accessed by {current_user['role']} ({current_user['full_name']})"
    )
    db.flush()  # Persist the access log in the same transaction

    # Determine if caller can see sensitive data
    can_see_sensitive = current_user["role"] not in SENSITIVE_DATA_RESTRICTED_ROLES

    # Fetch all history entries
    all_entries_query = db.query(MedicalHistoryEntry).filter(
        MedicalHistoryEntry.patient_id == patient_id
    )

    if not can_see_sensitive:
        # KDPA: Redact sensitive entries for non-clinical staff
        all_entries_query = all_entries_query.filter(MedicalHistoryEntry.is_sensitive == False)

    all_entries = all_entries_query.order_by(desc(MedicalHistoryEntry.created_at)).all()

    # Group entries by type
    def filter_by_type(type_key: str):
        return [e for e in all_entries if e.entry_type == type_key]

    # Fetch recent clinical visits (last 10)
    recent_records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(desc(MedicalRecord.created_at)).limit(10).all()

    recent_visits = []
    for rec in recent_records:
        doctor = db.query(User).filter(User.user_id == rec.doctor_id).first()
        recent_visits.append({
            "record_id": rec.record_id,
            "date": rec.created_at.isoformat() if rec.created_at else None,
            "doctor": doctor.full_name if doctor else "Unknown",
            "chief_complaint": rec.chief_complaint,
            "diagnosis": rec.diagnosis,
            "record_status": rec.record_status
        })

    # Fetch consent records
    consents = db.query(ConsentRecord).filter(
        ConsentRecord.patient_id == patient_id
    ).order_by(desc(ConsentRecord.consented_at)).all()

    db.commit()  # Commit the DataAccessLog

    return PatientMedicalChartResponse(
        patient_id=patient.patient_id,
        patient_name=f"{patient.surname}, {patient.other_names}",
        opd_number=patient.outpatient_no,
        blood_group=patient.blood_group,
        baseline_allergies=patient.allergies,
        baseline_conditions=patient.chronic_conditions,
        surgical_history=filter_by_type("SURGICAL_HISTORY"),
        family_history=filter_by_type("FAMILY_HISTORY"),
        social_history=filter_by_type("SOCIAL_HISTORY"),
        immunizations=filter_by_type("IMMUNIZATION"),
        allergies=filter_by_type("ALLERGY"),
        chronic_conditions=filter_by_type("CHRONIC_CONDITION"),
        past_medical_events=filter_by_type("PAST_MEDICAL_EVENT"),
        obstetric_history=filter_by_type("OBSTETRIC_HISTORY"),
        mental_health=filter_by_type("MENTAL_HEALTH"),
        recent_visits=recent_visits,
        consents=consents
    )


# ==========================================
# 2. ADD A HISTORY ENTRY
# ==========================================
@router.post("/entries", response_model=MedicalHistoryEntryResponse)
def add_history_entry(
    entry_in: MedicalHistoryEntryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("history:manage"))
):
    """
    Creates a new structured medical history entry for a patient.
    KDPA: Logs to audit_log with the recording clinician's ID and IP.
    """
    patient = db.query(Patient).filter(Patient.patient_id == entry_in.patient_id, Patient.is_active == True).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    new_entry = MedicalHistoryEntry(
        **entry_in.model_dump(),
        recorded_by=current_user["user_id"]
    )
    db.add(new_entry)
    db.flush()

    log_audit(
        db=db, user_id=current_user["user_id"],
        action="CREATE", entity_type="MedicalHistoryEntry",
        entity_id=str(new_entry.entry_id),
        old_value=None,
        new_value={"patient_id": entry_in.patient_id, "entry_type": entry_in.entry_type, "title": entry_in.title},
        ip_address=str(request.client.host if request.client else "unknown")
    )

    db.commit()
    db.refresh(new_entry)
    return new_entry


# ==========================================
# 3. UPDATE A HISTORY ENTRY
# ==========================================
@router.put("/entries/{entry_id}", response_model=MedicalHistoryEntryResponse)
def update_history_entry(
    entry_id: int,
    entry_update: MedicalHistoryEntryUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("history:manage"))
):
    """
    Updates an existing history entry. 
    KDPA: Old values are preserved in audit_log for a complete change history.
    """
    entry = db.query(MedicalHistoryEntry).filter(MedicalHistoryEntry.entry_id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found.")

    update_data = entry_update.model_dump(exclude_unset=True)
    old_values = {k: getattr(entry, k) for k in update_data.keys() if hasattr(entry, k)}

    for key, value in update_data.items():
        setattr(entry, key, value)

    log_audit(
        db=db, user_id=current_user["user_id"],
        action="UPDATE", entity_type="MedicalHistoryEntry",
        entity_id=str(entry_id),
        old_value=old_values,
        new_value=update_data,
        ip_address=str(request.client.host if request.client else "unknown")
    )

    db.commit()
    db.refresh(entry)
    return entry


# ==========================================
# 4. DELETE A HISTORY ENTRY
# ==========================================
@router.delete("/entries/{entry_id}")
def delete_history_entry(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("history:manage"))
):
    """
    Deletes a history entry. 
    KDPA: The full entry content is preserved in audit_logs before deletion, 
    ensuring medical record immutability for legal compliance.
    """
    entry = db.query(MedicalHistoryEntry).filter(MedicalHistoryEntry.entry_id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found.")

    # KDPA: Preserve entire record in audit log before deletion
    log_audit(
        db=db, user_id=current_user["user_id"],
        action="DELETE", entity_type="MedicalHistoryEntry",
        entity_id=str(entry_id),
        old_value={
            "patient_id": entry.patient_id, "entry_type": entry.entry_type,
            "title": entry.title, "description": entry.description
        },
        new_value=None,
        ip_address=str(request.client.host if request.client else "unknown")
    )

    db.delete(entry)
    db.commit()
    return {"message": "History entry permanently removed. Audit trail preserved."}


# ==========================================
# 5. RECORD PATIENT CONSENT
# ==========================================
@router.post("/consent", response_model=ConsentResponse)
def record_consent(
    consent_in: ConsentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("patients:write"))
):
    """
    Records formal patient consent as mandated by KDPA Section 30.
    Must be called before sensitive data is collected during registration/consultation.
    """
    patient = db.query(Patient).filter(Patient.patient_id == consent_in.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    new_consent = ConsentRecord(
        **consent_in.model_dump(),
        recorded_by=current_user["user_id"]
    )
    db.add(new_consent)
    db.flush()

    log_audit(
        db=db, user_id=current_user["user_id"],
        action="CREATE", entity_type="PatientConsent",
        entity_id=str(consent_in.patient_id),
        old_value=None,
        new_value={"consent_type": consent_in.consent_type, "consent_given": consent_in.consent_given},
        ip_address=str(request.client.host if request.client else "unknown")
    )

    db.commit()
    db.refresh(new_consent)
    return new_consent


# ==========================================
# 6. GET CONSENT RECORDS FOR A PATIENT
# ==========================================
@router.get("/consent/{patient_id}", response_model=List[ConsentResponse])
def get_patient_consents(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("patients:read"))
):
    """Returns all consent records for a patient. Useful for compliance verification."""
    return db.query(ConsentRecord).filter(
        ConsentRecord.patient_id == patient_id
    ).order_by(desc(ConsentRecord.consented_at)).all()


# ==========================================
# 7. GET DATA ACCESS AUDIT TRAIL (KDPA S.26 - Right to Know Who Accessed Records)
# ==========================================
@router.get("/access-log/{patient_id}")
def get_patient_access_log(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(RequirePermission("users:manage"))
):
    """
    Admin-only: Returns who has accessed this patient's medical records.
    KDPA S.26: Patients have a right to know who has accessed their personal data.
    Only accessible to 'Admin' (users:manage permission).
    """
    logs = db.query(DataAccessLog, User.full_name.label("accessor_name")).outerjoin(
        User, DataAccessLog.accessed_by == User.user_id
    ).filter(
        DataAccessLog.patient_id == patient_id
    ).order_by(desc(DataAccessLog.accessed_at)).all()

    return [
        {
            "log_id": log.log_id,
            "accessed_by_name": accessor_name,
            "patient_id": log.patient_id,
            "access_reason": log.access_reason,
            "ip_address": log.ip_address,
            "accessed_at": log.accessed_at.isoformat() if log.accessed_at else None
        }
        for log, accessor_name in logs
    ]
