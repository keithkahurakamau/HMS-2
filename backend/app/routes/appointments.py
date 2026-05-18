from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.clinical import Appointment
from app.models.patient import Patient
from app.models.user import User, Role
from app.schemas.appointment import AppointmentCreate, AppointmentResponse
from app.utils.audit import log_audit


router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


VALID_STATUSES = {"Scheduled", "Confirmed", "Completed", "Cancelled", "No-Show"}

# How long a default appointment is treated as occupying for the collision
# check. Until the model carries a duration column, we treat every slot as
# this many minutes for the purposes of availability queries.
DEFAULT_SLOT_MINUTES = 30


@router.get("/doctors", dependencies=[Depends(RequirePermission("patients:write"))])
def list_doctors(db: Session = Depends(get_db)):
    """Active doctors available for booking.

    Pulled from the tenant ``users`` table by role name = 'Doctor'.
    Exposed under the appointments router so any user with patients:write
    (front desk + clinicians) can populate the booking form — without
    needing users:manage, which is gate-kept for admin features.
    """
    doctors = (
        db.query(User)
          .join(Role, User.role_id == Role.role_id)
          .filter(Role.name == "Doctor", User.is_active == True)
          .order_by(User.full_name.asc())
          .all()
    )
    return [
        {
            "user_id":         d.user_id,
            "full_name":       d.full_name,
            "specialization":  d.specialization,
        }
        for d in doctors
    ]


@router.get("/availability", dependencies=[Depends(RequirePermission("patients:write"))])
def get_doctor_availability(
    doctor_id: int = Query(..., description="Doctor whose calendar we're inspecting"),
    date: str = Query(..., description="ISO date (YYYY-MM-DD) to inspect"),
    db: Session = Depends(get_db),
):
    """Existing bookings for *doctor_id* on *date*.

    Returns just the time slots that are taken — the frontend computes the
    free slots locally from the clinic's working hours so different tenants
    can apply their own working-hour configuration without a round-trip.
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")

    start_of_day = datetime.combine(day, datetime.min.time())
    end_of_day   = start_of_day + timedelta(days=1)

    booked = (
        db.query(Appointment)
          .filter(
              Appointment.doctor_id == doctor_id,
              Appointment.appointment_date >= start_of_day,
              Appointment.appointment_date <  end_of_day,
              Appointment.status.in_(["Scheduled", "Confirmed"]),
          )
          .order_by(Appointment.appointment_date.asc())
          .all()
    )

    return {
        "doctor_id": doctor_id,
        "date": date,
        "slot_minutes": DEFAULT_SLOT_MINUTES,
        "bookings": [
            {
                "appointment_id": a.appointment_id,
                "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None,
                "patient_id": a.patient_id,
                "status": a.status,
            }
            for a in booked
        ],
    }


def _enrich(db: Session, appt: Appointment) -> dict:
    """Pull patient + doctor names so the calendar UI doesn't need extra round-trips."""
    patient = appt.patient
    doctor = appt.doctor
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
    # Doctor must exist, be active, and hold the Doctor role. Without this
    # check the form can book against an Admin, an inactive user, or a
    # nonexistent user_id (the FK constraint catches the last case but with
    # a less helpful 500).
    doctor = (
        db.query(User)
          .join(Role, User.role_id == Role.role_id)
          .filter(User.user_id == appt_in.doctor_id)
          .first()
    )
    if not doctor or not doctor.is_active:
        raise HTTPException(status_code=400, detail="Selected doctor is not available for booking.")
    if not doctor.role or doctor.role.name != "Doctor":
        raise HTTPException(status_code=400, detail="Appointments can only be booked against a Doctor role.")

    # Patient must exist.
    if not db.query(Patient).filter(Patient.patient_id == appt_in.patient_id).first():
        raise HTTPException(status_code=400, detail="Patient not found.")

    # Past-dated appointments are almost always operator error. Allow a small
    # tolerance so a slot that's "right now" doesn't get rejected by a
    # second-difference clock skew.
    appt_when = appt_in.appointment_date
    if appt_when.tzinfo is None:
        now = datetime.now()
    else:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    if appt_when < now - timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="Appointment date cannot be in the past.")

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
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    q = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor)
    )
    if doctor_id is not None:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if patient_id is not None:
        q = q.filter(Appointment.patient_id == patient_id)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status must be one of {sorted(VALID_STATUSES)}.")
        q = q.filter(Appointment.status == status)
    if date_from:
        q = q.filter(Appointment.appointment_date >= date_from)
    if date_to:
        q = q.filter(Appointment.appointment_date <= date_to)
    appointments = q.order_by(Appointment.appointment_date.asc()).offset(skip).limit(limit).all()
    return [_enrich(db, a) for a in appointments]


@router.get("/{appointment_id}", dependencies=[Depends(RequirePermission("patients:write"))])
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    appt = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor)
    ).filter(Appointment.appointment_id == appointment_id).first()
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
