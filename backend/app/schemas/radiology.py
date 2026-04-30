from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# ====================
# Radiology Result Schemas
# ====================
class RadiologyResultCreate(BaseModel):
    findings: str
    conclusion: str
    image_url: Optional[str] = None

class RadiologyResultResponse(RadiologyResultCreate):
    result_id: int
    request_id: int
    performed_by: int
    created_at: datetime

    class Config:
        from_attributes = True

# ====================
# Radiology Request Schemas
# ====================
class RadiologyRequestCreate(BaseModel):
    patient_id: int
    exam_type: str
    clinical_notes: Optional[str] = None

class RadiologyRequestUpdate(BaseModel):
    status: str
    
class RadiologyRequestResponse(RadiologyRequestCreate):
    request_id: int
    requested_by: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    result: Optional[RadiologyResultResponse] = None

    class Config:
        from_attributes = True
