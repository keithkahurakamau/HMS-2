"""
Triage Queue integration tests.

Covers /api/queue/* :
  - Auth gating on POST
  - POST with valid payload (patient_id + department + acuity) → QueueResponse
  - GET filters out Completed rows
  - ?department= narrows results
  - Ordering: acuity ASC then joined_at ASC — a fresh Acuity 1 row should
    appear before an older Acuity 3 row in the same department.
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
        # The server enforces double-submit CSRF on state-changing methods. A
        # safe GET makes it set the `csrf_token` cookie; we echo that value back
        # as the `x-csrf-token` header on every subsequent request so POST/PATCH
        # pass CSRF and exercise the real protected path.
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


# ─── helpers ────────────────────────────────────────────────────────────────

def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies, *, surname_tag: str = "") -> dict:
    tag = surname_tag or uuid.uuid4().hex[:6].upper()
    payload = {
        "surname": f"ZZ_TEST_{tag}",
        "other_names": "Queue Patient",
        "sex": "Male",
        "date_of_birth": "1990-06-01",
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


# ─── 1. Auth ────────────────────────────────────────────────────────────────

class TestQueueAuth:
    def test_post_requires_auth(self, client):
        r = client.post(
            "/api/queue/",
            json={"patient_id": 1, "department": "Consultation", "acuity_level": 3},
        )
        assert r.status_code == 401


# ─── 2. POST / valid payload ────────────────────────────────────────────────

class TestQueueCreate:
    def test_valid_payload_creates_row(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies)
        try:
            r = client.post(
                "/api/queue/",
                cookies=receptionist_cookies,
                json={
                    "patient_id": patient["patient_id"],
                    "department": "Consultation",
                    "acuity_level": 2,
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            # Validate the QueueResponse schema fields
            for key in ("queue_id", "patient_id", "department", "acuity_level", "status", "joined_at"):
                assert key in body, f"missing key in QueueResponse: {key}"
            assert body["patient_id"] == patient["patient_id"]
            assert body["department"] == "Consultation"
            assert body["acuity_level"] == 2
            assert body["status"] == "Waiting"
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])


# ─── 3. GET / list active ───────────────────────────────────────────────────

class TestQueueList:
    def test_list_excludes_completed(self, client, receptionist_cookies):
        # Just make sure no Completed row leaks through. The endpoint is open
        # GET — no cookies required — but we pass them anyway for parity.
        r = client.get("/api/queue/", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        for row in r.json():
            assert row["status"] != "Completed"

    def test_department_filter_narrows(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="QF1")
        try:
            created = client.post(
                "/api/queue/",
                cookies=receptionist_cookies,
                json={
                    "patient_id": patient["patient_id"],
                    "department": "Pharmacy",
                    "acuity_level": 3,
                },
            )
            assert created.status_code == 200, created.text

            r = client.get("/api/queue/?department=Pharmacy", cookies=receptionist_cookies)
            assert r.status_code == 200, r.text
            rows = r.json()
            assert rows, "Expected the freshly-created Pharmacy row in the filtered list"
            for row in rows:
                assert row["department"] == "Pharmacy"
            assert any(row["queue_id"] == created.json()["queue_id"] for row in rows)
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])


# ─── 4. Ordering: acuity ASC then joined_at ASC ─────────────────────────────

class TestQueueOrdering:
    def test_emergency_jumps_ahead_of_older_standard(self, client, receptionist_cookies):
        """An Acuity-3 row added first must yield position to an Acuity-1
        row added second, when both target the same department."""
        # Use Wards as a low-traffic queue so we don't fight seed data.
        standard = _new_patient(client, receptionist_cookies, surname_tag="ORDSTD")
        emergency = _new_patient(client, receptionist_cookies, surname_tag="ORDEMG")
        try:
            std_resp = client.post(
                "/api/queue/",
                cookies=receptionist_cookies,
                json={
                    "patient_id": standard["patient_id"],
                    "department": "Wards",
                    "acuity_level": 3,
                },
            )
            assert std_resp.status_code == 200, std_resp.text
            std_qid = std_resp.json()["queue_id"]

            emg_resp = client.post(
                "/api/queue/",
                cookies=receptionist_cookies,
                json={
                    "patient_id": emergency["patient_id"],
                    "department": "Wards",
                    "acuity_level": 1,
                },
            )
            assert emg_resp.status_code == 200, emg_resp.text
            emg_qid = emg_resp.json()["queue_id"]

            rows = client.get(
                "/api/queue/?department=Wards", cookies=receptionist_cookies,
            ).json()

            positions = {row["queue_id"]: i for i, row in enumerate(rows)}
            assert emg_qid in positions and std_qid in positions
            # Emergency (acuity 1) must come BEFORE Standard (acuity 3)
            assert positions[emg_qid] < positions[std_qid], (
                f"Expected Acuity-1 row before Acuity-3 row, got positions "
                f"{positions[emg_qid]} vs {positions[std_qid]}"
            )
        finally:
            _cleanup_patient(client, receptionist_cookies, standard["patient_id"])
            _cleanup_patient(client, receptionist_cookies, emergency["patient_id"])


# ─── 5. Single checkout (remove one patient from the queue) ──────────────────

def _enqueue(client, cookies, patient_id, department="Consultation", acuity=3) -> int:
    r = client.post(
        "/api/queue/",
        cookies=cookies,
        json={"patient_id": patient_id, "department": department, "acuity_level": acuity},
    )
    assert r.status_code == 200, r.text
    return r.json()["queue_id"]


class TestQueueCheckout:
    def test_checkout_requires_auth(self, client):
        r = client.patch("/api/queue/1/checkout")
        assert r.status_code == 401

    def test_checkout_unknown_returns_404(self, client, receptionist_cookies):
        r = client.patch("/api/queue/999999999/checkout", cookies=receptionist_cookies)
        assert r.status_code == 404

    def test_checkout_completes_and_drops_from_active(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="CHKOUT")
        try:
            qid = _enqueue(client, receptionist_cookies, patient["patient_id"], department="Wards")

            r = client.patch(f"/api/queue/{qid}/checkout", cookies=receptionist_cookies)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "Completed"

            # The active queue must no longer surface this row.
            rows = client.get("/api/queue/?department=Wards", cookies=receptionist_cookies).json()
            assert all(row["queue_id"] != qid for row in rows)
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])

    def test_checkout_is_idempotent(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="CHKIDEM")
        try:
            qid = _enqueue(client, receptionist_cookies, patient["patient_id"], department="Wards")
            first = client.patch(f"/api/queue/{qid}/checkout", cookies=receptionist_cookies)
            second = client.patch(f"/api/queue/{qid}/checkout", cookies=receptionist_cookies)
            assert first.status_code == 200 and second.status_code == 200
            assert second.json()["status"] == "Completed"
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])


# ─── 6. End-of-day bulk checkout ────────────────────────────────────────────

class TestQueueEndOfDay:
    def test_end_of_day_requires_auth(self, client):
        r = client.post("/api/queue/end-of-day", json={"department": "Consultation"})
        assert r.status_code == 401

    def test_end_of_day_clears_department(self, client, receptionist_cookies):
        # Use Wards as a low-traffic department so the bulk clear is predictable.
        p1 = _new_patient(client, receptionist_cookies, surname_tag="EOD1")
        p2 = _new_patient(client, receptionist_cookies, surname_tag="EOD2")
        try:
            q1 = _enqueue(client, receptionist_cookies, p1["patient_id"], department="Wards")
            q2 = _enqueue(client, receptionist_cookies, p2["patient_id"], department="Wards", acuity=1)

            r = client.post(
                "/api/queue/end-of-day",
                cookies=receptionist_cookies,
                json={"department": "Wards"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["checked_out"] >= 2
            assert body["department"] == "Wards"

            rows = client.get("/api/queue/?department=Wards", cookies=receptionist_cookies).json()
            active_ids = {row["queue_id"] for row in rows}
            assert q1 not in active_ids and q2 not in active_ids
        finally:
            _cleanup_patient(client, receptionist_cookies, p1["patient_id"])
            _cleanup_patient(client, receptionist_cookies, p2["patient_id"])
