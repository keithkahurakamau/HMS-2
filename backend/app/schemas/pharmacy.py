from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DrugCreate(BaseModel):
    brand_name: str
    generic_name: str
    category: str
    dosage_form: str
    strength: str
    unit_price: float
    stock_quantity: int
    reorder_level: int = 10
    requires_prescription: bool = False

class DrugResponse(DrugCreate):
    drug_id: int
    last_restocked: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class DispenseRequest(BaseModel):
    idempotency_key: str  # CRITICAL: Prevents double-charging if network drops
    drug_id: int
    quantity: int
    patient_id: Optional[int] = None  # Null if it's a walk-in over-the-counter sale
    record_id: Optional[int] = None   # Null if not linked to a specific doctor's visit
    notes: Optional[str] = None

class DispenseResponse(BaseModel):
    dispense_id: int
    drug_id: int
    quantity_dispensed: int
    total_cost: float
    dispensed_at: datetime
    
    class Config:
        from_attributes = True