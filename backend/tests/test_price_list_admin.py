"""
Price-list admin integration tests.

Covers the new /api/accounting/config/price-list endpoints:
  - POST /import-lab-tests seeds Lab price items from the lab catalogue
    (idempotent — re-running creates nothing new)
  - q= search matches name and service code
  - DELETE removes a price item
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


class TestImportLabTests:
    def test_import_requires_auth(self, client):
        r = client.post("/api/accounting/config/price-list/import-lab-tests")
        assert r.status_code == 401

    def test_import_is_idempotent(self, client, admin_cookies):
        r1 = client.post("/api/accounting/config/price-list/import-lab-tests", cookies=admin_cookies)
        assert r1.status_code == 200, r1.text
        r2 = client.post("/api/accounting/config/price-list/import-lab-tests", cookies=admin_cookies)
        assert r2.status_code == 200
        # Second run must create nothing — everything already imported.
        assert r2.json()["created"] == 0

    def test_imported_items_are_lab_category(self, client, admin_cookies):
        client.post("/api/accounting/config/price-list/import-lab-tests", cookies=admin_cookies)
        r = client.get("/api/accounting/config/price-list", params={"category": "Lab"}, cookies=admin_cookies)
        assert r.status_code == 200
        lab_codes = [p["service_code"] for p in r.json()]
        assert any(code.startswith("LAB-") for code in lab_codes)


class TestSearchAndDelete:
    def test_q_search_matches_code_and_name(self, client, admin_cookies):
        tag = uuid.uuid4().hex[:8].upper()
        r = client.post("/api/accounting/config/price-list", cookies=admin_cookies, json={
            "service_code": f"ZZT-{tag}",
            "name": f"Searchable Test Service {tag}",
            "category": "Other",
            "unit_price": 100,
        })
        assert r.status_code == 200, r.text
        price_id = r.json()["price_id"]

        by_code = client.get("/api/accounting/config/price-list", params={"q": f"ZZT-{tag}"}, cookies=admin_cookies)
        by_name = client.get("/api/accounting/config/price-list", params={"q": tag.lower()}, cookies=admin_cookies)
        assert any(p["price_id"] == price_id for p in by_code.json())
        assert any(p["price_id"] == price_id for p in by_name.json())

        # Cleanup via the new DELETE — doubles as the delete test.
        r = client.delete(f"/api/accounting/config/price-list/{price_id}", cookies=admin_cookies)
        assert r.status_code == 200
        gone = client.get("/api/accounting/config/price-list", params={"q": f"ZZT-{tag}"}, cookies=admin_cookies)
        assert all(p["price_id"] != price_id for p in gone.json())

    def test_delete_missing_404(self, client, admin_cookies):
        r = client.delete("/api/accounting/config/price-list/99999999", cookies=admin_cookies)
        assert r.status_code == 404
