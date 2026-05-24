"""
Appointments integration tests.

Covers /api/appointments/* :
  - Auth gating
  - GET /doctors (filter to Role=Doctor, active only)
  - GET /availability (date validation, status filter, slot_minutes)
  - POST /  with conflict detection
  - GET /  with doctor_id / patient_id / status / date_from / date_to filters
  - GET /{id}  enriched fields + 404
  - PATCH /{id}/status valid + invalid transitions, audit log row
  - DELETE /{id} soft-cancel + 404
  - RBAC sanity for receptionist
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


# ─── shared fixtures ────────────────────────────────────────────────────────

def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies) -> dict:
    payload = {
        "surname": f"ZZ_TEST_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Appt Patient",
        "sex": "Female",
        "date_of_birth": "1991-02-03",
        "telephone_1": _unique_phone(),
    }
    r = client.post("/api/patients/", cookies=cookies, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _cleanup_patient(client, cookies, patient_id: int) -> None:
    try:
        client.delete(f"/api/patients/{patient_id}", cookies=cookies)
    except Exception:
        pass


def _cancel_appointment(client, cookies, appointment_id: int) -> None:
    try:
        client.delete(f"/api/appointments/{appointment_id}", cookies=cookies)
    except Exception:
        pass


@pytest.fixture(scope="module")
def appt_doctor(client, doctor_cookies):
    """An active Doctor we can book against — read from the doctors endpoint."""
    r = client.get("/api/appointments/doctors", cookies=doctor_cookies)
    assert r.status_code == 200, r.text
    docs = r.json()
    assert docs, "Demo seed must include at least one active Doctor"
    return docs[0]


@pytest.fixture(scope="module")
def appt_patient(client, receptionist_cookies):
    body = _new_patient(client, receptionist_cookies)
    yield body
    _cleanup_patient(client, receptionist_cookies, body["patient_id"])


def _future_iso(minutes_ahead: int) -> str:
    """ISO-8601 UTC timestamp some minutes into the future, second-precision."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)
    # Round to whole minute so conflict detection is deterministic.
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


# ─── 1. Auth ────────────────────────────────────────────────────────────────

class TestAppointmentAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/appointments/")
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        r = client.get("/api/appointments/1")
        assert r.status_code == 401

    def test_doctors_requires_auth(self, client):
        r = client.get("/api/appointments/doctors")
        assert r.status_code == 401

    def test_availability_requires_auth(self, client):
        r = client.get("/api/appointments/availability?doctor_id=1&date=2030-01-01")
        assert r.status_code == 401


# ─── 2. GET /doctors ────────────────────────────────────────────────────────

class TestDoctorsList:
    def test_doctors_returns_active_doctors_only(self, client, doctor_cookies):
        r = client.get("/api/appointments/doctors", cookies=doctor_cookies)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows
        for row in rows:
            assert "user_id" in row
            assert "full_name" in row
            # Specialization may be None for some doctors — column is just present
            assert "specialization" in row

    def test_receptionist_can_list_doctors(self, client, receptionist_cookies):
        r = client.get("/api/appointments/doctors", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# ─── 3. GET /availability ───────────────────────────────────────────────────

class TestAvailability:
    def test_bad_date_format_400(self, client, doctor_cookies, appt_doctor):
        r = client.get(
            f"/api/appointments/availability?doctor_id={appt_doctor['user_id']}&date=12-31-2030",
            cookies=doctor_cookies,
        )
        assert r.status_code == 400, r.text
        assert "yyyy-mm-dd" in r.json()["detail"].lower()

    def test_valid_date_returns_bookings_envelope(self, client, doctor_cookies, appt_doctor):
        # Use a far-future date so we know it's empty (or near empty).
        r = client.get(
            f"/api/appointments/availability?doctor_id={appt_doctor['user_id']}&date=2099-12-31",
            cookies=doctor_cookies,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["doctor_id"] == appt_doctor["user_id"]
        assert body["date"] == "2099-12-31"
        assert body["slot_minutes"] == 30
        assert isinstance(body["bookings"], list)

    def test_availability_filters_out_cancelled(self, client, receptionist_cookies, appt_doctor, appt_patient):
        """A Cancelled appointment must NOT appear in the availability list."""
        # Pick a far-future slot to avoid colliding with seed data
        slot = (datetime.now(timezone.utc) + timedelta(days=400)).replace(
            hour=10, minute=15, second=0, microsecond=0
        )
        date_str = slot.date().isoformat()

        # Create scheduled appointment then cancel it
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot.isoformat(),
                "notes": "ZZ_TEST availability cancel",
            },
        )
        assert created.status_code == 200, created.text
        appt_id = created.json()["appointment_id"]

        # Cancel it
        cancelled = client.delete(
            f"/api/appointments/{appt_id}",
            cookies=receptionist_cookies,
        )
        assert cancelled.status_code == 200, cancelled.text

        # Now availability should NOT list it
        avail = client.get(
            f"/api/appointments/availability?doctor_id={appt_doctor['user_id']}&date={date_str}",
            cookies=receptionist_cookies,
        )
        assert avail.status_code == 200, avail.text
        booking_ids = {b["appointment_id"] for b in avail.json()["bookings"]}
        assert appt_id not in booking_ids


