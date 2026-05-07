from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.clinical import Appointment
from app.models.patient import Patient
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentResponse
from app.utils.audit import log_audit


router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


VALID_STATUSES = {"Scheduled", "Confirmed", "Completed", "Cancelled", "No-Show"}


def _enrich(db: Session, appt: Appointment) -> dict:
    """Pull patient + doctor names so the calendar UI doesn't need extra round-trips."""
    patient = db.query(Patient).filter(Patient.patient_id == appt.patient_id).first()
    doctor = db.query(User).filter(User.user_id == appt.doctor_id).first()
    return {
        "appointment_id": appt.appointment_id,
        "patient_id": appt.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else "Unknown",
        "patient_opd": patient.outpatient_no if patient else None,
        "doctor_id": appt.doctor_id,
        "doctor_name": doctor.full_name if doctor else "Unknown",
        "appointment_date": appt.appointment_date.isoformat() if appt.appointment_date else None,
        "status": appt.status,
        "notes": appt.notes,
        "created_at": appt.created_at.isoformat() if appt.created_at else None,
    }


@router.post("/", dependencies=[Depends(RequirePermission("patients:write"))])
def create_appointment(
    appt_in: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Conflict check: doctor cannot have two appointments scheduled at the same minute.
    conflict = db.query(Appointment).filter(
        Appointment.doctor_id == appt_in.doctor_id,
        Appointment.appointment_date == appt_in.appointment_date,
        Appointment.status.in_(["Scheduled", "Confirmed"]),
    ).first()
    if conflict:
        raise HTTPException(status_code=409, detail="The doctor already has an appointment in this slot.")

    new_appt = Appointment(**appt_in.model_dump())
    db.add(new_appt)
    db.flush()

    log_audit(
        db, current_user["user_id"], "CREATE", "Appointment", str(new_appt.appointment_id),
        None, appt_in.model_dump(mode="json"),
        request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(new_appt)
    return _enrich(db, new_appt)


@router.get("/", dependencies=[Depends(RequirePermission("patients:write"))])
def list_appointments(
    db: Session = Depends(get_db),
    doctor_id: Optional[int] = Query(None),
    patient_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    q = db.query(Appointment)
    if doctor_id is not None:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if patient_id is not None:
        q = q.filter(Appointment.patient_id == patient_id)
    if status:
        q = q.filter(Appointment.status == status)
    if date_from:
        q = q.filter(Appointment.appointment_date >= date_from)
    if date_to:
        q = q.filter(Appointment.appointment_date <= date_to)
    appointments = q.order_by(Appointment.appointment_date.asc()).all()
    return [_enrich(db, a) for a in appointments]


@router.get("/{appointment_id}", dependencies=[Depends(RequirePermission("patients:write"))])
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return _enrich(db, appt)


class AppointmentStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


@router.patch("/{appointment_id}/status", dependencies=[Depends(RequirePermission("patients:write"))])
def update_status(
    appointment_id: int,
    payload: AppointmentStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {sorted(VALID_STATUSES)}.")

    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    old = {"status": appt.status, "notes": appt.notes}
    appt.status = payload.status
    if payload.notes is not None:
        appt.notes = payload.notes

    log_audit(
        db, current_user["user_id"], "UPDATE", "Appointment", str(appointment_id),
        old, {"status": payload.status, "notes": payload.notes},
        request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(appt)
    return _enrich(db, appt)


@router.delete("/{appointment_id}", dependencies=[Depends(RequirePermission("patients:write"))])
def cancel_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Soft-cancel: status flipped to Cancelled. Hard-deleting clinical records is forbidden."""
    appt = db.query(Appointment).filter(Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    old_status = appt.status
    appt.status = "Cancelled"
    log_audit(
        db, current_user["user_id"], "UPDATE", "Appointment", str(appointment_id),
        {"status": old_status}, {"status": "Cancelled"},
        request.client.host if request.client else None,
    )
    db.commit()
    return {"message": "Appointment cancelled."}
