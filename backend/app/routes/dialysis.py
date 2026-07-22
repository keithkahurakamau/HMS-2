"""Dialysis / renal module: session orders, a state machine, append-only
intradialytic observations, complications, adequacy (URR + Kt/V), and machine
safety checklists.

Every write is audit-logged. Follows the maternity module conventions
(inline Pydantic models, add→flush→audit→commit→refresh, DB-backed RBAC).
Unit management (vascular access, schedules, machines, consumables) is Phase 2.
"""
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.dialysis import (
    DialysisAdequacy, DialysisChecklist, DialysisChecklistRun,
    DialysisComplication, DialysisObservation, DialysisOrder,
)
from app.models.patient import Patient
from app.services.dialysis_adequacy import compute_adequacy
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/dialysis", tags=["Dialysis"])

# Session state machine: status → {action → next status}.
_TRANSITIONS = {
    "Ordered":      {"connect": "Connected", "cancel": "Cancelled"},
    "Connected":    {"disconnect": "Disconnected", "cancel": "Cancelled"},
    "Disconnected": {"complete": "Completed"},
}
_OBSERVABLE = {"Connected", "Disconnected"}
COMPLICATION_TYPES = {
    "Hypotension", "Cramps", "Nausea", "Vomiting", "Clotting", "Bleeding",
    "Chest-pain", "Fever", "Disequilibrium",
}
_now = lambda: datetime.now(timezone.utc)  # noqa: E731


# ─── Pydantic request models ────────────────────────────────────────────────
class OrderCreate(BaseModel):
    patient_id: int
    vascular_access_id: Optional[int] = None
    machine_id: Optional[int] = None
    nephrologist_id: Optional[int] = None
    schedule_id: Optional[int] = None
    screening_date: Optional[date] = None
    hiv_hbv_status: Optional[str] = Field(default=None, max_length=20)
    blood_group: Optional[str] = Field(default=None, max_length=8)
    dialyzer: Optional[str] = Field(default=None, max_length=60)
    membrane_type: Optional[str] = Field(default=None, max_length=60)
    priming: Optional[str] = Field(default=None, max_length=60)
    k_bath: Optional[str] = Field(default=None, max_length=20)
    dialysate_calcium: Optional[str] = Field(default=None, max_length=20)
    dialysate_bicarbonate: Optional[str] = Field(default=None, max_length=20)
    dialysate_sodium: Optional[str] = Field(default=None, max_length=20)
    dialysate_temp_c: Optional[float] = None
    blood_flow_target: Optional[int] = None
    dialysate_flow_target: Optional[int] = None
    treatment_time_min: Optional[int] = None
    anticoag_type: Optional[str] = Field(default=None, max_length=20)
    heparin_loading_dose: Optional[str] = Field(default=None, max_length=40)
    heparin_maintenance_dose: Optional[str] = Field(default=None, max_length=40)
    heparin_stop_time: Optional[str] = Field(default=None, max_length=20)
    pre_weight_kg: Optional[float] = None
    dry_weight_kg: Optional[float] = None
    target_uf_ml: Optional[int] = None
    intake_ml: Optional[int] = None
    fluid_removal_goal_ml: Optional[int] = None


class CancelBody(BaseModel):
    reason: str = Field(min_length=1)


