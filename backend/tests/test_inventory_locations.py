"""
Inventory storage-location management + expired-stock view tests.

Covers:
  - POST/PATCH/DELETE /inventory/locations (admin / inventory:manage)
  - Duplicate-name guard, delete-empty-only guard
  - GET /inventory/expired window filter + shape
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


class TestLocationCrud:
    def test_requires_auth(self, client):
        assert client.post("/api/inventory/locations", json={"name": "X"}).status_code == 401

    def test_create_update_delete(self, client, admin_cookies):
        name = f"ZZ_LOC_{uuid.uuid4().hex[:6].upper()}"
        r = client.post("/api/inventory/locations", cookies=admin_cookies,
                        json={"name": name, "description": "test store"})
        assert r.status_code == 200, r.text
        loc_id = r.json()["location_id"]

        # Duplicate (case-insensitive) rejected.
        dup = client.post("/api/inventory/locations", cookies=admin_cookies, json={"name": name.lower()})
        assert dup.status_code == 409

        # Rename.
        r = client.patch(f"/api/inventory/locations/{loc_id}", cookies=admin_cookies,
                         json={"name": f"{name}_2", "description": "renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == f"{name}_2"

        # Appears in the list.
        listed = client.get("/api/inventory/locations", cookies=admin_cookies).json()
        assert any(l["location_id"] == loc_id for l in listed)

        # Empty location deletes cleanly.
        assert client.delete(f"/api/inventory/locations/{loc_id}", cookies=admin_cookies).status_code == 200

    def test_delete_missing_404(self, client, admin_cookies):
        assert client.delete("/api/inventory/locations/99999999", cookies=admin_cookies).status_code == 404


class TestExpiredView:
    def test_requires_auth(self, client):
        assert client.get("/api/inventory/expired").status_code == 401

    def test_returns_list_shape(self, client, admin_cookies):
        r = client.get("/api/inventory/expired", params={"window_days": 90}, cookies=admin_cookies)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for key in ("batch_id", "item_name", "location_name", "expiry_date", "days_to_expiry", "is_expired"):
                assert key in row
