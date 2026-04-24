from pydantic import BaseModel
from typing import Optional

class AdmissionRequest(BaseModel):
    patient_id: int
    bed_id: int
    diagnosis: str

class DischargeRequest(BaseModel):
    notes: Optional[str] = ""