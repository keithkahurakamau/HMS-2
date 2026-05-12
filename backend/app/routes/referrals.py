"""External / specialist referral endpoints.

Doctors create referrals from the Clinical Desk. Receiving facilities update
status as the referral progresses (Sent → Accepted → Completed).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.patient import Patient
from app.models.referral import Referral
from app.models.user import User
from app.utils.audit import log_audit


router = APIRouter(prefix="/api/referrals", tags=["Referrals"])


VALID_URGENCY = {"Routine", "Urgent", "Emergency"}
VALID_STATUS = {"Pending", "Sent", "Accepted", "Completed", "Cancelled"}


class ReferralCreate(BaseModel):
    patient_id: int
    record_id: Optional[int] = None
    specialty: str = Field(..., min_length=1, max_length=120)
    target_facility: Optional[str] = Field(default=None, max_length=255)
    target_clinician: Optional[str] = Field(default=None, max_length=255)
    reason: str = Field(..., min_length=1)
    clinical_summary: Optional[str] = None
    urgency: str = "Routine"


class ReferralStatusUpdate(BaseModel):
    status: str


def _serialize(db: Session, r: Referral) -> dict:
    patient = db.query(Patient).filter(Patient.patient_id == r.patient_id).first()
    doctor = db.query(User).filter(User.user_id == r.referred_by).first() if r.referred_by else None
    return {
        "referral_id": r.referral_id,
        "patient_id": r.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "patient_opd": patient.outpatient_no if patient else None,
        "referred_by": r.referred_by,
        "doctor_name": doctor.full_name if doctor else None,
        "record_id": r.record_id,
        "specialty": r.specialty,
        "target_facility": r.target_facility,
        "target_clinician": r.target_clinician,
        "reason": r.reason,
        "clinical_summary": r.clinical_summary,
        "urgency": r.urgency,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.post("/", dependencies=[Depends(RequirePermission("referrals:manage"))])
def create_referral(
    payload: ReferralCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if payload.urgency not in VALID_URGENCY:
        raise HTTPException(status_code=400, detail=f"urgency must be one of {sorted(VALID_URGENCY)}")
    if not db.query(Patient).filter(Patient.patient_id == payload.patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found.")

    referral = Referral(
        patient_id=payload.patient_id,
        referred_by=current_user["user_id"],
        record_id=payload.record_id,
        specialty=payload.specialty.strip(),
        target_facility=payload.target_facility,
        target_clinician=payload.target_clinician,
        reason=payload.reason.strip(),
        clinical_summary=payload.clinical_summary,
        urgency=payload.urgency,
        status="Pending",
    )
    db.add(referral)
    db.flush()

    log_audit(
        db, current_user["user_id"], "CREATE", "Referral", str(referral.referral_id),
        None, {"specialty": referral.specialty, "urgency": referral.urgency},
        request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(referral)
    return _serialize(db, referral)


@router.get("/", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_referrals(
    db: Session = Depends(get_db),
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    q = db.query(Referral)
    if patient_id is not None:
        q = q.filter(Referral.patient_id == patient_id)
    if status:
        q = q.filter(Referral.status == status)
    rows = q.order_by(Referral.created_at.desc()).limit(limit).all()
    return [_serialize(db, r) for r in rows]


@router.patch("/{referral_id}/status", dependencies=[Depends(RequirePermission("referrals:manage"))])
def update_referral_status(
    referral_id: int,
    payload: ReferralStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if payload.status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUS)}")
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")

    old = referral.status
    referral.status = payload.status

    log_audit(
        db, current_user["user_id"], "UPDATE", "Referral", str(referral_id),
        {"status": old}, {"status": payload.status},
        request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(referral)
    return _serialize(db, referral)
