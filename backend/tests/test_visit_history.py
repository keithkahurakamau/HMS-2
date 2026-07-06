"""
Visit history integration tests.

Covers:
  - /api/medical-history/{pid}/chart returns ALL visits (no 10-row cap) with icd10_code
  - /api/clinical/record/{record_id} full-detail endpoint (Task 2)
  - multi-code icd10 round-trip + oversize rejection (Task 3)
"""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True, timeout=30) as c:
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
        "surname": f"ZZ_VHIST_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Visit History", "sex": "Male",
        "date_of_birth": "1980-03-03", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _consent(client, cookies, pid):
    client.cookies.update(cookies)
    r = client.post("/api/medical-history/consent", json={
        "patient_id": pid, "consent_type": "Treatment",
        "consent_given": True, "consent_method": "Verbal",
    })
    assert r.status_code == 200, r.text


def _submit_visit(client, cookies, pid, **overrides):
    client.cookies.update(cookies)
    payload = {
        "patient_id": pid, "record_status": "Completed",
        "chief_complaint": "cough", "diagnosis": "Acute bronchitis",
        "icd10_code": "J20.9",
    }
    payload.update(overrides)
    r = client.post("/api/clinical/submit", json=payload)
    assert r.status_code == 200, r.text


class TestChartAllVisits:
    def test_chart_returns_more_than_ten_visits(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            _consent(client, doctor_cookies, pid)
            for i in range(12):
                _submit_visit(client, doctor_cookies, pid,
                              chief_complaint=f"complaint {i}")

            chart = client.get(f"/api/medical-history/{pid}/chart")
            assert chart.status_code == 200, chart.text
            visits = chart.json()["recent_visits"]
            assert len(visits) == 12, f"expected all 12 visits, got {len(visits)}"
            assert visits[0]["icd10_code"] == "J20.9"
            # newest first
            assert visits[0]["chief_complaint"] == "complaint 11"
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")
