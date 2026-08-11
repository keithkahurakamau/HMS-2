"""Dialysis module: gating, permissions, order lifecycle, state machine,
observations, complications, adequacy, checklists. Hits the live server."""
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
        c.get("/api/dialysis/orders")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Dia{suffix}", "other_names": "Renal Test", "sex": "Male",
        "date_of_birth": "1980-01-01", "telephone_1": f"+2547{suffix[:8]}",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


def _make_order(client, cookies, pid) -> int:
    r = client.post("/api/dialysis/orders", cookies=cookies, json={
        "patient_id": pid, "dialyzer": "F6", "treatment_time_min": 240,
        "pre_weight_kg": 72.5, "target_uf_ml": 2500, "dialysate_temp_c": 36.5,
    })
    assert r.status_code == 200, r.text
    return r.json()["order_id"]


class TestAccess:
    def test_unauthenticated_401(self, client):
        assert client.get("/api/dialysis/orders").status_code == 401

    def test_nurse_can_list(self, client, nurse_cookies):
        assert client.get("/api/dialysis/orders", cookies=nurse_cookies).status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        assert client.get("/api/dialysis/orders", cookies=receptionist_cookies).status_code == 403


class TestOrderLifecycle:
    def test_create_list_get(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        # duplicate live session → 409
        r = client.post("/api/dialysis/orders", cookies=nurse_cookies, json={"patient_id": pid})
        assert r.status_code == 409
        # list filter
        r = client.get(f"/api/dialysis/orders?patient_id={pid}", cookies=nurse_cookies)
        assert r.status_code == 200
        assert any(o["order_id"] == oid for o in r.json())
        # detail children
        body = client.get(f"/api/dialysis/orders/{oid}", cookies=nurse_cookies).json()
        assert body["status"] == "Ordered"
        assert body["treatment_no"] == 1
        assert body["observations"] == [] and body["adequacy"] is None

    def test_unknown_patient_404(self, client, nurse_cookies):
        r = client.post("/api/dialysis/orders", cookies=nurse_cookies, json={"patient_id": 99999999})
        assert r.status_code == 404


class TestStateMachine:
    def test_full_flow(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        # connect before checklist → 409
        assert client.post(f"/api/dialysis/orders/{oid}/connect", cookies=nurse_cookies).status_code == 409
        # pass a checklist
        assert client.post(f"/api/dialysis/orders/{oid}/checklist-runs", cookies=nurse_cookies,
                           json={"passed": True}).status_code == 200
        # connect
        r = client.post(f"/api/dialysis/orders/{oid}/connect", cookies=nurse_cookies)
        assert r.status_code == 200 and r.json()["status"] == "Connected"
        # observation now allowed + appears in detail
        r = client.post(f"/api/dialysis/orders/{oid}/observations", cookies=nurse_cookies,
                        json={"bp_systolic": 130, "bp_diastolic": 80, "pulse": 76, "uf_volume_ml": 500})
        assert r.status_code == 200
        assert len(client.get(f"/api/dialysis/orders/{oid}", cookies=nurse_cookies).json()["observations"]) == 1
        # disconnect → complete
        assert client.post(f"/api/dialysis/orders/{oid}/disconnect", cookies=nurse_cookies).json()["status"] == "Disconnected"
        assert client.post(f"/api/dialysis/orders/{oid}/complete", cookies=nurse_cookies).json()["status"] == "Completed"
        # illegal transition now
        assert client.post(f"/api/dialysis/orders/{oid}/connect", cookies=nurse_cookies).status_code == 409

    def test_observation_blocked_while_ordered(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        r = client.post(f"/api/dialysis/orders/{oid}/observations", cookies=nurse_cookies, json={"pulse": 70})
        assert r.status_code == 409

    def test_cancel_requires_reason(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        assert client.post(f"/api/dialysis/orders/{oid}/cancel", cookies=nurse_cookies, json={}).status_code == 422
        r = client.post(f"/api/dialysis/orders/{oid}/cancel", cookies=nurse_cookies, json={"reason": "clotted lines"})
        assert r.status_code == 200 and r.json()["status"] == "Cancelled"


class TestComplicationsAdequacy:
    def test_complication_enum(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        assert client.post(f"/api/dialysis/orders/{oid}/complications", cookies=nurse_cookies,
                           json={"type": "Hypotension", "intervention": "saline bolus"}).status_code == 200
        assert client.post(f"/api/dialysis/orders/{oid}/complications", cookies=nurse_cookies,
                           json={"type": "Nonsense"}).status_code == 422

    def test_adequacy_computed(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = _make_order(client, nurse_cookies, pid)
        r = client.post(f"/api/dialysis/orders/{oid}/adequacy", cookies=nurse_cookies, json={
            "pre_urea": 30, "post_urea": 9, "session_duration_min": 240,
            "ultrafiltration_actual_ml": 2500, "post_weight_kg": 70,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["urr"] == 70.0 and 1.3 < body["kt_v"] < 1.6
        # bad input → 422
        assert client.post(f"/api/dialysis/orders/{oid}/adequacy", cookies=nurse_cookies, json={
            "pre_urea": 0, "post_urea": 9, "session_duration_min": 240,
            "ultrafiltration_actual_ml": 2500, "post_weight_kg": 70,
        }).status_code == 422


class TestChecklists:
    def test_list_seeded(self, client, nurse_cookies):
        r = client.get("/api/dialysis/checklists", cookies=nurse_cookies)
        assert r.status_code == 200 and len(r.json()) >= 5

    def test_create_requires_manage(self, client, nurse_cookies, receptionist_cookies):
        assert client.post("/api/dialysis/checklists", cookies=receptionist_cookies,
                           json={"name": "X"}).status_code == 403
        assert client.post("/api/dialysis/checklists", cookies=nurse_cookies,
                           json={"name": f"Chk {uuid.uuid4().hex[:6]}"}).status_code == 200
