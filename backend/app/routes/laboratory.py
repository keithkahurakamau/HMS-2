from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.config.database import get_db
from app.models.laboratory import LabTest, LabTestCatalog, LabCatalogParameter
from app.models.inventory import StockBatch, InventoryItem, InventoryUsageLog, Location
from app.models.patient import Patient
from app.models.user import User
from app.core.dependencies import get_current_user, RequirePermission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/laboratory", tags=["Laboratory"])

# ----------------------------------------------------------------------------
# Pydantic payloads
# ----------------------------------------------------------------------------
from pydantic import BaseModel, Field


class ConsumedItem(BaseModel):
    batch_id: int
    quantity: int = Field(ge=0)


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


class ParameterPayload(BaseModel):
    parameter_id: Optional[int] = None
    key: str
    name: str
    unit: Optional[str] = None
    value_type: str = "number"
    choices: Optional[str] = None
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    sort_order: int = 0
    is_active: bool = True


class CatalogPayload(BaseModel):
    test_name: str
    description: Optional[str] = None
    category: str
    default_specimen_type: str = "Blood"
    base_price: float
    turnaround_hours: int = 24
    is_active: bool = True
    requires_barcode: bool = False
    parameters: List[ParameterPayload] = []


class CatalogPatch(BaseModel):
    test_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    default_specimen_type: Optional[str] = None
    base_price: Optional[float] = None
    turnaround_hours: Optional[int] = None
    is_active: Optional[bool] = None
    requires_barcode: Optional[bool] = None


class RejectRequest(BaseModel):
    reason: str


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _serialize_parameter(p: LabCatalogParameter) -> Dict[str, Any]:
    return {
        "parameter_id": p.parameter_id,
        "key": p.key,
        "name": p.name,
        "unit": p.unit,
        "value_type": p.value_type,
        "choices": p.choices,
        "ref_low": p.ref_low,
        "ref_high": p.ref_high,
        "sort_order": p.sort_order,
        "is_active": p.is_active,
    }


def _serialize_catalog(c: LabTestCatalog, include_parameters: bool = True) -> Dict[str, Any]:
    data = {
        "catalog_id": c.catalog_id,
        "test_name": c.test_name,
        "description": c.description,
        "category": c.category,
        "default_specimen_type": c.default_specimen_type,
        "base_price": float(c.base_price) if c.base_price is not None else 0,
        "turnaround_hours": c.turnaround_hours,
        "is_active": c.is_active,
        "requires_barcode": bool(getattr(c, "requires_barcode", False)),
    }
    if include_parameters:
        data["parameters"] = [_serialize_parameter(p) for p in (c.parameters or [])]
    return data


# ==========================================
# 1. FETCH LAB QUEUE
# ==========================================
@router.get("/queue", dependencies=[Depends(RequirePermission("laboratory:read"))])
def get_lab_queue(db: Session = Depends(get_db)):
    try:
        # "Pending" and "Pending Collection" are both legitimate queue states —
        # the latter is only used when a catalog test requires a barcode step.
        tests = db.query(LabTest).filter(
            LabTest.status.in_(["Pending", "Pending Collection", "In Progress"])
        ).order_by(desc(LabTest.requested_at)).all()

        result = []
        for t in tests:
            patient = db.query(Patient).filter(Patient.patient_id == t.patient_id).first()
            doctor = db.query(User).filter(User.user_id == t.ordered_by).first()
            catalog = db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id == t.catalog_id).first()
            result.append({
                "test_id": t.test_id,
                "test_name": t.test_name,
                "catalog_id": t.catalog_id,
                "requires_barcode": bool(getattr(catalog, "requires_barcode", False)) if catalog else False,
                "priority": t.priority,
                "status": t.status,
                "patient": f"{patient.surname}, {patient.other_names}" if patient else "Unknown Patient",
                "doctor": doctor.full_name if doctor else "Unknown Doctor",
                "requested_at": t.requested_at.isoformat() if t.requested_at else None,
            })
        return result
    except Exception as e:
        logger.error(f"Error fetching lab queue: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch lab queue.")


