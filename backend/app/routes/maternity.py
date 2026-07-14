"""Maternity module: pregnancy episodes, ANC/PNC visits, deliveries, newborns.

Labor + partograph endpoints live in maternity_labor.py (same module key).
Every write is audit-logged. Charges ride app.services.maternity_billing.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.maternity import (
    AncVisit, DeliveryRecord, LaborAdmission, NewbornRecord,
    PncVisit, PregnancyEpisode,
)
from app.models.patient import Patient
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])

VALID_CLOSE_STATUS = {"Closed", "Transferred"}


class EpisodeCreate(BaseModel):
    patient_id: int
    gravida: int = Field(1, ge=1, le=30)
    para: int = Field(0, ge=0, le=30)
    lmp: Optional[date] = None
    edd: Optional[date] = None
    blood_group: Optional[str] = Field(default=None, max_length=8)
    rhesus: Optional[str] = Field(default=None, max_length=4)
    risk_flags: Optional[str] = None


class EpisodeClose(BaseModel):
    status: str
    reason: Optional[str] = None


def _episode_dict(db: Session, ep: PregnancyEpisode) -> dict:
    patient = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first()
    return {
        "episode_id": ep.episode_id,
        "patient_id": ep.patient_id,
        "patient_name": f"{patient.surname}, {patient.other_names}" if patient else None,
        "gravida": ep.gravida,
        "para": ep.para,
        "lmp": ep.lmp.isoformat() if ep.lmp else None,
        "edd": ep.edd.isoformat() if ep.edd else None,
        "blood_group": ep.blood_group,
        "rhesus": ep.rhesus,
        "risk_flags": ep.risk_flags,
        "status": ep.status,
        "created_at": ep.created_at.isoformat() if ep.created_at else None,
    }


def _get_episode_or_404(db: Session, episode_id: int) -> PregnancyEpisode:
    ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Pregnancy episode not found")
    return ep


@router.post("/episodes", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_episode(req: EpisodeCreate, request: Request, db: Session = Depends(get_db),
                   current_user: dict = Depends(get_current_user)):
    patient = db.query(Patient).filter(Patient.patient_id == req.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    active = (
        db.query(PregnancyEpisode)
        .filter(PregnancyEpisode.patient_id == req.patient_id,
                PregnancyEpisode.status == "Active")
        .first()
    )
    if active:
        raise HTTPException(status_code=409,
                            detail=f"Patient already has an Active pregnancy episode (#{active.episode_id}).")
    edd = req.edd or (req.lmp + timedelta(days=280) if req.lmp else None)
    ep = PregnancyEpisode(
        patient_id=req.patient_id, gravida=req.gravida, para=req.para,
        lmp=req.lmp, edd=edd, blood_group=req.blood_group, rhesus=req.rhesus,
        risk_flags=req.risk_flags, created_by=current_user["user_id"],
    )
    try:
        db.add(ep)
        db.flush()
        log_audit(db, current_user["user_id"], "CREATE", "PregnancyEpisode", ep.episode_id,
                  None, {"patient_id": req.patient_id, "gravida": req.gravida},
                  request.client.host)
        db.commit()
    except IntegrityError:
        # Race: concurrent POST passed the pre-check SELECT; the unique index caught the duplicate.
        db.rollback()
        raise HTTPException(status_code=409,
                            detail="Patient already has an Active pregnancy episode.")
    db.refresh(ep)
    return _episode_dict(db, ep)


@router.get("/episodes", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_episodes(status: Optional[str] = None, patient_id: Optional[int] = None,
                  db: Session = Depends(get_db)):
    q = db.query(PregnancyEpisode)
    if status:
        q = q.filter(PregnancyEpisode.status == status)
    if patient_id:
        q = q.filter(PregnancyEpisode.patient_id == patient_id)
    eps = q.order_by(PregnancyEpisode.created_at.desc()).limit(200).all()
    return [_episode_dict(db, ep) for ep in eps]


@router.get("/episodes/{episode_id}", dependencies=[Depends(RequirePermission("maternity:read"))])
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    ep = _get_episode_or_404(db, episode_id)
    body = _episode_dict(db, ep)
    body["anc_visits"] = [
        {
            "visit_id": v.visit_id, "visit_number": v.visit_number,
            "visit_date": v.visit_date.isoformat(), "gestation_weeks": v.gestation_weeks,
            "bp_systolic": v.bp_systolic, "bp_diastolic": v.bp_diastolic,
            "weight_kg": float(v.weight_kg) if v.weight_kg is not None else None,
            "fundal_height_cm": float(v.fundal_height_cm) if v.fundal_height_cm is not None else None,
            "fetal_heart_rate": v.fetal_heart_rate, "urine_dip": v.urine_dip,
            "notes": v.notes,
        }
        for v in sorted(ep.anc_visits, key=lambda v: (v.visit_date, v.visit_id))
    ]
    body["pnc_visits"] = [
        {
            "visit_id": v.visit_id, "visit_number": v.visit_number,
            "visit_date": v.visit_date.isoformat(),
            "bp_systolic": v.bp_systolic, "bp_diastolic": v.bp_diastolic,
            "involution": v.involution, "lochia": v.lochia, "feeding": v.feeding,
            "cord_status": v.cord_status, "baby_weight_g": v.baby_weight_g,
            "notes": v.notes,
        }
        for v in sorted(ep.pnc_visits, key=lambda v: (v.visit_date, v.visit_id))
    ]
    deliveries = (
        db.query(DeliveryRecord)
        .filter(DeliveryRecord.episode_id == episode_id)
        .order_by(DeliveryRecord.delivered_at)
        .all()
    )
    body["deliveries"] = [
        {
            "delivery_id": d.delivery_id,
            "delivered_at": d.delivered_at.isoformat(),
            "mode": d.mode, "mother_status": d.mother_status,
            "blood_loss_ml": d.blood_loss_ml, "complications": d.complications,
            "newborns": [
                {
                    "newborn_id": n.newborn_id, "birth_order": n.birth_order,
                    "sex": n.sex, "weight_g": n.weight_g, "outcome": n.outcome,
                    "apgar_1": n.apgar_1, "apgar_5": n.apgar_5,
                    "registered_patient_id": n.registered_patient_id,
                }
                for n in sorted(d.newborns, key=lambda n: n.birth_order)
            ],
        }
        for d in deliveries
    ]
    body["labor"] = [
        {
            "labor_admission_id": la.labor_admission_id,
            "admission_id": la.admission_id,
            "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
        }
        for la in db.query(LaborAdmission).filter(LaborAdmission.episode_id == episode_id).all()
    ]
    return body


@router.patch("/episodes/{episode_id}/close", dependencies=[Depends(RequirePermission("maternity:manage"))])
def close_episode(episode_id: int, req: EpisodeClose, request: Request,
                  db: Session = Depends(get_db),
                  current_user: dict = Depends(get_current_user)):
    if req.status not in VALID_CLOSE_STATUS:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {sorted(VALID_CLOSE_STATUS)}")
    ep = _get_episode_or_404(db, episode_id)
    old = ep.status
    from sqlalchemy.sql import func as _func
    ep.status = req.status
    ep.closed_at = _func.now()
    log_audit(db, current_user["user_id"], "UPDATE", "PregnancyEpisode", ep.episode_id,
              {"status": old}, {"status": req.status, "reason": req.reason},
              request.client.host)
    db.commit()
    db.refresh(ep)
    return _episode_dict(db, ep)
