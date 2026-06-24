"""Doctor's encounter stores Random Blood Sugar (RBS) carried from triage.

Live-server integration test (server on :8000, tenant mayoclinic_db).
"""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}

TENANT = "mayoclinic_db"
DOCTOR_EMAIL = "dr.kahura@mayoclinic.com"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client) -> dict:
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_RBS_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "RBS Patient", "sex": "Male",
        "date_of_birth": "1990-06-01", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _doctor_user_id() -> int:
    """Resolve the user_id the ``doctor_cookies`` fixture authenticates as
    (``dr.kahura@mayoclinic.com``) so the seeded consent's ``recorded_by``
    matches a real user rather than a hardcoded id."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    from app.models.user import User

    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        user = db.query(User).filter(User.email == DOCTOR_EMAIL).first()
        assert user is not None, f"Doctor user not found: {DOCTOR_EMAIL}"
        return user.user_id
    finally:
        db.close()
        engine.dispose()


def _seed_consent(patient_id: int, recorded_by: int) -> None:
    """Insert a Treatment consent record directly into the DB (medical_history
    module is feature-gated so the API endpoint returns 402 on this tenant)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    import app.models.patient  # noqa: F401 – needed by ConsentRecord relationship
    from app.models.medical_history import ConsentRecord

    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(ConsentRecord(
            patient_id=patient_id,
            consent_type="Treatment",
            consent_given=True,
            consent_method="Written",
            recorded_by=recorded_by,
        ))
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_clinical_submit_persists_blood_glucose(client, doctor_cookies):
    # Set auth cookies on the client instance once (avoids httpx's per-request
    # cookies= deprecation warning).
    client.cookies.update(doctor_cookies)

    patient = _new_patient(client)
    try:
        _seed_consent(patient["patient_id"], recorded_by=_doctor_user_id())
        r = client.post("/api/clinical/submit", json={
            "patient_id": patient["patient_id"],
            "record_status": "Draft",
            "blood_glucose": 6.4,
            "chief_complaint": "RBS check",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("blood_glucose") == 6.4, body

        # Produces clause: the record read must expose blood_glucose too.
        r = client.get(f"/api/clinical/records/{patient['patient_id']}")
        assert r.status_code == 200, r.text
        records = r.json()
        assert records, "expected at least one record for the patient"
        # Most recent record (handler returns created_at desc).
        assert records[0]["blood_glucose"] == 6.4, records[0]
    finally:
        client.delete(f"/api/patients/{patient['patient_id']}")
