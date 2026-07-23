"""Theatre Phase 2 — surgical team, consumables/implants, post-op recovery
observations, and the theatre schedule board. Same module key ("theatre") +
DB-backed RBAC as routes/theatre.py. Every write is audit-logged.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.theatre import (
    RecoveryObservation, SurgicalCase, SurgicalConsumable, SurgicalTeamMember, TheatreRoom,
)
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/theatre", tags=["Theatre"])

TEAM_ROLES = {"Surgeon", "Assistant", "Anaesthetist", "Scrub-Nurse", "Circulating-Nurse", "Perfusionist"}
_RECOVERY_STATUSES = {"Recovery", "Completed"}
_BOARD_ACTIVE = {"InTheatre", "Recovery"}


def _f(v):
    return float(v) if v is not None else None


def _ip(request: Request):
    return request.client.host if request.client else None


# ─── Pydantic ───────────────────────────────────────────────────────────────
class TeamMemberCreate(BaseModel):
    role: str
    user_id: Optional[int] = None
    name: Optional[str] = Field(default=None, max_length=120)


class ConsumableCreate(BaseModel):
    item_id: Optional[int] = None
    item_name: Optional[str] = Field(default=None, max_length=120)
    qty: Optional[float] = None
    is_implant: bool = False
    serial_no: Optional[str] = Field(default=None, max_length=80)


class RecoveryObsCreate(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    pulse: Optional[int] = None
    spo2: Optional[int] = None
    temperature_c: Optional[float] = None
    pain_score: Optional[int] = None
    consciousness: Optional[str] = Field(default=None, max_length=4)
    notes: Optional[str] = Field(default=None, max_length=255)
    corrects_obs_id: Optional[int] = None


# ─── Serializers ────────────────────────────────────────────────────────────
def _team_dict(m: SurgicalTeamMember) -> dict:
    return {"member_id": m.member_id, "user_id": m.user_id, "name": m.name, "role": m.role}


def _consumable_dict(c: SurgicalConsumable) -> dict:
    return {"consumable_id": c.consumable_id, "item_id": c.item_id, "item_name": c.item_name,
            "qty": _f(c.qty), "is_implant": c.is_implant, "serial_no": c.serial_no}


def _recovery_dict(o: RecoveryObservation) -> dict:
    return {"obs_id": o.obs_id, "recorded_at": o.recorded_at.isoformat() if o.recorded_at else None,
            "bp_systolic": o.bp_systolic, "bp_diastolic": o.bp_diastolic, "pulse": o.pulse,
            "spo2": o.spo2, "temperature_c": _f(o.temperature_c), "pain_score": o.pain_score,
            "consciousness": o.consciousness, "notes": o.notes, "corrects_obs_id": o.corrects_obs_id}


def _get_case_or_404(db: Session, case_id: int) -> SurgicalCase:
    c = db.query(SurgicalCase).filter(SurgicalCase.case_id == case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Surgical case not found")
    return c


# ─── Team ───────────────────────────────────────────────────────────────────
@router.post("/cases/{case_id}/team-members", dependencies=[Depends(RequirePermission("theatre:manage"))])
def add_team_member(case_id: int, req: TeamMemberCreate, request: Request,
                    db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_case_or_404(db, case_id)
    if req.role not in TEAM_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role '{req.role}'.")
    m = SurgicalTeamMember(case_id=case_id, user_id=req.user_id, name=req.name, role=req.role)
    db.add(m)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SurgicalTeamMember", m.member_id,
              None, {"case_id": case_id, "role": req.role}, _ip(request))
    db.commit()
    db.refresh(m)
    return _team_dict(m)


@router.delete("/cases/{case_id}/team-members/{member_id}", dependencies=[Depends(RequirePermission("theatre:manage"))])
def remove_team_member(case_id: int, member_id: int, request: Request,
                       db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    m = db.query(SurgicalTeamMember).filter(
        SurgicalTeamMember.member_id == member_id, SurgicalTeamMember.case_id == case_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Team member not found")
    db.delete(m)
    log_audit(db, current_user["user_id"], "DELETE", "SurgicalTeamMember", member_id,
              {"case_id": case_id}, None, _ip(request))
    db.commit()
    return {"deleted": member_id}


# ─── Consumables / implants ─────────────────────────────────────────────────
@router.post("/cases/{case_id}/consumables", dependencies=[Depends(RequirePermission("theatre:manage"))])
def add_consumable(case_id: int, req: ConsumableCreate, request: Request,
                   db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    _get_case_or_404(db, case_id)
    c = SurgicalConsumable(case_id=case_id, **req.model_dump())
    db.add(c)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "SurgicalConsumable", c.consumable_id,
              None, {"case_id": case_id, "item_name": req.item_name, "is_implant": req.is_implant}, _ip(request))
    db.commit()
    db.refresh(c)
    return _consumable_dict(c)


# ─── Recovery observations (append-only) ────────────────────────────────────
@router.post("/cases/{case_id}/recovery-observations", dependencies=[Depends(RequirePermission("theatre:manage"))])
def add_recovery_obs(case_id: int, req: RecoveryObsCreate, request: Request,
                     db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    c = _get_case_or_404(db, case_id)
    if c.status not in _RECOVERY_STATUSES:
        raise HTTPException(status_code=409, detail=f"Recovery obs only in Recovery/Completed (case is '{c.status}').")
    obs = RecoveryObservation(case_id=case_id, recorded_by=current_user["user_id"], **req.model_dump())
    db.add(obs)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "RecoveryObservation", obs.obs_id,
              None, {"case_id": case_id}, _ip(request))
    db.commit()
    db.refresh(obs)
    return _recovery_dict(obs)


# ─── Schedule board (cases per room for a day) ──────────────────────────────
@router.get("/board", dependencies=[Depends(RequirePermission("theatre:read"))])
def board(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    day = date.fromisoformat(date_str) if date_str else date.today()

    cases = (
        db.query(SurgicalCase)
        .filter(
            (func.date(SurgicalCase.scheduled_at) == day) | (SurgicalCase.status.in_(_BOARD_ACTIVE))
        )
        .order_by(SurgicalCase.scheduled_at.asc().nullslast())
        .all()
    )
    pt_ids = {c.patient_id for c in cases}
    patients = {
        p.patient_id: f"{p.surname}, {p.other_names}"
        for p in db.query(Patient).filter(Patient.patient_id.in_(pt_ids)).all()
    } if pt_ids else {}

    def _c(c):
        return {"case_id": c.case_id, "patient_name": patients.get(c.patient_id),
                "procedure_name": c.procedure_name, "status": c.status,
                "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None}

    rooms = db.query(TheatreRoom).filter(TheatreRoom.is_active == True).all()  # noqa: E712
    by_room = {}
    for c in cases:
        by_room.setdefault(c.theatre_room_id, []).append(c)

    return {
        "date": day.isoformat(),
        "rooms": [
            {"room_id": r.room_id, "name": r.name,
             "cases": [_c(c) for c in by_room.get(r.room_id, [])]}
            for r in rooms
        ],
        "unassigned": [_c(c) for c in by_room.get(None, [])],
    }
