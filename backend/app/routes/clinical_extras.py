"""Clinical-desk extras: sick notes, optical prescriptions, external requests,
and order sets. RBAC clinical:read / clinical:write; every write audit-logged.
Follows the module route conventions (inline Pydantic, add->flush->audit->commit).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.clinical_extras import (
    ExternalRequest, OpticalPrescription, OrderSet, OrderSetItem, SickNote,
)
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/clinical-extras", tags=["Clinical Extras"])

EXTERNAL_TYPES = {"Lab", "Radiology", "Referral", "Other"}
ORDER_ITEM_TYPES = {"Lab", "Radiology", "Drug"}


def _ip(request: Request):
    return request.client.host if request.client else None


def _require_patient(db: Session, patient_id: int) -> Patient:
    p = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


# ─── Sick notes ─────────────────────────────────────────────────────────────
class SickNoteCreate(BaseModel):
    patient_id: int
    diagnosis: Optional[str] = Field(default=None, max_length=255)
    start_date: date
    end_date: date
    days: Optional[int] = None
    recommendation: Optional[str] = None
    fit_for_duty: bool = False


def _sick_dict(s: SickNote) -> dict:
    return {"sick_note_id": s.sick_note_id, "patient_id": s.patient_id, "diagnosis": s.diagnosis,
            "start_date": s.start_date.isoformat() if s.start_date else None,
            "end_date": s.end_date.isoformat() if s.end_date else None, "days": s.days,
            "recommendation": s.recommendation, "fit_for_duty": s.fit_for_duty,
            "created_at": s.created_at.isoformat() if s.created_at else None}


@router.post("/sick-notes", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_sick_note(req: SickNoteCreate, request: Request, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    _require_patient(db, req.patient_id)
    days = req.days if req.days is not None else (req.end_date - req.start_date).days + 1
    s = SickNote(**req.model_dump(exclude={"days"}), days=days, issued_by=current_user["user_id"])
    db.add(s)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SickNote", s.sick_note_id,
              None, {"patient_id": req.patient_id, "days": days}, _ip(request))
    db.commit()
    db.refresh(s)
    return _sick_dict(s)


@router.get("/sick-notes", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_sick_notes(patient_id: int, db: Session = Depends(get_db)):
    rows = (db.query(SickNote).filter(SickNote.patient_id == patient_id)
            .order_by(SickNote.created_at.desc()).limit(100).all())
    return [_sick_dict(s) for s in rows]


# ─── Optical prescriptions ──────────────────────────────────────────────────
class OpticalCreate(BaseModel):
    patient_id: int
    right_sphere: Optional[str] = None
    right_cylinder: Optional[str] = None
    right_axis: Optional[str] = None
    right_add: Optional[str] = None
    left_sphere: Optional[str] = None
    left_cylinder: Optional[str] = None
    left_axis: Optional[str] = None
    left_add: Optional[str] = None
    pd: Optional[str] = None
    notes: Optional[str] = None


def _optical_dict(o: OpticalPrescription) -> dict:
    return {
        "optical_id": o.optical_id, "patient_id": o.patient_id,
        "right_sphere": o.right_sphere, "right_cylinder": o.right_cylinder,
        "right_axis": o.right_axis, "right_add": o.right_add,
        "left_sphere": o.left_sphere, "left_cylinder": o.left_cylinder,
        "left_axis": o.left_axis, "left_add": o.left_add, "pd": o.pd, "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.post("/optical-prescriptions", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_optical(req: OpticalCreate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    _require_patient(db, req.patient_id)
    o = OpticalPrescription(**req.model_dump(), issued_by=current_user["user_id"])
    db.add(o)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "OpticalPrescription", o.optical_id,
              None, {"patient_id": req.patient_id}, _ip(request))
    db.commit()
    db.refresh(o)
    return _optical_dict(o)


@router.get("/optical-prescriptions", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_optical(patient_id: int, db: Session = Depends(get_db)):
    rows = (db.query(OpticalPrescription).filter(OpticalPrescription.patient_id == patient_id)
            .order_by(OpticalPrescription.created_at.desc()).limit(100).all())
    return [_optical_dict(o) for o in rows]


# ─── External requests ──────────────────────────────────────────────────────
class ExternalCreate(BaseModel):
    patient_id: int
    facility: Optional[str] = Field(default=None, max_length=160)
    request_type: str
    details: Optional[str] = None
    reason: Optional[str] = None


def _external_dict(e: ExternalRequest) -> dict:
    return {"request_id": e.request_id, "patient_id": e.patient_id, "facility": e.facility,
            "request_type": e.request_type, "details": e.details, "reason": e.reason,
            "created_at": e.created_at.isoformat() if e.created_at else None}


@router.post("/external-requests", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_external(req: ExternalCreate, request: Request, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    _require_patient(db, req.patient_id)
    if req.request_type not in EXTERNAL_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid request_type '{req.request_type}'.")
    e = ExternalRequest(**req.model_dump(), issued_by=current_user["user_id"])
    db.add(e)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "ExternalRequest", e.request_id,
              None, {"patient_id": req.patient_id, "type": req.request_type}, _ip(request))
    db.commit()
    db.refresh(e)
    return _external_dict(e)


@router.get("/external-requests", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_external(patient_id: int, db: Session = Depends(get_db)):
    rows = (db.query(ExternalRequest).filter(ExternalRequest.patient_id == patient_id)
            .order_by(ExternalRequest.created_at.desc()).limit(100).all())
    return [_external_dict(e) for e in rows]


# ─── Order sets (config; applied client-side to pre-fill orders) ────────────
class OrderSetItemIn(BaseModel):
    item_type: str
    name: str = Field(min_length=1, max_length=160)
    ref_code: Optional[str] = Field(default=None, max_length=60)


class OrderSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=255)
    items: List[OrderSetItemIn] = []


def _order_set_dict(s: OrderSet) -> dict:
    return {
        "order_set_id": s.order_set_id, "name": s.name, "description": s.description,
        "is_active": s.is_active,
        "items": [{"item_id": i.item_id, "item_type": i.item_type, "name": i.name, "ref_code": i.ref_code}
                  for i in s.items],
    }


@router.get("/order-sets", dependencies=[Depends(RequirePermission("clinical:read"))])
def list_order_sets(db: Session = Depends(get_db)):
    rows = db.query(OrderSet).order_by(OrderSet.order_set_id).all()
    return [_order_set_dict(s) for s in rows]


@router.post("/order-sets", dependencies=[Depends(RequirePermission("clinical:write"))])
def create_order_set(req: OrderSetCreate, request: Request, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    for it in req.items:
        if it.item_type not in ORDER_ITEM_TYPES:
            raise HTTPException(status_code=422, detail=f"Invalid item_type '{it.item_type}'.")
    s = OrderSet(name=req.name, description=req.description)
    db.add(s)
    db.flush()
    for it in req.items:
        db.add(OrderSetItem(order_set_id=s.order_set_id, item_type=it.item_type, name=it.name, ref_code=it.ref_code))
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "OrderSet", s.order_set_id,
              None, {"name": req.name, "items": len(req.items)}, _ip(request))
    db.commit()
    db.refresh(s)
    return _order_set_dict(s)


@router.get("/order-sets/{order_set_id}", dependencies=[Depends(RequirePermission("clinical:read"))])
def get_order_set(order_set_id: int, db: Session = Depends(get_db)):
    s = db.query(OrderSet).filter(OrderSet.order_set_id == order_set_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Order set not found")
    return _order_set_dict(s)
