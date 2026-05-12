"""
Laboratory module integration tests.

Covers the flexibility revamp:
  - Catalog CRUD (create / patch / soft-delete) with discrete parameters
  - Parameter add/update/delete endpoints
  - Order creation respecting requires_barcode (Pending vs Pending Collection)
  - Specimen collect endpoint (auto-generates barcode when none supplied)
  - Complete with reusable items (logged but not deducted)
  - Reject flow

Runs against a live server at http://localhost:8000 with the demo seed loaded.
"""
import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


# ─── 1. Catalog CRUD ────────────────────────────────────────────────────────

class TestLabCatalog:
    def test_list_catalog_requires_auth(self, client):
        r = client.get("/api/laboratory/catalog")
        assert r.status_code == 401

    def test_admin_can_list_catalog(self, client, admin_cookies):
        r = client.get("/api/laboratory/catalog", cookies=admin_cookies)
        assert r.status_code == 200
        catalog = r.json()
        assert isinstance(catalog, list)
        # Seed inserts at least the six demo tests.
        names = {c["test_name"] for c in catalog}
        assert "Complete Blood Count (CBC)" in names

    def test_catalog_entries_carry_parameters(self, client, admin_cookies):
        r = client.get("/api/laboratory/catalog", cookies=admin_cookies)
        assert r.status_code == 200
        cbc = next((c for c in r.json() if c["test_name"] == "Complete Blood Count (CBC)"), None)
        assert cbc is not None
        keys = {p["key"] for p in cbc["parameters"]}
        # WBC, RBC, HGB, HCT, PLT all live in the seed
        assert {"wbc", "hgb", "plt"}.issubset(keys)

    def test_lab_tech_can_create_catalog_entry(self, client, lab_cookies):
        payload = {
            "test_name": "Test ESR (auto-test)",
            "category": "Hematology",
            "default_specimen_type": "Blood",
            "base_price": 300,
            "turnaround_hours": 2,
            "requires_barcode": False,
            "parameters": [
                {"key": "esr", "name": "ESR", "unit": "mm/hr", "value_type": "number",
                 "ref_low": 0, "ref_high": 20, "sort_order": 1, "is_active": True}
            ],
        }
        r = client.post("/api/laboratory/catalog", json=payload, cookies=lab_cookies)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["test_name"] == "Test ESR (auto-test)"
        assert len(body["parameters"]) == 1
        # Cleanup
        client.delete(f"/api/laboratory/catalog/{body['catalog_id']}", cookies=lab_cookies)

    def test_receptionist_cannot_create_catalog(self, client, receptionist_cookies):
        payload = {"test_name": "Unauthorized test", "category": "x",
                   "default_specimen_type": "Blood", "base_price": 1}
        r = client.post("/api/laboratory/catalog", json=payload, cookies=receptionist_cookies)
        assert r.status_code == 403

    def test_patch_catalog_entry(self, client, lab_cookies):
        create = client.post("/api/laboratory/catalog", cookies=lab_cookies, json={
            "test_name": "Patchable test (auto)", "category": "x",
            "default_specimen_type": "Urine", "base_price": 100,
        }).json()
        try:
            r = client.patch(f"/api/laboratory/catalog/{create['catalog_id']}",
                             cookies=lab_cookies, json={"base_price": 250, "requires_barcode": True})
            assert r.status_code == 200
            assert float(r.json()["base_price"]) == 250
            assert r.json()["requires_barcode"] is True
        finally:
            client.delete(f"/api/laboratory/catalog/{create['catalog_id']}", cookies=lab_cookies)

    def test_delete_catalog_soft_deactivates(self, client, lab_cookies):
        c = client.post("/api/laboratory/catalog", cookies=lab_cookies, json={
            "test_name": "Soft-delete test (auto)", "category": "x",
            "default_specimen_type": "Blood", "base_price": 1,
        }).json()
        r = client.delete(f"/api/laboratory/catalog/{c['catalog_id']}", cookies=lab_cookies)
        assert r.status_code == 200
        # Active list should no longer include it
        active = client.get("/api/laboratory/catalog", cookies=lab_cookies).json()
        assert all(row["catalog_id"] != c["catalog_id"] for row in active)
        # include_inactive surfaces it
        full = client.get("/api/laboratory/catalog?include_inactive=true", cookies=lab_cookies).json()
        assert any(row["catalog_id"] == c["catalog_id"] for row in full)


# ─── 2. Parameter CRUD ──────────────────────────────────────────────────────