class ObservationCreate(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    pulse: Optional[int] = None
    venous_pressure: Optional[int] = None
    arterial_pressure: Optional[int] = None
    tmp: Optional[int] = None
    conductivity: Optional[float] = None
    blood_flow_rate: Optional[int] = None
    dialysate_flow_rate: Optional[int] = None
    uf_volume_ml: Optional[int] = None
    blood_volume_processed_l: Optional[float] = None
    temperature_c: Optional[float] = None
    heparin_note: Optional[str] = Field(default=None, max_length=255)
    corrects_obs_id: Optional[int] = None


class ComplicationCreate(BaseModel):
    type: str
    intervention: Optional[str] = None
    resolved: bool = False


class AdequacyCreate(BaseModel):
    pre_urea: float
    post_urea: float
    session_duration_min: int
    ultrafiltration_actual_ml: int
    post_weight_kg: float
    pre_creatinine: Optional[float] = None
    post_creatinine: Optional[float] = None
    pre_potassium: Optional[float] = None
    post_potassium: Optional[float] = None
    pre_hb: Optional[float] = None


class ChecklistRunCreate(BaseModel):
    checklist_id: Optional[int] = None
    passed: bool
    note: Optional[str] = Field(default=None, max_length=255)


class ChecklistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class ChecklistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


# ─── Serialization helpers ──────────────────────────────────────────────────
def _f(v):
    return float(v) if v is not None else None


def _obs_dict(o: DialysisObservation) -> dict:
    return {
        "obs_id": o.obs_id, "recorded_at": o.recorded_at.isoformat() if o.recorded_at else None,
        "bp_systolic": o.bp_systolic, "bp_diastolic": o.bp_diastolic, "pulse": o.pulse,
        "venous_pressure": o.venous_pressure, "arterial_pressure": o.arterial_pressure,
        "tmp": o.tmp, "conductivity": _f(o.conductivity),
        "blood_flow_rate": o.blood_flow_rate, "dialysate_flow_rate": o.dialysate_flow_rate,
        "uf_volume_ml": o.uf_volume_ml, "blood_volume_processed_l": _f(o.blood_volume_processed_l),
        "temperature_c": _f(o.temperature_c), "heparin_note": o.heparin_note,
        "corrects_obs_id": o.corrects_obs_id,
    }


def _comp_dict(c: DialysisComplication) -> dict:
    return {
        "complication_id": c.complication_id,
        "occurred_at": c.occurred_at.isoformat() if c.occurred_at else None,
        "type": c.type, "intervention": c.intervention, "resolved": c.resolved,
    }


def _adeq_dict(a: DialysisAdequacy) -> dict:
    return {
        "adequacy_id": a.adequacy_id, "pre_urea": _f(a.pre_urea), "post_urea": _f(a.post_urea),
        "pre_creatinine": _f(a.pre_creatinine), "post_creatinine": _f(a.post_creatinine),
        "pre_potassium": _f(a.pre_potassium), "post_potassium": _f(a.post_potassium),
        "pre_hb": _f(a.pre_hb), "ultrafiltration_actual_ml": a.ultrafiltration_actual_ml,
        "session_duration_min": a.session_duration_min, "urr": _f(a.urr), "kt_v": _f(a.kt_v),
    }


def _run_dict(r: DialysisChecklistRun) -> dict:
    return {
        "run_id": r.run_id, "checklist_id": r.checklist_id,
        "passed": r.passed, "note": r.note,
    }


def _order_dict(o: DialysisOrder, patient: Optional[Patient] = None, deep: bool = False) -> dict:
    d = {
        "order_id": o.order_id, "patient_id": o.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "treatment_no": o.treatment_no, "status": o.status,
        "schedule_id": o.schedule_id, "vascular_access_id": o.vascular_access_id,
        "machine_id": o.machine_id, "nephrologist_id": o.nephrologist_id, "ordered_by": o.ordered_by,
        "screening_date": o.screening_date.isoformat() if o.screening_date else None,
        "hiv_hbv_status": o.hiv_hbv_status, "blood_group": o.blood_group,
        "dialyzer": o.dialyzer, "membrane_type": o.membrane_type, "priming": o.priming,
        "k_bath": o.k_bath, "dialysate_calcium": o.dialysate_calcium,
        "dialysate_bicarbonate": o.dialysate_bicarbonate, "dialysate_sodium": o.dialysate_sodium,
        "dialysate_temp_c": _f(o.dialysate_temp_c), "blood_flow_target": o.blood_flow_target,
        "dialysate_flow_target": o.dialysate_flow_target, "treatment_time_min": o.treatment_time_min,
        "anticoag_type": o.anticoag_type, "heparin_loading_dose": o.heparin_loading_dose,
        "heparin_maintenance_dose": o.heparin_maintenance_dose, "heparin_stop_time": o.heparin_stop_time,
        "pre_weight_kg": _f(o.pre_weight_kg), "dry_weight_kg": _f(o.dry_weight_kg),
        "post_weight_kg": _f(o.post_weight_kg), "target_uf_ml": o.target_uf_ml,
        "intake_ml": o.intake_ml, "fluid_removal_goal_ml": o.fluid_removal_goal_ml,
        "connected_at": o.connected_at.isoformat() if o.connected_at else None,
        "disconnected_at": o.disconnected_at.isoformat() if o.disconnected_at else None,
        "completed_at": o.completed_at.isoformat() if o.completed_at else None,
        "cancel_reason": o.cancel_reason,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
    if deep:
        d["observations"] = [_obs_dict(x) for x in sorted(o.observations, key=lambda x: (x.recorded_at, x.obs_id))]
        d["complications"] = [_comp_dict(x) for x in sorted(o.complications, key=lambda x: (x.occurred_at, x.complication_id))]
        d["adequacy"] = _adeq_dict(o.adequacy) if o.adequacy else None
        d["checklist_runs"] = [_run_dict(x) for x in o.checklist_runs]
        d["consumables"] = []  # Phase 2
    return d


def _get_order_or_404(db: Session, order_id: int) -> DialysisOrder:
    o = db.query(DialysisOrder).filter(DialysisOrder.order_id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Dialysis order not found")
    return o


# ─── Orders ─────────────────────────────────────────────────────────────────
@router.post("/orders", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def create_order(req: OrderCreate, request: Request, db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    prior = db.query(DialysisOrder).filter(DialysisOrder.patient_id == req.patient_id).count()
    order = DialysisOrder(
        **req.model_dump(),
        treatment_no=prior + 1,
        ordered_by=current_user["user_id"],
        status="Ordered",
    )
    try:
        db.add(order)
        db.flush()
        log_audit(db, current_user["user_id"], "CREATE", "DialysisOrder", order.order_id,
                  None, {"patient_id": req.patient_id}, request.client.host)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Patient already has a live dialysis session.")
    db.refresh(order)
    return _order_dict(order, patient, deep=True)


@router.get("/orders", dependencies=[Depends(RequirePermission("dialysis:read"))])
def list_orders(status: Optional[str] = None, patient_id: Optional[int] = None,
                db: Session = Depends(get_db)):
    q = db.query(DialysisOrder)
    if status:
        q = q.filter(DialysisOrder.status == status)
    if patient_id:
        q = q.filter(DialysisOrder.patient_id == patient_id)
    orders = q.order_by(DialysisOrder.created_at.desc()).limit(200).all()
    patients_by_id = {}
    if orders:
        ids = {o.patient_id for o in orders}
        patients_by_id = {p.patient_id: p for p in db.query(Patient).filter(Patient.patient_id.in_(ids)).all()}
    return [_order_dict(o, patients_by_id.get(o.patient_id)) for o in orders]


@router.get("/orders/{order_id}", dependencies=[Depends(RequirePermission("dialysis:read"))])
def get_order(order_id: int, db: Session = Depends(get_db)):
    o = _get_order_or_404(db, order_id)
    patient = db.query(Patient).filter(Patient.patient_id == o.patient_id).first()
    return _order_dict(o, patient, deep=True)


# ─── State machine ──────────────────────────────────────────────────────────
_ACTION_TIMESTAMP = {"connect": "connected_at", "disconnect": "disconnected_at", "complete": "completed_at"}


def _transition(db: Session, request: Request, current_user: dict, order_id: int,
                action: str, reason: Optional[str] = None) -> dict:
    o = _get_order_or_404(db, order_id)
    allowed = _TRANSITIONS.get(o.status, {})
    if action not in allowed:
        raise HTTPException(status_code=409, detail=f"Cannot {action} an order in status '{o.status}'.")
    if action == "connect":
        passed = (
            db.query(DialysisChecklistRun)
            .filter(DialysisChecklistRun.order_id == order_id, DialysisChecklistRun.passed == True)  # noqa: E712
            .first()
        )
        if not passed:
            raise HTTPException(status_code=409, detail="Machine safety checklist must pass before connecting.")
    old_status = o.status
    o.status = allowed[action]
    ts_field = _ACTION_TIMESTAMP.get(action)
    if ts_field:
        setattr(o, ts_field, _now())
    if action == "cancel":
        o.cancel_reason = reason
    log_audit(db, current_user["user_id"], "UPDATE", "DialysisOrder", o.order_id,
              {"status": old_status}, {"status": o.status}, request.client.host)
    db.commit()
    db.refresh(o)
    return _order_dict(o, deep=True)


@router.post("/orders/{order_id}/connect", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def connect_order(order_id: int, request: Request, db: Session = Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, order_id, "connect")


@router.post("/orders/{order_id}/disconnect", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def disconnect_order(order_id: int, request: Request, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, order_id, "disconnect")


@router.post("/orders/{order_id}/complete", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def complete_order(order_id: int, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, order_id, "complete")


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def cancel_order(order_id: int, body: CancelBody, request: Request, db: Session = Depends(get_db),
                 current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, order_id, "cancel", reason=body.reason)


# ─── Observations (append-only) + complications ─────────────────────────────
@router.post("/orders/{order_id}/observations", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def add_observation(order_id: int, req: ObservationCreate, request: Request,
                    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    o = _get_order_or_404(db, order_id)
    if o.status not in _OBSERVABLE:
        raise HTTPException(status_code=409, detail=f"Cannot record observations while '{o.status}'.")
    obs = DialysisObservation(order_id=order_id, recorded_by=current_user["user_id"], **req.model_dump())
    db.add(obs)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisObservation", obs.obs_id,
              None, {"order_id": order_id}, request.client.host)
    db.commit()
    db.refresh(obs)
    return _obs_dict(obs)


@router.post("/orders/{order_id}/complications", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def add_complication(order_id: int, req: ComplicationCreate, request: Request,
                     db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_order_or_404(db, order_id)
    if req.type not in COMPLICATION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown complication type '{req.type}'.")
    c = DialysisComplication(order_id=order_id, recorded_by=current_user["user_id"], **req.model_dump())
    db.add(c)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisComplication", c.complication_id,
              None, {"order_id": order_id, "type": req.type}, request.client.host)
    db.commit()
    db.refresh(c)
    return _comp_dict(c)


# ─── Adequacy (URR + Kt/V) ──────────────────────────────────────────────────
@router.post("/orders/{order_id}/adequacy", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def record_adequacy(order_id: int, req: AdequacyCreate, request: Request,
                    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_order_or_404(db, order_id)
    try:
        urr, kt_v = compute_adequacy(
            pre_urea=req.pre_urea, post_urea=req.post_urea,
            hours=req.session_duration_min / 60.0,
            uf_litres=req.ultrafiltration_actual_ml / 1000.0,
            post_weight=req.post_weight_kg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    a = db.query(DialysisAdequacy).filter(DialysisAdequacy.order_id == order_id).first()
    created = a is None
    if a is None:
        a = DialysisAdequacy(order_id=order_id)
        db.add(a)
    a.pre_urea, a.post_urea = req.pre_urea, req.post_urea
    a.pre_creatinine, a.post_creatinine = req.pre_creatinine, req.post_creatinine
    a.pre_potassium, a.post_potassium = req.pre_potassium, req.post_potassium
    a.pre_hb = req.pre_hb
    a.ultrafiltration_actual_ml = req.ultrafiltration_actual_ml
    a.session_duration_min = req.session_duration_min
    a.urr, a.kt_v = urr, kt_v
    a.recorded_by = current_user["user_id"]
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE" if created else "UPDATE",
              "DialysisAdequacy", a.adequacy_id, None, {"urr": urr, "kt_v": kt_v}, request.client.host)
    db.commit()
    db.refresh(a)
    return _adeq_dict(a)


# ─── Checklists (config) + runs ─────────────────────────────────────────────
@router.get("/checklists", dependencies=[Depends(RequirePermission("dialysis:read"))])
def list_checklists(db: Session = Depends(get_db)):
    rows = db.query(DialysisChecklist).order_by(DialysisChecklist.checklist_id).all()
    return [
        {"checklist_id": r.checklist_id, "name": r.name, "description": r.description, "is_active": r.is_active}
        for r in rows
    ]


@router.post("/checklists", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def create_checklist(req: ChecklistCreate, request: Request, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    row = DialysisChecklist(name=req.name, description=req.description, is_active=req.is_active)
    db.add(row)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisChecklist", row.checklist_id,
              None, {"name": req.name}, request.client.host)
    db.commit()
    db.refresh(row)
    return {"checklist_id": row.checklist_id, "name": row.name, "description": row.description, "is_active": row.is_active}


@router.put("/checklists/{checklist_id}", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def update_checklist(checklist_id: int, req: ChecklistUpdate, request: Request,
                     db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    row = db.query(DialysisChecklist).filter(DialysisChecklist.checklist_id == checklist_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Checklist not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "DialysisChecklist", row.checklist_id,
              None, data, request.client.host)
    db.commit()
    db.refresh(row)
    return {"checklist_id": row.checklist_id, "name": row.name, "description": row.description, "is_active": row.is_active}


@router.post("/orders/{order_id}/checklist-runs", dependencies=[Depends(RequirePermission("dialysis:manage"))])
def add_checklist_run(order_id: int, req: ChecklistRunCreate, request: Request,
                      db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_order_or_404(db, order_id)
    run = DialysisChecklistRun(
        order_id=order_id, checklist_id=req.checklist_id,
        passed=req.passed, note=req.note, checked_by=current_user["user_id"],
    )
    db.add(run)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "DialysisChecklistRun", run.run_id,
              None, {"order_id": order_id, "passed": req.passed}, request.client.host)
    db.commit()
    db.refresh(run)
    return _run_dict(run)
