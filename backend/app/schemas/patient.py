from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date, datetime

class PatientCreate(BaseModel):
    # Demographics
    surname: str
    other_names: str
    sex: str
    date_of_birth: date
    marital_status: Optional[str] = None
    religion: Optional[str] = None
    primary_language: Optional[str] = None

    # Clinical
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None

    # Identification
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    nationality: Optional[str] = None
    telephone_1: Optional[str] = None
    telephone_2: Optional[str] = None
    email: Optional[EmailStr] = None

    # Address & Meta
    postal_address: Optional[str] = None
    postal_code: Optional[str] = None
    residence: Optional[str] = None
    town: Optional[str] = None
    occupation: Optional[str] = None
    employer_name: Optional[str] = None
    reference_number: Optional[str] = None

    # NOK
    nok_name: Optional[str] = None
    nok_relationship: Optional[str] = None
    nok_contact: Optional[str] = None
    notes: Optional[str] = None

class PatientResponse(PatientCreate):
    patient_id: int
    outpatient_no: str
    inpatient_no: Optional[str] = None
    is_active: bool
    registered_on: datetime
    registered_by: int
    
    class Config:
        from_attributes = True