"""
Patient Self-Service Portal.

Pragmatic knowledge-factor verification for low-stakes view-only access:

  • OP number  (something they were issued)
  • Date of birth  (something they know)
  • Last 4 digits of registered phone  (something on a device they hold)

This is appropriate for a Kenyan clinic context where many patients lack email
accounts but always carry their OP card and a phone. It is INTENTIONALLY
read-only — no clinical data is mutated through this surface.

A short-lived JWT (60 min) is issued on successful verification and required
on every subsequent portal call. It is bound to `patient_id` and carries a
distinct `type=patient_portal` claim so it cannot be substituted for a staff
session.
"""
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.settings import settings
from app.core.limiter import limiter
from app.models.patient import Patient
from app.models.clinical import Appointment
from app.models.billing import Invoice
from app.models.medical_history import MedicalHistoryEntry
from app.models.user import User


router = APIRouter(prefix="/api/portal", tags=["Patient Portal"])


PORTAL_TOKEN_TTL_MINUTES = 60
PORTAL_COOKIE_NAME = "patient_portal_token"


# --- token helpers ----------------------------------------------------
def _issue_portal_token(patient_id: int) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PORTAL_TOKEN_TTL_MINUTES)
    token = jwt.encode(
        {
            "patient_id": patient_id,
            "type": "patient_portal",
            "exp": expires_at,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return token, expires_at


def _resolve_portal_patient(token: Optional[str], db: Session) -> Patient:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal session required.")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal session invalid or expired.")
    if payload.get("type") != "patient_portal":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type.")
    patient_id = payload.get("patient_id")
    patient = db.query(Patient).filter(Patient.patient_id == patient_id, Patient.is_active.is_(True)).first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient record unavailable.")
    return patient


# --- request models ---------------------------------------------------
class PortalLookupRequest(BaseModel):
    outpatient_no: str
    date_of_birth: date
    phone_last4: str  # exactly 4 digits


# --- routes -----------------------------------------------------------
@router.post("/lookup")
@limiter.limit("5/minute")
async def portal_lookup(
    payload: PortalLookupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Verifies (OP number + DOB + phone-suffix) and issues a 60-minute portal
    token via HttpOnly cookie. Always returns a generic 401 on mismatch — never
    leak which factor was wrong, lest the endpoint become an enumeration tool.
    """
    if not (payload.phone_last4.isdigit() and len(payload.phone_last4) == 4):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone_last4 must be 4 digits.")

    patient = (
        db.query(Patient)
        .filter(Patient.outpatient_no == payload.outpatient_no, Patient.is_active.is_(True))
        .first()
    )

    generic_failure = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="The supplied details do not match a patient record.",
    )

    if not patient:
        raise generic_failure
    if patient.date_of_birth != payload.date_of_birth:
        raise generic_failure
    if not patient.telephone_1 or not patient.telephone_1.endswith(payload.phone_last4):
        raise generic_failure

    token, expires_at = _issue_portal_token(patient.patient_id)

    is_production = settings.MPESA_ENV.lower() == "production"
    response.set_cookie(
        key=PORTAL_COOKIE_NAME,
        value=token,
        max_age=PORTAL_TOKEN_TTL_MINUTES * 60,
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        path="/api/portal",
    )

    return {
        "message": "Portal session opened.",
        "session_expires_at": expires_at.isoformat(),
        "patient": {
            "outpatient_no": patient.outpatient_no,
            "full_name": f"{patient.surname}, {patient.other_names}",
        },
    }


@router.post("/logout")
def portal_logout(response: Response):
    is_production = settings.MPESA_ENV.lower() == "production"
    response.delete_cookie(
        PORTAL_COOKIE_NAME,
        httponly=True,
        secure=is_production,
        samesite="none" if is_production else "lax",
        path="/api/portal",
    )
    return {"message": "Portal session ended."}


@router.get("/me")
def portal_me(
    db: Session = Depends(get_db),
    patient_portal_token: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    patient = _resolve_portal_patient(patient_portal_token, db)
    return {
        "outpatient_no": patient.outpatient_no,
        "full_name": f"{patient.surname}, {patient.other_names}",
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex": patient.sex,
        "blood_group": patient.blood_group,
        "allergies": patient.allergies,
        "chronic_conditions": patient.chronic_conditions,
        "telephone_1_masked": (patient.telephone_1[:-4].replace(patient.telephone_1[:-4], "****") + patient.telephone_1[-4:]) if patient.telephone_1 else None,
    }


@router.get("/appointments")
def portal_appointments(
    db: Session = Depends(get_db),
    patient_portal_token: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    patient = _resolve_portal_patient(patient_portal_token, db)
    appts = (
        db.query(Appointment)
        .filter(Appointment.patient_id == patient.patient_id)
        .order_by(Appointment.appointment_date.desc())
        .all()
    )
    out = []
    for a in appts:
        doc = db.query(User).filter(User.user_id == a.doctor_id).first()
        out.append({
            "appointment_id": a.appointment_id,
            "doctor_name": doc.full_name if doc else "Clinician",
            "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None,
            "status": a.status,
            "notes": a.notes,
        })
    return out


@router.get("/billing")
def portal_billing(
    db: Session = Depends(get_db),
    patient_portal_token: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    patient = _resolve_portal_patient(patient_portal_token, db)
    invoices = (
        db.query(Invoice)
        .filter(Invoice.patient_id == patient.patient_id)
        .order_by(Invoice.invoice_id.desc())
        .all()
    )
    return [
        {
            "invoice_id": i.invoice_id,
            "total_amount": float(i.total_amount or 0),
            "amount_paid": float(i.amount_paid or 0),
            "balance": float((i.total_amount or 0) - (i.amount_paid or 0)),
            "status": i.status,
            "billing_date": i.billing_date.isoformat() if getattr(i, "billing_date", None) else None,
        }
        for i in invoices
    ]


@router.get("/history")
def portal_history(
    db: Session = Depends(get_db),
    patient_portal_token: Optional[str] = Cookie(None, alias=PORTAL_COOKIE_NAME),
):
    """
    KDPA: patients can see their own non-sensitive history. Sensitive entries
    (mental health, obstetric) are filtered out — patients should request
    those through their clinician for proper context.
    """
    patient = _resolve_portal_patient(patient_portal_token, db)
    entries = (
        db.query(MedicalHistoryEntry)
        .filter(
            MedicalHistoryEntry.patient_id == patient.patient_id,
            MedicalHistoryEntry.is_sensitive.is_(False),
        )
        .order_by(MedicalHistoryEntry.created_at.desc())
        .all()
    )
    return [
        {
            "entry_id": e.entry_id,
            "type": e.entry_type,
            "title": e.title,
            "description": e.description,
            "event_date": e.event_date,
            "severity": e.severity,
            "status": e.status,
        }
        for e in entries
    ]
