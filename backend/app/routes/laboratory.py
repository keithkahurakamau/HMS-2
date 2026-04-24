from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.config.database import get_db
from app.models.laboratory import LabTest
from app.models.inventory import StockBatch, InventoryItem, InventoryUsageLog, Location
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/api/laboratory", tags=["Laboratory"])

from pydantic import BaseModel
class ConsumedItem(BaseModel):
    batch_id: int
    quantity: int

class TestCompletionRequest(BaseModel):
    result_data: Dict[str, Any] # e.g. {"wbc": 4.5, "hgb": 12.1}
    tech_notes: Optional[str] = None
    consumed_items: List[ConsumedItem] = []

@router.post("/tests/{test_id}/complete")
def complete_lab_test(
    test_id: int, 
    payload: TestCompletionRequest, 
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Saves discrete test results and deducts consumed reagents from Lab Inventory."""
    try:
        # 1. Find the test
        test = db.query(LabTest).filter(LabTest.test_id == test_id).first()
        if not test:
            raise HTTPException(status_code=404, detail="Lab test not found.")
        if test.status == "Completed":
            raise HTTPException(status_code=400, detail="Test is already completed.")

        # 2. Process Inventory Consumption Atomically
        lab_location = db.query(Location).filter(Location.name == "Laboratory").first()
        
        for item in payload.consumed_items:
            # Lock the specific batch assigned to the Laboratory
            batch = db.query(StockBatch).with_for_update().filter(
                StockBatch.batch_id == item.batch_id,
                StockBatch.location_id == lab_location.location_id
            ).first()
            
            if not batch:
                raise ValueError(f"Batch {item.batch_id} not found in Laboratory stock.")
            if batch.quantity < item.quantity:
                raise ValueError(f"Insufficient stock in batch {batch.batch_number}. Only {batch.quantity} available.")

            # Deduct stock
            batch.quantity -= item.quantity
            
            # Fetch item details for the log
            inv_item = db.query(InventoryItem).filter(InventoryItem.item_id == batch.item_id).first()

            # Create Usage Log
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

        # 3. Update the Clinical Test Record
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
        raise HTTPException(status_code=500, detail=f"Transaction failed: {str(e)}")