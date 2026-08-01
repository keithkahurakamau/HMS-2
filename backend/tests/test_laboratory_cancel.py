"""Laboratory can remove a pending test from the queue (soft cancel + reason)."""
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


def _new_patient(client) -> dict:
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_LABCAN_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Lab Cancel", "sex": "Male",
        "date_of_birth": "1990-01-01", "telephone_1": _phone()})
    assert r.status_code == 200, r.text
    return r.json()


def _catalog_id(client, lab_cookies) -> int:
    r = client.post("/api/laboratory/catalog", cookies=lab_cookies, json={
        "test_name": f"Cancelable {uuid.uuid4().hex[:6]}", "category": "Hematology",
        "default_specimen_type": "Blood", "base_price": 100, "requires_barcode": False})
    assert r.status_code in (200, 201), r.text
    return r.json()["catalog_id"]


def _order_test(client, doctor_cookies, patient_id, catalog_id) -> int:
    r = client.post("/api/laboratory/orders", cookies=doctor_cookies, json={
        "patient_id": patient_id, "tests": [{"catalog_id": catalog_id, "priority": "Routine"}]})
    assert r.status_code in (200, 201), r.text
    # order response returns created tests; grab the first test_id
    body = r.json()
    tests = body if isinstance(body, list) else body.get("tests", body.get("created", []))
    return tests[0]["test_id"]


def test_cancel_requires_auth(client):
    client.cookies.pop("access_token", None)
    r = client.post("/api/laboratory/tests/1/cancel", json={"reason": "x"})
    assert r.status_code == 401


def test_cancel_unknown_returns_404(client, lab_cookies):
    client.cookies.update(lab_cookies)
    r = client.post("/api/laboratory/tests/999999999/cancel", json={"reason": "x"})
    assert r.status_code == 404


def test_cancel_drops_test_from_queue(client, receptionist_cookies, doctor_cookies, lab_cookies):
    client.cookies.update(receptionist_cookies)
    patient = _new_patient(client)
    pid = patient["patient_id"]
    try:
        cat_id = _catalog_id(client, lab_cookies)
        client.cookies.update(doctor_cookies)
        test_id = _order_test(client, doctor_cookies, pid, cat_id)

        client.cookies.update(lab_cookies)
        # It should appear in the queue first.
        q = client.get("/api/laboratory/queue", cookies=lab_cookies).json()
        assert any(t["test_id"] == test_id for t in q)

        r = client.post(f"/api/laboratory/tests/{test_id}/cancel",
                        cookies=lab_cookies, json={"reason": "Ordered in error"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"

        # Cancelled tests drop out of the pending queue.
        q2 = client.get("/api/laboratory/queue", cookies=lab_cookies).json()
        assert not any(t["test_id"] == test_id for t in q2)

        # Cancelling again is refused (already cancelled).
        again = client.post(f"/api/laboratory/tests/{test_id}/cancel",
                            cookies=lab_cookies, json={"reason": "x"})
        assert again.status_code == 400
    finally:
        client.cookies.update(receptionist_cookies)
        client.delete(f"/api/patients/{pid}")
