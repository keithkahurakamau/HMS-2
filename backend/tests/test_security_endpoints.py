"""
Endpoint-security regression tests for the two holes closed in the audit.

1. The public hospital picker (/api/public/hospitals) must not leak commercial
   internals (feature_flags / plan_limits / notes) or suspended tenants to
   anonymous callers.
2. Ward discharge must reject unauthenticated callers (it previously had no
   auth dependency at all).
"""
from __future__ import annotations

import httpx
import pytest

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


class TestPublicHospitalsNoLeak:
    def test_anonymous_gets_minimal_fields_only(self, client):
        r = client.get("/api/public/hospitals")  # no auth cookies
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows, "expected at least one active tenant"
        for t in rows:
            assert "feature_flags" not in t, "anonymous caller must not see feature_flags"
            assert "plan_limits" not in t, "anonymous caller must not see plan_limits"
            assert "notes" not in t, "anonymous caller must not see operator notes"
            assert t["is_active"] is True, "anonymous caller must only see active tenants"

    def test_anonymous_cannot_force_inactive(self, client):
        r = client.get("/api/public/hospitals", params={"include_inactive": "true"})
        assert r.status_code == 200
        assert all(t["is_active"] is True for t in r.json()), \
            "include_inactive must be ignored for non-superadmin callers"


class TestWardDischargeGuarded:
    def test_discharge_requires_auth(self, client):
        # No staff cookie → must be refused (was previously wide open).
        r = client.post("/api/wards/discharge/1", json={"notes": "x"})
        assert r.status_code in (401, 403), r.text
