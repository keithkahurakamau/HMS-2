"""Labor admissions + append-only partograph.

Time zero (`active_labor_started_at`) anchors the WHO alert line: expected
dilation = 4 cm + 1 cm/hour. The action line runs 4 hours right of the alert
line. Entries plotting past a line notify ward staff (wards:manage holders).

Partograph rows are APPEND-ONLY by design: there are no update or delete
endpoints, and corrections are new rows pointing at the superseded row.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.maternity import LaborAdmission, PartographEntry, PregnancyEpisode
from app.models.patient import Patient
from app.models.wards import AdmissionRecord
from app.utils.audit import log_audit
from app.utils.notify import notify, users_with_permission

router = APIRouter(prefix="/api/maternity", tags=["Maternity"])


def alert_status(dilation_cm: Optional[float], hours_since_active: Optional[float]) -> str:
    """WHO partograph zones. 'ok' left of the alert line, 'alert' between the
    lines, 'action' right of the action line (alert + 4h)."""
    if dilation_cm is None or hours_since_active is None or hours_since_active < 0:
        return "ok"
    expected_alert = 4.0 + hours_since_active
    expected_action = 4.0 + max(0.0, hours_since_active - 4.0)
    if dilation_cm >= expected_alert:
        return "ok"
    if dilation_cm >= expected_action:
        return "alert"
    return "action"


class LaborLink(BaseModel):
    admission_id: int
    active_labor_started_at: Optional[datetime] = None


class PartographCreate(BaseModel):
    recorded_at: Optional[datetime] = None
    cervical_dilation_cm: Optional[float] = Field(default=None, ge=0, le=10)
    descent_fifths: Optional[int] = Field(default=None, ge=0, le=5)
    contractions_per_10min: Optional[int] = Field(default=None, ge=0, le=10)
    contraction_duration_sec: Optional[int] = Field(default=None, ge=0, le=600)
    fetal_heart_rate: Optional[int] = Field(default=None, ge=40, le=240)
    liquor: Optional[str] = Field(default=None, max_length=4)
    moulding: Optional[str] = Field(default=None, max_length=4)
    maternal_bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    maternal_bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    maternal_pulse: Optional[int] = Field(default=None, ge=20, le=250)
    temperature_c: Optional[float] = Field(default=None, ge=30, le=45)
    drugs_note: Optional[str] = Field(default=None, max_length=255)
    corrects_entry_id: Optional[int] = None


def _entry_dict(e: PartographEntry, active_start: Optional[datetime]) -> dict:
    hours = None
    if active_start and e.recorded_at:
        hours = (e.recorded_at - active_start).total_seconds() / 3600.0
    return {
        "entry_id": e.entry_id,
        "recorded_at": e.recorded_at.isoformat() if e.recorded_at else None,
        "hours_since_active": round(hours, 2) if hours is not None else None,
        "cervical_dilation_cm": float(e.cervical_dilation_cm) if e.cervical_dilation_cm is not None else None,
        "descent_fifths": e.descent_fifths,
        "contractions_per_10min": e.contractions_per_10min,
        "contraction_duration_sec": e.contraction_duration_sec,
        "fetal_heart_rate": e.fetal_heart_rate,
        "liquor": e.liquor,
        "moulding": e.moulding,
        "maternal_bp_systolic": e.maternal_bp_systolic,
        "maternal_bp_diastolic": e.maternal_bp_diastolic,
        "maternal_pulse": e.maternal_pulse,
        "temperature_c": float(e.temperature_c) if e.temperature_c is not None else None,
        "drugs_note": e.drugs_note,
        "corrects_entry_id": e.corrects_entry_id,
        "alert_status": alert_status(
            float(e.cervical_dilation_cm) if e.cervical_dilation_cm is not None else None,
            hours,
        ),
    }


@router.post("/episodes/{episode_id}/labor", dependencies=[Depends(RequirePermission("maternity:manage"))])
def link_labor(episode_id: int, req: LaborLink, request: Request,
               db: Session = Depends(get_db),
               current_user: dict = Depends(get_current_user)):
    ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Pregnancy episode not found")
    adm = db.query(AdmissionRecord).filter(AdmissionRecord.admission_id == req.admission_id).first()
    if not adm:
        raise HTTPException(status_code=404, detail="Admission not found")
    if adm.patient_id != ep.patient_id:
        raise HTTPException(status_code=400, detail="Admission belongs to a different patient")
    if adm.status != "Active":
        raise HTTPException(status_code=400, detail="Admission is not Active")
    if db.query(LaborAdmission).filter(LaborAdmission.admission_id == req.admission_id).first():
        raise HTTPException(status_code=409, detail="Admission is already linked to a labor record")

    active_labor_started_at = req.active_labor_started_at
    if active_labor_started_at is not None and active_labor_started_at.tzinfo is None:
        active_labor_started_at = active_labor_started_at.replace(tzinfo=timezone.utc)

    la = LaborAdmission(episode_id=episode_id, admission_id=req.admission_id,
                        active_labor_started_at=active_labor_started_at)
    try:
        db.add(la)
        db.flush()
        log_audit(db, current_user["user_id"], "CREATE", "LaborAdmission", la.labor_admission_id,
                  None, {"episode_id": episode_id, "admission_id": req.admission_id},
                  request.client.host)
        db.commit()
    except IntegrityError:
        # Race: concurrent POST passed the pre-check SELECT; the unique index caught the duplicate.
        db.rollback()
        raise HTTPException(status_code=409,
                            detail="Admission is already linked to a labor record.")
    return {
        "labor_admission_id": la.labor_admission_id,
        "episode_id": episode_id,
        "admission_id": req.admission_id,
        "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
    }


def _get_labor_or_404(db: Session, labor_admission_id: int) -> LaborAdmission:
    la = db.query(LaborAdmission).filter(LaborAdmission.labor_admission_id == labor_admission_id).first()
    if not la:
        raise HTTPException(status_code=404, detail="Labor record not found")
    return la


@router.post("/labor/{labor_admission_id}/partograph", dependencies=[Depends(RequirePermission("maternity:manage"))])
def append_partograph_entry(labor_admission_id: int, req: PartographCreate, request: Request,
                            db: Session = Depends(get_db),
                            current_user: dict = Depends(get_current_user)):
    la = _get_labor_or_404(db, labor_admission_id)
    if req.corrects_entry_id is not None:
        target = (
            db.query(PartographEntry)
            .filter(PartographEntry.entry_id == req.corrects_entry_id,
                    PartographEntry.labor_admission_id == labor_admission_id)
            .first()
        )
        if not target:
            raise HTTPException(status_code=404, detail="Entry to correct not found on this labor record")

    recorded_at = req.recorded_at or datetime.now(timezone.utc)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    entry = PartographEntry(
        labor_admission_id=labor_admission_id,
        recorded_at=recorded_at,
        cervical_dilation_cm=req.cervical_dilation_cm,
        descent_fifths=req.descent_fifths,
        contractions_per_10min=req.contractions_per_10min,
        contraction_duration_sec=req.contraction_duration_sec,
        fetal_heart_rate=req.fetal_heart_rate,
        liquor=req.liquor,
        moulding=req.moulding,
        maternal_bp_systolic=req.maternal_bp_systolic,
        maternal_bp_diastolic=req.maternal_bp_diastolic,
        maternal_pulse=req.maternal_pulse,
        temperature_c=req.temperature_c,
        drugs_note=req.drugs_note,
        corrects_entry_id=req.corrects_entry_id,
        recorded_by=current_user["user_id"],
    )
    db.add(entry)

    # First >= 4 cm observation anchors time zero.
    if (la.active_labor_started_at is None
            and req.cervical_dilation_cm is not None
            and req.cervical_dilation_cm >= 4.0):
        la.active_labor_started_at = recorded_at

    db.flush()

    hours = None
    if la.active_labor_started_at:
        hours = (recorded_at - la.active_labor_started_at).total_seconds() / 3600.0
    status = alert_status(req.cervical_dilation_cm, hours)
    if status in ("alert", "action"):
        ep = db.query(PregnancyEpisode).filter(PregnancyEpisode.episode_id == la.episode_id).first()
        patient = db.query(Patient).filter(Patient.patient_id == ep.patient_id).first() if ep else None
        pname = f"{patient.surname}, {patient.other_names}" if patient else f"episode #{la.episode_id}"
        for uid in users_with_permission(db, "wards:manage", exclude_roles=("Admin",)):
            notify(
                db, user_id=uid, category="warning",
                title=f"Partograph {status}-line crossing — {pname}"[:255],
                body=f"Dilation {req.cervical_dilation_cm} cm at {round(hours or 0, 1)} h of active labor.",
                link="/app/maternity",
            )

    log_audit(db, current_user["user_id"], "CREATE", "PartographEntry", entry.entry_id,
              None, {"labor_admission_id": labor_admission_id, "alert_status": status},
              request.client.host)
    db.commit()
    return _entry_dict(entry, la.active_labor_started_at)


@router.get("/labor/{labor_admission_id}/partograph", dependencies=[Depends(RequirePermission("maternity:read"))])
def list_partograph(labor_admission_id: int, db: Session = Depends(get_db)):
    la = _get_labor_or_404(db, labor_admission_id)
    entries = (
        db.query(PartographEntry)
        .filter(PartographEntry.labor_admission_id == labor_admission_id)
        .order_by(PartographEntry.recorded_at, PartographEntry.entry_id)
        .all()
    )
    superseded_ids = {e.corrects_entry_id for e in entries if e.corrects_entry_id}
    out = []
    for e in entries:
        d = _entry_dict(e, la.active_labor_started_at)
        d["superseded"] = e.entry_id in superseded_ids
        out.append(d)
    return {
        "labor_admission_id": labor_admission_id,
        "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
        "entries": out,
    }


@router.get("/board", dependencies=[Depends(RequirePermission("maternity:read"))])
def labor_board(db: Session = Depends(get_db)):
    from app.models.maternity import DeliveryRecord

    rows = (
        db.query(LaborAdmission, PregnancyEpisode, AdmissionRecord)
        .join(PregnancyEpisode, PregnancyEpisode.episode_id == LaborAdmission.episode_id)
        .join(AdmissionRecord, AdmissionRecord.admission_id == LaborAdmission.admission_id)
        .filter(AdmissionRecord.status == "Active")
        .all()
    )
    if not rows:
        return []

    episode_ids = [ep.episode_id for _, ep, _ in rows]
    delivered = {
        eid for (eid,) in db.query(DeliveryRecord.episode_id)
        .filter(DeliveryRecord.episode_id.in_(episode_ids)).all()
    }
    patient_ids = [ep.patient_id for _, ep, _ in rows]
    patients = {
        p.patient_id: p for p in
        db.query(Patient).filter(Patient.patient_id.in_(patient_ids)).all()
    }
    labor_ids = [la.labor_admission_id for la, _, _ in rows]
    entries = (
        db.query(PartographEntry)
        .filter(PartographEntry.labor_admission_id.in_(labor_ids))
        .order_by(PartographEntry.labor_admission_id,
                  PartographEntry.recorded_at.desc(),
                  PartographEntry.entry_id.desc())
        .all()
    )
    # Build the set of superseded entry IDs (entries that are corrected by other entries).
    superseded_ids = {e.corrects_entry_id for e in entries if e.corrects_entry_id}
    latest_by_labor = {}
    for e in entries:
        # Skip superseded entries; the newest non-superseded entry wins.
        if e.entry_id not in superseded_ids:
            latest_by_labor.setdefault(e.labor_admission_id, e)

    out = []
    for la, ep, adm in rows:
        if ep.episode_id in delivered:
            continue
        p = patients.get(ep.patient_id)
        latest = latest_by_labor.get(la.labor_admission_id)
        latest_dict = None
        if latest:
            d = _entry_dict(latest, la.active_labor_started_at)
            latest_dict = {
                "recorded_at": d["recorded_at"],
                "cervical_dilation_cm": d["cervical_dilation_cm"],
                "fetal_heart_rate": d["fetal_heart_rate"],
                "alert_status": d["alert_status"],
            }
        out.append({
            "labor_admission_id": la.labor_admission_id,
            "episode_id": ep.episode_id,
            "patient_id": ep.patient_id,
            "patient_name": f"{p.surname}, {p.other_names}" if p else None,
            "admission_id": adm.admission_id,
            "active_labor_started_at": la.active_labor_started_at.isoformat() if la.active_labor_started_at else None,
            "latest": latest_dict,
        })
    return out
