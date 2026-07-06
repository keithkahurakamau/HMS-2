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


class TestVisitDetail:
    def _make_visit(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        _consent(client, doctor_cookies, pid)
        _submit_visit(
            client, doctor_cookies, pid,
            icd10_code="J20.9, E11.9",
            diagnosis="Acute bronchitis; Type 2 diabetes",
            history_of_present_illness="Productive cough for 3 days",
            blood_pressure="120/80", heart_rate=72,
            treatment_plan='[{"drug":"Amoxicillin","formulation":"caps","dosage":"500mg","frequency":"8h","duration":"5d"}]',
            internal_notes="internal only",
        )
        client.cookies.update(doctor_cookies)
        chart = client.get(f"/api/medical-history/{pid}/chart")
        record_id = chart.json()["recent_visits"][0]["record_id"]
        return pid, record_id

    def test_requires_auth(self):
        # Fresh anonymous client — do NOT clear cookies on the shared module
        # client, that would drop its csrf_token and break later POSTs.
        with httpx.Client(base_url=BASE, headers=HEADERS) as anon:
            r = anon.get("/api/clinical/record/1")
            assert r.status_code == 401

    def test_full_detail(self, client, receptionist_cookies, doctor_cookies):
        pid, record_id = self._make_visit(client, receptionist_cookies, doctor_cookies)
        try:
            r = client.get(f"/api/clinical/record/{record_id}")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["icd10_codes"] == ["J20.9", "E11.9"]
            assert d["vitals"]["blood_pressure"] == "120/80"
            assert d["vitals"]["heart_rate"] == 72
            assert d["history_of_present_illness"] == "Productive cough for 3 days"
            assert d["prescriptions"][0]["drug"] == "Amoxicillin"
            assert d["doctor"] and d["doctor"] != "Unknown"
            assert isinstance(d["lab_tests"], list)
            assert isinstance(d["radiology"], list)
            # doctor is a clinical role → sees internal notes
            assert d["internal_notes"] == "internal only"
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")

    def test_not_found(self, client, doctor_cookies):
        client.cookies.update(doctor_cookies)
        r = client.get("/api/clinical/record/99999999")
        assert r.status_code == 404

    def test_admin_can_read_but_not_internal_notes(self, client, receptionist_cookies, doctor_cookies, admin_cookies):
        # Admin is in SENSITIVE_DATA_RESTRICTED_ROLES but still holds
        # history:read, so the endpoint must succeed — just without the
        # internal_notes key.
        pid, record_id = self._make_visit(client, receptionist_cookies, doctor_cookies)
        try:
            client.cookies.update(admin_cookies)
            r = client.get(f"/api/clinical/record/{record_id}")
            assert r.status_code == 200, r.text
            assert "internal_notes" not in r.json()
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")

    def test_legacy_display_string_icd10_kept_as_single_entry(self, client, receptionist_cookies, doctor_cookies):
        # Legacy records store a display string (with a comma) in icd10_code
        # rather than a modern comma-separated code list. Naive comma-split
        # would wrongly produce two chips here — it must stay one entry.
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            _consent(client, doctor_cookies, pid)
            _submit_visit(
                client, doctor_cookies, pid,
                icd10_code="Type 2 diabetes mellitus, unspecified",
            )
            client.cookies.update(doctor_cookies)
            chart = client.get(f"/api/medical-history/{pid}/chart")
            record_id = chart.json()["recent_visits"][0]["record_id"]
            r = client.get(f"/api/clinical/record/{record_id}")
            assert r.status_code == 200, r.text
            assert r.json()["icd10_codes"] == ["Type 2 diabetes mellitus, unspecified"]
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")


class TestMultiIcdGuard:
    def test_oversize_icd_list_rejected(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            _consent(client, doctor_cookies, pid)
            client.cookies.update(doctor_cookies)
            too_long = ", ".join(f"Z{i:02d}.{i%10}XX" for i in range(40))  # > 255 chars
            r = client.post("/api/clinical/submit", json={
                "patient_id": pid, "record_status": "Draft",
                "icd10_code": too_long, "diagnosis": "x",
            })
            assert r.status_code == 400, r.text
            assert "ICD-10" in r.json()["detail"]
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")


class TestReferralApi:
    """Sanity checks on the existing referrals API the new modal depends on."""

    def test_create_requires_specialty_and_reason(self, client, doctor_cookies):
        client.cookies.update(doctor_cookies)
        r = client.post("/api/referrals/", json={"patient_id": 1, "specialty": "", "reason": ""})
        assert r.status_code == 422  # Pydantic min_length=1

    def test_create_and_serialize(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            client.cookies.update(doctor_cookies)
            r = client.post("/api/referrals/", json={
                "patient_id": pid, "specialty": "Cardiology",
                "reason": "Suspected arrhythmia", "urgency": "Urgent",
                "target_facility": "KNH",
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["specialty"] == "Cardiology"
            assert body["status"] == "Pending"
            assert body["doctor_name"], body
            assert body["patient_opd"], body
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")
