"""Reprintable document archive — index + per-document payloads.

Live-server integration test (server on :8000, tenant mayoclinic_db), matching
the house style for route tests. Creates its own patient and invoice so the
assertions don't depend on whatever happens to be seeded.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}

KINDS = {"invoice", "prescription", "lab_report",
         "radiology_report", "admission", "visit_summary"}


def _charge_consultation(client, doctor_cookies, patient_id: int) -> int:
    """Creates a Pending invoice the only way the API allows — a doctor
    charging a consultation — and returns its id.

    Reads the id straight from the tenant DB rather than scanning
    /billing/queue: that queue is shared tenant-wide and unbounded, so on a
    busy database the invoice we just made can fall outside the listing and
    the test fails for reasons that have nothing to do with the archive.
    """
    r = client.post("/api/billing/consultation-fee", cookies=doctor_cookies,
                    json={"patient_id": patient_id})
    assert r.status_code == 200, r.text

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine, text
    from app.config.settings import settings

    engine = create_engine(settings.DATABASE_URL.rsplit("/", 1)[0] + "/mayoclinic_db")
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT invoice_id FROM invoices WHERE patient_id = :pid "
                "ORDER BY invoice_id DESC LIMIT 1"
            ), {"pid": patient_id}).first()
        assert row is not None, f"no invoice created for patient {patient_id}"
        return row[0]
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def client(admin_cookies):
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True, timeout=60) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        c.cookies.update(admin_cookies)
        yield c


@pytest.fixture()
def patient(client):
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_DOCS_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Archive Test", "sex": "Female",
        "date_of_birth": "1990-05-04",
        "telephone_1": "9" + uuid.uuid4().int.__str__()[:11],
    })
    assert r.status_code == 200, r.text
    p = r.json()
    yield p
    client.delete(f"/api/patients/{p['patient_id']}")


def test_new_patient_has_an_empty_archive(client, patient):
    r = client.get(f"/api/patients/{patient['patient_id']}/documents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["documents"] == []
    assert body["total"] == 0
    # The patient block still comes back so the UI can render a header.
    assert body["patient"]["outpatient_no"] == patient["outpatient_no"]


def test_index_advertises_every_reprintable_kind(client, patient):
    r = client.get(f"/api/patients/{patient['patient_id']}/documents")
    assert set(r.json()["kinds"]) == KINDS


def test_unknown_patient_is_404(client):
    assert client.get("/api/patients/99999999/documents").status_code == 404


def test_unknown_kind_is_rejected(client, patient):
    pid = patient["patient_id"]
    assert client.get(f"/api/patients/{pid}/documents", params={"kind": "nope"}).status_code == 400
    assert client.get(f"/api/patients/{pid}/documents/nope/1").status_code == 400


def test_invoice_is_indexed_and_reprintable(client, doctor_cookies, patient):
    pid = patient["patient_id"]
    invoice_id = _charge_consultation(client, doctor_cookies, pid)

    listing = client.get(f"/api/patients/{pid}/documents").json()
    invoices = [d for d in listing["documents"] if d["kind"] == "invoice"]
    assert [d["id"] for d in invoices] == [invoice_id]
    assert invoices[0]["date"] is not None

    detail = client.get(f"/api/patients/{pid}/documents/invoice/{invoice_id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()["payload"]
    # Exactly the shape printInvoice() consumes.
    assert payload["invoice_id"] == invoice_id
    assert payload["patient_opd"] == patient["outpatient_no"]
    assert payload["items"], "invoice payload must carry its line items"
    assert float(payload["total_amount"]) > 0


def test_kind_filter_narrows_the_index(client, doctor_cookies, patient):
    pid = patient["patient_id"]
    _charge_consultation(client, doctor_cookies, pid)
    r = client.get(f"/api/patients/{pid}/documents", params={"kind": "invoice"})
    assert r.status_code == 200
    assert {d["kind"] for d in r.json()["documents"]} == {"invoice"}

    r = client.get(f"/api/patients/{pid}/documents", params={"kind": "lab_report"})
    assert r.json()["documents"] == []


def test_document_belonging_to_another_patient_is_404(client, doctor_cookies, patient):
    """A reprint must not become a way to read another chart by guessing IDs."""
    pid = patient["patient_id"]
    other = client.post("/api/patients/", json={
        "surname": f"ZZ_DOCS_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Other Patient", "sex": "Male",
        "date_of_birth": "1985-01-01",
        "telephone_1": "9" + uuid.uuid4().int.__str__()[:11],
    }).json()
    try:
        invoice_id = _charge_consultation(client, doctor_cookies, other["patient_id"])
        # Real invoice, wrong patient in the path → not found, not leaked.
        r = client.get(f"/api/patients/{pid}/documents/invoice/{invoice_id}")
        assert r.status_code == 404
    finally:
        client.delete(f"/api/patients/{other['patient_id']}")


def test_index_is_sorted_newest_first(client, doctor_cookies, patient):
    pid = patient["patient_id"]
    _charge_consultation(client, doctor_cookies, pid)
    docs = client.get(f"/api/patients/{pid}/documents").json()["documents"]
    dated = [d["date"] for d in docs if d["date"]]
    assert dated == sorted(dated, reverse=True)
