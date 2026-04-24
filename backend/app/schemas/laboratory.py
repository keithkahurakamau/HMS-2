from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class LabTestOrder(BaseModel):
    patient_id: int
    catalog_id: int

class LabTestResult(BaseModel):
    result_summary: str
    result_data: Dict[str, Any] # e.g., {"WBC": "7.5", "RBC": "4.8"}

class LabTestResponse(BaseModel):
    test_id: int
    patient_id: int
    test_name: str
    status: str
    billed_price: float
    result_summary: Optional[str] = None
    requested_at: datetime
    
    class Config:
        from_attributes = True