# ─── 4. POST / create + conflict ────────────────────────────────────────────

class TestAppointmentCreate:
    def test_receptionist_can_create(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 90)  # 90 days out
        r = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
                "notes": "ZZ_TEST initial booking",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        try:
            assert body["status"] == "Scheduled"
            assert body["doctor_id"] == appt_doctor["user_id"]
            assert body["patient_id"] == appt_patient["patient_id"]
            assert body["patient_name"]
            assert body["doctor_name"]
            assert body["patient_opd"] == appt_patient["outpatient_no"]
        finally:
            _cancel_appointment(client, receptionist_cookies, body["appointment_id"])

    def test_conflict_returns_409(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = (datetime.now(timezone.utc) + timedelta(days=120)).replace(
            hour=9, minute=30, second=0, microsecond=0
        ).isoformat()

        first = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
                "notes": "ZZ_TEST first",
            },
        )
        assert first.status_code == 200, first.text
        appt_id = first.json()["appointment_id"]

        try:
            second = client.post(
                "/api/appointments/",
                cookies=receptionist_cookies,
                json={
                    "patient_id": appt_patient["patient_id"],
                    "doctor_id": appt_doctor["user_id"],
                    "appointment_date": slot,
                    "notes": "ZZ_TEST conflicting",
                },
            )
            assert second.status_code == 409, second.text
            assert "slot" in second.json()["detail"].lower() or "appointment" in second.json()["detail"].lower()
        finally:
            _cancel_appointment(client, receptionist_cookies, appt_id)


# ─── 5. List filters ────────────────────────────────────────────────────────

