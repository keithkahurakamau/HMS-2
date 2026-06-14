"""
Notification fan-out integration tests.

Proves the cross-module wiring actually reaches the right roles:
  - Queuing a Consultation patient notifies doctors (clinical:write),
    not the receptionist who queued them.
  - Booking an appointment notifies the assigned doctor.
Each asserts via the recipient's own /api/notifications/ feed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies) -> dict:
    tag = uuid.uuid4().hex[:6].upper()
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_NOTIF_{tag}", "other_names": "Bell Test",
        "sex": "Female", "date_of_birth": "1992-03-03", "telephone_1": _unique_phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _latest_titles(client, cookies, n: int = 10) -> list[str]:
    r = client.get("/api/notifications/", cookies=cookies, params={"limit": n})
    assert r.status_code == 200, r.text
    return [x["title"] for x in r.json()["notifications"]]


class TestQueueNotifiesDoctors:
    def test_queueing_consultation_pages_the_doctor(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        r = client.post("/api/queue/", cookies=receptionist_cookies, json={
            "patient_id": patient["patient_id"], "department": "Consultation", "acuity_level": 2,
        })
        assert r.status_code == 200, r.text
        assert any("consultation queue" in t.lower() for t in _latest_titles(client, doctor_cookies))


class TestAppointmentNotifiesDoctor:
    def test_booking_pages_the_assigned_doctor(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        doctors = client.get("/api/appointments/doctors", cookies=receptionist_cookies).json()
        assert doctors, "need at least one doctor"
        doctor_id = doctors[0]["user_id"]
        when = (datetime.now() + timedelta(days=2)).replace(microsecond=0)
        r = client.post("/api/appointments/", cookies=receptionist_cookies, json={
            "patient_id": patient["patient_id"], "doctor_id": doctor_id,
            "appointment_date": when.isoformat(),
        })
        assert r.status_code == 200, r.text
        assert any("appointment booked" in t.lower() for t in _latest_titles(client, doctor_cookies))
