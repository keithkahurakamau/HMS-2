from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class MedicalRecordCreate(BaseModel):
    patient_id: int
    queue_id: Optional[int] = None 
    record_status: str = "Draft" # Controls the workflow routing
    
    # Vitals
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    calculated_bmi: Optional[float] = None
    
    # Clinical (SOAP)
    chief_complaint: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    review_of_systems: Optional[Dict[str, Any]] = None
    physical_examination: Optional[str] = None
    
    # Diagnosis & Plan
    icd10_code: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    prescription_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    follow_up_date: Optional[datetime] = None

class MedicalRecordResponse(BaseModel):
    record_id: int
    patient_id: int
    doctor_id: int
    record_status: str
    blood_pressure: Optional[str]
    chief_complaint: Optional[str]
    icd10_code: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True