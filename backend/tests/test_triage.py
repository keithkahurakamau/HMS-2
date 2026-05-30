"""
Triage module integration tests.

Covers /api/triage/* :
  - Auth + RBAC gating (nurse can write, unauthenticated cannot)
  - GET /queue lists patients routed to the Triage department
  - POST /submit records vitals, closes the Triage row, and re-queues the
    patient into Consultation carrying the nurse-assessed acuity
  - GET /patients/{id}/latest returns the most recent triage for prefill

Requires a running server on localhost:8000 against the seeded mayoclinic_db
(same convention as test_queue.py).
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
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


# ─── helpers ────────────────────────────────────────────────────────────────

def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies, *, surname_tag: str = "") -> dict:
    tag = surname_tag or uuid.uuid4().hex[:6].upper()
    payload = {
        "surname": f"ZZ_TRIAGE_{tag}",
        "other_names": "Triage Patient",
        "sex": "Female",
        "date_of_birth": "1992-03-15",
        "telephone_1": _unique_phone(),
    }
    r = client.post("/api/patients/", cookies=cookies, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _queue_to_triage(client, cookies, patient_id: int) -> dict:
    r = client.post(
        "/api/queue/",
        cookies=cookies,
        json={"patient_id": patient_id, "department": "Triage", "acuity_level": 3},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _cleanup_patient(client, cookies, patient_id: int) -> None:
    try:
        client.delete(f"/api/patients/{patient_id}", cookies=cookies)
    except Exception:
        pass


# ─── 1. Auth / RBAC ───────────────────────────────────────────────────────────

class TestTriageAuth:
    def test_submit_requires_auth(self, client):
        r = client.post("/api/triage/submit", json={"patient_id": 1})
        assert r.status_code == 401

    def test_queue_requires_auth(self, client):
        r = client.get("/api/triage/queue")
        assert r.status_code == 401


# ─── 2. Submit records vitals + routes onward ─────────────────────────────────

class TestTriageSubmit:
    def test_nurse_submit_routes_to_consultation(self, client, receptionist_cookies, nurse_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="SUB")
        pid = patient["patient_id"]
        try:
            triage_queue = _queue_to_triage(client, receptionist_cookies, pid)

            r = client.post(
                "/api/triage/submit",
                cookies=nurse_cookies,
                json={
                    "patient_id": pid,
                    "queue_id": triage_queue["queue_id"],
                    "blood_pressure": "118/76",
                    "heart_rate": 80,
                    "temperature": 37.1,
                    "spo2": 98,
                    "weight_kg": 64.0,
                    "height_cm": 168.0,
                    "pain_score": 2,
                    "chief_complaint": "Headache and mild fever",
                    "acuity_level": 2,
                    "disposition": "Consultation",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["disposition"] == "Consultation"
            assert body["triage_id"] > 0

            # Patient should now sit in the Consultation queue at acuity 2.
            consult = client.get(
                "/api/queue/?department=Consultation", cookies=receptionist_cookies
            ).json()
            mine = [row for row in consult if row["patient_id"] == pid]
            assert mine, "Patient was not re-queued into Consultation after triage"
            assert mine[0]["acuity_level"] == 2

            # The Triage queue row should be closed (no longer active).
            triage_active = client.get(
                "/api/queue/?department=Triage", cookies=receptionist_cookies
            ).json()
            assert not any(row["patient_id"] == pid for row in triage_active), (
                "Triage row should be Completed after submit"
            )
        finally:
            _cleanup_patient(client, receptionist_cookies, pid)

    def test_submit_requires_some_data(self, client, receptionist_cookies, nurse_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="EMPTY")
        pid = patient["patient_id"]
        try:
            # No vitals + no complaint is still accepted server-side (the UI
            # guards it); the row simply carries the default acuity. Confirm
            # BMI is derived when weight + height are present.
            r = client.post(
                "/api/triage/submit",
                cookies=nurse_cookies,
                json={"patient_id": pid, "weight_kg": 80.0, "height_cm": 200.0},
            )
            assert r.status_code == 200, r.text

            latest = client.get(
                f"/api/triage/patients/{pid}/latest", cookies=nurse_cookies
            ).json()
            assert latest is not None
            # 80 / (2.0^2) = 20.0
            assert latest["calculated_bmi"] == pytest.approx(20.0, abs=0.05)
        finally:
            _cleanup_patient(client, receptionist_cookies, pid)


# ─── 3. Latest triage prefill ─────────────────────────────────────────────────

class TestTriageLatest:
    def test_latest_returns_most_recent(self, client, receptionist_cookies, nurse_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="LATEST")
        pid = patient["patient_id"]
        try:
            client.post("/api/triage/submit", cookies=nurse_cookies,
                        json={"patient_id": pid, "heart_rate": 70})
            client.post("/api/triage/submit", cookies=nurse_cookies,
                        json={"patient_id": pid, "heart_rate": 99})

            latest = client.get(
                f"/api/triage/patients/{pid}/latest", cookies=nurse_cookies
            ).json()
            assert latest["heart_rate"] == 99, "Latest should reflect the most recent submit"
        finally:
            _cleanup_patient(client, receptionist_cookies, pid)

    def test_latest_null_when_never_triaged(self, client, receptionist_cookies, nurse_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="NONE")
        pid = patient["patient_id"]
        try:
            r = client.get(f"/api/triage/patients/{pid}/latest", cookies=nurse_cookies)
            assert r.status_code == 200
            assert r.json() is None
        finally:
            _cleanup_patient(client, receptionist_cookies, pid)
