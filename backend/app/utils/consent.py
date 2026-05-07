"""
KDPA Section 30 — Consent enforcement.

Records that already exist in `consent_records` document that a patient consented
to a specific processing purpose (Treatment, Data Sharing, Research, etc.). The
existing flow only *logs* consent — it does not gate writes.

`require_active_consent()` enforces consent at the point of new clinical writes:
no active, unexpired, "consent_given=True" record → 403.

We deliberately do NOT block reads. Clinicians under a duty of care must be able
to access an existing chart even where consent for new processing has been
withdrawn — KDPA balances data protection with the right to receive care.
"""
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.medical_history import ConsentRecord


def has_active_consent(db: Session, patient_id: int, consent_type: str = "Treatment") -> bool:
    """Returns True if the patient has an active, non-expired, granted consent of the given type."""
    record = (
        db.query(ConsentRecord)
        .filter(
            ConsentRecord.patient_id == patient_id,
            ConsentRecord.consent_type == consent_type,
            ConsentRecord.consent_given.is_(True),
        )
        .order_by(ConsentRecord.consented_at.desc())
        .first()
    )
    if not record:
        return False
    if record.consent_expires_at:
        expiry = record.consent_expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < datetime.now(timezone.utc):
            return False
    return True


def require_active_consent(db: Session, patient_id: int, consent_type: str = "Treatment") -> None:
    """Raises 403 unless an active consent record exists. Use as a guard in write paths."""
    if not has_active_consent(db, patient_id, consent_type):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"KDPA: Patient consent for '{consent_type}' is missing or expired. "
                "Record consent before proceeding with this action."
            ),
        )
