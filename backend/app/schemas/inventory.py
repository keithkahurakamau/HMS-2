from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None

class LocationResponse(LocationCreate):
    location_id: int
    class Config: from_attributes = True

class InventoryItemCreate(BaseModel):
    item_code: Optional[str] = None
    name: str
    category: str # Drug/Consumable/Reagent/Equipment
    unit_cost: float
    unit_price: float
    reorder_threshold: int = 10
    is_active: bool = True

class InventoryItemResponse(InventoryItemCreate):
    item_id: int
    class Config: from_attributes = True

class StockBatchCreate(BaseModel):
    item_id: int
    location_id: int
    batch_number: str
    quantity: int
    expiry_date: date
    supplier_name: Optional[str] = None

class StockBatchResponse(StockBatchCreate):
    batch_id: int
    added_at: datetime
    class Config: from_attributes = True

class UsageLogResponse(BaseModel):
    log_id: int
    item_name: str
    quantity_used: int
    department: str
    timestamp: datetime
    class Config: from_attributes = True