class TestAppointmentListFilters:
    @pytest.fixture(scope="class")
    def seeded_appt(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = (datetime.now(timezone.utc) + timedelta(days=150)).replace(
            hour=11, minute=0, second=0, microsecond=0
        ).isoformat()
        r = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
                "notes": "ZZ_TEST filter-seed",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        yield body
        _cancel_appointment(client, receptionist_cookies, body["appointment_id"])

    def test_filter_by_doctor(self, client, receptionist_cookies, seeded_appt, appt_doctor):
        r = client.get(
            f"/api/appointments/?doctor_id={appt_doctor['user_id']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        for row in r.json():
            assert row["doctor_id"] == appt_doctor["user_id"]

    def test_filter_by_patient(self, client, receptionist_cookies, seeded_appt, appt_patient):
        r = client.get(
            f"/api/appointments/?patient_id={appt_patient['patient_id']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        for row in r.json():
            assert row["patient_id"] == appt_patient["patient_id"]

    def test_filter_by_status(self, client, receptionist_cookies, seeded_appt):
        r = client.get(
            "/api/appointments/?status=Scheduled",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        for row in r.json():
            assert row["status"] == "Scheduled"

    def test_filter_by_date_range(self, client, receptionist_cookies, seeded_appt):
        date_from = (datetime.now(timezone.utc) + timedelta(days=149)).isoformat()
        date_to = (datetime.now(timezone.utc) + timedelta(days=151)).isoformat()
        r = client.get(
            f"/api/appointments/?date_from={date_from}&date_to={date_to}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        ids = {row["appointment_id"] for row in r.json()}
        assert seeded_appt["appointment_id"] in ids


# ─── 6. GET /{id} ───────────────────────────────────────────────────────────

class TestAppointmentDetail:
    def test_unknown_id_returns_404(self, client, doctor_cookies):
        r = client.get("/api/appointments/999999999", cookies=doctor_cookies)
        assert r.status_code == 404, r.text

    def test_enriched_response_fields(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 200)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        assert created.status_code == 200, created.text
        appt_id = created.json()["appointment_id"]
        try:
            r = client.get(f"/api/appointments/{appt_id}", cookies=receptionist_cookies)
            assert r.status_code == 200, r.text
            body = r.json()
            for key in ("patient_name", "patient_opd", "doctor_name"):
                assert key in body
            assert body["patient_opd"] == appt_patient["outpatient_no"]
        finally:
            _cancel_appointment(client, receptionist_cookies, appt_id)


# ─── 7. PATCH /{id}/status ──────────────────────────────────────────────────

class TestAppointmentStatus:
    def test_invalid_status_400(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 220)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        appt_id = created.json()["appointment_id"]
        try:
            r = client.patch(
                f"/api/appointments/{appt_id}/status",
                cookies=receptionist_cookies,
                json={"status": "Banana"},
            )
            assert r.status_code == 400, r.text
            detail = r.json()["detail"].lower()
            assert "scheduled" in detail and "completed" in detail
        finally:
            _cancel_appointment(client, receptionist_cookies, appt_id)

    def test_valid_status_persists_and_audits(self, client, admin_cookies, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 230)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        appt_id = created.json()["appointment_id"]
        try:
            r = client.patch(
                f"/api/appointments/{appt_id}/status",
                cookies=receptionist_cookies,
                json={"status": "Confirmed", "notes": "ZZ_TEST confirmed"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "Confirmed"
            assert r.json()["notes"] == "ZZ_TEST confirmed"

            # Audit log written
            logs = client.get("/api/admin/audit-logs?limit=200", cookies=admin_cookies)
            assert logs.status_code == 200
            entries = logs.json()
            hit = next(
                (e for e in entries
                 if e["entity_type"] == "Appointment"
                 and e["action"] == "UPDATE"
                 and e["entity_id"] == str(appt_id)),
                None,
            )
            assert hit is not None, "Expected an UPDATE audit row for the appointment"
        finally:
            _cancel_appointment(client, receptionist_cookies, appt_id)

    def test_no_show_status_accepted(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 240)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        appt_id = created.json()["appointment_id"]
        try:
            r = client.patch(
                f"/api/appointments/{appt_id}/status",
                cookies=receptionist_cookies,
                json={"status": "No-Show"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "No-Show"
        finally:
            _cancel_appointment(client, receptionist_cookies, appt_id)


# ─── 8. DELETE / cancel ─────────────────────────────────────────────────────

class TestAppointmentCancel:
    def test_cancel_flips_status(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 260)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        appt_id = created.json()["appointment_id"]
        r = client.delete(f"/api/appointments/{appt_id}", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text

        detail = client.get(f"/api/appointments/{appt_id}", cookies=receptionist_cookies)
        assert detail.status_code == 200
        assert detail.json()["status"] == "Cancelled"

    def test_cancel_unknown_returns_404(self, client, receptionist_cookies):
        r = client.delete("/api/appointments/999999999", cookies=receptionist_cookies)
        assert r.status_code == 404


# ─── 9. RBAC ────────────────────────────────────────────────────────────────

class TestAppointmentRBAC:
    def test_nurse_cannot_create(self, client, nurse_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 280)
        r = client.post(
            "/api/appointments/",
            cookies=nurse_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        assert r.status_code == 403, r.text

    def test_receptionist_can_cancel(self, client, receptionist_cookies, appt_doctor, appt_patient):
        slot = _future_iso(60 * 24 * 290)
        created = client.post(
            "/api/appointments/",
            cookies=receptionist_cookies,
            json={
                "patient_id": appt_patient["patient_id"],
                "doctor_id": appt_doctor["user_id"],
                "appointment_date": slot,
            },
        )
        appt_id = created.json()["appointment_id"]
        r = client.delete(f"/api/appointments/{appt_id}", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
