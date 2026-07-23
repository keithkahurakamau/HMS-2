"""Dialysis Phase 2 — vascular access, machines, schedules, roster, renal
profile, consumables, and session charge-on-complete. Hits the live server."""
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
        c.get("/api/dialysis/orders")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    s = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Ren{s}", "other_names": "Unit Test", "sex": "Male",
        "date_of_birth": "1975-01-01", "telephone_1": f"+2547{s[:8]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


class TestVascularAccess:
    def test_crud(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/dialysis/vascular-accesses", cookies=nurse_cookies,
                        json={"patient_id": pid, "type": "AVF", "site": "Left radiocephalic"})
        assert r.status_code == 200, r.text
        aid = r.json()["access_id"]
        r = client.get(f"/api/dialysis/vascular-accesses?patient_id={pid}", cookies=nurse_cookies)
        assert r.status_code == 200 and any(a["access_id"] == aid for a in r.json())
        r = client.put(f"/api/dialysis/vascular-accesses/{aid}", cookies=nurse_cookies, json={"status": "Failed"})
        assert r.status_code == 200 and r.json()["status"] == "Failed"

    def test_receptionist_forbidden(self, client, receptionist_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/dialysis/vascular-accesses", cookies=receptionist_cookies,
                        json={"patient_id": pid, "type": "AVF"})
        assert r.status_code == 403


class TestMachinesSchedulesRoster:
    def test_machines(self, client, nurse_cookies):
        r = client.get("/api/dialysis/machines", cookies=nurse_cookies)
        assert r.status_code == 200 and len(r.json()) >= 1  # seeded HD-01
        r = client.post("/api/dialysis/machines", cookies=nurse_cookies,
                        json={"name": f"HD-{uuid.uuid4().hex[:4]}", "station": "Bay 2"})
        assert r.status_code == 200

    def test_schedule_and_roster(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        r = client.post("/api/dialysis/schedules", cookies=nurse_cookies,
                        json={"patient_id": pid, "pattern": "Daily", "shift": "Morning"})
        assert r.status_code == 200, r.text
        body = client.get("/api/dialysis/roster", cookies=nurse_cookies).json()
        assert "machines" in body and "scheduled" in body
        assert any(s["patient_id"] == pid for s in body["scheduled"])  # Daily → every weekday

    def test_renal_profile(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        client.post("/api/dialysis/vascular-accesses", cookies=nurse_cookies,
                    json={"patient_id": pid, "type": "AVG"})
        body = client.get(f"/api/dialysis/patients/{pid}/renal-profile", cookies=nurse_cookies).json()
        assert body["patient_id"] == pid
        assert len(body["accesses"]) == 1
        assert "adequacy_trend" in body


class TestConsumablesBilling:
    def _run_to_complete(self, client, cookies, pid):
        oid = client.post("/api/dialysis/orders", cookies=cookies, json={"patient_id": pid}).json()["order_id"]
        client.post(f"/api/dialysis/orders/{oid}/checklist-runs", cookies=cookies, json={"passed": True})
        client.post(f"/api/dialysis/orders/{oid}/connect", cookies=cookies)
        client.post(f"/api/dialysis/orders/{oid}/disconnect", cookies=cookies)
        client.post(f"/api/dialysis/orders/{oid}/complete", cookies=cookies)
        return oid

    def test_consumable_recorded_and_in_detail(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        oid = client.post("/api/dialysis/orders", cookies=nurse_cookies, json={"patient_id": pid}).json()["order_id"]
        r = client.post(f"/api/dialysis/orders/{oid}/consumables", cookies=nurse_cookies,
                        json={"item_name": "Dialyzer F6", "qty": 1, "dialyzer_reuse_count": 0})
        assert r.status_code == 200, r.text
        detail = client.get(f"/api/dialysis/orders/{oid}", cookies=nurse_cookies).json()
        assert len(detail["consumables"]) == 1
        assert detail["consumables"][0]["item_name"] == "Dialyzer F6"

    def test_completing_priced_session_creates_bill_item(self, client, nurse_cookies, admin_cookies):
        base = settings.DATABASE_URL.rsplit("/", 1)[0]
        eng = create_engine(f"{base}/{TENANT}")
        with eng.begin() as conn:
            conn.execute(text("UPDATE acc_price_list SET unit_price = 4500 WHERE service_code = 'DIA-HD-SESSION'"))
        pid = _make_patient(client, admin_cookies)
        self._run_to_complete(client, nurse_cookies, pid)
        with eng.connect() as conn:
            n = conn.execute(text(
                "SELECT count(*) FROM invoice_items ii "
                "JOIN invoices i ON i.invoice_id = ii.invoice_id "
                "WHERE i.patient_id = :pid AND ii.item_type = 'Dialysis'"
            ), {"pid": pid}).scalar()
        eng.dispose()
        assert n >= 1
