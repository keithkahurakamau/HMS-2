"""
Patient Register integration tests.

Covers the full lifecycle of the /api/patients/* router:
  - Auth gating on list/get
  - Registration: required fields, OP number format, blank id_number → NULL
  - Duplicate guard on telephone_1 and non-null id_number
  - Search across name / OP / id / phone
  - Pagination
  - Get-by-id 404
  - Update (PUT) writes audit row
  - Soft-delete (DELETE) flips is_active and removes from list
  - History endpoint shape
  - Access log endpoint (truncation to 255)
  - Staff picker filtering
  - Route-to-queue (canonical mapping, acuity clamp, idempotency, assigned_to)
  - RBAC sanity (receptionist write path; nurse blocked from write)

Runs against a live server at http://localhost:8000 with the demo seed loaded.
All test patients use the ZZ_TEST_ surname prefix so they sort to the bottom
and are easy to identify for cleanup.
"""
from __future__ import annotations

import time
import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        # Prime the double-submit CSRF token: a safe GET makes the server set the
        # csrf_token cookie; echo it back as x-csrf-token on every request so
        # state-changing calls pass the CSRF middleware.
        c.get("/api/patients/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


# ─── helpers ────────────────────────────────────────────────────────────────

def _unique_phone() -> str:
    """Generate a phone that's vanishingly unlikely to collide with seed data."""
    # 12-digit numeric, starts with 9 so it's outside the seed's +2547... range.
    return "9" + uuid.uuid4().int.__str__()[:11]


def _unique_id_number() -> str:
    return f"ID-AUTO-{uuid.uuid4().hex[:10].upper()}"


def _base_patient(**overrides) -> dict:
    payload = {
        "surname": f"ZZ_TEST_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Auto Patient",
        "sex": "Female",
        "date_of_birth": "1992-04-17",
        "telephone_1": _unique_phone(),
    }
    payload.update(overrides)
    return payload


def _register(client, cookies, **overrides) -> dict:
    """Register a fresh patient and return the response body."""
    r = client.post("/api/patients/", cookies=cookies, json=_base_patient(**overrides))
    assert r.status_code == 200, r.text
    return r.json()


def _cleanup(client, cookies, patient_id: int) -> None:
    """Best-effort soft-delete; swallow errors so a failed test doesn't cascade."""
    try:
        client.delete(f"/api/patients/{patient_id}", cookies=cookies)
    except Exception:
        pass


# ─── 1. Auth gating ─────────────────────────────────────────────────────────

class TestPatientAuth:
    def test_list_requires_auth(self, client):
        r = client.get("/api/patients/")
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        r = client.get("/api/patients/1")
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/api/patients/1/history")
        assert r.status_code == 401


# ─── 2. Registration ────────────────────────────────────────────────────────

class TestPatientRegistration:
    def test_receptionist_can_register(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            assert body["patient_id"] is not None
            assert body["surname"].startswith("ZZ_TEST_")
            assert body["is_active"] is True
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_op_number_format(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            op = body["outpatient_no"]
            # Format: OP-YYYY-NNNN
            assert op.startswith("OP-"), op
            parts = op.split("-")
            assert len(parts) == 3, op
            year = parts[1]
            seq = parts[2]
            assert len(year) == 4 and year.isdigit()
            assert len(seq) == 4 and seq.isdigit()
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_blank_id_number_normalized_to_null(self, client, receptionist_cookies):
        """Two registrations with id_number="" must not collide — both store NULL."""
        a = _register(client, receptionist_cookies, id_number="")
        b = _register(client, receptionist_cookies, id_number="   ")
        try:
            assert a["id_number"] in (None, "")
            assert b["id_number"] in (None, "")
            # Critically — both succeeded with a 200, despite the blank field
            assert a["patient_id"] != b["patient_id"]
        finally:
            _cleanup(client, receptionist_cookies, a["patient_id"])
            _cleanup(client, receptionist_cookies, b["patient_id"])

    def test_blank_email_and_telephone2_normalized(self, client, receptionist_cookies):
        a = _register(client, receptionist_cookies,
                       email="", telephone_2="", reference_number="")
        b = _register(client, receptionist_cookies,
                       email="", telephone_2="", reference_number="")
        try:
            # Both succeed — the route collapsed "" → None for these unique-ish fields.
            assert a["patient_id"] != b["patient_id"]
        finally:
            _cleanup(client, receptionist_cookies, a["patient_id"])
            _cleanup(client, receptionist_cookies, b["patient_id"])


# ─── 3. Duplicate guard ─────────────────────────────────────────────────────

class TestDuplicateGuard:
    def test_duplicate_phone_rejected(self, client, receptionist_cookies):
        phone = _unique_phone()
        first = _register(client, receptionist_cookies, telephone_1=phone)
        try:
            r = client.post(
                "/api/patients/",
                cookies=receptionist_cookies,
                json=_base_patient(telephone_1=phone),
            )
            assert r.status_code == 400, r.text
            assert "phone" in r.json()["detail"].lower() or "id" in r.json()["detail"].lower()
        finally:
            _cleanup(client, receptionist_cookies, first["patient_id"])

    def test_duplicate_id_number_rejected(self, client, receptionist_cookies):
        id_no = _unique_id_number()
        first = _register(client, receptionist_cookies, id_number=id_no)
        try:
            r = client.post(
                "/api/patients/",
                cookies=receptionist_cookies,
                json=_base_patient(id_number=id_no),
            )
            assert r.status_code == 400, r.text
        finally:
            _cleanup(client, receptionist_cookies, first["patient_id"])


# ─── 4. Search & pagination ─────────────────────────────────────────────────

class TestSearch:
    @pytest.fixture(scope="class")
    def seed_patient(self, client, receptionist_cookies):
        body = _register(
            client, receptionist_cookies,
            surname="ZZ_TEST_SEARCH",
            other_names="Findable Person",
            id_number=_unique_id_number(),
        )
        yield body
        _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_search_by_surname(self, client, receptionist_cookies, seed_patient):
        r = client.get("/api/patients/?search=ZZ_TEST_SEARCH", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        ids = {p["patient_id"] for p in r.json()}
        assert seed_patient["patient_id"] in ids

    def test_search_by_other_names(self, client, receptionist_cookies, seed_patient):
        r = client.get("/api/patients/?search=Findable", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        ids = {p["patient_id"] for p in r.json()}
        assert seed_patient["patient_id"] in ids

    def test_search_by_op_number(self, client, receptionist_cookies, seed_patient):
        r = client.get(
            f"/api/patients/?search={seed_patient['outpatient_no']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        ids = {p["patient_id"] for p in r.json()}
        assert seed_patient["patient_id"] in ids

    def test_search_by_id_number(self, client, receptionist_cookies, seed_patient):
        r = client.get(
            f"/api/patients/?search={seed_patient['id_number']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        ids = {p["patient_id"] for p in r.json()}
        assert seed_patient["patient_id"] in ids

    def test_search_by_phone(self, client, receptionist_cookies, seed_patient):
        r = client.get(
            f"/api/patients/?search={seed_patient['telephone_1']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
        ids = {p["patient_id"] for p in r.json()}
        assert seed_patient["patient_id"] in ids


class TestPagination:
    def test_limit_clamps_result_count(self, client, doctor_cookies):
        r = client.get("/api/patients/?limit=2&skip=0", cookies=doctor_cookies)
        assert r.status_code == 200, r.text
        assert len(r.json()) <= 2

    def test_skip_offsets(self, client, doctor_cookies):
        first = client.get("/api/patients/?limit=5&skip=0", cookies=doctor_cookies).json()
        second = client.get("/api/patients/?limit=5&skip=5", cookies=doctor_cookies).json()
        if len(first) == 5 and second:
            first_ids = {p["patient_id"] for p in first}
            second_ids = {p["patient_id"] for p in second}
            # Disjoint windows
            assert first_ids.isdisjoint(second_ids)


# ─── 5. Get-by-id ───────────────────────────────────────────────────────────

class TestGetById:
    def test_unknown_id_returns_404(self, client, doctor_cookies):
        r = client.get("/api/patients/999999999", cookies=doctor_cookies)
        assert r.status_code == 404, r.text

    def test_known_id_returns_record(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.get(f"/api/patients/{body['patient_id']}", cookies=receptionist_cookies)
            assert r.status_code == 200, r.text
            assert r.json()["patient_id"] == body["patient_id"]
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])


# ─── 6. Update ──────────────────────────────────────────────────────────────

class TestPatientUpdate:
    def test_put_modifies_fields(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.put(
                f"/api/patients/{body['patient_id']}",
                cookies=receptionist_cookies,
                json={"occupation": "QA Engineer", "town": "Nairobi"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["occupation"] == "QA Engineer"
            assert r.json()["town"] == "Nairobi"
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_put_with_date_of_birth_serializes_audit(self, client, receptionist_cookies):
        """Regression: a PUT carrying date_of_birth used to 500 because the audit
        log's old/new payloads contained a datetime.date the JSONB serializer
        couldn't encode. The real frontend always sends date_of_birth, so this
        mirrors the production edit-patient payload."""
        body = _register(client, receptionist_cookies)
        try:
            r = client.put(
                f"/api/patients/{body['patient_id']}",
                cookies=receptionist_cookies,
                json={
                    "date_of_birth": "2004-05-30",
                    "surname": body["surname"],
                    "other_names": "Edited Name",
                    "town": "Pattaya",
                },
            )
            assert r.status_code == 200, r.text
            assert r.json()["other_names"] == "Edited Name"
            assert str(r.json()["date_of_birth"]).startswith("2004-05-30")
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_put_email_null_clears_it(self, client, receptionist_cookies):
        """The 'No email address' toggle sends email=null to clear a stored
        address; a blank '' is also accepted (coerced to None) at registration."""
        body = _register(client, receptionist_cookies, email="patient@example.com")
        try:
            assert body.get("email") == "patient@example.com"
            r = client.put(
                f"/api/patients/{body['patient_id']}",
                cookies=receptionist_cookies,
                json={"email": None},
            )
            assert r.status_code == 200, r.text
            assert r.json()["email"] in (None, ""), r.text
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_put_writes_audit_log(self, client, admin_cookies, receptionist_cookies):
        """Admin can query /api/admin/audit-logs — we look for our UPDATE entry."""
        body = _register(client, receptionist_cookies)
        try:
            r = client.put(
                f"/api/patients/{body['patient_id']}",
                cookies=receptionist_cookies,
                json={"occupation": "Audit Marker"},
            )
            assert r.status_code == 200, r.text

            logs = client.get("/api/admin/audit-logs?limit=200", cookies=admin_cookies)
            assert logs.status_code == 200, logs.text
            entries = logs.json()
            hit = next(
                (e for e in entries
                 if e["entity_type"] == "Patient"
                 and e["action"] == "UPDATE"
                 and str(body["patient_id"]) == e["entity_id"]),
                None,
            )
            assert hit is not None, "Expected an UPDATE audit row for the patient"
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])


# ─── 7. Soft-delete ─────────────────────────────────────────────────────────

class TestSoftDelete:
    def test_delete_sets_inactive_and_excludes_from_list(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies, surname="ZZ_TEST_DELETE")
        pid = body["patient_id"]

        r = client.delete(f"/api/patients/{pid}", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text

        # Direct fetch still works (no is_active filter on get-by-id)
        detail = client.get(f"/api/patients/{pid}", cookies=receptionist_cookies)
        assert detail.status_code == 200
        assert detail.json()["is_active"] is False

        # But the list endpoint filters is_active=True
        listed = client.get(
            "/api/patients/?search=ZZ_TEST_DELETE",
            cookies=receptionist_cookies,
        )
        assert listed.status_code == 200
        ids = {p["patient_id"] for p in listed.json()}
        assert pid not in ids


# ─── 8. History endpoint ────────────────────────────────────────────────────

class TestHistory:
    def test_history_shape(self, client, doctor_cookies, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.get(
                f"/api/patients/{body['patient_id']}/history",
                cookies=doctor_cookies,
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            for key in ("demographics", "clinical_records", "lab_tests", "appointments"):
                assert key in payload, f"missing key: {key}"
            assert payload["demographics"]["opd"] == body["outpatient_no"]
            assert isinstance(payload["clinical_records"], list)
            assert isinstance(payload["lab_tests"], list)
            assert isinstance(payload["appointments"], list)
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_history_unknown_id(self, client, doctor_cookies):
        r = client.get("/api/patients/999999999/history", cookies=doctor_cookies)
        assert r.status_code == 404


# ─── 9. Access log ──────────────────────────────────────────────────────────

class TestAccessLog:
    def test_access_log_ok(self, client, doctor_cookies, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/access",
                cookies=doctor_cookies,
                json={"module": "Clinical Desk", "reason": "Routine consult"},
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"ok": True}
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_access_log_truncates_to_255_chars(self, client, doctor_cookies, receptionist_cookies):
        """The route truncates the resolved reason to 255 chars before insert.

        We verify the endpoint accepts an oversize payload without 500-ing —
        if truncation weren't applied, the underlying VARCHAR(255) would
        explode at commit time.
        """
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/access",
                cookies=doctor_cookies,
                json={"module": "X" * 600, "reason": "Y" * 600},
            )
            assert r.status_code == 200, r.text
            assert r.json() == {"ok": True}
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_access_log_defaults_when_no_payload(self, client, doctor_cookies, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/access",
                cookies=doctor_cookies,
                json={},
            )
            assert r.status_code == 200, r.text
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])


# ─── 10. Staff picker ───────────────────────────────────────────────────────

class TestStaffPicker:
    def test_doctor_role_filter(self, client, receptionist_cookies):
        r = client.get("/api/patients/staff?role=Doctor", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows, "Demo seed must include at least one Doctor"
        for row in rows:
            assert row["role"] == "Doctor"
            # The picker is restricted to active staff.
            assert "user_id" in row and "full_name" in row

    def test_empty_role_returns_all_active(self, client, receptionist_cookies):
        r = client.get("/api/patients/staff", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows
        # Multiple roles present in the seed (Admin, Doctor, Nurse, etc.)
        roles = {row["role"] for row in rows}
        assert len(roles) > 1

    def test_staff_requires_auth(self, client):
        r = client.get("/api/patients/staff")
        assert r.status_code == 401


# ─── 11. Route to queue ─────────────────────────────────────────────────────

class TestRoutePatient:
    def test_clinical_desk_resolves_to_consultation(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Clinical Desk", "acuity_level": 3},
            )
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["department"] == "Consultation"
            assert payload["already_queued"] is False
            assert payload["status"] == "Waiting"
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_lab_alias_resolves_to_laboratory(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "lab", "acuity_level": 2},
            )
            assert r.status_code == 200, r.text
            assert r.json()["department"] == "Laboratory"
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_unknown_department_400(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Atlantis", "acuity_level": 3},
            )
            assert r.status_code == 400, r.text
            # Error should enumerate the allowed canonical names
            detail = r.json()["detail"].lower()
            for canonical in ("consultation", "laboratory", "radiology"):
                assert canonical in detail
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_acuity_clamped_low(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Triage", "acuity_level": -7},
            )
            assert r.status_code == 200, r.text
            qid = r.json()["queue_id"]
            # Fetch via queue list to confirm acuity = 1
            queue = client.get("/api/queue/?department=Triage", cookies=receptionist_cookies).json()
            row = next((q for q in queue if q["queue_id"] == qid), None)
            assert row is not None
            assert row["acuity_level"] == 1
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_acuity_clamped_high(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Pharmacy", "acuity_level": 99},
            )
            assert r.status_code == 200, r.text
            qid = r.json()["queue_id"]
            queue = client.get("/api/queue/?department=Pharmacy", cookies=receptionist_cookies).json()
            row = next((q for q in queue if q["queue_id"] == qid), None)
            assert row is not None
            assert row["acuity_level"] == 5
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_route_idempotency(self, client, receptionist_cookies):
        """Same patient routed twice to the same department → second call
        returns already_queued=True with the existing queue_id."""
        body = _register(client, receptionist_cookies)
        try:
            first = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Consultation", "acuity_level": 3},
            )
            assert first.status_code == 200, first.text
            assert first.json()["already_queued"] is False
            qid_first = first.json()["queue_id"]

            second = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Consultation", "acuity_level": 3},
            )
            assert second.status_code == 200, second.text
            assert second.json()["already_queued"] is True
            assert second.json()["queue_id"] == qid_first
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_route_with_valid_assigned_to(self, client, receptionist_cookies):
        # Pick the first active Doctor from the staff picker
        staff = client.get(
            "/api/patients/staff?role=Doctor", cookies=receptionist_cookies,
        ).json()
        assert staff, "Need at least one Doctor in the seed"
        doctor_id = staff[0]["user_id"]

        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={
                    "department": "Consultation",
                    "acuity_level": 3,
                    "assigned_to": doctor_id,
                },
            )
            assert r.status_code == 200, r.text
            qid = r.json()["queue_id"]
            rows = client.get("/api/queue/?department=Consultation", cookies=receptionist_cookies).json()
            row = next((q for q in rows if q["queue_id"] == qid), None)
            assert row is not None
            # QueueResponse may not surface assigned_to in the response schema; if
            # present, verify; otherwise just confirm the row exists.
            if "assigned_to" in row:
                assert row["assigned_to"] == doctor_id
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_route_with_unknown_assigned_to_400(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={
                    "department": "Consultation",
                    "acuity_level": 3,
                    "assigned_to": 999_999_999,
                },
            )
            assert r.status_code == 400, r.text
            assert "staff" in r.json()["detail"].lower() or "inactive" in r.json()["detail"].lower()
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_route_unknown_patient_404(self, client, receptionist_cookies):
        r = client.post(
            "/api/patients/999999999/route",
            cookies=receptionist_cookies,
            json={"department": "Consultation", "acuity_level": 3},
        )
        assert r.status_code == 404, r.text


# ─── 12. RBAC ───────────────────────────────────────────────────────────────

class TestRBAC:
    def test_receptionist_can_register_and_route(self, client, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.post(
                f"/api/patients/{body['patient_id']}/route",
                cookies=receptionist_cookies,
                json={"department": "Consultation", "acuity_level": 3},
            )
            assert r.status_code == 200, r.text
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_nurse_cannot_register(self, client, nurse_cookies):
        """Nurses have patients:read but not patients:write → 403 on POST."""
        r = client.post(
            "/api/patients/",
            cookies=nurse_cookies,
            json=_base_patient(),
        )
        assert r.status_code == 403, r.text

    def test_nurse_cannot_delete(self, client, nurse_cookies, receptionist_cookies):
        body = _register(client, receptionist_cookies)
        try:
            r = client.delete(
                f"/api/patients/{body['patient_id']}",
                cookies=nurse_cookies,
            )
            assert r.status_code == 403, r.text
        finally:
            _cleanup(client, receptionist_cookies, body["patient_id"])

    def test_pharmacist_cannot_register(self, client, pharmacist_cookies):
        r = client.post(
            "/api/patients/",
            cookies=pharmacist_cookies,
            json=_base_patient(),
        )
        assert r.status_code == 403, r.text

    def test_receptionist_can_delete(self, client, receptionist_cookies):
        """Per current PERMISSION_CATALOG, Receptionist has patients:write,
        and DELETE is gated on patients:write — so receptionist CAN delete.

        Flagged in the test suite summary as a possible RBAC gap: hospitals
        may want a distinct patients:delete (or admin-only) gate for soft
        deactivation rather than rolling it into patients:write.
        """
        body = _register(client, receptionist_cookies)
        r = client.delete(
            f"/api/patients/{body['patient_id']}",
            cookies=receptionist_cookies,
        )
        assert r.status_code == 200, r.text
