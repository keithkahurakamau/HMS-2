"""Maternity module: gating, permissions, and episode lifecycle tests."""
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
        c.get("/api/maternity/episodes")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


class TestAccess:
    def test_unauthenticated_401(self, client):
        r = client.get("/api/maternity/episodes")
        assert r.status_code == 401

    def test_nurse_can_list(self, client, nurse_cookies):
        r = client.get("/api/maternity/episodes", cookies=nurse_cookies)
        assert r.status_code == 200

    def test_receptionist_403(self, client, receptionist_cookies):
        r = client.get("/api/maternity/episodes", cookies=receptionist_cookies)
        assert r.status_code == 403


def _make_patient(client, admin_cookies) -> int:
    suffix = uuid.uuid4().hex[:8]
    r = client.post("/api/patients/", cookies=admin_cookies, json={
        "surname": f"Mat{suffix}",
        "other_names": "Test Mother",
        "sex": "Female",
        "date_of_birth": "1996-04-02",
        "telephone_1": f"+2547{suffix[:8]}",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["patient_id"]


class TestEpisodeLifecycle:
    def test_create_list_get_close(self, client, nurse_cookies, admin_cookies):
        pid = _make_patient(client, admin_cookies)

        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 2, "para": 1, "lmp": "2026-03-01",
        })
        assert r.status_code == 200, r.text
        ep = r.json()
        assert ep["status"] == "Active"
        # EDD defaults to LMP + 280 days
        assert ep["edd"] == "2026-12-06"

        # Duplicate Active episode → 409
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 2, "para": 1,
        })
        assert r.status_code == 409

        # List filters by patient
        r = client.get(f"/api/maternity/episodes?patient_id={pid}", cookies=nurse_cookies)
        assert r.status_code == 200
        assert any(e["episode_id"] == ep["episode_id"] for e in r.json())

        # Detail view carries the child collections
        r = client.get(f"/api/maternity/episodes/{ep['episode_id']}", cookies=nurse_cookies)
        assert r.status_code == 200
        body = r.json()
        assert body["anc_visits"] == []
        assert body["deliveries"] == []

        # Close
        r = client.patch(
            f"/api/maternity/episodes/{ep['episode_id']}/close",
            cookies=nurse_cookies, json={"status": "Closed", "reason": "test"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "Closed"

        # After closing, a new episode is allowed again
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": pid, "gravida": 3, "para": 1,
        })
        assert r.status_code == 200

    def test_unknown_patient_404(self, client, nurse_cookies):
        r = client.post("/api/maternity/episodes", cookies=nurse_cookies, json={
            "patient_id": 99999999, "gravida": 1, "para": 0,
        })
        assert r.status_code == 404
