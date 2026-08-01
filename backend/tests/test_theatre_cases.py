"""Theatre module: gating, permissions, case lifecycle, WHO-checklist-gated
state machine, checklists, operative note / anaesthesia, billing. Live server."""
from __future__ import annotations

import uuid

import pytest
import httpx
from sqlalchemy import create_engine, text

from app.config.settings import settings

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/theatre/cases")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    s = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Surg{s}", "other_names": "Theatre Test", "sex": "Male",
        "date_of_birth": "1985-01-01", "telephone_1": f"+2547{s[:8]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


def _make_case(client, cookies, pid) -> int:
    r = client.post("/api/theatre/cases", cookies=cookies, json={
        "patient_id": pid, "procedure_name": "Appendectomy", "priority": "Emergency"})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def _check_phase(client, cookies, cid, phase):
    r = client.post(f"/api/theatre/cases/{cid}/checklist-runs", cookies=cookies,
                    json={"phase": phase, "checked": True})
    assert r.status_code == 200, r.text


class TestAccess:
    def test_unauthenticated_401(self, client):
        assert client.get("/api/theatre/cases").status_code == 401

    def test_nurse_can_list(self, client, nurse_cookies):
        assert client.get("/api/theatre/cases", cookies=nurse_cookies).status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        assert client.get("/api/theatre/cases", cookies=receptionist_cookies).status_code == 403


class TestCaseLifecycle:
    def test_create_list_get(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        r = client.get(f"/api/theatre/cases?patient_id={pid}", cookies=nurse_cookies)
        assert r.status_code == 200 and any(c["case_id"] == cid for c in r.json())
        body = client.get(f"/api/theatre/cases/{cid}", cookies=nurse_cookies).json()
        assert body["status"] == "Scheduled"
        assert body["checklist_runs"] == [] and body["operative_note"] is None

    def test_unknown_patient_404(self, client, nurse_cookies):
        r = client.post("/api/theatre/cases", cookies=nurse_cookies,
                        json={"patient_id": 99999999, "procedure_name": "X"})
        assert r.status_code == 404

    def test_invalid_priority_422(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/theatre/cases", cookies=nurse_cookies,
                        json={"patient_id": pid, "procedure_name": "X", "priority": "Whenever"})
        assert r.status_code == 422


class TestStateMachineWhoGates:
    def test_full_flow(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        # start before Time-Out → 409
        assert client.post(f"/api/theatre/cases/{cid}/start", cookies=nurse_cookies).status_code == 409
        _check_phase(client, nurse_cookies, cid, "TimeOut")
        r = client.post(f"/api/theatre/cases/{cid}/start", cookies=nurse_cookies)
        assert r.status_code == 200 and r.json()["status"] == "InTheatre"
        assert client.post(f"/api/theatre/cases/{cid}/to-recovery", cookies=nurse_cookies).json()["status"] == "Recovery"
        # complete before Sign-Out → 409
        assert client.post(f"/api/theatre/cases/{cid}/complete", cookies=nurse_cookies).status_code == 409
        _check_phase(client, nurse_cookies, cid, "SignOut")
        assert client.post(f"/api/theatre/cases/{cid}/complete", cookies=nurse_cookies).json()["status"] == "Completed"
        # illegal transition now
        assert client.post(f"/api/theatre/cases/{cid}/start", cookies=nurse_cookies).status_code == 409

    def test_illegal_transition(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        assert client.post(f"/api/theatre/cases/{cid}/complete", cookies=nurse_cookies).status_code == 409

    def test_cancel_requires_reason(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        assert client.post(f"/api/theatre/cases/{cid}/cancel", cookies=nurse_cookies, json={}).status_code == 422
        r = client.post(f"/api/theatre/cases/{cid}/cancel", cookies=nurse_cookies, json={"reason": "postponed"})
        assert r.status_code == 200 and r.json()["status"] == "Cancelled"


class TestChecklistsRecords:
    def test_checklists_seeded_and_filtered(self, client, nurse_cookies):
        allc = client.get("/api/theatre/checklists", cookies=nurse_cookies).json()
        assert len(allc) >= 15
        timeout = client.get("/api/theatre/checklists?phase=TimeOut", cookies=nurse_cookies).json()
        assert timeout and all(c["phase"] == "TimeOut" for c in timeout)

    def test_checklist_create_requires_manage(self, client, nurse_cookies, receptionist_cookies):
        assert client.post("/api/theatre/checklists", cookies=receptionist_cookies,
                           json={"phase": "SignIn", "name": "X"}).status_code == 403
        assert client.post("/api/theatre/checklists", cookies=nurse_cookies,
                           json={"phase": "SignIn", "name": f"Chk {uuid.uuid4().hex[:6]}"}).status_code == 200

    def test_operative_note_upsert(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        r = client.put(f"/api/theatre/cases/{cid}/operative-note", cookies=nurse_cookies,
                       json={"findings": "Inflamed appendix", "blood_loss_ml": 50})
        assert r.status_code == 200 and r.json()["blood_loss_ml"] == 50
        r = client.put(f"/api/theatre/cases/{cid}/operative-note", cookies=nurse_cookies,
                       json={"findings": "Inflamed appendix", "blood_loss_ml": 80})
        assert r.status_code == 200 and r.json()["blood_loss_ml"] == 80
        assert client.get(f"/api/theatre/cases/{cid}", cookies=nurse_cookies).json()["operative_note"]["blood_loss_ml"] == 80

    def test_anaesthesia_upsert_and_enums(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        r = client.put(f"/api/theatre/cases/{cid}/anaesthesia", cookies=nurse_cookies,
                       json={"type": "GA", "asa_grade": "II"})
        assert r.status_code == 200 and r.json()["type"] == "GA"
        assert client.put(f"/api/theatre/cases/{cid}/anaesthesia", cookies=nurse_cookies,
                          json={"type": "Nonsense"}).status_code == 422
        assert client.put(f"/api/theatre/cases/{cid}/anaesthesia", cookies=nurse_cookies,
                          json={"type": "GA", "asa_grade": "IX"}).status_code == 422


class TestRoomsBilling:
    def test_rooms(self, client, nurse_cookies):
        assert len(client.get("/api/theatre/rooms", cookies=nurse_cookies).json()) >= 1  # seeded
        assert client.post("/api/theatre/rooms", cookies=nurse_cookies,
                           json={"name": f"Theatre {uuid.uuid4().hex[:4]}"}).status_code == 200

    def test_completing_priced_case_creates_bill_item(self, client, nurse_cookies, admin_cookies):
        base = settings.DATABASE_URL.rsplit("/", 1)[0]
        eng = create_engine(f"{base}/{TENANT}")
        with eng.begin() as conn:
            conn.execute(text("UPDATE acc_price_list SET unit_price = 12000 WHERE service_code = 'THEATRE-MAJOR'"))
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        _check_phase(client, nurse_cookies, cid, "TimeOut")
        client.post(f"/api/theatre/cases/{cid}/start", cookies=nurse_cookies)
        client.post(f"/api/theatre/cases/{cid}/to-recovery", cookies=nurse_cookies)
        _check_phase(client, nurse_cookies, cid, "SignOut")
        client.post(f"/api/theatre/cases/{cid}/complete", cookies=nurse_cookies)
        with eng.connect() as conn:
            n = conn.execute(text(
                "SELECT count(*) FROM invoice_items ii JOIN invoices i ON i.invoice_id = ii.invoice_id "
                "WHERE i.patient_id = :pid AND ii.item_type = 'Theatre'"), {"pid": pid}).scalar()
        eng.dispose()
        assert n >= 1
