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
from app.core.dependencies import get_current_user, RequirePermission
from app.utils.audit import log_audit
from app.utils.notify import notify_permission

router = APIRouter(prefix="/api/wards", tags=["Wards & Admissions"])

# --- NEW SCHEMAS FOR WARD INVENTORY ---
class ConsumedItem(BaseModel):
    batch_id: int
    quantity: int

class WardConsumptionRequest(BaseModel):
    items: List[ConsumedItem]
    notes: Optional[str] = None

# --- WARD & BED MANAGEMENT ENDPOINTS ---

@router.get("/board", dependencies=[Depends(get_current_user)])
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
                    bed_info["patient"] = f"{patient.surname}, {patient.other_names}" if patient else "Unknown"
                    bed_info["admission_date"] = active_admission.admitted_at.strftime("%Y-%m-%d")
                    bed_info["diagnosis"] = active_admission.primary_diagnosis
                    bed_info["admission_id"] = active_admission.admission_id
                    
            ward_data["beds"].append(bed_info)
        board.append(ward_data)
        
    return board

# --- WARD & BED SETUP (so beds exist before anyone can allocate them) ---

class WardCreateRequest(BaseModel):
    name: str
    capacity: int


class WardUpdateRequest(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None


class BedCreateRequest(BaseModel):
    """Either a single named bed (bed_number) or a bulk run (count + prefix,
    auto-numbered prefix-1 … prefix-N continuing after existing beds)."""
    bed_number: Optional[str] = None
    count: Optional[int] = None
    prefix: Optional[str] = None


# Occupied is deliberately excluded — that transition only happens via /admit.
BED_SETUP_STATUSES = ("Available", "Maintenance", "Cleaning")


class BedUpdateRequest(BaseModel):
    status: str


@router.post("/", dependencies=[Depends(RequirePermission("wards:manage"))])
def create_ward(req: WardCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Ward name is required.")
    if req.capacity < 1:
        raise HTTPException(status_code=400, detail="Capacity must be at least 1.")
    if db.query(Ward).filter(func.lower(Ward.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail=f"Ward '{name}' already exists.")
    ward = Ward(name=name, capacity=req.capacity)
    db.add(ward)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "Ward", str(ward.ward_id), None,
              {"name": name, "capacity": req.capacity}, None)
    db.commit()
    return {"message": "Ward created.", "ward_id": ward.ward_id}


@router.patch("/{ward_id}", dependencies=[Depends(RequirePermission("wards:manage"))])
def update_ward(ward_id: int, req: WardUpdateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ward = db.query(Ward).filter(Ward.ward_id == ward_id).first()
    if not ward:
        raise HTTPException(status_code=404, detail="Ward not found.")
    before = {"name": ward.name, "capacity": ward.capacity}
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Ward name cannot be empty.")
        clash = db.query(Ward).filter(func.lower(Ward.name) == name.lower(), Ward.ward_id != ward_id).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Ward '{name}' already exists.")
        ward.name = name
    if req.capacity is not None:
        bed_count = db.query(func.count(Bed.bed_id)).filter(Bed.ward_id == ward_id).scalar() or 0
        if req.capacity < bed_count:
            raise HTTPException(status_code=400, detail=f"Capacity cannot be below the {bed_count} bed(s) already set up.")
        ward.capacity = req.capacity
    log_audit(db, current_user["user_id"], "UPDATE", "Ward", str(ward_id), before,
              {"name": ward.name, "capacity": ward.capacity}, None)
    db.commit()
    return {"message": "Ward updated."}


@router.post("/{ward_id}/beds", dependencies=[Depends(RequirePermission("wards:manage"))])
def add_beds(ward_id: int, req: BedCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ward = db.query(Ward).filter(Ward.ward_id == ward_id).first()
    if not ward:
        raise HTTPException(status_code=404, detail="Ward not found.")

    existing = db.query(func.count(Bed.bed_id)).filter(Bed.ward_id == ward_id).scalar() or 0

    if req.bed_number:
        labels = [req.bed_number.strip()]
    elif req.count:
        if req.count < 1 or req.count > 200:
            raise HTTPException(status_code=400, detail="Count must be between 1 and 200.")
        prefix = (req.prefix or ward.name[:3].upper()).strip()
        labels = [f"{prefix}-{existing + i + 1}" for i in range(req.count)]
    else:
        raise HTTPException(status_code=400, detail="Provide a bed_number, or a count for bulk creation.")

    if existing + len(labels) > ward.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Ward capacity is {ward.capacity} and {existing} bed(s) exist — "
                   f"adding {len(labels)} would exceed it. Increase the ward capacity first.",
        )

    # bed_number is globally unique — reject any clash up front so the whole
    # batch lands or none of it does.
    clashes = [b.bed_number for b in db.query(Bed).filter(Bed.bed_number.in_(labels)).all()]
    if clashes:
        raise HTTPException(status_code=409, detail=f"Bed number(s) already in use: {', '.join(clashes)}")

    for label in labels:
        db.add(Bed(ward_id=ward_id, bed_number=label, status="Available"))
    log_audit(db, current_user["user_id"], "CREATE", "Bed", f"ward:{ward_id}", None,
              {"beds": labels}, None)
    db.commit()
    return {"message": f"Added {len(labels)} bed(s) to {ward.name}.", "beds": labels}


@router.patch("/beds/{bed_id}", dependencies=[Depends(RequirePermission("wards:manage"))])
def update_bed(bed_id: int, req: BedUpdateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Maintenance-state changes only — occupancy is owned by admit/discharge."""
    bed = db.query(Bed).filter(Bed.bed_id == bed_id).first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found.")
    if bed.status == "Occupied":
        raise HTTPException(status_code=400, detail="Bed is occupied — discharge the patient first.")
    if req.status not in BED_SETUP_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of {list(BED_SETUP_STATUSES)}.")
    before = bed.status
    bed.status = req.status
    log_audit(db, current_user["user_id"], "UPDATE", "Bed", str(bed_id),
              {"status": before}, {"status": req.status}, None)
    db.commit()
    return {"message": "Bed updated."}


@router.delete("/beds/{bed_id}", dependencies=[Depends(RequirePermission("wards:manage"))])
def delete_bed(bed_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    bed = db.query(Bed).filter(Bed.bed_id == bed_id).first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found.")
    if bed.status == "Occupied":
        raise HTTPException(status_code=400, detail="Bed is occupied — discharge the patient first.")
    # Past admissions FK this bed; keep history intact by refusing the delete.
    if db.query(AdmissionRecord).filter(AdmissionRecord.bed_id == bed_id).first():
        raise HTTPException(status_code=400, detail="Bed has admission history — set it to Maintenance instead of deleting.")
    db.delete(bed)
    log_audit(db, current_user["user_id"], "DELETE", "Bed", str(bed_id),
              {"bed_number": bed.bed_number, "ward_id": bed.ward_id}, None, None)
    db.commit()
    return {"message": "Bed deleted."}


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
    db.flush()

    # Ward nursing staff manage admitted patients — page them on a new admission.
    notify_permission(
        db, "wards:manage",
        title="New patient admitted",
        body=f"{patient.other_names} {patient.surname} → bed {bed.bed_number} · {req.diagnosis}",
        link="/app/wards",
        exclude_user_id=current_user["user_id"],
    )

    db.commit()
    return {"message": "Patient admitted successfully."}

@router.post("/discharge/{admission_id}", dependencies=[Depends(RequirePermission("wards:manage"))])
def discharge_patient(admission_id: int, req: DischargeRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Ends the admission and flags the bed for cleaning.

    SEC: previously had NO auth dependency at all — any caller who could reach
    the tenant API could discharge a patient. Now gated on wards:manage, the
    same capability /admit and the bed-setup endpoints require.
    """
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

@router.get("/inventory", dependencies=[Depends(get_current_user)])
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

# ==========================================
# CLINICAL OBSERVATIONS LOG (per admission)
# ==========================================
class ClinicalNoteRequest(BaseModel):
    note: str


@router.post("/admissions/{admission_id}/notes")
def append_clinical_note(
    admission_id: int,
    payload: ClinicalNoteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Appends a free-text observation to the admission record. Persists in audit_logs
    so the timeline is recoverable even if the admission row is later edited."""
    admission = db.query(AdmissionRecord).filter(AdmissionRecord.admission_id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found.")
    if not payload.note.strip():
        raise HTTPException(status_code=400, detail="Note cannot be empty.")

    log_audit(
        db,
        current_user["user_id"],
        "OBSERVATION",
        "AdmissionRecord",
        str(admission_id),
        old_value=None,
        new_value={"note": payload.note},
        ip_address=None,
    )
    db.commit()
    return {"message": "Observation logged.", "admission_id": admission_id}
