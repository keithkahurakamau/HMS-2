from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class TriageCreate(BaseModel):
    patient_id: int
    # Triage queue row being closed out. Optional for walk-ins triaged
    # without a formal queue entry.
    queue_id: Optional[int] = None

    # Vitals
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    calculated_bmi: Optional[float] = None
    pain_score: Optional[int] = None
    blood_glucose: Optional[float] = None

    # Assessment
    chief_complaint: Optional[str] = None
    acuity_level: int = 3  # 1=Emergency … 5=Non-urgent
    triage_notes: Optional[str] = None
    # Where the nurse routes the patient next. Defaults to the doctor's desk.
    disposition: str = "Consultation"


class TriageResponse(BaseModel):
    triage_id: int
    patient_id: int
    nurse_id: int
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    calculated_bmi: Optional[float] = None
    pain_score: Optional[int] = None
    blood_glucose: Optional[float] = None
    chief_complaint: Optional[str] = None
    acuity_level: int
    triage_notes: Optional[str] = None
    disposition: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
