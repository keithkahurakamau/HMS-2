"""DoctorV2 Assess & Plan: assessment_plan round-trips through /clinical/submit
(generic setattr persist) and surfaces in the visit detail. Live server."""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}
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


def _doctor_user_id() -> int:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    from app.models.user import User
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    db = sessionmaker(bind=engine)()
    try:
        u = db.query(User).filter(User.email == DOCTOR_EMAIL).first()
        assert u is not None
        return u.user_id
    finally:
        db.close(); engine.dispose()


def _seed_consent(patient_id: int, recorded_by: int) -> None:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings
    import app.models.patient  # noqa: F401
    from app.models.medical_history import ConsentRecord
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/{TENANT}")
    db = sessionmaker(bind=engine)()
    try:
        db.add(ConsentRecord(patient_id=patient_id, consent_type="Treatment",
                             consent_given=True, consent_method="Written", recorded_by=recorded_by))
        db.commit()
    finally:
        db.close(); engine.dispose()


@pytest.fixture()
def patient(client):
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_AP_{uuid.uuid4().hex[:6].upper()}", "other_names": "Assess Plan",
        "sex": "Male", "date_of_birth": "1985-05-05", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    p = r.json()
    _seed_consent(p["patient_id"], recorded_by=_doctor_user_id())
    yield p
    client.delete(f"/api/patients/{p['patient_id']}")


def test_assessment_plan_round_trips(client, patient):
    ap = "Assessment:\nStable.\n\nPlan:\nContinue meds, review in 2 weeks."
    r = client.post("/api/clinical/submit", json={
        "patient_id": patient["patient_id"],
        "record_status": "Draft",
        "chief_complaint": "Follow-up",
        "assessment_plan": ap,
    })
    assert r.status_code == 200, r.text
    rid = r.json()["record_id"]

    detail = client.get(f"/api/clinical/record/{rid}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["assessment_plan"] == ap