# ==========================================
# 2. FETCH ADMIN TEST CATALOG (with parameters)
# ==========================================
@router.get("/catalog", dependencies=[Depends(RequirePermission("laboratory:read"))])
def get_lab_catalog(include_inactive: bool = False, db: Session = Depends(get_db)):
    try:
        query = db.query(LabTestCatalog)
        if not include_inactive:
            query = query.filter(LabTestCatalog.is_active == True)
        rows = query.order_by(LabTestCatalog.test_name).all()
        return [_serialize_catalog(c) for c in rows]
    except Exception as e:
        logger.error(f"Error fetching catalog: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch catalog.")


# ==========================================
# 2b. CATALOG CRUD (admin / lab manager)
# ==========================================
@router.post("/catalog", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def create_catalog_entry(payload: CatalogPayload, db: Session = Depends(get_db)):
    existing = db.query(LabTestCatalog).filter(LabTestCatalog.test_name == payload.test_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A test named '{payload.test_name}' already exists.")

    catalog = LabTestCatalog(
        test_name=payload.test_name,
        description=payload.description,
        category=payload.category,
        default_specimen_type=payload.default_specimen_type,
        base_price=payload.base_price,
        turnaround_hours=payload.turnaround_hours,
        is_active=payload.is_active,
        requires_barcode=payload.requires_barcode,
    )
    db.add(catalog)
    db.flush()

    for p in payload.parameters:
        db.add(LabCatalogParameter(
            catalog_id=catalog.catalog_id,
            key=p.key, name=p.name, unit=p.unit,
            value_type=p.value_type, choices=p.choices,
            ref_low=p.ref_low, ref_high=p.ref_high,
            sort_order=p.sort_order, is_active=p.is_active,
        ))

    db.commit()
    db.refresh(catalog)
    return _serialize_catalog(catalog)


@router.patch("/catalog/{catalog_id}", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def update_catalog_entry(catalog_id: int, payload: CatalogPatch, db: Session = Depends(get_db)):
    catalog = db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id == catalog_id).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog entry not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(catalog, field, value)

    db.commit()
    db.refresh(catalog)
    return _serialize_catalog(catalog)


@router.delete("/catalog/{catalog_id}", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def delete_catalog_entry(catalog_id: int, db: Session = Depends(get_db)):
    catalog = db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id == catalog_id).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog entry not found.")

    # Soft delete: deactivate so historical orders still resolve. The actual
    # DB row stays put because LabTest.catalog_id points at it.
    catalog.is_active = False
    db.commit()
    return {"status": "deactivated", "catalog_id": catalog_id}


# ==========================================
# 2c. PARAMETER CRUD
# ==========================================
@router.post("/catalog/{catalog_id}/parameters", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def add_parameter(catalog_id: int, payload: ParameterPayload, db: Session = Depends(get_db)):
    catalog = db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id == catalog_id).first()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog entry not found.")

    param = LabCatalogParameter(
        catalog_id=catalog_id,
        key=payload.key, name=payload.name, unit=payload.unit,
        value_type=payload.value_type, choices=payload.choices,
        ref_low=payload.ref_low, ref_high=payload.ref_high,
        sort_order=payload.sort_order, is_active=payload.is_active,
    )
    db.add(param)
    db.commit()
    db.refresh(param)
    return _serialize_parameter(param)


@router.patch("/parameters/{parameter_id}", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def update_parameter(parameter_id: int, payload: ParameterPayload, db: Session = Depends(get_db)):
    param = db.query(LabCatalogParameter).filter(LabCatalogParameter.parameter_id == parameter_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found.")

    for field in ("key", "name", "unit", "value_type", "choices",
                  "ref_low", "ref_high", "sort_order", "is_active"):
        setattr(param, field, getattr(payload, field))

    db.commit()
    db.refresh(param)
    return _serialize_parameter(param)


@router.delete("/parameters/{parameter_id}", dependencies=[Depends(RequirePermission("laboratory:manage"))])
def delete_parameter(parameter_id: int, db: Session = Depends(get_db)):
    param = db.query(LabCatalogParameter).filter(LabCatalogParameter.parameter_id == parameter_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found.")
    db.delete(param)
    db.commit()
    return {"status": "deleted", "parameter_id": parameter_id}


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
            StockBatch.quantity > 0,
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
                    "unit": item.dosage_form or "units",
                    "is_reusable": bool(getattr(item, "is_reusable", False)),
                })
        return result
    except Exception as e:
        logger.error(f"Error fetching lab inventory: {e}")
        raise HTTPException(status_code=500, detail=f"Database schema mismatch error: {str(e)}")


# ==========================================
# 4. CREATE LAB ORDERS (DOCTOR-INITIATED)
# ==========================================
@router.post("/orders", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_lab_orders(
    payload: LabOrderRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create one or more lab tests for a patient in a single transaction.

    Status starts at "Pending" so the lab tech sees it in the queue
    immediately. Tests whose catalog row sets requires_barcode=True open in
    a barcode-print step in the UI; the rest can be completed in one click.
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
        initial_status = "Pending Collection" if getattr(cat, "requires_barcode", False) else "Pending"
        test = LabTest(
            patient_id=payload.patient_id,
            record_id=payload.record_id,
            ordered_by=current_user["user_id"],
            catalog_id=cat.catalog_id,
            test_name=cat.test_name,
            clinical_notes=item.clinical_notes,
            billed_price=cat.base_price,
            specimen_type=cat.default_specimen_type,
            status=initial_status,
            priority=priority,
        )
        db.add(test)
        db.flush()
        created.append({
            "test_id": test.test_id,
            "test_name": test.test_name,
            "priority": test.priority,
            "billed_price": float(test.billed_price),
            "status": test.status,
        })

    db.commit()
    return {"created": created, "count": len(created)}


# ==========================================
# 5. COLLECT SPECIMEN (only for barcode-required tests)
# ==========================================
class CollectRequest(BaseModel):
    specimen_id: Optional[str] = None  # auto-generated if omitted


@router.post("/tests/{test_id}/collect", dependencies=[Depends(RequirePermission("laboratory:read"))])
def collect_specimen(
    test_id: int,
    payload: CollectRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    test = db.query(LabTest).filter(LabTest.test_id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Lab test not found.")
    if test.status == "Completed":
        raise HTTPException(status_code=400, detail="Test is already completed.")

    # Generate a default barcode when one isn't supplied so the lab can opt
    # in to labelling without micromanaging the format.
    test.specimen_id = payload.specimen_id or f"LAB-{test.test_id:06d}-{int(datetime.now().timestamp())}"
    test.sample_collected_at = datetime.now()
    test.status = "In Progress"
    db.commit()
    return {
        "status": "in_progress",
        "specimen_id": test.specimen_id,
        "collected_at": test.sample_collected_at.isoformat(),
    }


# ==========================================
# 6. COMPLETE TEST & DEDUCT INVENTORY
# ==========================================
@router.post("/tests/{test_id}/complete")
def complete_lab_test(
    test_id: int,
    payload: TestCompletionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
                StockBatch.location_id == lab_location.location_id,
            ).first()

            if not batch:
                raise ValueError(f"Batch {item.batch_id} not found in Laboratory stock.")

            inventory_item = db.query(InventoryItem).filter(InventoryItem.item_id == batch.item_id).first()
            is_reusable = bool(getattr(inventory_item, "is_reusable", False)) if inventory_item else False

            # Reusable items (glassware, slides, probes…) get logged but never
            # decrement the batch — they go back into circulation after
            # cleaning. Quantity=0 also implies a reusable-style log.
            should_deduct = (not is_reusable) and item.quantity > 0
            if should_deduct:
                if getattr(batch, "quantity", 0) < item.quantity:
                    raise ValueError(
                        f"Insufficient stock in batch {getattr(batch, 'batch_number', 'Unknown')}."
                    )
                batch.quantity -= item.quantity

            usage_log = InventoryUsageLog(
                item_id=batch.item_id,
                batch_id=batch.batch_id,
                location_id=lab_location.location_id,
                quantity_used=item.quantity if should_deduct else 0,
                used_by_user_id=current_user["user_id"],
                reference_type="LabTest",
                reference_id=test.test_id,
                is_reusable_use=(not should_deduct),
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
# 7. REJECT TEST (sample contamination, wrong specimen, etc.)
# ==========================================
@router.post("/tests/{test_id}/reject", dependencies=[Depends(RequirePermission("laboratory:read"))])
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
    test.lab_technician_notes = (test.lab_technician_notes or "") + (
        f"\nREJECTED ({datetime.now().isoformat()}): {payload.reason}"
    )
    test.performed_by_id = current_user["user_id"]
    db.commit()
    return {"status": "rejected", "message": "Sample rejected. Requesting clinician will be notified."}
