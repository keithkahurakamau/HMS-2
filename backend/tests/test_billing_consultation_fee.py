"""
Per-doctor consultation fee integration tests.

Covers /api/billing/consultation-fee* :
  - Auth gating on GET/PUT /consultation-fee/me
  - GET returns the tenant default for a doctor with no saved fee
  - PUT upserts the doctor's personal fee (price-list row CONSULT-DR-<id>)
  - PUT rejects zero / negative amounts
  - POST /consultation-fee bills the doctor's *saved* fee server-side,
    ignoring whatever amount the client sends (tamper resistance)
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
        # Safe GET makes the server set the csrf_token cookie; echo it back
        # so PUT/POST pass the double-submit CSRF check.
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


# ─── helpers ────────────────────────────────────────────────────────────────

def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies) -> dict:
    tag = uuid.uuid4().hex[:6].upper()
    payload = {
        "surname": f"ZZ_TEST_{tag}",
        "other_names": "Fee Patient",
        "sex": "Male",
        "date_of_birth": "1990-06-01",
        "telephone_1": _unique_phone(),
    }
    r = client.post("/api/patients/", cookies=cookies, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _set_fee(client, cookies, amount: float) -> dict:
    r = client.put("/api/billing/consultation-fee/me", cookies=cookies, json={"amount": amount})
    assert r.status_code == 200, r.text
    return r.json()


# ─── 1. Auth ────────────────────────────────────────────────────────────────

class TestFeeAuth:
    def test_get_requires_auth(self, client):
        r = client.get("/api/billing/consultation-fee/me")
        assert r.status_code == 401

    def test_put_requires_auth(self, client):
        r = client.put("/api/billing/consultation-fee/me", json={"amount": 500})
        assert r.status_code == 401


# ─── 2. Read + upsert own fee ───────────────────────────────────────────────

class TestMyFee:
    def test_get_returns_amount_and_flag(self, client, doctor_cookies):
        r = client.get("/api/billing/consultation-fee/me", cookies=doctor_cookies)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "amount" in body and "is_custom" in body
        assert body["amount"] > 0

    def test_put_then_get_roundtrip(self, client, doctor_cookies):
        saved = _set_fee(client, doctor_cookies, 1750.50)
        assert saved == {"amount": 1750.50, "is_custom": True}

        r = client.get("/api/billing/consultation-fee/me", cookies=doctor_cookies)
        assert r.status_code == 200
        assert r.json() == {"amount": 1750.50, "is_custom": True}

    def test_put_is_an_update_not_a_duplicate(self, client, doctor_cookies):
        _set_fee(client, doctor_cookies, 1200)
        _set_fee(client, doctor_cookies, 1300)
        r = client.get("/api/billing/consultation-fee/me", cookies=doctor_cookies)
        assert r.json()["amount"] == 1300

    @pytest.mark.parametrize("bad", [0, -50, "not-a-number"])
    def test_put_rejects_invalid_amounts(self, client, doctor_cookies, bad):
        r = client.put("/api/billing/consultation-fee/me", cookies=doctor_cookies, json={"amount": bad})
        assert r.status_code in (400, 422), r.text


# ─── 3. Charging uses the saved fee server-side ─────────────────────────────

class TestChargeUsesSavedFee:
    def test_client_amount_cannot_override_saved_fee(
        self, client, doctor_cookies, receptionist_cookies
    ):
        # Doctor saves a distinctive fee, then the client tries to charge a
        # different (tiny) amount — the invoice must carry the saved fee.
        saved_amount = 1234.00
        _set_fee(client, doctor_cookies, saved_amount)

        patient = _new_patient(client, receptionist_cookies)
        r = client.post(
            "/api/billing/consultation-fee",
            cookies=doctor_cookies,
            json={"patient_id": patient["patient_id"], "amount": 5.0},
        )
        assert r.status_code == 200, r.text

        # The cashier's billing queue shows the Pending invoice with the line
        # item priced at the doctor's saved fee, not the tampered amount.
        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        invoices = [inv for inv in r.json() if inv["patient_id"] == patient["patient_id"]]
        assert invoices, "expected a Pending invoice for the charged patient"
        items = [i for i in invoices[0]["items"] if i["item_type"] == "Consultation"]
        assert items and items[0]["amount"] == saved_amount

    def test_charge_without_amount_uses_saved_fee(
        self, client, doctor_cookies, receptionist_cookies
    ):
        saved_amount = 1450.00
        _set_fee(client, doctor_cookies, saved_amount)

        patient = _new_patient(client, receptionist_cookies)
        r = client.post(
            "/api/billing/consultation-fee",
            cookies=doctor_cookies,
            json={"patient_id": patient["patient_id"]},
        )
        assert r.status_code == 200, r.text

        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        invoices = [inv for inv in r.json() if inv["patient_id"] == patient["patient_id"]]
        assert invoices
        items = [i for i in invoices[0]["items"] if i["item_type"] == "Consultation"]
        assert items and items[0]["amount"] == saved_amount
