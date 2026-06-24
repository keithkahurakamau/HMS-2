"""Billing can void a fully-unpaid Pending invoice (soft + GL reversal)."""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        tok = c.cookies.get("csrf_token")
        if tok:
            c.headers["x-csrf-token"] = tok
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client):
    """Create a patient. Caller must have receptionist/doctor cookies set on the client."""
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_VOID_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Void Test", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _charge_consult_fee(client, patient_id):
    """Charge a consultation fee → creates a Pending invoice (+GL post).
    Caller must have doctor cookies set on the client."""
    r = client.post("/api/billing/consultation-fee",
                    json={"patient_id": patient_id, "amount": 500})
    if r.status_code == 400 and "fee" in r.text.lower():
        # No fee configured — set one first, then retry
        client.put("/api/billing/consultation-fee/me", json={"amount": 500})
        r = client.post("/api/billing/consultation-fee",
                        json={"patient_id": patient_id, "amount": 500})
    assert r.status_code == 200, r.text


def _find_pending_invoice(client, patient_id):
    """Find the pending invoice for a patient. Caller must have billing cookies set."""
    q = client.get("/api/billing/queue").json()
    mine = [i for i in q if i.get("patient_id") == patient_id]
    assert mine, f"expected a pending invoice for {patient_id}"
    return mine[0]["invoice_id"]


def test_void_requires_auth(client):
    # No auth cookie -> must reject with 401 (CSRF header still present).
    client.cookies.pop("access_token", None)
    r = client.post("/api/billing/invoices/1/void", json={"reason": "x"})
    assert r.status_code == 401


def test_void_unknown_returns_404(client, admin_cookies):
    client.cookies.update(admin_cookies)
    r = client.post("/api/billing/invoices/999999999/void", json={"reason": "x"})
    assert r.status_code == 404


def test_void_pending_invoice_drops_from_queue(client, doctor_cookies, admin_cookies, receptionist_cookies):
    # Receptionist creates the patient
    client.cookies.update(receptionist_cookies)
    patient = _new_patient(client)
    pid = patient["patient_id"]
    try:
        # Doctor charges the consultation fee (creates Pending invoice + GL post)
        client.cookies.update(doctor_cookies)
        _charge_consult_fee(client, pid)

        # Admin finds and voids the invoice
        client.cookies.update(admin_cookies)
        inv_id = _find_pending_invoice(client, pid)

        r = client.post(f"/api/billing/invoices/{inv_id}/void",
                        json={"reason": "Duplicate charge"})
        assert r.status_code == 200, r.text

        q = client.get("/api/billing/queue").json()
        assert all(i["invoice_id"] != inv_id for i in q)

        # Idempotency / guard: a second void is rejected (already Cancelled).
        again = client.post(f"/api/billing/invoices/{inv_id}/void",
                            json={"reason": "again"})
        assert again.status_code == 400, again.text
    finally:
        client.cookies.update(doctor_cookies)
        client.delete(f"/api/patients/{pid}")
