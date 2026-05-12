from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Radiology Exam Catalog
# ─────────────────────────────────────────────────────────────────────────────
class RadiologyCatalogBase(BaseModel):
    exam_name: str
    modality: str
    body_part: Optional[str] = None
    description: Optional[str] = None
    base_price: float = 0
    requires_prep: bool = False
    requires_contrast: bool = False
    default_findings_template: Optional[str] = None
    default_impression_template: Optional[str] = None
    is_active: bool = True


class RadiologyCatalogCreate(RadiologyCatalogBase):
    pass


class RadiologyCatalogPatch(BaseModel):
    exam_name: Optional[str] = None
    modality: Optional[str] = None
    body_part: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    requires_prep: Optional[bool] = None
    requires_contrast: Optional[bool] = None
    default_findings_template: Optional[str] = None
    default_impression_template: Optional[str] = None
    is_active: Optional[bool] = None


class RadiologyCatalogResponse(RadiologyCatalogBase):
    catalog_id: int

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Radiology Result
# ─────────────────────────────────────────────────────────────────────────────
class RadiologyResultCreate(BaseModel):
    findings: str
    conclusion: str
    image_url: Optional[str] = None
    contrast_used: Optional[str] = None


class RadiologyResultResponse(RadiologyResultCreate):
    result_id: int
    request_id: int
    performed_by: int
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Radiology Request
# ─────────────────────────────────────────────────────────────────────────────
class RadiologyRequestCreate(BaseModel):
    patient_id: int
    exam_type: str
    catalog_id: Optional[int] = None
    clinical_notes: Optional[str] = None
    priority: str = "Routine"


class RadiologyRequestUpdate(BaseModel):
    status: str


class RadiologyRequestResponse(BaseModel):
    request_id: int
    patient_id: int
    requested_by: int
    catalog_id: Optional[int] = None
    exam_type: str
    clinical_notes: Optional[str] = None
    priority: str = "Routine"
    billed_price: Optional[float] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    result: Optional[RadiologyResultResponse] = None

    class Config:
        from_attributes = True
