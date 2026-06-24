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


def _new_patient(client, cookies) -> dict:
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_RBS_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "RBS Patient", "sex": "Male",
        "date_of_birth": "1990-06-01", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _seed_consent(patient_id: int) -> None:
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
            recorded_by=2,  # dr.kahura user_id
        ))
        db.commit()
    finally:
        db.close()
    engine.dispose()


def test_clinical_submit_persists_blood_glucose(client, doctor_cookies):
    patient = _new_patient(client, doctor_cookies)
    try:
        _seed_consent(patient["patient_id"])
        r = client.post("/api/clinical/submit", cookies=doctor_cookies, json={
            "patient_id": patient["patient_id"],
            "record_status": "Draft",
            "blood_glucose": 6.4,
            "chief_complaint": "RBS check",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("blood_glucose") == 6.4, body
    finally:
        client.delete(f"/api/patients/{patient['patient_id']}", cookies=doctor_cookies)
