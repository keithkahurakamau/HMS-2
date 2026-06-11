"""
Ward & bed setup integration tests.

Covers the new /api/wards setup endpoints:
  - POST /            create ward (validation + duplicate guard)
  - POST /{id}/beds   single + bulk bed creation, capacity guard
  - PATCH /beds/{id}  housekeeping status changes (Cleaning → Available)
  - DELETE /beds/{id} removal of never-used beds
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
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


@pytest.fixture(scope="module")
def ward(client, admin_cookies):
    """A fresh ward for this test run (unique name, capacity 5)."""
    name = f"ZZ_TEST_WARD_{uuid.uuid4().hex[:6].upper()}"
    r = client.post("/api/wards/", cookies=admin_cookies, json={"name": name, "capacity": 5})
    assert r.status_code == 200, r.text
    return {"ward_id": r.json()["ward_id"], "name": name}


class TestWardCreate:
    def test_requires_auth(self, client):
        r = client.post("/api/wards/", json={"name": "X", "capacity": 1})
        assert r.status_code == 401

    def test_duplicate_name_409(self, client, admin_cookies, ward):
        r = client.post("/api/wards/", cookies=admin_cookies,
                        json={"name": ward["name"].lower(), "capacity": 3})
        assert r.status_code == 409

    def test_zero_capacity_400(self, client, admin_cookies):
        r = client.post("/api/wards/", cookies=admin_cookies, json={"name": f"ZZ_{uuid.uuid4().hex[:6]}", "capacity": 0})
        assert r.status_code == 400


class TestBedSetup:
    def test_bulk_then_single_then_capacity_guard(self, client, admin_cookies, ward):
        wid = ward["ward_id"]

        # Bulk: 3 beds, auto-prefixed.
        r = client.post(f"/api/wards/{wid}/beds", cookies=admin_cookies,
                        json={"count": 3, "prefix": ward["name"][-6:]})
        assert r.status_code == 200, r.text
        assert len(r.json()["beds"]) == 3

        # Single named bed.
        single = f"{ward['name'][-6:]}-SOLO"
        r = client.post(f"/api/wards/{wid}/beds", cookies=admin_cookies, json={"bed_number": single})
        assert r.status_code == 200, r.text

        # Duplicate bed number → 409.
        r = client.post(f"/api/wards/{wid}/beds", cookies=admin_cookies, json={"bed_number": single})
        assert r.status_code == 409

        # 4 beds exist, capacity 5 → adding 2 more exceeds it.
        r = client.post(f"/api/wards/{wid}/beds", cookies=admin_cookies,
                        json={"count": 2, "prefix": ward["name"][-6:]})
        assert r.status_code == 400

    def test_board_shows_new_beds_available(self, client, admin_cookies, ward):
        r = client.get("/api/wards/board", cookies=admin_cookies)
        assert r.status_code == 200
        mine = next((w for w in r.json() if w["id"] == ward["ward_id"]), None)
        assert mine is not None
        assert mine["beds"], "expected beds on the board"
        assert all(b["status"] == "Available" for b in mine["beds"])


class TestBedLifecycle:
    def test_status_cycle_and_delete(self, client, admin_cookies, ward):
        r = client.get("/api/wards/board", cookies=admin_cookies)
        bed = next(w for w in r.json() if w["id"] == ward["ward_id"])["beds"][0]

        # Cleaning → Available (the housekeeping loop).
        r = client.patch(f"/api/wards/beds/{bed['id']}", cookies=admin_cookies, json={"status": "Cleaning"})
        assert r.status_code == 200, r.text
        r = client.patch(f"/api/wards/beds/{bed['id']}", cookies=admin_cookies, json={"status": "Available"})
        assert r.status_code == 200

        # Occupied is not settable through setup.
        r = client.patch(f"/api/wards/beds/{bed['id']}", cookies=admin_cookies, json={"status": "Occupied"})
        assert r.status_code == 400

        # Never-admitted bed deletes cleanly.
        r = client.delete(f"/api/wards/beds/{bed['id']}", cookies=admin_cookies)
        assert r.status_code == 200
