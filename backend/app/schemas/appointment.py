from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    appointment_date: datetime
    notes: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentResponse(AppointmentBase):
    appointment_id: int
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)