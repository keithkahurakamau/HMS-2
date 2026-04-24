from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from app.config.database import get_db
from app.models.wards import Ward, Bed, AdmissionRecord
from app.models.patient import Patient
from app.models.inventory import StockBatch, InventoryItem, InventoryUsageLog, Location
from app.schemas.wards import AdmissionRequest, DischargeRequest
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/wards", tags=["Wards & Admissions"])

# --- NEW SCHEMAS FOR WARD INVENTORY ---
class ConsumedItem(BaseModel):
    batch_id: int
    quantity: int

class WardConsumptionRequest(BaseModel):
    items: List[ConsumedItem]
    notes: Optional[str] = None

# --- WARD & BED MANAGEMENT ENDPOINTS ---

@router.get("/board")
def get_bed_board(db: Session = Depends(get_db)):
    """Fetches the entire hospital ward layout, including active patients."""
    wards = db.query(Ward).all()
    board = []
    
    for ward in wards:
        ward_data = {
            "id": ward.ward_id,
            "name": ward.name,
            "capacity": ward.capacity,
            "beds": []
        }
        
        beds = db.query(Bed).filter(Bed.ward_id == ward.ward_id).all()
        for bed in beds:
            bed_info = {
                "id": bed.bed_id, 
                "number": bed.bed_number, 
                "status": bed.status, 
                "patient": None, 
                "admission_date": None, 
                "diagnosis": None
            }
            
            if bed.status == "Occupied":
                # Find the active admission for this bed
                active_admission = db.query(AdmissionRecord).filter(
                    AdmissionRecord.bed_id == bed.bed_id, 
                    AdmissionRecord.status == "Active"
                ).first()
                
                if active_admission:
                    patient = db.query(Patient).filter(Patient.patient_id == active_admission.patient_id).first()
                    bed_info["patient"] = f"{patient.surname}, {patient.first_name}" if patient else "Unknown"
                    bed_info["admission_date"] = active_admission.admitted_at.strftime("%Y-%m-%d")
                    bed_info["diagnosis"] = active_admission.primary_diagnosis
                    bed_info["admission_id"] = active_admission.admission_id
                    
            ward_data["beds"].append(bed_info)
        board.append(ward_data)
        
    return board

@router.post("/admit")
def admit_patient(req: AdmissionRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Locks a bed and creates an active Admission Record."""
    # 1. Lock the bed to prevent double-booking
    bed = db.query(Bed).with_for_update().filter(Bed.bed_id == req.bed_id).first()
    
    if not bed or bed.status != "Available":
        raise HTTPException(status_code=400, detail="Bed is not available.")
        
    # 2. Verify patient exists
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
        
    # 3. Update Bed Status
    bed.status = "Occupied"
    
    # 4. Create Admission Record
    admission = AdmissionRecord(
        patient_id=req.patient_id,
        bed_id=req.bed_id,
        admitting_doctor_id=current_user["user_id"],
        primary_diagnosis=req.diagnosis
    )
    
    db.add(admission)
    db.commit()
    return {"message": "Patient admitted successfully."}

@router.post("/discharge/{admission_id}")
def discharge_patient(admission_id: int, req: DischargeRequest, db: Session = Depends(get_db)):
    """Ends the admission and flags the bed for cleaning."""
    admission = db.query(AdmissionRecord).filter(AdmissionRecord.admission_id == admission_id).first()
    if not admission or admission.status != "Active":
        raise HTTPException(status_code=404, detail="Active admission not found.")
        
    # 1. Mark admission complete
    admission.status = "Discharged"
    admission.discharged_at = datetime.now(timezone.utc)
    admission.discharge_notes = req.notes
    
    # 2. Free the bed (Requires cleaning before next use)
    bed = db.query(Bed).filter(Bed.bed_id == admission.bed_id).first()
    if bed:
        bed.status = "Cleaning" 
    
    db.commit()
    return {"message": "Patient discharged. Bed flagged for cleaning."}


# --- WARD INVENTORY & CONSUMPTION ENDPOINTS ---

@router.get("/inventory")
def get_ward_inventory(db: Session = Depends(get_db)):
    """Fetches all stock currently physically located in the Wards."""
    # Find the generic "Wards" location (or specific ward if configured)
    ward_location = db.query(Location).filter(Location.name == "Wards").first()
    if not ward_location:
        return []

    # Join StockBatch with Master Inventory
    inventory = db.query(
        InventoryItem.item_id,
        InventoryItem.name,
        InventoryItem.unit_price,
        StockBatch.batch_id,
        StockBatch.batch_number,
        StockBatch.quantity,
        StockBatch.expiry_date
    ).join(
        StockBatch, InventoryItem.item_id == StockBatch.item_id
    ).filter(
        StockBatch.location_id == ward_location.location_id,
        StockBatch.quantity > 0
    ).order_by(StockBatch.expiry_date.asc()).all()

    return [dict(item._mapping) for item in inventory]

@router.post("/{admission_id}/consume")
def consume_ward_stock(
    admission_id: int, 
    req: WardConsumptionRequest, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """
    Atomically deducts stock from the Ward location and logs it against the patient's admission.
    This creates an immutable audit trail.
    """
    try:
        admission = db.query(AdmissionRecord).filter(AdmissionRecord.admission_id == admission_id).first()
        if not admission or admission.status != "Active":
            raise HTTPException(status_code=404, detail="Active admission not found.")

        ward_location = db.query(Location).filter(Location.name == "Wards").first()
        if not ward_location:
            raise HTTPException(status_code=500, detail="System configuration error: 'Wards' location undefined.")
        
        for item in req.items:
            # 1. Lock the batch row to prevent concurrent race conditions
            batch = db.query(StockBatch).with_for_update().filter(
                StockBatch.batch_id == item.batch_id,
                StockBatch.location_id == ward_location.location_id
            ).first()
            
            if not batch:
                raise ValueError(f"Batch {item.batch_id} not found in Ward inventory.")
            if batch.quantity < item.quantity:
                raise ValueError(f"Insufficient stock in batch {batch.batch_number}. Only {batch.quantity} available.")

            # 2. Deduct Physical Stock
            batch.quantity -= item.quantity

            # 3. Create Immutable Audit Log tying the item to the specific Admission
            usage_log = InventoryUsageLog(
                item_id=batch.item_id,
                batch_id=batch.batch_id,
                location_id=ward_location.location_id,
                quantity_used=item.quantity,
                used_by_user_id=current_user["user_id"],
                reference_type="InpatientAdmission",
                reference_id=admission.admission_id
            )
            db.add(usage_log)

        db.commit()
        return {"status": "success", "message": "Items administered and audit log generated."}

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Transaction failed.")