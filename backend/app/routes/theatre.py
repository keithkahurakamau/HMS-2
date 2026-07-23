"""Theatre / surgery module: surgical cases, a WHO-checklist-gated state
machine, operative notes, anaesthesia records, theatre rooms + checklist config.

Every write is audit-logged. Follows the dialysis module conventions (inline
Pydantic, add->flush->audit->commit->refresh, DB-backed RBAC). Team, consumables
and recovery observations are Phase 2 (theatre_unit.py).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.theatre import (
    AnaesthesiaRecord, OperativeNote, SurgicalCase, SurgicalChecklist,
    SurgicalChecklistRun, TheatreRoom,
)
from app.models.patient import Patient
from app.services.theatre_billing import raise_theatre_charge
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/theatre", tags=["Theatre"])

# Case state machine: status -> {action -> next status}.
_TRANSITIONS = {
    "Scheduled": {"start": "InTheatre", "cancel": "Cancelled"},
    "InTheatre": {"to-recovery": "Recovery", "cancel": "Cancelled"},
    "Recovery":  {"complete": "Completed"},
}
PHASES = {"SignIn", "TimeOut", "SignOut"}
PRIORITIES = {"Elective", "Emergency"}
ANAES_TYPES = {"GA", "Spinal", "Epidural", "Local", "Sedation"}
ASA_GRADES = {"I", "II", "III", "IV", "V"}
_now = lambda: datetime.now(timezone.utc)  # noqa: E731


# ─── Pydantic ───────────────────────────────────────────────────────────────
class CaseCreate(BaseModel):
    patient_id: int
    procedure_name: str = Field(min_length=1, max_length=200)
    procedure_code: Optional[str] = Field(default=None, max_length=40)
    diagnosis: Optional[str] = Field(default=None, max_length=255)
    priority: str = "Elective"
    scheduled_at: Optional[datetime] = None
    admission_id: Optional[int] = None
    theatre_room_id: Optional[int] = None
    primary_surgeon_id: Optional[int] = None
    anaesthetist_id: Optional[int] = None


class CancelBody(BaseModel):
    reason: str = Field(min_length=1)


class ChecklistRunCreate(BaseModel):
    phase: str
    checklist_id: Optional[int] = None
    checked: bool
    note: Optional[str] = Field(default=None, max_length=255)


class ChecklistCreate(BaseModel):
    phase: str
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class ChecklistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class OperativeNoteUpsert(BaseModel):
    findings: Optional[str] = None
    procedure_performed: Optional[str] = None
    technique: Optional[str] = None
    closure: Optional[str] = Field(default=None, max_length=255)
    blood_loss_ml: Optional[int] = None
    specimens: Optional[str] = Field(default=None, max_length=255)
    complications: Optional[str] = None
    estimated_duration_min: Optional[int] = None


class AnaesthesiaUpsert(BaseModel):
    type: str
    asa_grade: Optional[str] = None
    agents: Optional[str] = Field(default=None, max_length=255)
    airway: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = None


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    is_active: Optional[bool] = None


# ─── Serializers ────────────────────────────────────────────────────────────
def _f(v):
    return float(v) if v is not None else None


def _run_dict(r: SurgicalChecklistRun) -> dict:
    return {"run_id": r.run_id, "checklist_id": r.checklist_id, "phase": r.phase,
            "checked": r.checked, "note": r.note}


def _opnote_dict(o: OperativeNote) -> dict:
    return {
        "note_id": o.note_id, "findings": o.findings, "procedure_performed": o.procedure_performed,
        "technique": o.technique, "closure": o.closure, "blood_loss_ml": o.blood_loss_ml,
        "specimens": o.specimens, "complications": o.complications,
        "estimated_duration_min": o.estimated_duration_min,
    }


def _anaes_dict(a: AnaesthesiaRecord) -> dict:
    return {"anaesthesia_id": a.anaesthesia_id, "type": a.type, "asa_grade": a.asa_grade,
            "agents": a.agents, "airway": a.airway, "notes": a.notes}


def _case_dict(c: SurgicalCase, patient: Optional[Patient] = None, deep: bool = False) -> dict:
    d = {
        "case_id": c.case_id, "patient_id": c.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "procedure_name": c.procedure_name, "procedure_code": c.procedure_code,
        "diagnosis": c.diagnosis, "priority": c.priority, "status": c.status,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "admission_id": c.admission_id, "theatre_room_id": c.theatre_room_id,
        "primary_surgeon_id": c.primary_surgeon_id, "anaesthetist_id": c.anaesthetist_id,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "cancel_reason": c.cancel_reason,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if deep:
        d["checklist_runs"] = [_run_dict(x) for x in c.checklist_runs]
        d["operative_note"] = _opnote_dict(c.operative_note) if c.operative_note else None
        d["anaesthesia"] = _anaes_dict(c.anaesthesia) if c.anaesthesia else None
        d["team_members"] = [
            {"member_id": m.member_id, "user_id": m.user_id, "name": m.name, "role": m.role}
            for m in c.team_members
        ]
        d["consumables"] = [
            {"consumable_id": x.consumable_id, "item_id": x.item_id, "item_name": x.item_name,
             "qty": _f(x.qty), "is_implant": x.is_implant, "serial_no": x.serial_no}
            for x in c.consumables
        ]
        d["recovery_observations"] = [
            {"obs_id": o.obs_id, "recorded_at": o.recorded_at.isoformat() if o.recorded_at else None,
             "bp_systolic": o.bp_systolic, "bp_diastolic": o.bp_diastolic, "pulse": o.pulse,
             "spo2": o.spo2, "temperature_c": _f(o.temperature_c), "pain_score": o.pain_score,
             "consciousness": o.consciousness, "notes": o.notes}
            for o in sorted(c.recovery_observations, key=lambda o: (o.recorded_at, o.obs_id))
        ]
    return d


def _get_case_or_404(db: Session, case_id: int) -> SurgicalCase:
    c = db.query(SurgicalCase).filter(SurgicalCase.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Surgical case not found")
    return c


# ─── Cases ──────────────────────────────────────────────────────────────────
@router.post("/cases", dependencies=[Depends(RequirePermission("theatre:manage"))])
def create_case(req: CaseCreate, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    if req.priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Invalid priority '{req.priority}'.")
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    case = SurgicalCase(**req.model_dump(), status="Scheduled", created_by=current_user["user_id"])
    db.add(case)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SurgicalCase", case.case_id,
              None, {"patient_id": req.patient_id, "procedure": req.procedure_name}, request.client.host)
    db.commit()
    db.refresh(case)
    return _case_dict(case, patient, deep=True)


@router.get("/cases", dependencies=[Depends(RequirePermission("theatre:read"))])
def list_cases(status: Optional[str] = None, patient_id: Optional[int] = None,
               db: Session = Depends(get_db)):
    q = db.query(SurgicalCase)
    if status:
        q = q.filter(SurgicalCase.status == status)
    if patient_id:
        q = q.filter(SurgicalCase.patient_id == patient_id)
    cases = q.order_by(SurgicalCase.created_at.desc()).limit(200).all()
    patients_by_id = {}
    if cases:
        ids = {c.patient_id for c in cases}
        patients_by_id = {p.patient_id: p for p in db.query(Patient).filter(Patient.patient_id.in_(ids)).all()}
    return [_case_dict(c, patients_by_id.get(c.patient_id)) for c in cases]


@router.get("/cases/{case_id}", dependencies=[Depends(RequirePermission("theatre:read"))])
def get_case(case_id: int, db: Session = Depends(get_db)):
    c = _get_case_or_404(db, case_id)
    patient = db.query(Patient).filter(Patient.patient_id == c.patient_id).first()
    return _case_dict(c, patient, deep=True)


# ─── State machine + WHO gates ──────────────────────────────────────────────
_ACTION_TIMESTAMP = {"start": "started_at", "complete": "ended_at"}


def _phase_passed(db: Session, case_id: int, phase: str) -> bool:
    return db.query(SurgicalChecklistRun).filter(
        SurgicalChecklistRun.case_id == case_id,
        SurgicalChecklistRun.phase == phase,
        SurgicalChecklistRun.checked == True,  # noqa: E712
    ).first() is not None


def _transition(db, request, current_user, case_id, action, reason=None):
    c = _get_case_or_404(db, case_id)
    allowed = _TRANSITIONS.get(c.status, {})
    if action not in allowed:
        raise HTTPException(status_code=409, detail=f"Cannot {action} a case in status '{c.status}'.")
    if action == "start" and not _phase_passed(db, case_id, "TimeOut"):
        raise HTTPException(status_code=409, detail="WHO Time-Out must be completed before starting.")
    if action == "complete" and not _phase_passed(db, case_id, "SignOut"):
        raise HTTPException(status_code=409, detail="WHO Sign-Out must be completed before finishing.")
    old = c.status
    c.status = allowed[action]
    ts = _ACTION_TIMESTAMP.get(action)
    if ts:
        setattr(c, ts, _now())
    if action == "cancel":
        c.cancel_reason = reason
    if action == "complete":
        raise_theatre_charge(db, patient_id=c.patient_id, service_code="THEATRE-MAJOR",
                             clinician_name=current_user.get("full_name") or "Surgeon",
                             user_id=current_user["user_id"])
    log_audit(db, current_user["user_id"], "UPDATE", "SurgicalCase", c.case_id,
              {"status": old}, {"status": c.status}, request.client.host)
    db.commit()
    db.refresh(c)
    return _case_dict(c, deep=True)


@router.post("/cases/{case_id}/start", dependencies=[Depends(RequirePermission("theatre:manage"))])
def start_case(case_id: int, request: Request, db: Session = Depends(get_db),
               current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, case_id, "start")


@router.post("/cases/{case_id}/to-recovery", dependencies=[Depends(RequirePermission("theatre:manage"))])
def to_recovery(case_id: int, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, case_id, "to-recovery")


@router.post("/cases/{case_id}/complete", dependencies=[Depends(RequirePermission("theatre:manage"))])
def complete_case(case_id: int, request: Request, db: Session = Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, case_id, "complete")


@router.post("/cases/{case_id}/cancel", dependencies=[Depends(RequirePermission("theatre:manage"))])
def cancel_case(case_id: int, body: CancelBody, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    return _transition(db, request, current_user, case_id, "cancel", reason=body.reason)


# ─── Checklist runs ─────────────────────────────────────────────────────────
@router.post("/cases/{case_id}/checklist-runs", dependencies=[Depends(RequirePermission("theatre:manage"))])
def add_checklist_run(case_id: int, req: ChecklistRunCreate, request: Request,
                      db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_case_or_404(db, case_id)
    if req.phase not in PHASES:
        raise HTTPException(status_code=422, detail=f"Invalid phase '{req.phase}'.")
    run = SurgicalChecklistRun(case_id=case_id, checklist_id=req.checklist_id, phase=req.phase,
                               checked=req.checked, note=req.note, checked_by=current_user["user_id"])
    db.add(run)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SurgicalChecklistRun", run.run_id,
              None, {"case_id": case_id, "phase": req.phase, "checked": req.checked}, request.client.host)
    db.commit()
    db.refresh(run)
    return _run_dict(run)


# ─── Operative note + anaesthesia (upsert) ──────────────────────────────────
@router.put("/cases/{case_id}/operative-note", dependencies=[Depends(RequirePermission("theatre:manage"))])
def put_operative_note(case_id: int, req: OperativeNoteUpsert, request: Request,
                       db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_case_or_404(db, case_id)
    note = db.query(OperativeNote).filter(OperativeNote.case_id == case_id).first()
    created = note is None
    if note is None:
        note = OperativeNote(case_id=case_id, surgeon_id=current_user["user_id"])
        db.add(note)
    for k, v in req.model_dump().items():
        setattr(note, k, v)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE" if created else "UPDATE",
              "OperativeNote", note.note_id, None, {"case_id": case_id}, request.client.host)
    db.commit()
    db.refresh(note)
    return _opnote_dict(note)


@router.put("/cases/{case_id}/anaesthesia", dependencies=[Depends(RequirePermission("theatre:manage"))])
def put_anaesthesia(case_id: int, req: AnaesthesiaUpsert, request: Request,
                    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_case_or_404(db, case_id)
    if req.type not in ANAES_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid anaesthesia type '{req.type}'.")
    if req.asa_grade is not None and req.asa_grade not in ASA_GRADES:
        raise HTTPException(status_code=422, detail=f"Invalid ASA grade '{req.asa_grade}'.")
    rec = db.query(AnaesthesiaRecord).filter(AnaesthesiaRecord.case_id == case_id).first()
    created = rec is None
    if rec is None:
        rec = AnaesthesiaRecord(case_id=case_id, anaesthetist_id=current_user["user_id"], type=req.type)
        db.add(rec)
    for k, v in req.model_dump().items():
        setattr(rec, k, v)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE" if created else "UPDATE",
              "AnaesthesiaRecord", rec.anaesthesia_id, None, {"case_id": case_id}, request.client.host)
    db.commit()
    db.refresh(rec)
    return _anaes_dict(rec)


# ─── Checklists config ──────────────────────────────────────────────────────
@router.get("/checklists", dependencies=[Depends(RequirePermission("theatre:read"))])
def list_checklists(phase: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(SurgicalChecklist)
    if phase:
        q = q.filter(SurgicalChecklist.phase == phase)
    rows = q.order_by(SurgicalChecklist.checklist_id).all()
    return [{"checklist_id": r.checklist_id, "phase": r.phase, "name": r.name,
             "description": r.description, "is_active": r.is_active} for r in rows]


@router.post("/checklists", dependencies=[Depends(RequirePermission("theatre:manage"))])
def create_checklist(req: ChecklistCreate, request: Request, db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    if req.phase not in PHASES:
        raise HTTPException(status_code=422, detail=f"Invalid phase '{req.phase}'.")
    row = SurgicalChecklist(phase=req.phase, name=req.name, description=req.description, is_active=req.is_active)
    db.add(row)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SurgicalChecklist", row.checklist_id,
              None, {"phase": req.phase, "name": req.name}, request.client.host)
    db.commit()
    db.refresh(row)
    return {"checklist_id": row.checklist_id, "phase": row.phase, "name": row.name,
            "description": row.description, "is_active": row.is_active}


@router.put("/checklists/{checklist_id}", dependencies=[Depends(RequirePermission("theatre:manage"))])
def update_checklist(checklist_id: int, req: ChecklistUpdate, request: Request,
                     db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    row = db.query(SurgicalChecklist).filter(SurgicalChecklist.checklist_id == checklist_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Checklist item not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "SurgicalChecklist", row.checklist_id, None, data, request.client.host)
    db.commit()
    db.refresh(row)
    return {"checklist_id": row.checklist_id, "phase": row.phase, "name": row.name,
            "description": row.description, "is_active": row.is_active}


# ─── Rooms config ───────────────────────────────────────────────────────────
@router.get("/rooms", dependencies=[Depends(RequirePermission("theatre:read"))])
def list_rooms(db: Session = Depends(get_db)):
    return [{"room_id": r.room_id, "name": r.name, "is_active": r.is_active}
            for r in db.query(TheatreRoom).order_by(TheatreRoom.room_id).all()]


@router.post("/rooms", dependencies=[Depends(RequirePermission("theatre:manage"))])
def create_room(req: RoomCreate, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    r = TheatreRoom(name=req.name, is_active=req.is_active)
    db.add(r)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "TheatreRoom", r.room_id, None, {"name": req.name}, request.client.host)
    db.commit()
    db.refresh(r)
    return {"room_id": r.room_id, "name": r.name, "is_active": r.is_active}


@router.put("/rooms/{room_id}", dependencies=[Depends(RequirePermission("theatre:manage"))])
def update_room(room_id: int, req: RoomUpdate, request: Request, db: Session = Depends(get_db),
                current_user: dict = Depends(get_current_user)):
    r = db.query(TheatreRoom).filter(TheatreRoom.room_id == room_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Room not found")
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(r, k, v)
    log_audit(db, current_user["user_id"], "UPDATE", "TheatreRoom", r.room_id, None, data, request.client.host)
    db.commit()
    db.refresh(r)
    return {"room_id": r.room_id, "name": r.name, "is_active": r.is_active}
