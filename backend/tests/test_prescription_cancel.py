"""Pharmacy can cancel a pending prescription (soft, with reason + audit).

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
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _doctor_user_id() -> int:
    """Resolve the user_id for dr.kahura@mayoclinic.com from the DB."""
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
    """Insert a Treatment consent record directly into the DB."""
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


def _new_patient(client, cookies):
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_RXCAN_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Rx Cancel", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _forward_to_pharmacy(client, doctor_cookies, patient_id) -> int:
    """Create a clinical record routed to Pharmacy; return record_id."""
    _seed_consent(patient_id, recorded_by=_doctor_user_id())
    r = client.post("/api/clinical/submit", cookies=doctor_cookies, json={
        "patient_id": patient_id,
        "record_status": "Pharmacy",
        "chief_complaint": "rx cancel test",
        "prescription_notes": "Amoxicillin 500mg",
    })
    assert r.status_code == 200, r.text
    # Find the record via the pending list
    pend = client.get("/api/clinical/prescriptions/pending", cookies=doctor_cookies).json()
    mine = [p for p in pend if p.get("patient_id") == patient_id]
    assert mine, f"expected a pending script for patient {patient_id}: {pend[:2]}"
    return mine[0]["record_id"]


def test_cancel_requires_auth(client):
    r = client.post("/api/clinical/prescriptions/1/cancel", json={"reason": "x"})
    assert r.status_code == 401


def test_cancel_unknown_returns_404(client, pharmacist_cookies):
    r = client.post("/api/clinical/prescriptions/999999999/cancel",
                    cookies=pharmacist_cookies, json={"reason": "x"})
    assert r.status_code == 404


def test_cancel_drops_from_pending(client, doctor_cookies, pharmacist_cookies):
    patient = _new_patient(client, doctor_cookies)
    pid = patient["patient_id"]
    try:
        rid = _forward_to_pharmacy(client, doctor_cookies, pid)
        r = client.post(f"/api/clinical/prescriptions/{rid}/cancel",
                        cookies=pharmacist_cookies, json={"reason": "Duplicate script"})
        assert r.status_code == 200, r.text

        pend = client.get("/api/clinical/prescriptions/pending", cookies=pharmacist_cookies).json()
        assert all(p["record_id"] != rid for p in pend)
    finally:
        client.delete(f"/api/patients/{pid}", cookies=doctor_cookies)
