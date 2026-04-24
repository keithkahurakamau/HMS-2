from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from datetime import datetime

from app.config.database import get_db
from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/patients", tags=["Patients"])

@router.post("/", response_model=PatientResponse, dependencies=[Depends(RequirePermission("patients:write"))])
def register_patient(patient_in: PatientCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Auto-generate OP Number: OP-YYYYMMDD-XXXX
    date_str = datetime.now().strftime("%Y%m%d")
    count = db.query(Patient).filter(Patient.registered_on >= datetime.now().date()).count() + 1
    op_number = f"OP-{date_str}-{count:04d}"

    new_patient = Patient(
        **patient_in.model_dump(), 
        outpatient_no=op_number, 
        registered_by=current_user["user_id"]
    )
    db.add(new_patient)
    db.flush() 

    # Audit Log
    log_audit(db, current_user["user_id"], "CREATE", "Patient", new_patient.patient_id, None, patient_in.model_dump(), request.client.host)
    
    db.commit()
    db.refresh(new_patient)
    return new_patient

@router.get("/", response_model=List[PatientResponse], dependencies=[Depends(RequirePermission("patients:read"))])
def get_patients(search: str = None, skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Patient)
    if search:
        query = query.filter(
            or_(
                Patient.outpatient_no.ilike(f"%{search}%"),
                Patient.surname.ilike(f"%{search}%"),
                Patient.id_number.ilike(f"%{search}%"),
                Patient.telephone_1.ilike(f"%{search}%")
            )
        )
    return query.offset(skip).limit(limit).all()

@router.get("/{patient_id}", response_model=PatientResponse, dependencies=[Depends(RequirePermission("patients:read"))])
def get_patient_by_id(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient