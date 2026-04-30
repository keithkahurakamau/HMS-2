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
from app.utils.audit import log_audit
from app.models.billing import Invoice, InvoiceItem

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
def get_patients(search: str = Query("", description="Search by name, ID, OP number, or phone"), skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
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
        existing_patient = db.query(Patient).filter(
            or_(
                Patient.telephone_1 == patient_data.get("telephone_1"),
                (Patient.id_number == patient_data.get("id_number")) & (Patient.id_number != "")
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
# 7. ROUTE PATIENT TO QUEUE
# ==========================================
class QueueRequest(BaseModel):
    department: str
    acuity_level: int = 3

@router.post("/{patient_id}/route", dependencies=[Depends(RequirePermission("patients:write"))])
def route_patient(patient_id: int, request: QueueRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    existing = db.query(PatientQueue).filter(
        PatientQueue.patient_id == patient_id,
        PatientQueue.department == request.department,
        PatientQueue.status.in_(["Waiting", "In Progress"])
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Patient is already active in the {existing.department} queue.")

    new_queue = PatientQueue(
        patient_id=patient_id,
        department=request.department,
        acuity_level=request.acuity_level,
        status="Waiting"
    )
    db.add(new_queue)
    
    # Generate Consultation Fee Invoice
    fee_mapping = {
        "General OPD": 1000.0,
        "Specialist Clinic": 2500.0,
        "Dental": 1500.0,
        "Emergency": 3000.0
    }
    amount = fee_mapping.get(request.department, 1000.0)
    
    invoice = Invoice(
        patient_id=patient_id,
        total_amount=amount,
        status="Pending",
        created_by=current_user["user_id"]
    )
    db.add(invoice)
    db.flush()
    
    item = InvoiceItem(
        invoice_id=invoice.invoice_id,
        description=f"Consultation Fee - {request.department}",
        amount=amount,
        item_type="Consultation"
    )
    db.add(item)
    
    db.commit()
    return {"message": f"Patient routed to {request.department}. Consultation fee of {amount} generated."}