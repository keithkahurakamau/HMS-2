"""
Hospital settings (tenant-side) integration tests.

Covers:
  - List groups by category and includes seeded defaults
  - GET single setting by category+key
  - PUT upsert: type coercion (string/number/boolean/json)
  - PUT bulk update
  - DELETE setting
  - Permission gating: settings:read for everyone, settings:manage admin-only
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


class TestSettingsList:
    def test_list_requires_auth(self, client):
        r = client.get("/api/settings/")
        assert r.status_code == 401

    def test_admin_lists_grouped_categories(self, client, admin_cookies):
        r = client.get("/api/settings/", cookies=admin_cookies)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "categories" in body
        category_keys = {c["key"] for c in body["categories"]}
        # Seed must include these.
        assert {"branding", "billing", "laboratory", "radiology"}.issubset(category_keys)

    def test_doctor_can_read_settings(self, client, doctor_cookies):
        """Every role gets settings:read so the UI can react to branding/etc."""
        r = client.get("/api/settings/", cookies=doctor_cookies)
        assert r.status_code == 200

    def test_filter_by_category(self, client, admin_cookies):
        r = client.get("/api/settings/?category=billing", cookies=admin_cookies)
        assert r.status_code == 200
        cats = r.json()["categories"]
        assert all(c["key"] == "billing" for c in cats)
        items = cats[0]["items"]
        keys = {i["key"] for i in items}
        assert "currency" in keys


class TestSettingGetUpsert:
    def test_get_single(self, client, admin_cookies):
        r = client.get("/api/settings/branding/hospital_name", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["key"] == "hospital_name"

    def test_get_unknown_404(self, client, admin_cookies):
        r = client.get("/api/settings/does/not_exist", cookies=admin_cookies)
        assert r.status_code == 404

    def test_doctor_cannot_upsert(self, client, doctor_cookies):
        r = client.put("/api/settings/", cookies=doctor_cookies, json={
            "category": "billing", "key": "currency", "value": "USD",
        })
        assert r.status_code == 403

    def test_admin_upsert_string(self, client, admin_cookies):
        r = client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "branding", "key": "hospital_name", "value": "Mayo Clinic Kenya"
        })
        assert r.status_code == 200, r.text
        assert r.json()["value"] == "Mayo Clinic Kenya"

    def test_upsert_boolean_coercion(self, client, admin_cookies):
        # boolean column stored as text "true"/"false" — verify decode
        r = client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "billing", "key": "lock_pricing_on_order", "value": "yes",
            "data_type": "boolean",
        })
        assert r.status_code == 200
        assert r.json()["value"] is True

    def test_upsert_number_coercion(self, client, admin_cookies):
        r = client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "billing", "key": "tax_rate_pct", "value": 18,
            "data_type": "number",
        })
        assert r.status_code == 200
        assert r.json()["value"] in (18, 18.0)

    def test_upsert_rejects_bad_boolean(self, client, admin_cookies):
        r = client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "billing", "key": "lock_pricing_on_order", "value": "maybe",
            "data_type": "boolean",
        })
        assert r.status_code == 400

    def test_create_new_custom_setting(self, client, admin_cookies):
        r = client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "integrations", "key": "slack_webhook_auto",
            "label": "Slack webhook URL",
            "description": "Test custom setting",
            "data_type": "string", "value": "https://example.com/hook",
        })
        assert r.status_code == 200
        assert r.json()["category"] == "integrations"
        # Cleanup
        client.delete("/api/settings/integrations/slack_webhook_auto", cookies=admin_cookies)


class TestSettingsBulk:
    def test_bulk_update(self, client, admin_cookies):
        # Snapshot current values so we can restore.
        before = client.get("/api/settings/billing/currency", cookies=admin_cookies).json()
        before_tax = client.get("/api/settings/billing/tax_rate_pct", cookies=admin_cookies).json()

        r = client.put("/api/settings/bulk", cookies=admin_cookies, json={"updates": [
            {"category": "billing", "key": "currency", "value": "USD"},
            {"category": "billing", "key": "tax_rate_pct", "value": 20},
        ]})
        assert r.status_code == 200
        assert r.json()["count"] == 2

        # Restore so the test is idempotent.
        client.put("/api/settings/bulk", cookies=admin_cookies, json={"updates": [
            {"category": "billing", "key": "currency", "value": before["value"]},
            {"category": "billing", "key": "tax_rate_pct", "value": before_tax["value"]},
        ]})


class TestSettingsDelete:
    def test_delete_then_recreate(self, client, admin_cookies):
        # Create a throwaway custom setting then delete it.
        client.put("/api/settings/", cookies=admin_cookies, json={
            "category": "test_auto", "key": "throwaway",
            "data_type": "string", "value": "x",
        })
        r = client.delete("/api/settings/test_auto/throwaway", cookies=admin_cookies)
        assert r.status_code == 200
        gone = client.get("/api/settings/test_auto/throwaway", cookies=admin_cookies)
        assert gone.status_code == 404
