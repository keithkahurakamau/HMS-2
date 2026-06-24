"""Patient chart includes triage history.

Live-server integration test (server on :8000, tenant mayoclinic_db).
"""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    client.cookies.update(cookies)
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_MHTRI_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Hist Patient", "sex": "Female",
        "date_of_birth": "1991-02-02", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_chart_includes_triage_history(client, receptionist_cookies, nurse_cookies, doctor_cookies):
    # receptionist creates the patient and queues them (patients:write required)
    patient = _new_patient(client, receptionist_cookies)
    pid = patient["patient_id"]
    try:
        # receptionist queues the patient to Triage
        client.cookies.update(receptionist_cookies)
        q = client.post("/api/queue/", json={
            "patient_id": pid, "department": "Triage", "acuity_level": 3})
        assert q.status_code == 200, q.text

        # nurse submits triage (triage:write)
        client.cookies.update(nurse_cookies)
        sub = client.post("/api/triage/submit", json={
            "patient_id": pid, "queue_id": q.json()["queue_id"],
            "blood_glucose": 7.1, "calculated_bmi": 24.2,
            "chief_complaint": "headache", "acuity_level": 2,
            "disposition": "Consultation"})
        assert sub.status_code == 200, sub.text

        # doctor reads the chart (history:read)
        client.cookies.update(doctor_cookies)
        chart = client.get(f"/api/medical-history/{pid}/chart")
        assert chart.status_code == 200, chart.text
        th = chart.json().get("triage_history")
        assert isinstance(th, list) and len(th) >= 1, chart.json()
        latest = th[0]
        assert latest["chief_complaint"] == "headache"
        assert latest["blood_glucose"] == 7.1
        assert latest["acuity_level"] == 2
    finally:
        client.cookies.update(receptionist_cookies)
        client.delete(f"/api/patients/{pid}")
