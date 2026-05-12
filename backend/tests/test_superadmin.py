"""
Superadmin endpoint tests:
  - Cross-tenant patient browser (read-only)
  - Tenant flexibility fields (feature_flags / plan_limits / notes)
  - Suspended-tenant filtering on /api/public/hospitals
"""
import os
import pytest
import httpx
from datetime import datetime, timedelta, timezone
from jose import jwt

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, follow_redirects=True) as c:
        yield c


@pytest.fixture(scope="module")
def superadmin_token():
    """Mint a real superadmin JWT directly so we don't burn the login rate limit.

    Reads the master DB via SQLAlchemy to find the first active superadmin.
    """
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from app.config.database import MasterSessionLocal
    from app.config.settings import settings
    from app.models.master import SuperAdmin

    db = MasterSessionLocal()
    try:
        admin = db.query(SuperAdmin).filter(SuperAdmin.is_active == True).first()
        if not admin:
            pytest.skip("No superadmin in master DB — seed first.")
        payload = {
            "user_id": admin.admin_id,
            "role": "superadmin",
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=20),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    finally:
        db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── /api/public/hospitals ─────────────────────────────────────────────────

class TestHospitalRegistry:
    def test_public_list_excludes_inactive(self, client):
        r = client.get("/api/public/hospitals")
        assert r.status_code == 200
        for t in r.json():
            assert t["is_active"] is True

    def test_include_inactive_requires_no_special_auth(self, client):
        """include_inactive is a query flag — endpoint stays public for the
        sign-in page picker. (This test pins behaviour: if it's later locked
        down, update the contract here.)"""
        r = client.get("/api/public/hospitals?include_inactive=true")
        assert r.status_code == 200


# ─── Tenant flexibility fields ─────────────────────────────────────────────

class TestTenantFlexibility:
    def test_patch_tenant_feature_flags(self, client, superadmin_token):
        # Find a tenant to patch (Mayo Clinic demo)
        hospitals = client.get("/api/public/hospitals?include_inactive=true",
                               headers=_auth(superadmin_token)).json()
        mayo = next((h for h in hospitals if h["db_name"] == "mayoclinic_db"), None)
        if not mayo:
            pytest.skip("Demo seed not present — run seed_demo.py first.")

        original_flags = mayo.get("feature_flags") or {}
        r = client.patch(f"/api/public/hospitals/{mayo['tenant_id']}",
                         headers=_auth(superadmin_token),
                         json={"feature_flags": {**original_flags, "auto_test_flag": True}})
        assert r.status_code == 200, r.text
        assert r.json()["feature_flags"]["auto_test_flag"] is True

        # Restore
        client.patch(f"/api/public/hospitals/{mayo['tenant_id']}",
                     headers=_auth(superadmin_token),
                     json={"feature_flags": original_flags})

    def test_patch_tenant_plan_limits(self, client, superadmin_token):
        hospitals = client.get("/api/public/hospitals?include_inactive=true",
                               headers=_auth(superadmin_token)).json()
        mayo = next((h for h in hospitals if h["db_name"] == "mayoclinic_db"), None)
        if not mayo:
            pytest.skip("Demo seed not present.")

        r = client.patch(f"/api/public/hospitals/{mayo['tenant_id']}",
                         headers=_auth(superadmin_token),
                         json={"plan_limits": {"max_users": 50, "storage_gb": 200}})
        assert r.status_code == 200
        body = r.json()
        assert body["plan_limits"]["max_users"] == 50
        assert body["plan_limits"]["storage_gb"] == 200

    def test_patch_tenant_notes(self, client, superadmin_token):
        hospitals = client.get("/api/public/hospitals?include_inactive=true",
                               headers=_auth(superadmin_token)).json()
        mayo = next((h for h in hospitals if h["db_name"] == "mayoclinic_db"), None)
        if not mayo:
            pytest.skip("Demo seed not present.")

        r = client.patch(f"/api/public/hospitals/{mayo['tenant_id']}",
                         headers=_auth(superadmin_token),
                         json={"notes": "Auto-test operator note"})
        assert r.status_code == 200
        assert r.json()["notes"] == "Auto-test operator note"

        # Clear so re-runs are idempotent
        client.patch(f"/api/public/hospitals/{mayo['tenant_id']}",
                     headers=_auth(superadmin_token), json={"notes": None})


# ─── Cross-tenant patient browser (read-only) ──────────────────────────────

class TestSuperadminPatientBrowser:
    def test_requires_superadmin_token(self, client):
        r = client.get("/api/public/superadmin/patients")
        assert r.status_code == 401

    def test_lists_patients_across_tenants(self, client, superadmin_token):
        r = client.get("/api/public/superadmin/patients",
                       headers=_auth(superadmin_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "patients" in body and "count" in body
        assert "tenants_scanned" in body
        assert isinstance(body["patients"], list)

    def test_search_filter(self, client, superadmin_token):
        r = client.get("/api/public/superadmin/patients?search=Kamau",
                       headers=_auth(superadmin_token))
        assert r.status_code == 200
        names = " ".join(p["surname"] + " " + (p["other_names"] or "") for p in r.json()["patients"])
        # Demo seed has a Kamau, John Mwangi; only assert when seed is present.
        if r.json()["count"] > 0:
            assert "Kamau" in names

    def test_tenant_filter(self, client, superadmin_token):
        # Use a known tenant_id when the demo seed is present.
        hospitals = client.get("/api/public/hospitals?include_inactive=true",
                               headers=_auth(superadmin_token)).json()
        mayo = next((h for h in hospitals if h["db_name"] == "mayoclinic_db"), None)
        if not mayo:
            pytest.skip("Demo seed not present.")

        r = client.get(f"/api/public/superadmin/patients?tenant_id={mayo['tenant_id']}",
                       headers=_auth(superadmin_token))
        assert r.status_code == 200
        for p in r.json()["patients"]:
            assert p["tenant_id"] == mayo["tenant_id"]

    def test_patient_detail_read_only_payload(self, client, superadmin_token):
        # Find a patient to detail
        listing = client.get("/api/public/superadmin/patients?limit_per_tenant=1",
                             headers=_auth(superadmin_token)).json()
        if listing["count"] == 0:
            pytest.skip("No patients to test against.")
        p = listing["patients"][0]
        r = client.get(f"/api/public/superadmin/patients/{p['tenant_id']}/{p['patient_id']}",
                       headers=_auth(superadmin_token))
        assert r.status_code == 200
        detail = r.json()
        assert "tenant" in detail
        assert detail["patient_id"] == p["patient_id"]
        # Read-only contract: ensure no write endpoints are advertised in the
        # response (sanity check — there's no mutation route on the path).
        assert "write" not in detail and "delete" not in detail
