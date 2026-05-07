"""
KDPA Subject Rights endpoints:

  - Section 26 — Right to access (data export, machine-readable).
  - Section 40 — Right to erasure / "right to be forgotten" (anonymization
                 because clinical records cannot be hard-deleted under the
                 Health Act 2017's seven-year retention rule).
  - Section 43 — Breach notification scaffolding (managed via /privacy/breaches).

Erasure strategy:
  We do NOT hard-delete patient rows. Doing so would orphan billing, lab,
  pharmacy, and audit FKs that the system relies on. Instead we replace
  identifying fields with deterministic placeholders and flip is_active=False.
  The clinical/billing trail is preserved in pseudonymous form, satisfying
  KDPA and the Health Act simultaneously.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.config.database import get_db
from app.core.dependencies import get_current_user, RequirePermission
from app.models.patient import Patient
from app.models.clinical import MedicalRecord, Appointment, PatientQueue
from app.models.laboratory import LabTest
from app.models.radiology import RadiologyRequest, RadiologyResult
from app.models.billing import Invoice, InvoiceItem
from app.models.medical_history import MedicalHistoryEntry, ConsentRecord, DataAccessLog
from app.models.wards import AdmissionRecord
from app.models.user import User
from app.models.breach import BreachIncident
from app.utils.audit import log_audit


router = APIRouter(prefix="/api/privacy", tags=["KDPA Privacy"])


# =====================================================================
# 1. DATA PORTABILITY — Patient export (KDPA S.26)
# =====================================================================
def _serialize_patient(patient: Patient) -> dict:
    return {
        "outpatient_no": patient.outpatient_no,
        "inpatient_no": patient.inpatient_no,
        "surname": patient.surname,
        "other_names": patient.other_names,
        "sex": patient.sex,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "marital_status": patient.marital_status,
        "religion": patient.religion,
        "primary_language": patient.primary_language,
        "blood_group": patient.blood_group,
        "allergies": patient.allergies,
        "chronic_conditions": patient.chronic_conditions,
        "id_type": patient.id_type,
        "id_number": patient.id_number,
        "nationality": patient.nationality,
        "telephone_1": patient.telephone_1,
        "telephone_2": patient.telephone_2,
        "email": patient.email,
        "postal_address": patient.postal_address,
        "postal_code": patient.postal_code,
        "residence": patient.residence,
        "town": patient.town,
        "occupation": patient.occupation,
        "employer_name": patient.employer_name,
        "nok_name": patient.nok_name,
        "nok_relationship": patient.nok_relationship,
        "nok_contact": patient.nok_contact,
        "insurance_provider": patient.insurance_provider,
        "insurance_policy_number": patient.insurance_policy_number,
        "registered_on": patient.registered_on.isoformat() if patient.registered_on else None,
    }


@router.get("/patients/{patient_id}/export", dependencies=[Depends(RequirePermission("history:read"))])
def export_patient_data(
    patient_id: int,
    request: Request,
    fmt: str = "json",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Returns a portable, machine-readable bundle of every record we hold about
    the patient. Default format JSON; pass ?fmt=csv for a flat CSV manifest.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    # Audit the export — KDPA requires accountability for subject access requests.
    log_audit(
        db, current_user["user_id"], "EXPORT", "Patient", str(patient_id),
        old_value=None, new_value={"format": fmt},
        ip_address=request.client.host if request.client else None,
    )
    db.add(DataAccessLog(
        accessed_by=current_user["user_id"],
        patient_id=patient_id,
        access_reason=f"Subject Access Request — export ({fmt})",
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()

    bundle = {
        "kdpa_export_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": {"user_id": current_user["user_id"], "role": current_user["role"]},
        "patient": _serialize_patient(patient),
        "consents": [
            {
                "consent_id": c.consent_id,
                "type": c.consent_type,
                "given": c.consent_given,
                "method": c.consent_method,
                "consented_at": c.consented_at.isoformat() if c.consented_at else None,
                "expires_at": c.consent_expires_at.isoformat() if c.consent_expires_at else None,
                "notes": c.notes,
            }
            for c in db.query(ConsentRecord).filter(ConsentRecord.patient_id == patient_id).all()
        ],
        "medical_history": [
            {
                "entry_id": e.entry_id,
                "type": e.entry_type,
                "title": e.title,
                "description": e.description,
                "event_date": e.event_date,
                "severity": e.severity,
                "status": e.status,
                "is_sensitive": e.is_sensitive,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in db.query(MedicalHistoryEntry).filter(MedicalHistoryEntry.patient_id == patient_id).all()
        ],
        "encounters": [
            {
                "record_id": r.record_id,
                "doctor_id": r.doctor_id,
                "blood_pressure": r.blood_pressure,
                "heart_rate": r.heart_rate,
                "temperature": r.temperature,
                "chief_complaint": r.chief_complaint,
                "diagnosis": r.diagnosis,
                "treatment_plan": r.treatment_plan,
                "icd10_code": r.icd10_code,
                "record_status": r.record_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in db.query(MedicalRecord).filter(MedicalRecord.patient_id == patient_id).all()
        ],
        "appointments": [
            {
                "appointment_id": a.appointment_id,
                "doctor_id": a.doctor_id,
                "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None,
                "status": a.status,
            }
            for a in db.query(Appointment).filter(Appointment.patient_id == patient_id).all()
        ],
        "lab_tests": [
            {
                "test_id": t.test_id,
                "test_name": t.test_name,
                "status": t.status,
                "priority": t.priority,
                "result_summary": t.result_summary,
                "billed_price": t.billed_price,
                "requested_at": t.requested_at.isoformat() if t.requested_at else None,
            }
            for t in db.query(LabTest).filter(LabTest.patient_id == patient_id).all()
        ],
        "radiology": [
            {
                "request_id": r.request_id,
                "modality": getattr(r, "modality", None),
                "body_part": getattr(r, "body_part", None),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in db.query(RadiologyRequest).filter(RadiologyRequest.patient_id == patient_id).all()
        ],
        "admissions": [
            {
                "admission_id": a.admission_id,
                "bed_id": a.bed_id,
                "primary_diagnosis": a.primary_diagnosis,
                "status": a.status,
                "admission_date": a.admission_date.isoformat() if a.admission_date else None,
            }
            for a in db.query(AdmissionRecord).filter(AdmissionRecord.patient_id == patient_id).all()
        ],
        "billing": [
            {
                "invoice_id": i.invoice_id,
                "total_amount": i.total_amount,
                "amount_paid": i.amount_paid,
                "status": i.status,
                "billing_date": i.billing_date.isoformat() if getattr(i, "billing_date", None) else None,
            }
            for i in db.query(Invoice).filter(Invoice.patient_id == patient_id).all()
        ],
    }

    if fmt.lower() == "csv":
        # Flat CSV manifest — useful for spreadsheet importers. JSON remains the
        # canonical format because clinical data is hierarchical.
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["section", "field", "value"])
        for k, v in bundle["patient"].items():
            writer.writerow(["patient", k, v if v is not None else ""])
        for entry in bundle["medical_history"]:
            for k, v in entry.items():
                writer.writerow([f"history#{entry['entry_id']}", k, v if v is not None else ""])
        for visit in bundle["encounters"]:
            for k, v in visit.items():
                writer.writerow([f"encounter#{visit['record_id']}", k, v if v is not None else ""])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="patient_{patient.outpatient_no}_export.csv"'},
        )

    return bundle


# =====================================================================
# 2. RIGHT TO ERASURE — Patient anonymization (KDPA S.40)
# =====================================================================
class ErasureRequest(BaseModel):
    reason: str
    confirm_outpatient_no: str  # Operator must re-type the OP number to confirm intent.


@router.post(
    "/patients/{patient_id}/erase",
    dependencies=[Depends(RequirePermission("users:manage"))],
)
def erase_patient(
    patient_id: int,
    payload: ErasureRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Anonymizes the patient. Identifying fields are replaced with deterministic
    redactions (e.g., "REDACTED-{patient_id}"). Clinical FK integrity is
    preserved so historical billing/encounter rows continue to reconcile.

    This is the KDPA "right to erasure" pathway. Health Act 2017 mandates
    seven-year retention of clinical records, so a hard delete is not legally
    available — anonymization is the compliant alternative.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found.")

    if payload.confirm_outpatient_no != patient.outpatient_no:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation OP number does not match the target patient.",
        )

    if patient.outpatient_no.startswith("REDACTED-"):
        raise HTTPException(status_code=400, detail="Patient is already anonymized.")

    # Snapshot the original values for the audit trail (one final time, then gone).
    pre_state = _serialize_patient(patient)

    redacted_marker = f"REDACTED-{patient.patient_id}"
    patient.surname = "REDACTED"
    patient.other_names = redacted_marker
    patient.id_number = None
    patient.telephone_1 = None
    patient.telephone_2 = None
    patient.email = None
    patient.postal_address = None
    patient.postal_code = None
    patient.residence = None
    patient.town = None
    patient.occupation = None
    patient.employer_name = None
    patient.reference_number = None
    patient.nok_name = None
    patient.nok_relationship = None
    patient.nok_contact = None
    patient.notes = f"Anonymized on {datetime.now(timezone.utc).isoformat()} per KDPA S.40 — reason: {payload.reason}"
    patient.is_active = False

    log_audit(
        db, current_user["user_id"], "ERASE", "Patient", str(patient_id),
        old_value={"snapshot_redacted": True, "original_op": pre_state["outpatient_no"]},
        new_value={"reason": payload.reason, "anonymized": True},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "message": "Patient successfully anonymized. Clinical record stubs preserved per Health Act 2017.",
        "anonymized_marker": redacted_marker,
    }


# =====================================================================
# 3. BREACH NOTIFICATION (KDPA S.43)
# =====================================================================
class BreachCreateRequest(BaseModel):
    severity: str = "Medium"
    nature: str
    description: str
    affected_categories: Optional[List[str]] = None
    estimated_records_affected: Optional[int] = None
    affected_patient_ids: Optional[List[int]] = None
    likely_consequences: Optional[str] = None
    mitigation_steps: Optional[str] = None


class BreachStatusUpdate(BaseModel):
    status: Optional[str] = None
    odpc_notified: Optional[bool] = None
    odpc_reference: Optional[str] = None
    patients_notified: Optional[bool] = None
    mitigation_steps: Optional[str] = None


def _breach_to_dict(b: BreachIncident) -> dict:
    detected_aware = b.detected_at if (b.detected_at and b.detected_at.tzinfo) else (b.detected_at.replace(tzinfo=timezone.utc) if b.detected_at else None)
    deadline = detected_aware + timedelta(hours=72) if detected_aware else None
    now = datetime.now(timezone.utc)
    hours_remaining = ((deadline - now).total_seconds() / 3600.0) if deadline else None

    return {
        "incident_id": b.incident_id,
        "detected_at": b.detected_at.isoformat() if b.detected_at else None,
        "severity": b.severity,
        "nature": b.nature,
        "description": b.description,
        "affected_categories": b.affected_categories,
        "estimated_records_affected": b.estimated_records_affected,
        "affected_patient_ids": b.affected_patient_ids,
        "likely_consequences": b.likely_consequences,
        "mitigation_steps": b.mitigation_steps,
        "odpc_notified": b.odpc_notified,
        "odpc_notified_at": b.odpc_notified_at.isoformat() if b.odpc_notified_at else None,
        "odpc_reference": b.odpc_reference,
        "patients_notified": b.patients_notified,
        "patients_notified_at": b.patients_notified_at.isoformat() if b.patients_notified_at else None,
        "status": b.status,
        "closed_at": b.closed_at.isoformat() if b.closed_at else None,
        "kdpa_deadline_at": deadline.isoformat() if deadline else None,
        "hours_remaining_to_notify": round(hours_remaining, 2) if hours_remaining is not None else None,
        "overdue": (hours_remaining is not None and hours_remaining < 0 and not b.odpc_notified),
    }


@router.post("/breaches", dependencies=[Depends(RequirePermission("users:manage"))])
def report_breach(
    payload: BreachCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Logs a suspected/confirmed breach. The 72-hour ODPC notification clock starts at detected_at."""
    incident = BreachIncident(
        reported_by=current_user["user_id"],
        severity=payload.severity,
        nature=payload.nature,
        description=payload.description,
        affected_categories=payload.affected_categories,
        estimated_records_affected=payload.estimated_records_affected,
        affected_patient_ids=payload.affected_patient_ids,
        likely_consequences=payload.likely_consequences,
        mitigation_steps=payload.mitigation_steps,
        status="Open",
    )
    db.add(incident)
    db.flush()

    log_audit(
        db, current_user["user_id"], "CREATE", "BreachIncident", str(incident.incident_id),
        old_value=None,
        new_value={"severity": payload.severity, "nature": payload.nature},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(incident)
    return _breach_to_dict(incident)


@router.get("/breaches", dependencies=[Depends(RequirePermission("users:manage"))])
def list_breaches(db: Session = Depends(get_db)):
    breaches = db.query(BreachIncident).order_by(BreachIncident.detected_at.desc()).all()
    return [_breach_to_dict(b) for b in breaches]


@router.patch("/breaches/{incident_id}", dependencies=[Depends(RequirePermission("users:manage"))])
def update_breach(
    incident_id: int,
    payload: BreachStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    incident = db.query(BreachIncident).filter(BreachIncident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")

    old = {
        "status": incident.status,
        "odpc_notified": incident.odpc_notified,
        "patients_notified": incident.patients_notified,
    }

    if payload.status is not None:
        incident.status = payload.status
        if payload.status == "Closed":
            incident.closed_at = datetime.now(timezone.utc)
    if payload.odpc_notified is True and not incident.odpc_notified:
        incident.odpc_notified = True
        incident.odpc_notified_at = datetime.now(timezone.utc)
    if payload.odpc_reference is not None:
        incident.odpc_reference = payload.odpc_reference
    if payload.patients_notified is True and not incident.patients_notified:
        incident.patients_notified = True
        incident.patients_notified_at = datetime.now(timezone.utc)
    if payload.mitigation_steps is not None:
        incident.mitigation_steps = payload.mitigation_steps

    log_audit(
        db, current_user["user_id"], "UPDATE", "BreachIncident", str(incident_id),
        old_value=old,
        new_value=payload.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(incident)
    return _breach_to_dict(incident)


@router.get("/breaches/{incident_id}/notification", dependencies=[Depends(RequirePermission("users:manage"))])
def render_breach_notification(incident_id: int, db: Session = Depends(get_db)):
    """
    Generates a draft ODPC notification text containing every field KDPA S.43(2) requires.
    The operations team copy/pastes this into the formal notification channel.
    """
    incident = db.query(BreachIncident).filter(BreachIncident.incident_id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found.")

    reporter = db.query(User).filter(User.user_id == incident.reported_by).first()

    template = (
        f"OFFICE OF THE DATA PROTECTION COMMISSIONER\n"
        f"Personal Data Breach Notification — KDPA Section 43\n"
        f"\n"
        f"Incident ID: {incident.incident_id}\n"
        f"Reported By: {reporter.full_name if reporter else 'Unknown'} ({reporter.email if reporter else '—'})\n"
        f"Detected At: {incident.detected_at.isoformat() if incident.detected_at else 'Unknown'}\n"
        f"Severity: {incident.severity}\n"
        f"\n"
        f"1. NATURE OF THE BREACH\n{incident.nature}\n"
        f"\n2. DESCRIPTION\n{incident.description}\n"
        f"\n3. AFFECTED CATEGORIES OF DATA\n{', '.join(incident.affected_categories or []) or 'Under investigation'}\n"
        f"\n4. APPROXIMATE NUMBER OF DATA SUBJECTS AFFECTED\n{incident.estimated_records_affected or 'Under investigation'}\n"
        f"\n5. LIKELY CONSEQUENCES\n{incident.likely_consequences or 'Under assessment'}\n"
        f"\n6. MEASURES TAKEN OR PROPOSED\n{incident.mitigation_steps or 'Containment in progress'}\n"
        f"\n7. CONTACT POINT\nData Protection Officer of the reporting facility.\n"
    )

    return {"draft": template, "incident": _breach_to_dict(incident)}
