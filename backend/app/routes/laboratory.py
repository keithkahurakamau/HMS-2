from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.config.database import get_db
from app.models.laboratory import LabTest, LabTestCatalog
from app.models.inventory import StockBatch, InventoryItem, InventoryUsageLog, Location
from app.models.patient import Patient
from app.models.user import User
from app.core.dependencies import get_current_user, RequirePermission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/laboratory", tags=["Laboratory"])

from pydantic import BaseModel
class ConsumedItem(BaseModel):
    batch_id: int
    quantity: int

class TestCompletionRequest(BaseModel):
    result_data: Dict[str, Any]
    tech_notes: Optional[str] = None
    consumed_items: List[ConsumedItem] = []


class LabOrderItem(BaseModel):
    catalog_id: int
    clinical_notes: Optional[str] = None
    priority: Optional[str] = "Routine"  # Routine | Urgent | STAT


class LabOrderRequest(BaseModel):
    patient_id: int
    record_id: Optional[int] = None
    tests: List[LabOrderItem]

# ==========================================
# 1. FETCH LAB QUEUE
# ==========================================
@router.get("/queue", dependencies=[Depends(RequirePermission("laboratory:read"))])
def get_lab_queue(db: Session = Depends(get_db)):
    try:
        tests = db.query(LabTest).filter(
            LabTest.status.in_(["Pending Collection", "In Progress"])
        ).order_by(desc(LabTest.requested_at)).all()
        
        result = []
        for t in tests:
            patient = db.query(Patient).filter(Patient.patient_id == t.patient_id).first()
            doctor = db.query(User).filter(User.user_id == t.ordered_by).first()
            result.append({
                "test_id": t.test_id,
                "test_name": t.test_name,
                "catalog_id": t.catalog_id,
                "priority": t.priority,
                "status": t.status,
                "patient": f"{patient.surname}, {patient.other_names}" if patient else "Unknown Patient",
                "doctor": doctor.full_name if doctor else "Unknown Doctor",
                "requested_at": t.requested_at.isoformat() if t.requested_at else None
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching lab queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch lab queue.")

# ==========================================
# 2. FETCH ADMIN TEST CATALOG
# ==========================================
@router.get("/catalog", dependencies=[Depends(RequirePermission("laboratory:read"))])
def get_lab_catalog(db: Session = Depends(get_db)):
    try:
        return db.query(LabTestCatalog).filter(LabTestCatalog.is_active == True).order_by(LabTestCatalog.test_name).all()
    except Exception as e:
        logger.error(f"Error fetching catalog: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch catalog.")

# ==========================================
# 3. FETCH LOCAL LAB INVENTORY
# ==========================================
@router.get("/inventory", dependencies=[Depends(RequirePermission("laboratory:read"))])
def get_lab_inventory(db: Session = Depends(get_db)):
    try:
        lab_loc = db.query(Location).filter(Location.name == "Laboratory").first()
        if not lab_loc:
            return []
        
        batches = db.query(StockBatch).filter(
            StockBatch.location_id == lab_loc.location_id, 
            StockBatch.quantity > 0
        ).all()
        
        result = []
        for b in batches:
            item = db.query(InventoryItem).filter(InventoryItem.item_id == b.item_id).first()
            if item:
                result.append({
                    "batch_id": b.batch_id,
                    "batch_no": b.batch_number,
                    "name": item.name,
                    "stock": b.quantity,
                    # Fallback to "units" if dosage form is not provided
                    "unit": item.dosage_form or "units" 
                })
        return result
    except Exception as e:
        logger.error(f"Error fetching lab inventory: {e}")
        raise HTTPException(status_code=500, detail=f"Database schema mismatch error: {str(e)}")

# ==========================================
# 3.5. CREATE LAB ORDERS (DOCTOR-INITIATED)
# ==========================================
@router.post("/orders", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_lab_orders(
    payload: LabOrderRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create one or more lab tests for a patient in a single transaction.

    Pricing is locked at order time (``billed_price``) so subsequent catalogue
    edits never re-price an existing order. Status starts at ``Pending`` so the
    lab tech sees it in the queue immediately.
    """
    if not payload.tests:
        raise HTTPException(status_code=400, detail="At least one test is required.")

    patient = db.query(Patient).filter(Patient.patient_id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    catalog_ids = [t.catalog_id for t in payload.tests]
    catalog_rows = db.query(LabTestCatalog).filter(
        LabTestCatalog.catalog_id.in_(catalog_ids),
        LabTestCatalog.is_active == True,
    ).all()
    catalog_map = {c.catalog_id: c for c in catalog_rows}

    missing = set(catalog_ids) - set(catalog_map.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown or inactive catalog ids: {sorted(missing)}")

    created = []
    for item in payload.tests:
        cat = catalog_map[item.catalog_id]
        priority = item.priority if item.priority in ("Routine", "Urgent", "STAT") else "Routine"
        test = LabTest(
            patient_id=payload.patient_id,
            record_id=payload.record_id,
            ordered_by=current_user["user_id"],
            catalog_id=cat.catalog_id,
            test_name=cat.test_name,
            clinical_notes=item.clinical_notes,
            billed_price=cat.base_price,
            specimen_type=cat.default_specimen_type,
            status="Pending",
            priority=priority,
        )
        db.add(test)
        db.flush()
        created.append({
            "test_id": test.test_id,
            "test_name": test.test_name,
            "priority": test.priority,
            "billed_price": float(test.billed_price),
        })

    db.commit()
    return {"created": created, "count": len(created)}


# ==========================================
# 4. COMPLETE TEST & DEDUCT INVENTORY
# ==========================================
@router.post("/tests/{test_id}/complete")
def complete_lab_test(
    test_id: int, 
    payload: TestCompletionRequest, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        test = db.query(LabTest).filter(LabTest.test_id == test_id).first()
        if not test:
            raise HTTPException(status_code=404, detail="Lab test not found.")
        if test.status == "Completed":
            raise HTTPException(status_code=400, detail="Test is already completed.")

        lab_location = db.query(Location).filter(Location.name == "Laboratory").first()
        
        for item in payload.consumed_items:
            batch = db.query(StockBatch).with_for_update().filter(
                StockBatch.batch_id == item.batch_id,
                StockBatch.location_id == lab_location.location_id
            ).first()
            
            if not batch:
                raise ValueError(f"Batch {item.batch_id} not found in Laboratory stock.")
            if getattr(batch, 'quantity', 0) < item.quantity:
                raise ValueError(f"Insufficient stock in batch {getattr(batch, 'batch_number', 'Unknown')}.")

            batch.quantity -= item.quantity
            
            usage_log = InventoryUsageLog(
                item_id=batch.item_id,
                batch_id=batch.batch_id,
                location_id=lab_location.location_id,
                quantity_used=item.quantity,
                used_by_user_id=current_user["user_id"],
                reference_type="LabTest",
                reference_id=test.test_id
            )
            db.add(usage_log)

        test.result_data = payload.result_data
        test.lab_technician_notes = payload.tech_notes
        test.status = "Completed"
        test.completed_at = datetime.now()
        test.performed_by_id = current_user["user_id"]

        db.commit()
        return {"status": "success", "message": "Test completed and inventory updated."}

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transaction failed: {str(e)}")


# ==========================================
# 5. REJECT TEST (sample contamination, wrong specimen, etc.)
# ==========================================
class RejectRequest(BaseModel):
    reason: str


@router.post("/tests/{test_id}/reject", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def reject_lab_test(
    test_id: int,
    payload: RejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Marks the test as Rejected and records the reason. Lab consumables are not deducted."""
    test = db.query(LabTest).filter(LabTest.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Lab test not found.")
    if test.status == "Completed":
        raise HTTPException(status_code=400, detail="Cannot reject a completed test.")

    test.status = "Rejected"
    test.lab_technician_notes = (test.lab_technician_notes or "") + f"\nREJECTED ({datetime.now().isoformat()}): {payload.reason}"
    test.performed_by_id = current_user["user_id"]
    db.commit()
    return {"status": "rejected", "message": "Sample rejected. Requesting clinician will be notified."}