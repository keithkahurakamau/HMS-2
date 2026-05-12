"""
Cheque register integration tests.

Covers the full lifecycle:
  - CRUD (list / summary / detail / create / patch)
  - Transitions: deposit, clear (posts Payment), bounce, cancel
  - Permission gating
  - Duplicate detection
"""
import pytest
import httpx
from datetime import date

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


def _make_payload(suffix: str, **overrides):
    base = {
        "cheque_number": f"AUTO-{suffix}",
        "drawer_name": f"AutoTest Drawer {suffix}",
        "drawer_type": "Insurance",
        "bank_name": "Test Bank",
        "bank_branch": "Main",
        "amount": 12500,
        "currency": "KES",
        "date_on_cheque": str(date.today()),
        "notes": "auto-test fixture",
    }
    base.update(overrides)
    return base


# ─── List / summary / read ─────────────────────────────────────────────────

class TestChequeRead:
    def test_list_requires_auth(self, client):
        r = client.get("/api/cheques/")
        assert r.status_code == 401

    def test_admin_lists(self, client, admin_cookies):
        r = client.get("/api/cheques/", cookies=admin_cookies)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_doctor_can_read(self, client, doctor_cookies):
        """Clinical roles get cheques:read so they can see payment status."""
        r = client.get("/api/cheques/", cookies=doctor_cookies)
        assert r.status_code == 200

    def test_summary_shape(self, client, admin_cookies):
        r = client.get("/api/cheques/summary", cookies=admin_cookies)
        assert r.status_code == 200
        body = r.json()
        for key in ("Received", "Deposited", "Cleared", "Bounced", "Cancelled"):
            assert key in body
            assert "count" in body[key] and "total" in body[key]


# ─── Create / duplicate detection / patch ──────────────────────────────────

