"""
Unified payments-ledger integration tests.

Covers /api/billing/transactions :
  - Auth gating
  - A cash payment shows up with type, receipt reference, Completed status,
    and a human-readable description (the "all payments, even cash" ask).
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
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _unique_phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies) -> dict:
    tag = uuid.uuid4().hex[:6].upper()
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_TEST_{tag}",
        "other_names": "Ledger Patient",
        "sex": "Male",
        "date_of_birth": "1990-06-01",
        "telephone_1": _unique_phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestPaymentsLedger:
    def test_requires_auth(self, client):
        r = client.get("/api/billing/transactions")
        assert r.status_code == 401

    def test_cash_payment_recorded_with_description(self, client, doctor_cookies, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies)

        # Doctor charges a consultation → Pending invoice exists.
        r = client.post("/api/billing/consultation-fee", cookies=doctor_cookies,
                        json={"patient_id": patient["patient_id"]})
        assert r.status_code == 200, r.text

        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        invoice = next(inv for inv in r.json() if inv["patient_id"] == patient["patient_id"])

        # Cashier takes the full amount in cash.
        r = client.post("/api/billing/process-payment", cookies=receptionist_cookies, json={
            "invoice_id": invoice["invoice_id"],
            "amount": invoice["total_amount"],
            "payment_method": "Cash",
            "idempotency_key": uuid.uuid4().hex,
        })
        assert r.status_code == 200, r.text

        # The unified ledger must show the cash payment with all the
        # cashflow-readability fields.
        r = client.get("/api/billing/transactions", cookies=receptionist_cookies)
        assert r.status_code == 200, r.text
        rows = [t for t in r.json() if t["invoice_id"] == invoice["invoice_id"] and t["type"] == "Cash"]
        assert rows, "cash payment missing from the unified ledger"
        row = rows[0]
        assert row["status"] == "Completed"
        assert row["receipt"].startswith("PAY-")
        assert "Cash payment" in row["description"]
        assert f"Invoice #{invoice['invoice_id']}" in row["description"]
        assert row["amount"] == pytest.approx(invoice["total_amount"])

    def test_overpayment_rejected(self, client, doctor_cookies, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies)
        r = client.post("/api/billing/consultation-fee", cookies=doctor_cookies,
                        json={"patient_id": patient["patient_id"]})
        assert r.status_code == 200, r.text

        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        invoice = next(inv for inv in r.json() if inv["patient_id"] == patient["patient_id"])

        r = client.post("/api/billing/process-payment", cookies=receptionist_cookies, json={
            "invoice_id": invoice["invoice_id"],
            "amount": invoice["total_amount"] + 1000,
            "payment_method": "Cash",
            "idempotency_key": uuid.uuid4().hex,
        })
        assert r.status_code == 400
        assert "outstanding" in r.json()["detail"].lower()


class TestAccountingTransactionLog:
    def test_rebuild_backfills_cash_payment_into_journal(self, client, admin_cookies, doctor_cookies, receptionist_cookies):
        """A cash payment must be visible in the Accounting transaction log.

        The live path auto-posts; the rebuild endpoint replays history. We
        assert the end state: after a cash payment + rebuild, the journal
        register contains a billing entry referencing the invoice.
        """
        patient = _new_patient(client, receptionist_cookies)
        r = client.post("/api/billing/consultation-fee", cookies=doctor_cookies,
                        json={"patient_id": patient["patient_id"]})
        assert r.status_code == 200, r.text
        r = client.get("/api/billing/queue", cookies=receptionist_cookies)
        invoice = next(inv for inv in r.json() if inv["patient_id"] == patient["patient_id"])
        r = client.post("/api/billing/process-payment", cookies=receptionist_cookies, json={
            "invoice_id": invoice["invoice_id"],
            "amount": invoice["total_amount"],
            "payment_method": "Cash",
            "idempotency_key": uuid.uuid4().hex,
        })
        assert r.status_code == 200, r.text

        r = client.post("/api/accounting/transaction-log/rebuild", cookies=admin_cookies)
        assert r.status_code == 200, r.text
        assert "totals" in r.json()

        r = client.get("/api/accounting/transaction-log", cookies=admin_cookies,
                       params={"q": f"INV-{invoice['invoice_id']}", "source": "billing"})
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert items, "cash payment missing from the accounting transaction log"
        memos = " | ".join((i.get("memo") or "") for i in items)
        assert "Cash" in memos or "Payment" in memos
