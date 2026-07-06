import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config.database import get_db
from app.models.clinical import MedicalRecord
from app.models.user import User
from app.models.laboratory import LabTest
from app.models.radiology import RadiologyRequest
from app.core.dependencies import get_current_user, RequirePermission
from app.routes.clinical import _parse_prescriptions

router = APIRouter(prefix="/api/clinical", tags=["Clinical Desk"])


@router.get("/record/{record_id}", dependencies=[Depends(RequirePermission("history:read"))])
def get_visit_detail(record_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Full detail for one clinical visit — everything the doctor did.

    Backs the expandable rows in the Medical History visit list. Access is
    KDPA-logged like the chart itself; internal notes are withheld from
    non-clinical roles.
    """
    from app.routes.medical_history import SENSITIVE_DATA_RESTRICTED_ROLES, _log_data_access

    rec = db.query(MedicalRecord).filter(MedicalRecord.record_id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Medical record not found.")

    _log_data_access(
        db, current_user["user_id"], rec.patient_id,
        str(request.client.host if request.client else "unknown"),
        f"Visit detail #{record_id} accessed by {current_user['role']} ({current_user['full_name']})",
    )

    doctor = db.query(User).filter(User.user_id == rec.doctor_id).first()

    labs = db.query(LabTest).filter(LabTest.record_id == record_id).all()

    # RadiologyRequest has no record FK — best-effort match: same patient,
    # same calendar day as the visit.
    rads = []
    if rec.created_at is not None:
        rads = db.query(RadiologyRequest).filter(
            RadiologyRequest.patient_id == rec.patient_id,
            func.date(RadiologyRequest.created_at) == rec.created_at.date(),
        ).all()

    # Legacy records store display strings in icd10_code (e.g.
    # "J20.9 - Acute bronchitis" or "Type 2 diabetes mellitus, unspecified" —
    # note the comma). A naive comma-split on those makes garbage chips, so
    # only treat the value as a modern comma-separated code list when every
    # comma-split part actually looks like an ICD-10 code (letter + digit).
    # Otherwise keep the whole legacy string as a single entry.
    raw = (rec.icd10_code or "").strip()
    parts = [c.strip() for c in raw.split(",") if c.strip()]
    if parts and all(re.match(r"^[A-Z]\d", p) for p in parts):
        codes = parts          # modern comma-separated code list
    elif raw:
        codes = [raw]          # legacy display string — keep whole as one entry
    else:
        codes = []

    detail = {
        "record_id": rec.record_id,
        "date": rec.created_at.isoformat() if rec.created_at else None,
        "doctor": doctor.full_name if doctor else "Unknown",
        "record_status": rec.record_status,
        "vitals": {
            "blood_pressure": rec.blood_pressure,
            "heart_rate": rec.heart_rate,
            "respiratory_rate": rec.respiratory_rate,
            "temperature": rec.temperature,
            "spo2": rec.spo2,
            "weight_kg": rec.weight_kg,
            "height_cm": rec.height_cm,
            "calculated_bmi": rec.calculated_bmi,
            "blood_glucose": rec.blood_glucose,
        },
        "chief_complaint": rec.chief_complaint,
        "history_of_present_illness": rec.history_of_present_illness,
        "review_of_systems": rec.review_of_systems,
        "physical_examination": rec.physical_examination,
        "icd10_codes": codes,
        "diagnosis": rec.diagnosis,
        "prescriptions": _parse_prescriptions(rec.treatment_plan) if rec.treatment_plan else [],
        "prescription_notes": rec.prescription_notes,
        "follow_up_date": rec.follow_up_date.isoformat() if rec.follow_up_date else None,
        "lab_tests": [
            {"test_id": t.test_id, "test_name": t.test_name, "status": t.status,
             "result_summary": t.result_summary}
            for t in labs
        ],
        "radiology": [
            {"request_id": r.request_id, "exam_type": r.exam_type, "status": r.status,
             "conclusion": r.result.conclusion if r.result else None}
            for r in rads
        ],
    }
    if current_user["role"] not in SENSITIVE_DATA_RESTRICTED_ROLES:
        detail["internal_notes"] = rec.internal_notes

    db.commit()  # persist the data-access log row
    return detail