class TestParameterCRUD:
    def _new_catalog(self, client, cookies):
        return client.post("/api/laboratory/catalog", cookies=cookies, json={
            "test_name": "Param fixture (auto)", "category": "x",
            "default_specimen_type": "Blood", "base_price": 0,
        }).json()

    def test_add_param(self, client, lab_cookies):
        c = self._new_catalog(client, lab_cookies)
        try:
            r = client.post(f"/api/laboratory/catalog/{c['catalog_id']}/parameters", cookies=lab_cookies, json={
                "key": "ph", "name": "pH", "unit": "", "value_type": "number",
                "ref_low": 4.5, "ref_high": 8.0, "sort_order": 1, "is_active": True,
            })
            assert r.status_code == 200
            assert r.json()["key"] == "ph"
        finally:
            client.delete(f"/api/laboratory/catalog/{c['catalog_id']}", cookies=lab_cookies)

    def test_update_and_delete_param(self, client, lab_cookies):
        c = self._new_catalog(client, lab_cookies)
        param = client.post(f"/api/laboratory/catalog/{c['catalog_id']}/parameters", cookies=lab_cookies, json={
            "key": "k", "name": "Something", "unit": "u", "value_type": "number",
            "ref_low": 0, "ref_high": 10, "sort_order": 1, "is_active": True,
        }).json()
        try:
            r = client.patch(f"/api/laboratory/parameters/{param['parameter_id']}", cookies=lab_cookies, json={
                "key": "k", "name": "Updated", "unit": "u", "value_type": "number",
                "ref_low": 1, "ref_high": 20, "sort_order": 2, "is_active": True,
            })
            assert r.status_code == 200
            assert r.json()["name"] == "Updated"
            assert r.json()["ref_high"] == 20

            r2 = client.delete(f"/api/laboratory/parameters/{param['parameter_id']}", cookies=lab_cookies)
            assert r2.status_code == 200
        finally:
            client.delete(f"/api/laboratory/catalog/{c['catalog_id']}", cookies=lab_cookies)


# ─── 3. Order + specimen + complete flow ────────────────────────────────────

@pytest.fixture(scope="module")
def lab_patient_id(client, doctor_cookies):
    """Return any patient id we can target. Seed has at least 10."""
    r = client.get("/api/patients/?search=Kamau", cookies=doctor_cookies)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, "Demo seed must produce at least one Kamau patient"
    return rows[0]["patient_id"]


def _cbc_catalog_id(client, cookies):
    cat = client.get("/api/laboratory/catalog", cookies=cookies).json()
    cbc = next(c for c in cat if c["test_name"] == "Complete Blood Count (CBC)")
    return cbc["catalog_id"], cbc["requires_barcode"]


class TestOrderFlow:
    def test_doctor_creates_lab_order(self, client, doctor_cookies, lab_patient_id):
        catalog_id, requires_barcode = _cbc_catalog_id(client, doctor_cookies)
        r = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
            "patient_id": lab_patient_id,
            "tests": [{"catalog_id": catalog_id, "priority": "Routine"}],
        })
        assert r.status_code == 200, r.text
        created = r.json()["created"]
        assert len(created) == 1
        # CBC has requires_barcode=True in seed → initial status is "Pending Collection"
        expected = "Pending Collection" if requires_barcode else "Pending"
        assert created[0]["status"] == expected

    def test_create_order_rejects_unknown_catalog(self, client, doctor_cookies, lab_patient_id):
        r = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
            "patient_id": lab_patient_id,
            "tests": [{"catalog_id": 999999}],
        })
        assert r.status_code == 400

    def test_collect_specimen_assigns_barcode(self, client, doctor_cookies, lab_cookies, lab_patient_id):
        catalog_id, _ = _cbc_catalog_id(client, doctor_cookies)
        created = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
            "patient_id": lab_patient_id,
            "tests": [{"catalog_id": catalog_id}],
        }).json()["created"]
        test_id = created[0]["test_id"]

        r = client.post(f"/api/laboratory/tests/{test_id}/collect", cookies=lab_cookies, json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "in_progress"
        assert body["specimen_id"].startswith("LAB-")

    def test_complete_with_reusable_does_not_deduct(self, client, doctor_cookies, lab_cookies, lab_patient_id):
        # Find a reusable inventory batch in the lab
        inv = client.get("/api/laboratory/inventory", cookies=lab_cookies).json()
        reusable = next((i for i in inv if i.get("is_reusable")), None)
        if reusable is None:
            pytest.skip("Seed has no reusable lab inventory in this run.")
        starting_stock = reusable["stock"]

        catalog_id, _ = _cbc_catalog_id(client, doctor_cookies)
        created = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
            "patient_id": lab_patient_id,
            "tests": [{"catalog_id": catalog_id}],
        }).json()["created"]
        test_id = created[0]["test_id"]

        # Complete with the reusable item present — qty=0 signals "reusable use".
        payload = {
            "result_data": {"wbc": 6.0, "hgb": 14.0, "plt": 250},
            "tech_notes": "auto-test reusable",
            "consumed_items": [{"batch_id": reusable["batch_id"], "quantity": 0}],
        }
        r = client.post(f"/api/laboratory/tests/{test_id}/complete", cookies=lab_cookies, json=payload)
        assert r.status_code == 200, r.text

        # Stock should NOT have changed.
        inv_after = client.get("/api/laboratory/inventory", cookies=lab_cookies).json()
        after = next((i for i in inv_after if i["batch_id"] == reusable["batch_id"]), None)
        assert after is not None
        assert after["stock"] == starting_stock, "Reusable items must not decrement stock."

    def test_reject_sample(self, client, doctor_cookies, lab_cookies, lab_patient_id):
        catalog_id, _ = _cbc_catalog_id(client, doctor_cookies)
        created = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
            "patient_id": lab_patient_id,
            "tests": [{"catalog_id": catalog_id}],
        }).json()["created"]
        test_id = created[0]["test_id"]

        r = client.post(f"/api/laboratory/tests/{test_id}/reject", cookies=lab_cookies,
                        json={"reason": "auto-test rejection"})
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
