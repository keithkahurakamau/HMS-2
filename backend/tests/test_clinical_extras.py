"""Clinical-desk extras: sick notes, optical prescriptions, external requests,
order sets. RBAC clinical:read (Nurse/Doctor/Admin) / clinical:write (Doctor/Admin).
Live server."""
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
        c.get("/api/clinical-extras/order-sets")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    s = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Extra{s}", "other_names": "Clinical Test", "sex": "Female",
        "date_of_birth": "1990-01-01", "telephone_1": f"+2547{s[:8]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


class TestAccess:
    def test_unauthenticated_401(self, client):
        assert client.get("/api/clinical-extras/order-sets").status_code == 401

    def test_nurse_can_read(self, client, nurse_cookies):
        assert client.get("/api/clinical-extras/order-sets", cookies=nurse_cookies).status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        assert client.get("/api/clinical-extras/order-sets", cookies=receptionist_cookies).status_code == 403

    def test_nurse_cannot_write_sick_note(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-extras/sick-notes", cookies=nurse_cookies, json={
            "patient_id": pid, "start_date": "2026-07-24", "end_date": "2026-07-26"})
        assert r.status_code == 403


class TestSickNotes:
    def test_create_auto_days_and_list(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-extras/sick-notes", cookies=doctor_cookies, json={
            "patient_id": pid, "diagnosis": "Acute bronchitis",
            "start_date": "2026-07-24", "end_date": "2026-07-26",
            "recommendation": "Rest and fluids"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["days"] == 3  # inclusive 24..26
        assert body["fit_for_duty"] is False
        rows = client.get(f"/api/clinical-extras/sick-notes?patient_id={pid}", cookies=doctor_cookies).json()
        assert any(s["sick_note_id"] == body["sick_note_id"] for s in rows)

    def test_explicit_days_respected(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-extras/sick-notes", cookies=doctor_cookies, json={
            "patient_id": pid, "start_date": "2026-07-24", "end_date": "2026-07-30", "days": 5})
        assert r.status_code == 200 and r.json()["days"] == 5

    def test_unknown_patient_404(self, client, doctor_cookies):
        r = client.post("/api/clinical-extras/sick-notes", cookies=doctor_cookies, json={
            "patient_id": 99999999, "start_date": "2026-07-24", "end_date": "2026-07-26"})
        assert r.status_code == 404


class TestOptical:
    def test_create_and_list(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-extras/optical-prescriptions", cookies=doctor_cookies, json={
            "patient_id": pid, "right_sphere": "-1.25", "right_cylinder": "-0.50",
            "right_axis": "180", "left_sphere": "-1.00", "pd": "62", "notes": "Distance"})
        assert r.status_code == 200, r.text
        oid = r.json()["optical_id"]
        rows = client.get(f"/api/clinical-extras/optical-prescriptions?patient_id={pid}", cookies=doctor_cookies).json()
        assert any(o["optical_id"] == oid and o["right_sphere"] == "-1.25" for o in rows)


class TestExternalRequests:
    def test_create_and_validate_type(self, client, doctor_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/clinical-extras/external-requests", cookies=doctor_cookies, json={
            "patient_id": pid, "facility": "Lancet Labs", "request_type": "Lab",
            "details": "HbA1c", "reason": "Diabetic follow-up"})
        assert r.status_code == 200, r.text
        assert client.post("/api/clinical-extras/external-requests", cookies=doctor_cookies, json={
            "patient_id": pid, "request_type": "Nonsense"}).status_code == 422
        rows = client.get(f"/api/clinical-extras/external-requests?patient_id={pid}", cookies=doctor_cookies).json()
        assert any(e["request_type"] == "Lab" for e in rows)


class TestOrderSets:
    def test_create_with_items_and_fetch(self, client, doctor_cookies):
        name = f"Diabetes work-up {uuid.uuid4().hex[:6]}"
        r = client.post("/api/clinical-extras/order-sets", cookies=doctor_cookies, json={
            "name": name, "description": "Routine diabetic panel", "items": [
                {"item_type": "Lab", "name": "HbA1c"},
                {"item_type": "Lab", "name": "Fasting glucose"},
                {"item_type": "Drug", "name": "Metformin 500mg"}]})
        assert r.status_code == 200, r.text
        sid = r.json()["order_set_id"]
        assert len(r.json()["items"]) == 3
        detail = client.get(f"/api/clinical-extras/order-sets/{sid}", cookies=doctor_cookies).json()
        assert detail["name"] == name and len(detail["items"]) == 3
        assert any(s["order_set_id"] == sid for s in
                   client.get("/api/clinical-extras/order-sets", cookies=doctor_cookies).json())

    def test_invalid_item_type_422(self, client, doctor_cookies):
        r = client.post("/api/clinical-extras/order-sets", cookies=doctor_cookies, json={
            "name": "Bad", "items": [{"item_type": "Potion", "name": "X"}]})
        assert r.status_code == 422

    def test_get_unknown_404(self, client, doctor_cookies):
        assert client.get("/api/clinical-extras/order-sets/99999999", cookies=doctor_cookies).status_code == 404