class TestChequeCRUD:
    def test_admin_creates(self, client, admin_cookies):
        payload = _make_payload("CREATE1")
        r = client.post("/api/cheques/", cookies=admin_cookies, json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "Received"
        assert body["cheque_number"] == "AUTO-CREATE1"

    def test_doctor_cannot_create(self, client, doctor_cookies):
        r = client.post("/api/cheques/", cookies=doctor_cookies,
                        json=_make_payload("NOPE"))
        assert r.status_code == 403

    def test_duplicate_rejected(self, client, admin_cookies):
        payload = _make_payload("DUP1")
        client.post("/api/cheques/", cookies=admin_cookies, json=payload)
        again = client.post("/api/cheques/", cookies=admin_cookies, json=payload)
        assert again.status_code == 409

    def test_invalid_drawer_type(self, client, admin_cookies):
        r = client.post("/api/cheques/", cookies=admin_cookies,
                        json=_make_payload("BADTYPE", drawer_type="NotARealType"))
        assert r.status_code == 422  # pydantic validator fires

    def test_amount_must_be_positive(self, client, admin_cookies):
        r = client.post("/api/cheques/", cookies=admin_cookies,
                        json=_make_payload("ZERO", amount=0))
        assert r.status_code == 422

    def test_patch_updates_non_terminal(self, client, admin_cookies):
        created = client.post("/api/cheques/", cookies=admin_cookies,
                              json=_make_payload("PATCH1")).json()
        r = client.patch(f"/api/cheques/{created['cheque_id']}",
                         cookies=admin_cookies, json={"notes": "edited", "amount": 99999})
        assert r.status_code == 200
        assert r.json()["notes"] == "edited"
        assert float(r.json()["amount"]) == 99999

    def test_get_one(self, client, admin_cookies):
        created = client.post("/api/cheques/", cookies=admin_cookies,
                              json=_make_payload("GET1")).json()
        r = client.get(f"/api/cheques/{created['cheque_id']}", cookies=admin_cookies)
        assert r.status_code == 200
        assert r.json()["cheque_id"] == created["cheque_id"]


# ─── Transition flow ───────────────────────────────────────────────────────

class TestChequeLifecycle:
    def _create(self, client, cookies, suffix, **overrides):
        return client.post("/api/cheques/", cookies=cookies,
                           json=_make_payload(suffix, **overrides)).json()

    def test_deposit(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "DEP1")
        r = client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                        json={"deposit_account": "KCB 1180123456"})
        assert r.status_code == 200
        assert r.json()["status"] == "Deposited"
        assert r.json()["deposit_account"] == "KCB 1180123456"

    def test_deposit_blocked_when_not_received(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "DEP2")
        client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                    json={"deposit_account": "X"})
        r = client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                        json={"deposit_account": "Y"})
        assert r.status_code == 400

    def test_clear_posts_payment_against_invoice(self, client, admin_cookies, doctor_cookies):
        """Clearing a cheque linked to an invoice must bump invoice.amount_paid."""
        # Find an invoice we can pay against — seed produces some, but if none
        # exist, skip rather than failing the suite.
        invoices = client.get("/api/billing/invoices", cookies=admin_cookies)
        if invoices.status_code != 200 or not invoices.json():
            pytest.skip("No invoices available in demo seed.")
        invoice = invoices.json()[0]

        c = self._create(client, admin_cookies, "CLEAR1",
                         invoice_id=invoice["invoice_id"],
                         amount=100,
                         patient_id=invoice.get("patient_id"))
        client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                    json={"deposit_account": "KCB 1180"})
        before_paid = float(invoice.get("amount_paid") or 0)

        r = client.post(f"/api/cheques/{c['cheque_id']}/clear", cookies=admin_cookies, json={})
        assert r.status_code == 200
        assert r.json()["status"] == "Cleared"

        after = client.get(f"/api/billing/invoices/{invoice['invoice_id']}", cookies=admin_cookies)
        if after.status_code == 200:
            after_paid = float(after.json().get("amount_paid") or 0)
            assert after_paid >= before_paid + 100 - 0.01

    def test_bounce(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "BNC1")
        client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                    json={"deposit_account": "K"})
        r = client.post(f"/api/cheques/{c['cheque_id']}/bounce", cookies=admin_cookies,
                        json={"reason": "Insufficient funds"})
        assert r.status_code == 200
        assert r.json()["status"] == "Bounced"
        assert "Insufficient funds" in r.json()["bounce_reason"]

    def test_bounce_requires_reason(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "BNC2")
        client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                    json={"deposit_account": "K"})
        r = client.post(f"/api/cheques/{c['cheque_id']}/bounce", cookies=admin_cookies,
                        json={"reason": ""})
        assert r.status_code in (400, 422)

    def test_cancel(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "CAN1")
        r = client.post(f"/api/cheques/{c['cheque_id']}/cancel", cookies=admin_cookies,
                        json={"reason": "Issued in error"})
        assert r.status_code == 200
        assert r.json()["status"] == "Cancelled"

    def test_cancel_after_clear_rejected(self, client, admin_cookies):
        """Once cleared, a cheque is terminal — cancel must refuse."""
        c = self._create(client, admin_cookies, "CAN2")
        client.post(f"/api/cheques/{c['cheque_id']}/deposit", cookies=admin_cookies,
                    json={"deposit_account": "K"})
        client.post(f"/api/cheques/{c['cheque_id']}/clear", cookies=admin_cookies, json={})
        r = client.post(f"/api/cheques/{c['cheque_id']}/cancel", cookies=admin_cookies,
                        json={"reason": "too late"})
        assert r.status_code == 400

    def test_patch_blocked_after_terminal(self, client, admin_cookies):
        c = self._create(client, admin_cookies, "EDITX")
        client.post(f"/api/cheques/{c['cheque_id']}/cancel", cookies=admin_cookies,
                    json={"reason": "stop"})
        r = client.patch(f"/api/cheques/{c['cheque_id']}", cookies=admin_cookies,
                         json={"notes": "should fail"})
        assert r.status_code == 400


# ─── Filters ───────────────────────────────────────────────────────────────

class TestChequeFilters:
    def test_status_filter(self, client, admin_cookies):
        r = client.get("/api/cheques/?status=Received", cookies=admin_cookies)
        assert r.status_code == 200
        for c in r.json():
            assert c["status"] == "Received"

    def test_search_by_drawer(self, client, admin_cookies):
        # Use a known seed entry — Jubilee Insurance ships in seed_demo.
        r = client.get("/api/cheques/?search=Jubilee", cookies=admin_cookies)
        assert r.status_code == 200
        for c in r.json():
            haystack = f"{c['drawer_name']} {c['bank_name']} {c['cheque_number']}".lower()
            assert "jubilee" in haystack
