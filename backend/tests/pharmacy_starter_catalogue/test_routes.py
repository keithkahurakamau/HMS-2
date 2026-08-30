"""HTTP-layer tests for /api/pharmacy/starter-catalogue*: the operator
feature-flag gate (both ways) and the adopt endpoint's response shape.

Uses FastAPI's TestClient with dependency overrides rather than a live
server: get_db is swapped for the isolated test session (conftest.py),
get_current_user is swapped for a fixed permissioned user, and
get_tenant_flags_cached is monkeypatched so the test controls the tenant's
feature flag directly instead of needing a real master-DB tenant row.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core import module_gate
from app.core.dependencies import get_current_user
from app.main import app
from app.models.inventory import InventoryItem
from app.routes import pharmacy_starter_catalogue as route_module
from app.services import pharmacy_starter_catalogue as svc

TENANT_HEADERS = {"X-Tenant-ID": "hms_pharmacy_starter_test"}
CATALOGUE = ["Paracetamol 500mg", "Amoxicillin 250mg"]


@pytest.fixture(autouse=True)
def _fake_catalogue(monkeypatch):
    monkeypatch.setattr(svc, "_cache", list(CATALOGUE))
    yield
    monkeypatch.setattr(svc, "_cache", None)


@pytest.fixture(autouse=True)
def _bypass_module_gate(monkeypatch):
    """The ModuleGateMiddleware checks whether the tenant has purchased the
    whole "pharmacy" module against the real master DB. That's a separate
    concern from this suite (the pharmacy_starter_catalogue feature flag),
    and the fake tenant here has no master-DB row at all, so let every
    module through and test only our own flag check.
    """
    monkeypatch.setattr(module_gate, "is_module_enabled", lambda flags_raw, module: True)


def _set_flag(monkeypatch, enabled: bool):
    monkeypatch.setattr(
        route_module, "get_tenant_flags_cached",
        lambda tenant_db: '{"pharmacy_starter_catalogue": true}' if enabled else '{}',
    )


@pytest.fixture()
def client(db):
    def _get_db():
        yield db

    def _get_current_user():
        return {"user_id": 1, "permissions": ["pharmacy:read", "pharmacy:manage"]}

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    try:
        test_client = TestClient(app)
        # POST /adopt is a state-changing request: the app's CSRF middleware
        # requires the double-submit cookie + header pair on every unsafe
        # method, GET requests don't need it.
        test_client.cookies.set("csrf_token", "test-csrf-token")
        test_client.headers.update({"x-csrf-token": "test-csrf-token"})
        yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


class TestFlagGating:
    def test_status_reports_disabled_when_flag_off(self, client, monkeypatch):
        _set_flag(monkeypatch, False)
        r = client.get("/api/pharmacy/starter-catalogue/status", headers=TENANT_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"enabled": False}

    def test_status_reports_enabled_when_flag_on(self, client, monkeypatch):
        _set_flag(monkeypatch, True)
        r = client.get("/api/pharmacy/starter-catalogue/status", headers=TENANT_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"enabled": True}

    def test_status_disabled_without_a_tenant_header(self, client, monkeypatch):
        _set_flag(monkeypatch, True)
        r = client.get("/api/pharmacy/starter-catalogue/status")
        assert r.status_code == 200, r.text
        assert r.json() == {"enabled": False}

    def test_catalogue_is_403_when_flag_off(self, client, monkeypatch):
        _set_flag(monkeypatch, False)
        r = client.get("/api/pharmacy/starter-catalogue", headers=TENANT_HEADERS)
        assert r.status_code == 403, r.text

    def test_catalogue_is_200_when_flag_on(self, client, monkeypatch):
        _set_flag(monkeypatch, True)
        r = client.get("/api/pharmacy/starter-catalogue", headers=TENANT_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["available"] is True
        assert set(body["products"]) == set(CATALOGUE)

    def test_adopt_is_403_when_flag_off(self, client, monkeypatch, db):
        _set_flag(monkeypatch, False)
        r = client.post("/api/pharmacy/starter-catalogue/adopt", headers=TENANT_HEADERS, json={})
        assert r.status_code == 403, r.text
        assert db.query(InventoryItem).count() == 0

    def test_adopt_is_200_when_flag_on_and_creates_items(self, client, monkeypatch, db):
        _set_flag(monkeypatch, True)
        r = client.post("/api/pharmacy/starter-catalogue/adopt", headers=TENANT_HEADERS, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["created"] == 2
        assert body["skipped"] == 0
        assert db.query(InventoryItem).count() == 2


class TestUnavailableCatalogueDoesNotCrash:
    def test_empty_catalogue_is_a_clean_200_not_an_error(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_cache", [])
        _set_flag(monkeypatch, True)
        r = client.get("/api/pharmacy/starter-catalogue", headers=TENANT_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"available": False, "products": []}

    def test_adopt_against_empty_catalogue_reports_zero_not_an_error(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_cache", [])
        _set_flag(monkeypatch, True)
        r = client.post("/api/pharmacy/starter-catalogue/adopt", headers=TENANT_HEADERS, json={})
        assert r.status_code == 200, r.text
        assert r.json() == {"created": 0, "skipped": 0, "created_items": [], "skipped_items": []}
