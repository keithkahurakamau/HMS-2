"""Draft resume / update-in-place for Clinical Desk encounters.

Every save used to INSERT a new MedicalRecord, so "Save draft" piled up
duplicate rows and a draft could never be reopened. These tests cover:

  * /clinical/submit returns the record_id it wrote
  * /clinical/submit with record_id updates that record instead of inserting
  * update is refused once a record is finalised (only Draft/Returned)
  * /clinical/patients/{id}/resumable surfaces the doctor's latest
    Draft/Returned record with ICD-10 codes resolved for chip rebuild

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
def client(doctor_cookies):
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        c.cookies.update(doctor_cookies)
        yield c


def _phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client) -> dict:
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_DRAFT_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Draft Patient", "sex": "Female",
        "date_of_birth": "1988-03-14", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _doctor_user_id() -> int:
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
    """Insert a Treatment consent directly (medical_history API is
    feature-gated on this tenant)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    import app.models.patient  # noqa: F401 – ConsentRecord relationship
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


@pytest.fixture()
def patient(client):
    p = _new_patient(client)
    _seed_consent(p["patient_id"], recorded_by=_doctor_user_id())
    yield p
    client.delete(f"/api/patients/{p['patient_id']}")


def test_submit_returns_record_id(client, patient):
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Draft",
        "chief_complaint": "Headache",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("record_id"), int), body


def test_submit_with_record_id_updates_in_place(client, patient):
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Draft",
        "chief_complaint": "Headache",
    })
    assert r.status_code == 200, r.text
    record_id = r.json()["record_id"]

    r = client.post("/api/clinical/submit", json={
        "record_id": record_id,
        "patient_id": patient["patient_id"],
        "record_status": "Completed",
        "chief_complaint": "Headache; Photophobia",
        "diagnosis": "Migraine without aura",
        "icd10_code": "G43.009",
    })
    assert r.status_code == 200, r.text
    assert r.json()["record_id"] == record_id

    r = client.get(f"/api/clinical/records/{patient['patient_id']}")
    assert r.status_code == 200, r.text
    records = r.json()
    assert len(records) == 1, f"expected one record, got {len(records)}: {records}"
    assert records[0]["record_status"] == "Completed"
    assert records[0]["chief_complaint"] == "Headache; Photophobia"
    assert records[0]["icd10_code"] == "G43.009"


def test_update_refused_once_finalised(client, patient):
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Completed",
        "chief_complaint": "Sprained ankle",
    })
    assert r.status_code == 200, r.text
    record_id = r.json()["record_id"]

    r = client.post("/api/clinical/submit", json={
        "record_id": record_id,
        "patient_id": patient["patient_id"],
        "record_status": "Draft",
        "chief_complaint": "Trying to reopen",
    })
    assert r.status_code == 400, r.text
    assert "finalised" in r.json()["detail"].lower() or "draft" in r.json()["detail"].lower()


def test_resumable_returns_latest_draft_with_resolved_codes(client, patient):
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Draft",
        "chief_complaint": "Polyuria; Polydipsia",
        "icd10_code": "E11.9, I10",
        "diagnosis": "suspected metabolic syndrome",
    })
    assert r.status_code == 200, r.text
    record_id = r.json()["record_id"]

    r = client.get(f"/api/clinical/patients/{patient['patient_id']}/resumable")
    assert r.status_code == 200, r.text
    rec = r.json()["record"]
    assert rec is not None
    assert rec["record_id"] == record_id
    assert rec["record_status"] == "Draft"
    assert rec["chief_complaint"] == "Polyuria; Polydipsia"
    assert rec["diagnosis"] == "suspected metabolic syndrome"
    codes = {c["code"]: c["description"] for c in rec["icd10_codes"]}
    assert set(codes) == {"E11.9", "I10"}
    # Descriptions come from the CMS catalogue, not echoes of the code.
    assert "diabetes" in codes["E11.9"].lower()
    assert "hypertension" in codes["I10"].lower()


def test_resumable_empty_for_fresh_patient(client, patient):
    r = client.get(f"/api/clinical/patients/{patient['patient_id']}/resumable")
    assert r.status_code == 200, r.text
    assert r.json()["record"] is None


def test_resumable_ignores_finalised_records(client, patient):
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Completed",
        "chief_complaint": "Done and dusted",
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/api/clinical/patients/{patient['patient_id']}/resumable")
    assert r.status_code == 200, r.text
    assert r.json()["record"] is None
