"""Theatre Phase 2 — team, consumables/implants, recovery observations, board."""
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
        c.get("/api/theatre/cases")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _make_patient(client, admin_cookies) -> int:
    s = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Srg{s}", "other_names": "Unit Test", "sex": "Male",
        "date_of_birth": "1985-01-01", "telephone_1": f"+2547{s[:8]}"})
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


def _make_case(client, cookies, pid) -> int:
    return client.post("/api/theatre/cases", cookies=cookies,
                       json={"patient_id": pid, "procedure_name": "Laparotomy"}).json()["case_id"]


def _to_recovery(client, cookies, cid):
    client.post(f"/api/theatre/cases/{cid}/checklist-runs", cookies=cookies, json={"phase": "TimeOut", "checked": True})
    client.post(f"/api/theatre/cases/{cid}/start", cookies=cookies)
    client.post(f"/api/theatre/cases/{cid}/to-recovery", cookies=cookies)


class TestTeam:
    def test_add_remove_and_enum(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        r = client.post(f"/api/theatre/cases/{cid}/team-members", cookies=nurse_cookies,
                        json={"role": "Surgeon", "name": "Dr A"})
        assert r.status_code == 200, r.text
        mid = r.json()["member_id"]
        assert client.post(f"/api/theatre/cases/{cid}/team-members", cookies=nurse_cookies,
                           json={"role": "Bogus"}).status_code == 422
        detail = client.get(f"/api/theatre/cases/{cid}", cookies=nurse_cookies).json()
        assert any(m["member_id"] == mid for m in detail["team_members"])
        assert client.delete(f"/api/theatre/cases/{cid}/team-members/{mid}", cookies=nurse_cookies).status_code == 200

    def test_receptionist_forbidden(self, client, receptionist_cookies, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        assert client.post(f"/api/theatre/cases/{cid}/team-members", cookies=receptionist_cookies,
                           json={"role": "Surgeon"}).status_code == 403


class TestConsumablesRecovery:
    def test_consumable_with_implant(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        r = client.post(f"/api/theatre/cases/{cid}/consumables", cookies=nurse_cookies,
                        json={"item_name": "Hip prosthesis", "qty": 1, "is_implant": True, "serial_no": "IMP-77"})
        assert r.status_code == 200 and r.json()["is_implant"] is True
        detail = client.get(f"/api/theatre/cases/{cid}", cookies=nurse_cookies).json()
        assert detail["consumables"][0]["serial_no"] == "IMP-77"

    def test_recovery_obs_gated_to_recovery(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        cid = _make_case(client, nurse_cookies, pid)
        # Scheduled → recovery obs blocked
        assert client.post(f"/api/theatre/cases/{cid}/recovery-observations", cookies=nurse_cookies,
                           json={"pulse": 80}).status_code == 409
        _to_recovery(client, nurse_cookies, cid)
        r = client.post(f"/api/theatre/cases/{cid}/recovery-observations", cookies=nurse_cookies,
                        json={"bp_systolic": 120, "bp_diastolic": 70, "pulse": 78, "spo2": 98, "pain_score": 3, "consciousness": "A"})
        assert r.status_code == 200, r.text
        detail = client.get(f"/api/theatre/cases/{cid}", cookies=nurse_cookies).json()
        assert len(detail["recovery_observations"]) == 1 and detail["recovery_observations"][0]["spo2"] == 98


class TestBoard:
    def test_board_shape(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)
        _make_case(client, nurse_cookies, pid)  # unscheduled → not necessarily on board
        body = client.get("/api/theatre/board", cookies=nurse_cookies).json()
        assert "rooms" in body and "unassigned" in body and "date" in body
        assert isinstance(body["rooms"], list)
