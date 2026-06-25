"""Radiology can cancel an imaging request (soft, reason + audit)."""
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
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client) -> dict:
    """Create a patient. Caller must have receptionist/doctor cookies set on the client."""
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_RADCAN_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Rad Cancel", "sex": "Female",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _create_request(client, patient_id) -> int:
    """Create a radiology request. Caller must have doctor cookies set on the client."""
    r = client.post("/api/radiology/", json={
        "patient_id": patient_id, "exam_type": "Chest X-Ray", "priority": "Routine"})
    assert r.status_code in (200, 201), r.text
    return r.json()["request_id"]


def test_cancel_requires_auth(client):
    # No auth cookie -> must reject with 401 (CSRF header still present).
    client.cookies.pop("access_token", None)
    r = client.post("/api/radiology/1/cancel", json={"reason": "x"})
    assert r.status_code == 401


def test_cancel_unknown_returns_404(client, radiologist_cookies):
    client.cookies.update(radiologist_cookies)
    r = client.post("/api/radiology/999999999/cancel", json={"reason": "x"})
    assert r.status_code == 404


def test_cancel_sets_status_and_drops(client, receptionist_cookies, doctor_cookies, radiologist_cookies):
    # Receptionist creates the patient.
    client.cookies.update(receptionist_cookies)
    patient = _new_patient(client)
    pid = patient["patient_id"]
    try:
        # Doctor creates the imaging request.
        client.cookies.update(doctor_cookies)
        req_id = _create_request(client, pid)

        # Radiologist cancels it.
        client.cookies.update(radiologist_cookies)
        r = client.post(f"/api/radiology/{req_id}/cancel", json={"reason": "Wrong order"})
        assert r.status_code == 200, r.text

        # Verify: either dropped from list, or present but marked Cancelled.
        rows = client.get("/api/radiology/").json()
        match = [x for x in rows if x.get("request_id") == req_id]
        assert not match or match[0].get("status") == "Cancelled", match
    finally:
        client.cookies.update(receptionist_cookies)
        client.delete(f"/api/patients/{pid}")
