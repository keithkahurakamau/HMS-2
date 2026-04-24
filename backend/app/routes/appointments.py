from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List

from app.config.database import get_db
from app.models.clinical import Appointment
from app.schemas.appointment import AppointmentCreate, AppointmentResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])

@router.post("/", response_model=AppointmentResponse, dependencies=[Depends(RequirePermission("appointments:manage"))])
def create_appointment(appt_in: AppointmentCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_appt = Appointment(**appt_in.model_dump())
    db.add(new_appt)
    db.flush()

    log_audit(db, current_user["user_id"], "CREATE", "Appointment", new_appt.appointment_id, None, appt_in.model_dump(), request.client.host)
    
    db.commit()
    db.refresh(new_appt)
    return new_appt

@router.get("/", response_model=List[AppointmentResponse], dependencies=[Depends(RequirePermission("appointments:manage"))])
def list_appointments(db: Session = Depends(get_db)):
    return db.query(Appointment).order_by(Appointment.appointment_date.asc()).all()