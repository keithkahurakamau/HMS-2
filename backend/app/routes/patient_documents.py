"""Reprintable document archive for a patient.

Every printed document in MediFleet (invoice, prescription, lab report,
radiology report, admission slip, visit summary) is generated on demand from
live records rather than stored as a file. That means a reprint is always
faithful to the current chart — and it also means there was no single place to
answer "what has this patient been given, and can I print it again?".

This module provides that: one chronological index of everything printable for
a patient, plus a per-document endpoint returning exactly the payload the
matching frontend print template expects, so the UI stays a thin dispatcher.

Reprints are PHI access. Both endpoints write a KDPA Section 26 DataAccessLog
row, the same as opening the chart itself.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config.database import get_db
from app.core.dependencies import RequirePermission, get_current_user
from app.models.billing import Invoice
from app.models.clinical import MedicalRecord
from app.models.laboratory import LabTest
from app.models.patient import Patient
from app.models.radiology import RadiologyRequest
from app.models.user import User
from app.models.wards import AdmissionRecord, Bed, Ward
from app.routes.clinical import _parse_prescriptions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patients", tags=["Patient Documents"])

# Document kinds this archive can reprint. The value is the label shown in the
# UI; the key is what the frontend switches on to pick a print template.
DOCUMENT_KINDS = {
    "invoice": "Invoice / Receipt",
    "prescription": "Prescription",
    "lab_report": "Laboratory Report",
    "radiology_report": "Radiology Report",
    "admission": "Admission / Discharge",
    "visit_summary": "Visit Summary",
}

MAX_PER_KIND = 200


# ── Helpers ─────────────────────────────────────────────────────────────────
def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _age(dob: Optional[date]) -> Optional[int]:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _patient_block(p: Patient) -> Dict[str, Any]:
    """The shared patient panel every print template renders."""
    return {
        "patient_id": p.patient_id,
        "full_name": f"{p.surname} {p.other_names}".strip(),
        "outpatient_no": p.outpatient_no,
        "sex": p.sex,
        "date_of_birth": _iso(p.date_of_birth),
        "age": _age(p.date_of_birth),
        "blood_group": p.blood_group,
        "allergies": p.allergies,
    }


def _get_patient(db: Session, patient_id: int) -> Patient:
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return patient


def _log_access(db: Session, request: Request, current_user: dict,
                patient_id: int, reason: str) -> None:
    from app.routes.medical_history import _log_data_access
    _log_data_access(
        db, current_user["user_id"], patient_id,
        str(request.client.host if request.client else "unknown"), reason,
    )


def _user_name(db: Session, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    user = db.query(User).filter(User.user_id == user_id).first()
    return user.full_name if user else None


# ── Index ───────────────────────────────────────────────────────────────────
@router.get("/{patient_id}/documents",
            dependencies=[Depends(RequirePermission("history:read"))])
def list_patient_documents(
    patient_id: int,
    request: Request,
    kind: Optional[str] = Query(None, description="Filter to a single document kind"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Every printable document for this patient, newest first.

    Descriptors only — the payload for an actual reprint is fetched per
    document, so a patient with years of history doesn't drag their whole
    archive over the wire to render a list.
    """
    if kind and kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown document kind '{kind}'.")

    patient = _get_patient(db, patient_id)
    wanted = {kind} if kind else set(DOCUMENT_KINDS)
    docs: List[Dict[str, Any]] = []

    if "invoice" in wanted:
        invoices = (db.query(Invoice)
                    .filter(Invoice.patient_id == patient_id)
                    .order_by(Invoice.billing_date.desc())
                    .limit(MAX_PER_KIND).all())
        for inv in invoices:
            total = float(inv.total_amount or 0)
            paid = float(inv.amount_paid or 0)
            settled = paid >= total and total > 0
            docs.append({
                "kind": "invoice",
                "id": inv.invoice_id,
                "title": f"{'Receipt' if settled else 'Invoice'} INV-{inv.invoice_id}",
                "date": _iso(inv.billing_date),
                "summary": f"KES {total:,.2f}",
                "status": inv.status,
            })

    # Prescriptions and visit summaries both come off MedicalRecord; a record
    # only yields a prescription when the doctor actually prescribed something.
    if {"prescription", "visit_summary"} & wanted:
        records = (db.query(MedicalRecord)
                   .filter(MedicalRecord.patient_id == patient_id)
                   .order_by(MedicalRecord.created_at.desc())
                   .limit(MAX_PER_KIND).all())
        for rec in records:
            if "visit_summary" in wanted:
                docs.append({
                    "kind": "visit_summary",
                    "id": rec.record_id,
                    "title": f"Visit summary #{rec.record_id}",
                    "date": _iso(rec.created_at),
                    "summary": rec.diagnosis or rec.chief_complaint or "Clinical encounter",
                    "status": rec.record_status,
                })
            if "prescription" in wanted and rec.treatment_plan:
                items = _parse_prescriptions(rec.treatment_plan)
                if items:
                    docs.append({
                        "kind": "prescription",
                        "id": rec.record_id,
                        "title": f"Prescription RX-{rec.record_id}",
                        "date": _iso(rec.created_at),
                        "summary": f"{len(items)} item{'s' if len(items) != 1 else ''}",
                        "status": rec.record_status,
                    })

    if "lab_report" in wanted:
        tests = (db.query(LabTest)
                 .filter(LabTest.patient_id == patient_id)
                 .order_by(LabTest.requested_at.desc())
                 .limit(MAX_PER_KIND).all())
        for t in tests:
            docs.append({
                "kind": "lab_report",
                "id": t.test_id,
                "title": t.test_name or "Laboratory test",
                "date": _iso(t.requested_at),
                "summary": t.result_summary or "Awaiting result",
                "status": t.status,
            })

    if "radiology_report" in wanted:
        reqs = (db.query(RadiologyRequest)
                .options(joinedload(RadiologyRequest.result))
                .filter(RadiologyRequest.patient_id == patient_id)
                .order_by(RadiologyRequest.created_at.desc())
                .limit(MAX_PER_KIND).all())
        for r in reqs:
            docs.append({
                "kind": "radiology_report",
                "id": r.request_id,
                "title": r.exam_type or "Radiology exam",
                "date": _iso(r.created_at),
                "summary": (r.result.conclusion if r.result else None) or "Awaiting report",
                "status": r.status,
            })

    if "admission" in wanted:
        admissions = (db.query(AdmissionRecord)
                      .filter(AdmissionRecord.patient_id == patient_id)
                      .order_by(AdmissionRecord.admitted_at.desc())
                      .limit(MAX_PER_KIND).all())
        for a in admissions:
            discharged = (a.status or "").lower() == "discharged"
            docs.append({
                "kind": "admission",
                "id": a.admission_id,
                "title": f"{'Discharge summary' if discharged else 'Admission slip'} ADM-{a.admission_id}",
                "date": _iso(a.admitted_at),
                "summary": a.primary_diagnosis or "—",
                "status": a.status,
            })

    # Undated rows (rare, legacy imports) sort last rather than crashing the
    # comparison against timezone-aware ISO strings.
    docs.sort(key=lambda d: (d["date"] is not None, d["date"] or ""), reverse=True)

    _log_access(db, request, current_user, patient_id,
                f"Document archive listed by {current_user['role']} ({current_user['full_name']})")
    db.commit()

    return {
        "patient": _patient_block(patient),
        "kinds": DOCUMENT_KINDS,
        "documents": docs,
        "total": len(docs),
    }


