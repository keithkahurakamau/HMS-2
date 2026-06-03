from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from typing import Optional
from datetime import date, datetime


class _PatientNorm(BaseModel):
    """Shared normalizers for the patient request schemas.

    A blank email is the common case for walk-in patients, and the front-end
    sends the field as an empty string rather than omitting it. EmailStr rejects
    "" with a cryptic 422 ("must have an @-sign"), so coerce empty/whitespace to
    None *before* validation — the column is nullable and the route's
    _normalize_blanks already treats null as "not provided". check_fields=False
    lets this live on the mixin even though `email` is declared on the children.
    """
    @field_validator("email", mode="before", check_fields=False)
    @classmethod
    def _blank_email_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

# Audit PER-001: the patient registration / update routes previously took
# `patient_data: dict`, then mass-assigned every supplied key onto the
# SQLAlchemy Patient model via setattr(...). Anything the Patient ORM has
# (e.g. is_active, registered_by, outpatient_no) was rewritable from a
# client request. Locking `extra="forbid"` here makes the request contract
# explicit — any unknown field is a 422, not a silent mass-assign.
_STRICT = ConfigDict(extra="forbid")


class PatientCreate(_PatientNorm):
    model_config = _STRICT
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

    # Insurance
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None

class PatientUpdate(_PatientNorm):
    model_config = _STRICT
    surname: Optional[str] = None
    other_names: Optional[str] = None
    sex: Optional[str] = None
    date_of_birth: Optional[date] = None
    marital_status: Optional[str] = None
    religion: Optional[str] = None
    primary_language: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    nationality: Optional[str] = None
    telephone_1: Optional[str] = None
    telephone_2: Optional[str] = None
    email: Optional[EmailStr] = None
    postal_address: Optional[str] = None
    postal_code: Optional[str] = None
    residence: Optional[str] = None
    town: Optional[str] = None
    occupation: Optional[str] = None
    employer_name: Optional[str] = None
    reference_number: Optional[str] = None
    nok_name: Optional[str] = None
    nok_relationship: Optional[str] = None
    nok_contact: Optional[str] = None
    notes: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_policy_number: Optional[str] = None
    is_active: Optional[bool] = None

class PatientResponse(PatientCreate):
    patient_id: int
    outpatient_no: str
    inpatient_no: Optional[str] = None
    is_active: bool
    registered_on: datetime
    registered_by: int
    
    class Config:
        from_attributes = True