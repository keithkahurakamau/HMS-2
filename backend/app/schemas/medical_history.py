"""
Medical History Schemas - Pydantic Validation Layer
Kenya Data Protection Act 2019 Compliant.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, Dict, List
from datetime import datetime


# ====================
# Consent Schemas
# ====================
VALID_CONSENT_TYPES = ["Treatment", "Data Sharing", "Research", "Photography", "Emergency Override"]
VALID_CONSENT_METHODS = ["Written", "Verbal", "Guardian/Next of Kin", "Implied (Emergency)"]

class ConsentCreate(BaseModel):
    patient_id: int
    consent_type: str
    consent_given: bool = True
    consent_method: str = "Written"
    notes: Optional[str] = None
    consent_expires_at: Optional[datetime] = None

    @field_validator('consent_type')
    @classmethod
    def validate_consent_type(cls, v):
        if v not in VALID_CONSENT_TYPES:
            raise ValueError(f"Invalid consent type. Must be one of: {VALID_CONSENT_TYPES}")
        return v

    @field_validator('consent_method')
    @classmethod
    def validate_consent_method(cls, v):
        if v not in VALID_CONSENT_METHODS:
            raise ValueError(f"Invalid consent method. Must be one of: {VALID_CONSENT_METHODS}")
        return v

class ConsentResponse(BaseModel):
    consent_id: int
    patient_id: int
    recorded_by: int
    consent_type: str
    consent_given: bool
    consent_method: str
    notes: Optional[str] = None
    consented_at: datetime
    consent_expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ====================
# Medical History Entry Schemas
# ====================
VALID_ENTRY_TYPES = [
    "SURGICAL_HISTORY",
    "FAMILY_HISTORY",
    "SOCIAL_HISTORY",
    "IMMUNIZATION",
    "ALLERGY",
    "CHRONIC_CONDITION",
    "PAST_MEDICAL_EVENT",
    "OBSTETRIC_HISTORY",
    "MENTAL_HEALTH",
]

VALID_SEVERITY_LEVELS = ["Mild", "Moderate", "Severe", "Life-threatening", "N/A"]
VALID_STATUSES = ["Active", "Resolved", "Managed", "Remission", "Deceased"]

class MedicalHistoryEntryCreate(BaseModel):
    patient_id: int
    record_id: Optional[int] = None
    entry_type: str
    title: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=5)
    event_date: Optional[str] = None
    severity: Optional[str] = None
    status: str = "Active"
    extra_data: Optional[Dict[str, Any]] = None
    is_sensitive: bool = False

    @field_validator('entry_type')
    @classmethod
    def validate_entry_type(cls, v):
        if v not in VALID_ENTRY_TYPES:
            raise ValueError(f"Invalid entry type. Must be one of: {VALID_ENTRY_TYPES}")
        return v

    @field_validator('severity')
    @classmethod
    def validate_severity(cls, v):
        if v and v not in VALID_SEVERITY_LEVELS:
            raise ValueError(f"Invalid severity. Must be one of: {VALID_SEVERITY_LEVELS}")
        return v

class MedicalHistoryEntryUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, min_length=5)
    event_date: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    is_sensitive: Optional[bool] = None

class MedicalHistoryEntryResponse(BaseModel):
    entry_id: int
    patient_id: int
    record_id: Optional[int] = None
    recorded_by: int
    entry_type: str
    title: str
    description: str
    event_date: Optional[str] = None
    severity: Optional[str] = None
    status: str
    extra_data: Optional[Dict[str, Any]] = None
    is_sensitive: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ====================
# Aggregated History Response (Full Patient Chart)
# ====================
class PatientMedicalChartResponse(BaseModel):
    """The complete structured medical chart for a patient."""
    patient_id: int
    patient_name: str
    opd_number: str
    blood_group: Optional[str]
    baseline_allergies: Optional[str]
    baseline_conditions: Optional[str]
    
    # Grouped history by category
    surgical_history: List[MedicalHistoryEntryResponse] = []
    family_history: List[MedicalHistoryEntryResponse] = []
    social_history: List[MedicalHistoryEntryResponse] = []
    immunizations: List[MedicalHistoryEntryResponse] = []
    allergies: List[MedicalHistoryEntryResponse] = []
    chronic_conditions: List[MedicalHistoryEntryResponse] = []
    past_medical_events: List[MedicalHistoryEntryResponse] = []
    obstetric_history: List[MedicalHistoryEntryResponse] = []
    mental_health: List[MedicalHistoryEntryResponse] = []
    
    # Recent clinical encounters
    recent_visits: List[Dict[str, Any]] = []
    consents: List[ConsentResponse] = []

    class Config:
        from_attributes = True