# ── Single document, ready to print ─────────────────────────────────────────
@router.get("/{patient_id}/documents/{kind}/{doc_id}",
            dependencies=[Depends(RequirePermission("history:read"))])
def get_patient_document(
    patient_id: int,
    kind: str,
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """The payload for one reprint, shaped for the matching print template."""
    if kind not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown document kind '{kind}'.")

    patient = _get_patient(db, patient_id)
    block = _patient_block(patient)
    payload: Dict[str, Any]

    if kind == "invoice":
        inv = (db.query(Invoice)
               .options(joinedload(Invoice.items))
               .filter(Invoice.invoice_id == doc_id,
                       Invoice.patient_id == patient_id).first())
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found for this patient.")
        payload = {
            "invoice_id": inv.invoice_id,
            "patient_name": block["full_name"],
            "patient_opd": block["outpatient_no"],
            "total_amount": float(inv.total_amount or 0),
            "amount_paid": float(inv.amount_paid or 0),
            "status": inv.status,
            "billing_date": _iso(inv.billing_date),
            "items": [{"description": i.description, "item_type": i.item_type,
                       "amount": float(i.amount or 0)} for i in inv.items],
        }

    elif kind in ("prescription", "visit_summary"):
        rec = db.query(MedicalRecord).filter(
            MedicalRecord.record_id == doc_id,
            MedicalRecord.patient_id == patient_id).first()
        if not rec:
            raise HTTPException(status_code=404, detail="Medical record not found for this patient.")
        doctor = _user_name(db, rec.doctor_id)
        if kind == "prescription":
            items = _parse_prescriptions(rec.treatment_plan) if rec.treatment_plan else []
            if not items:
                raise HTTPException(status_code=404,
                                    detail="That visit has no prescription to reprint.")
            payload = {"patient": block, "doctor": doctor, "items": items,
                       "notes": rec.prescription_notes, "recordId": rec.record_id}
        else:
            payload = {
                "patient": block,
                "record": {
                    "record_id": rec.record_id,
                    "date": _iso(rec.created_at),
                    "doctor": doctor,
                    "record_status": rec.record_status,
                    "chief_complaint": rec.chief_complaint,
                    "diagnosis": rec.diagnosis,
                    "assessment_plan": rec.assessment_plan,
                    "icd10_code": rec.icd10_code,
                    "follow_up_date": _iso(rec.follow_up_date),
                    "vitals": {
                        "blood_pressure": rec.blood_pressure,
                        "heart_rate": rec.heart_rate,
                        "temperature": rec.temperature,
                        "spo2": rec.spo2,
                        "weight_kg": rec.weight_kg,
                    },
                },
            }

    elif kind == "lab_report":
        test = db.query(LabTest).filter(
            LabTest.test_id == doc_id, LabTest.patient_id == patient_id).first()
        if not test:
            raise HTTPException(status_code=404, detail="Lab test not found for this patient.")
        payload = {
            "patient": block,
            "test": {
                "test_id": test.test_id, "test_name": test.test_name,
                "status": test.status, "priority": test.priority,
                "result_summary": test.result_summary,
                "result_data": test.result_data,
                "specimen_id": test.specimen_id,
                "specimen_type": test.specimen_type,
                "clinical_notes": test.clinical_notes,
                "requested_at": _iso(test.requested_at),
                "completed_at": _iso(test.completed_at),
            },
            "performedBy": _user_name(db, test.performed_by_id),
            "orderedBy": _user_name(db, test.ordered_by),
        }

    elif kind == "radiology_report":
        req = (db.query(RadiologyRequest)
               .options(joinedload(RadiologyRequest.result))
               .filter(RadiologyRequest.request_id == doc_id,
                       RadiologyRequest.patient_id == patient_id).first())
        if not req:
            raise HTTPException(status_code=404, detail="Radiology request not found for this patient.")
        res = req.result
        payload = {
            "patient": block,
            "request": {
                "request_id": req.request_id,
                # The print template reads `modality`; this schema keeps the
                # whole exam description in exam_type, so map it across.
                "modality": req.exam_type,
                "exam_type": req.exam_type,
                "body_part": None,
                "status": req.status, "priority": req.priority,
                "clinical_notes": req.clinical_notes,
                "created_at": _iso(req.created_at),
            },
            "result": None if not res else {
                "findings": res.findings,
                "conclusion": res.conclusion,
                "contrast_used": res.contrast_used,
                "reported_at": _iso(res.created_at),
            },
            "radiologist": _user_name(db, res.performed_by) if res else None,
        }

    else:  # admission
        adm = db.query(AdmissionRecord).filter(
            AdmissionRecord.admission_id == doc_id,
            AdmissionRecord.patient_id == patient_id).first()
        if not adm:
            raise HTTPException(status_code=404, detail="Admission not found for this patient.")
        bed = db.query(Bed).filter(Bed.bed_id == adm.bed_id).first()
        ward = db.query(Ward).filter(Ward.ward_id == bed.ward_id).first() if bed else None
        payload = {
            "patient": block,
            "admission": {
                "admission_id": adm.admission_id,
                "primary_diagnosis": adm.primary_diagnosis,
                "status": adm.status,
                "admitted_at": _iso(adm.admitted_at),
                "discharged_at": _iso(adm.discharged_at),
                "discharge_notes": adm.discharge_notes,
                "ward_name": ward.name if ward else None,
                "bed_number": getattr(bed, "bed_number", None) if bed else None,
            },
            "doctor": _user_name(db, adm.admitting_doctor_id),
        }

    _log_access(db, request, current_user, patient_id,
                f"Reprinted {DOCUMENT_KINDS[kind]} #{doc_id} "
                f"by {current_user['role']} ({current_user['full_name']})")
    db.commit()

    return {"kind": kind, "id": doc_id, "payload": payload}
