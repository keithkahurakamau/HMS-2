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


def _open_tenant_session():
    """Open a direct Session against mayoclinic_db (consent-seed helper pattern)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config.settings import settings

    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    engine = create_engine(f"{base}/mayoclinic_db")
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _posted_gl_entry_ids(invoice_id):
    """entry_ids of POSTED GL entries for an invoice's items (direct DB read)."""
    import app.models.patient  # noqa: F401 – Invoice.patient relationship target
    from app.models.billing import InvoiceItem
    from app.models.accounting import JournalEntry

    engine, db = _open_tenant_session()
    try:
        item_ids = [r[0] for r in db.query(InvoiceItem.id)
                    .filter(InvoiceItem.invoice_id == invoice_id).all()]
        if not item_ids:
            return []
        return [r[0] for r in db.query(JournalEntry.entry_id).filter(
            JournalEntry.source_type == "billing.invoice.created",
            JournalEntry.source_id.in_(item_ids),
            JournalEntry.status == "posted",
        ).all()]
    finally:
        db.close()
        engine.dispose()


def _gl_entry_statuses(entry_ids):
    """{entry_id: status} for the given GL entry_ids (direct DB read)."""
    from app.models.accounting import JournalEntry

    engine, db = _open_tenant_session()
    try:
        rows = db.query(JournalEntry.entry_id, JournalEntry.status).filter(
            JournalEntry.entry_id.in_(entry_ids)).all()
        return {eid: status for eid, status in rows}
    finally:
        db.close()
        engine.dispose()


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

        # Capture the POSTED GL entries BEFORE the void. If the tenant has no
        # ledger mapping configured nothing posts — skip rather than pass
        # silently, so the reversal assertion is only meaningful when real.
        pre_posted = _posted_gl_entry_ids(inv_id)
        if not pre_posted:
            pytest.skip("no GL posting to reverse on this tenant")

        r = client.post(f"/api/billing/invoices/{inv_id}/void",
                        json={"reason": "Duplicate charge"})
        assert r.status_code == 200, r.text

        # The void MUST have reversed every previously-posted GL entry.
        post_statuses = _gl_entry_statuses(pre_posted)
        assert len(post_statuses) == len(pre_posted), post_statuses
        assert all(post_statuses.get(eid) == "reversed" for eid in pre_posted), \
            f"expected all {pre_posted} reversed, got {post_statuses}"

        q = client.get("/api/billing/queue").json()
        assert all(i["invoice_id"] != inv_id for i in q)

        # Idempotency / guard: a second void is rejected (already Cancelled).
        again = client.post(f"/api/billing/invoices/{inv_id}/void",
                            json={"reason": "again"})
        assert again.status_code == 400, again.text
    finally:
        client.cookies.update(doctor_cookies)
        client.delete(f"/api/patients/{pid}")
