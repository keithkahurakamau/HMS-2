"""Maternity module: pregnancy episodes, ANC/PNC visits, deliveries, newborns.

Labor + partograph endpoints live in maternity_labor.py (same module key).
Every write is audit-logged. Charges ride app.services.maternity_billing.
"""
from datetime import date, datetime, timedelta
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
from app.services.maternity_billing import raise_maternity_charge
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


class AncVisitCreate(BaseModel):
    visit_date: date
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=300)
    fundal_height_cm: Optional[float] = Field(default=None, ge=4, le=60)
    fetal_heart_rate: Optional[int] = Field(default=None, ge=60, le=220)
    urine_dip: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = None


class PncVisitCreate(BaseModel):
    visit_date: date
    newborn_id: Optional[int] = None
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=300)
    involution: Optional[str] = Field(default=None, max_length=40)
    lochia: Optional[str] = Field(default=None, max_length=40)
    feeding: Optional[str] = Field(default=None, max_length=40)
    cord_status: Optional[str] = Field(default=None, max_length=40)
    baby_weight_g: Optional[int] = Field(default=None, ge=200, le=9000)
    urine_dip: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = None


@router.post("/episodes/{episode_id}/anc-visits", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_anc_visit(episode_id: int, req: AncVisitCreate, request: Request,
                     db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    ep = _get_episode_or_404(db, episode_id)
    if ep.status != "Active":
        raise HTTPException(status_code=400, detail=f"Episode is {ep.status}; ANC visits need an Active episode.")
    count = db.query(AncVisit).filter(AncVisit.episode_id == episode_id).count()
    gestation = None
    if ep.lmp:
        gestation = max(0, (req.visit_date - ep.lmp).days // 7)
    visit = AncVisit(
        episode_id=episode_id, visit_number=count + 1, visit_date=req.visit_date,
        gestation_weeks=gestation, bp_systolic=req.bp_systolic,
        bp_diastolic=req.bp_diastolic, weight_kg=req.weight_kg,
        fundal_height_cm=req.fundal_height_cm, fetal_heart_rate=req.fetal_heart_rate,
        urine_dip=req.urine_dip, notes=req.notes,
        recorded_by=current_user["user_id"],
    )
    db.add(visit)
    db.flush()
    raise_maternity_charge(
        db, patient_id=ep.patient_id, service_code="MAT-ANC-VISIT",
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "AncVisit", visit.visit_id,
              None, {"episode_id": episode_id, "visit_date": req.visit_date.isoformat()},
              request.client.host)
    db.commit()
    return {
        "visit_id": visit.visit_id, "visit_number": visit.visit_number,
        "visit_date": visit.visit_date.isoformat(),
        "gestation_weeks": visit.gestation_weeks,
    }


@router.post("/episodes/{episode_id}/pnc-visits", dependencies=[Depends(RequirePermission("maternity:manage"))])
def create_pnc_visit(episode_id: int, req: PncVisitCreate, request: Request,
                     db: Session = Depends(get_db),
                     current_user: dict = Depends(get_current_user)):
    ep = _get_episode_or_404(db, episode_id)
    if req.newborn_id is not None:
        nb = db.query(NewbornRecord).filter(NewbornRecord.newborn_id == req.newborn_id).first()
        if not nb:
            raise HTTPException(status_code=404, detail="Newborn record not found")
    count = db.query(PncVisit).filter(PncVisit.episode_id == episode_id).count()
    visit = PncVisit(
        episode_id=episode_id, newborn_id=req.newborn_id,
        visit_number=count + 1, visit_date=req.visit_date,
        bp_systolic=req.bp_systolic, bp_diastolic=req.bp_diastolic,
        weight_kg=req.weight_kg, involution=req.involution, lochia=req.lochia,
        feeding=req.feeding, cord_status=req.cord_status,
        baby_weight_g=req.baby_weight_g, urine_dip=req.urine_dip,
        notes=req.notes, recorded_by=current_user["user_id"],
    )
    db.add(visit)
    db.flush()
    raise_maternity_charge(
        db, patient_id=ep.patient_id, service_code="MAT-PNC-VISIT",
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "PncVisit", visit.visit_id,
              None, {"episode_id": episode_id, "visit_date": req.visit_date.isoformat()},
              request.client.host)
    db.commit()
    return {
        "visit_id": visit.visit_id, "visit_number": visit.visit_number,
        "visit_date": visit.visit_date.isoformat(),
    }


VALID_DELIVERY_MODES = {"SVD": "MAT-DEL-SVD", "Assisted": "MAT-DEL-ASSISTED",
                        "CSection": "MAT-DEL-CS", "Breech": "MAT-DEL-BREECH"}
VALID_MOTHER_STATUS = {"Stable", "Referred", "Deceased"}
VALID_OUTCOME = {"Live", "FSB", "MSB"}


class NewbornCreate(BaseModel):
    birth_order: int = Field(1, ge=1, le=8)
    sex: str = Field(..., max_length=10)
    weight_g: Optional[int] = Field(default=None, ge=200, le=9000)
    apgar_1: Optional[int] = Field(default=None, ge=0, le=10)
    apgar_5: Optional[int] = Field(default=None, ge=0, le=10)
    apgar_10: Optional[int] = Field(default=None, ge=0, le=10)
    outcome: str = "Live"
    resuscitated: bool = False
    notes: Optional[str] = None


class DeliveryCreate(BaseModel):
    delivered_at: datetime
    mode: str
    labor_admission_id: Optional[int] = None
    placenta_complete: Optional[bool] = None
    blood_loss_ml: Optional[int] = Field(default=None, ge=0, le=10000)
    perineum: Optional[str] = Field(default=None, max_length=40)
    complications: Optional[str] = None
    mother_status: str = "Stable"
    newborns: List[NewbornCreate]


@router.post("/episodes/{episode_id}/delivery", dependencies=[Depends(RequirePermission("maternity:manage"))])
def record_delivery(episode_id: int, req: DeliveryCreate, request: Request,
                    db: Session = Depends(get_db),
                    current_user: dict = Depends(get_current_user)):
    if req.mode not in VALID_DELIVERY_MODES:
        raise HTTPException(status_code=400,
                            detail=f"mode must be one of {sorted(VALID_DELIVERY_MODES)}")
    if req.mother_status not in VALID_MOTHER_STATUS:
        raise HTTPException(status_code=400,
                            detail=f"mother_status must be one of {sorted(VALID_MOTHER_STATUS)}")
    if not req.newborns:
        raise HTTPException(status_code=400, detail="At least one newborn record is required")
    for nb in req.newborns:
        if nb.outcome not in VALID_OUTCOME:
            raise HTTPException(status_code=400,
                                detail=f"newborn outcome must be one of {sorted(VALID_OUTCOME)}")
    ep = _get_episode_or_404(db, episode_id)
    existing = db.query(DeliveryRecord).filter(DeliveryRecord.episode_id == episode_id).first()
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"Episode already has delivery #{existing.delivery_id}")
    if req.labor_admission_id is not None:
        la = (
            db.query(LaborAdmission)
            .filter(LaborAdmission.labor_admission_id == req.labor_admission_id,
                    LaborAdmission.episode_id == episode_id)
            .first()
        )
        if not la:
            raise HTTPException(status_code=404, detail="Labor record not found on this episode")

    delivery = DeliveryRecord(
        episode_id=episode_id, labor_admission_id=req.labor_admission_id,
        delivered_at=req.delivered_at, mode=req.mode,
        placenta_complete=req.placenta_complete, blood_loss_ml=req.blood_loss_ml,
        perineum=req.perineum, complications=req.complications,
        mother_status=req.mother_status, conducted_by=current_user["user_id"],
    )
    db.add(delivery)
    db.flush()
    newborn_rows = []
    for i, nb in enumerate(req.newborns, start=1):
        row = NewbornRecord(
            delivery_id=delivery.delivery_id,
            birth_order=nb.birth_order if nb.birth_order else i,
            sex=nb.sex, weight_g=nb.weight_g,
            apgar_1=nb.apgar_1, apgar_5=nb.apgar_5, apgar_10=nb.apgar_10,
            outcome=nb.outcome, resuscitated=nb.resuscitated, notes=nb.notes,
        )
        db.add(row)
        newborn_rows.append(row)
    ep.status = "Delivered"
    db.flush()

    raise_maternity_charge(
        db, patient_id=ep.patient_id,
        service_code=VALID_DELIVERY_MODES[req.mode],
        clinician_name=current_user.get("full_name") or "Clinician",
        user_id=current_user["user_id"],
    )
    log_audit(db, current_user["user_id"], "CREATE", "DeliveryRecord", delivery.delivery_id,
              None, {"episode_id": episode_id, "mode": req.mode,
                     "newborns": len(newborn_rows)},
              request.client.host)
    db.commit()
    return {
        "delivery_id": delivery.delivery_id,
        "episode_id": episode_id,
        "mode": delivery.mode,
        "delivered_at": delivery.delivered_at.isoformat(),
        "newborns": [
            {"newborn_id": n.newborn_id, "birth_order": n.birth_order,
             "sex": n.sex, "outcome": n.outcome}
            for n in newborn_rows
        ],
    }


@router.post("/newborns/{newborn_id}/register-patient",
             dependencies=[Depends(RequirePermission("maternity:manage")),
                           Depends(RequirePermission("patients:write"))])
def register_newborn_as_patient(newborn_id: int, request: Request,
                                db: Session = Depends(get_db),
                                current_user: dict = Depends(get_current_user)):
    nb = db.query(NewbornRecord).filter(NewbornRecord.newborn_id == newborn_id).first()
    if not nb:
        raise HTTPException(status_code=404, detail="Newborn record not found")
    if nb.registered_patient_id:
        raise HTTPException(status_code=409,
                            detail=f"Newborn is already registered as patient #{nb.registered_patient_id}")
    if nb.outcome != "Live":
        raise HTTPException(status_code=400, detail="Only live newborns can be registered as patients")

    delivery = db.query(DeliveryRecord).filter(DeliveryRecord.delivery_id == nb.delivery_id).first()
    ep = _get_episode_or_404(db, delivery.episode_id)
    mother = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first()
    if not mother:
        raise HTTPException(status_code=404, detail="Mother's patient record not found")

    # Reuse the canonical creation path (OP-number generation + write-surface
    # allowlist) — NOT register_patient's endpoint logic, since its phone
    # blind-index dup-check would match the mother (the newborn reuses her
    # telephone_1) and wrongly 400. create_patient_record skips dup-checking
    # by design; this caller owns the transaction and the audit entry below.
    from app.routes.patients import create_patient_record
    baby = create_patient_record(
        db,
        created_by=current_user["user_id"],
        surname=mother.surname,
        other_names=f"Baby of {mother.other_names}".strip()[:150],
        sex=nb.sex,
        date_of_birth=delivery.delivered_at.date(),
        telephone_1=mother.telephone_1,
        nok_name=f"{mother.surname}, {mother.other_names}"[:150],
        nok_contact=mother.telephone_1,
    )
    nb.registered_patient_id = baby.patient_id
    log_audit(db, current_user["user_id"], "CREATE", "Patient", baby.patient_id,
              None, {"source": "newborn_registration", "newborn_id": newborn_id},
              request.client.host)
    db.commit()
    return {"patient_id": baby.patient_id}
