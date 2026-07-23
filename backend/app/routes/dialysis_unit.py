"""Dialysis Phase 2 — unit management: vascular-access registry, machines,
recurring schedule roster, patient renal profile, and per-session consumables.

Same module key ("dialysis") + DB-backed RBAC as routes/dialysis.py. Every
write is audit-logged. Registered as a second router in main.py (the
maternity / maternity_labor split convention).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.dialysis import (
    DialysisConsumable, DialysisMachine, DialysisOrder, DialysisSchedule, VascularAccess,
)
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/dialysis", tags=["Dialysis"])

_ACTIVE_STATUSES = ("Ordered", "Connected", "Disconnected")
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pattern_includes(pattern: str, weekday_idx: int) -> bool:
    if pattern == "Daily":
        return True
    if pattern == "MWF":
        return weekday_idx in (0, 2, 4)
    if pattern == "TTS":
        return weekday_idx in (1, 3, 5)
    return False  # Custom patterns aren't auto-expanded onto the roster


def _f(v):
    return float(v) if v is not None else None


# ─── Pydantic ───────────────────────────────────────────────────────────────
class VascularAccessCreate(BaseModel):
    patient_id: int
    type: str = Field(min_length=1, max_length=30)
    site: Optional[str] = Field(default=None, max_length=80)
    created_date: Optional[date] = None
    status: str = "Active"
    notes: Optional[str] = None
    complications: Optional[str] = None


class VascularAccessUpdate(BaseModel):
    type: Optional[str] = Field(default=None, max_length=30)
    site: Optional[str] = Field(default=None, max_length=80)
    status: Optional[str] = None
    last_assessed: Optional[date] = None
    notes: Optional[str] = None
    complications: Optional[str] = None


class MachineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    station: Optional[str] = Field(default=None, max_length=40)
    is_active: bool = True


class MachineUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    model: Optional[str] = Field(default=None, max_length=80)
    station: Optional[str] = Field(default=None, max_length=40)
    is_active: Optional[bool] = None
    last_serviced: Optional[date] = None


class ScheduleCreate(BaseModel):
    patient_id: int
    pattern: str = Field(min_length=1, max_length=20)
    shift: Optional[str] = Field(default=None, max_length=20)
    sessions_per_week: Optional[int] = None
    preferred_machine_id: Optional[int] = None
    target_dry_weight_kg: Optional[float] = None
    start_date: Optional[date] = None
    status: str = "Active"


class ScheduleUpdate(BaseModel):
    pattern: Optional[str] = Field(default=None, max_length=20)
    shift: Optional[str] = Field(default=None, max_length=20)
    sessions_per_week: Optional[int] = None
    preferred_machine_id: Optional[int] = None
    target_dry_weight_kg: Optional[float] = None
    status: Optional[str] = None


class ConsumableCreate(BaseModel):
    item_id: Optional[int] = None
    item_name: Optional[str] = Field(default=None, max_length=120)
    qty: Optional[float] = None
    dialyzer_reuse_count: Optional[int] = None


# ─── Serializers ────────────────────────────────────────────────────────────
def _access_dict(a: VascularAccess) -> dict:
    return {
        "access_id": a.access_id, "patient_id": a.patient_id, "type": a.type, "site": a.site,
        "status": a.status,
        "created_date": a.created_date.isoformat() if a.created_date else None,
        "last_assessed": a.last_assessed.isoformat() if a.last_assessed else None,
        "complications": a.complications, "notes": a.notes,
    }


def _machine_dict(m: DialysisMachine) -> dict:
    return {
        "machine_id": m.machine_id, "name": m.name, "model": m.model, "station": m.station,
        "is_active": m.is_active,
        "last_serviced": m.last_serviced.isoformat() if m.last_serviced else None,
        "hours_run": m.hours_run,
    }


def _schedule_dict(s: DialysisSchedule) -> dict:
    return {
        "schedule_id": s.schedule_id, "patient_id": s.patient_id, "pattern": s.pattern,
        "shift": s.shift, "sessions_per_week": s.sessions_per_week,
        "preferred_machine_id": s.preferred_machine_id,
        "target_dry_weight_kg": _f(s.target_dry_weight_kg),
        "start_date": s.start_date.isoformat() if s.start_date else None, "status": s.status,
    }


def _consumable_dict(c: DialysisConsumable) -> dict:
    return {
        "consumable_id": c.consumable_id, "item_id": c.item_id, "item_name": c.item_name,
        "qty": _f(c.qty), "dialyzer_reuse_count": c.dialyzer_reuse_count,
    }


def _ip(request: Request):
    return request.client.host if request.client else None


# ─── Vascular access ────────────────────────────────────────────────────────
@router.get("/vascular-accesses", dependencies=[Depends(RequirePermission("dialysis:read"))])
def list_vascular_accesses(patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(VascularAccess)
    if patient_id:
        q = q.filter(VascularAccess.patient_id == patient_id)
    return [_access_dict(a) for a in q.order_by(VascularAccess.created_at.desc()).limit(200).all()]


@router.post("/vascular-accesses", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def create_vascular_access(req: VascularAccessCreate, request: Request, db: Session = Depends(get_db),
                           current_user: dict = Depends(get_current_user)):
    if not db.query(Patient).filter(Patient.patient_id == req.patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")
    a = VascularAccess(**req.model_dump(), created_by=current_user["user_id"])
    db.add(a)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "VascularAccess", a.access_id,
              None, {"patient_id": req.patient_id, "type": req.type}, _ip(request))
    db.commit()
    db.refresh(a)
    return _access_dict(a)


@router.put("/vascular-accesses/{access_id}", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def update_vascular_access(access_id: int, req: VascularAccessUpdate, request: Request,
                           db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    a = db.query(VascularAccess).filter(VascularAccess.access_id == access_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Vascular access not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(a, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "VascularAccess", a.access_id, None, data, _ip(request))
    db.commit()
    db.refresh(a)
    return _access_dict(a)


# ─── Machines ───────────────────────────────────────────────────────────────
@router.get("/machines", dependencies=[Depends(RequirePermission("dialysis:read"))])
def list_machines(db: Session = Depends(get_db)):
    return [_machine_dict(m) for m in db.query(DialysisMachine).order_by(DialysisMachine.machine_id).all()]


@router.post("/machines", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def create_machine(req: MachineCreate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    m = DialysisMachine(**req.model_dump())
    db.add(m)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisMachine", m.machine_id,
              None, {"name": req.name}, _ip(request))
    db.commit()
    db.refresh(m)
    return _machine_dict(m)


@router.put("/machines/{machine_id}", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def update_machine(machine_id: int, req: MachineUpdate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    m = db.query(DialysisMachine).filter(DialysisMachine.machine_id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(m, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "DialysisMachine", m.machine_id, None, data, _ip(request))
    db.commit()
    db.refresh(m)
    return _machine_dict(m)


# ─── Schedules ──────────────────────────────────────────────────────────────
@router.get("/schedules", dependencies=[Depends(RequirePermission("dialysis:read"))])
def list_schedules(patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(DialysisSchedule)
    if patient_id:
        q = q.filter(DialysisSchedule.patient_id == patient_id)
    return [_schedule_dict(s) for s in q.order_by(DialysisSchedule.schedule_id.desc()).limit(200).all()]


@router.post("/schedules", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def create_schedule(req: ScheduleCreate, request: Request, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    if not db.query(Patient).filter(Patient.patient_id == req.patient_id).first():
        raise HTTPException(status_code=404, detail="Patient not found")
    s = DialysisSchedule(**req.model_dump(), created_by=current_user["user_id"])
    db.add(s)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisSchedule", s.schedule_id,
              None, {"patient_id": req.patient_id, "pattern": req.pattern}, _ip(request))
    db.commit()
    db.refresh(s)
    return _schedule_dict(s)


@router.put("/schedules/{schedule_id}", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def update_schedule(schedule_id: int, req: ScheduleUpdate, request: Request, db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    s = db.query(DialysisSchedule).filter(DialysisSchedule.schedule_id == schedule_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "DialysisSchedule", s.schedule_id, None, data, _ip(request))
    db.commit()
    db.refresh(s)
    return _schedule_dict(s)


# ─── Roster (chair occupancy for a day) ─────────────────────────────────────
@router.get("/roster", dependencies=[Depends(RequirePermission("dialysis:read"))])
def roster(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    day = date.fromisoformat(date_str) if date_str else date.today()
    weekday_idx = day.weekday()

    machines = db.query(DialysisMachine).filter(DialysisMachine.is_active == True).all()  # noqa: E712
    active_orders = (
        db.query(DialysisOrder)
        .filter(DialysisOrder.status.in_(_ACTIVE_STATUSES), DialysisOrder.machine_id.isnot(None))
        .all()
    )
    order_by_machine = {o.machine_id: o for o in active_orders}
    pt_ids = {o.patient_id for o in active_orders}

    schedules = db.query(DialysisSchedule).filter(DialysisSchedule.status == "Active").all()
    scheduled = [s for s in schedules if _pattern_includes(s.pattern, weekday_idx)]
    pt_ids |= {s.patient_id for s in scheduled}

    patients = {
        p.patient_id: f"{p.surname}, {p.other_names}"
        for p in db.query(Patient).filter(Patient.patient_id.in_(pt_ids)).all()
    } if pt_ids else {}

    return {
        "date": day.isoformat(),
        "weekday": _WEEKDAYS[weekday_idx],
        "machines": [
            {
                **_machine_dict(m),
                "current_order": (
                    {"order_id": order_by_machine[m.machine_id].order_id,
                     "patient_name": patients.get(order_by_machine[m.machine_id].patient_id),
                     "status": order_by_machine[m.machine_id].status}
                    if m.machine_id in order_by_machine else None
                ),
            }
            for m in machines
        ],
        "scheduled": [
            {**_schedule_dict(s), "patient_name": patients.get(s.patient_id)} for s in scheduled
        ],
    }


# ─── Renal profile (longitudinal) ───────────────────────────────────────────
@router.get("/patients/{patient_id}/renal-profile", dependencies=[Depends(RequirePermission("dialysis:read"))])
def renal_profile(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    accesses = (
        db.query(VascularAccess).filter(VascularAccess.patient_id == patient_id)
        .order_by(VascularAccess.created_at.desc()).all()
    )
    schedule = (
        db.query(DialysisSchedule)
        .filter(DialysisSchedule.patient_id == patient_id, DialysisSchedule.status == "Active")
        .first()
    )
    orders = (
        db.query(DialysisOrder).filter(DialysisOrder.patient_id == patient_id)
        .order_by(DialysisOrder.created_at.desc()).limit(10).all()
    )
    adequacy_trend = [
        {"order_id": o.order_id,
         "completed_at": o.completed_at.isoformat() if o.completed_at else None,
         "urr": _f(o.adequacy.urr), "kt_v": _f(o.adequacy.kt_v)}
        for o in orders if o.adequacy is not None
    ]
    return {
        "patient_id": patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}",
        "accesses": [_access_dict(a) for a in accesses],
        "schedule": _schedule_dict(schedule) if schedule else None,
        "adequacy_trend": adequacy_trend,
        "recent_sessions": [
            {"order_id": o.order_id, "status": o.status, "treatment_no": o.treatment_no,
             "created_at": o.created_at.isoformat() if o.created_at else None}
            for o in orders
        ],
    }


# ─── Consumables ────────────────────────────────────────────────────────────
@router.post("/orders/{order_id}/consumables", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def add_consumable(order_id: int, req: ConsumableCreate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    if not db.query(DialysisOrder).filter(DialysisOrder.order_id == order_id).first():
        raise HTTPException(status_code=404, detail="Dialysis order not found")
    c = DialysisConsumable(order_id=order_id, **req.model_dump())
    db.add(c)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisConsumable", c.consumable_id,
              None, {"order_id": order_id, "item_name": req.item_name}, _ip(request))
    db.commit()
    db.refresh(c)
    return _consumable_dict(c)
