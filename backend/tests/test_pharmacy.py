"""
Pharmacy module route-layer integration tests.

Runs against a live server at http://localhost:8000 with the demo seed
loaded. Pairs with backend/tests/accounting/test_pharmacy_payment.py and
test_pharmacy_otc_receipt_ledger.py which exercise the same routes via
direct function calls. This file is the HTTP/RBAC sibling: it locks
down auth gates, idempotency, validation, and response shapes by going
over the wire.

Covers:
  - Auth gating on every endpoint
  - Inventory list shape + zero-stock exclusion
  - Dispense happy path, idempotency, validation, walk-in OTC
  - Payment collection: cash, card, M-Pesa (tolerant of missing creds)
  - Payment-status poll + receipt endpoint
  - Transactions ledger pagination + filters
  - RBAC enforcement against the pharmacy permission catalog
"""
from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        yield c


# ─── Helpers ────────────────────────────────────────────────────────────────

def _unique_phone() -> str:
    """Return a Safaricom-shaped phone number unlikely to collide."""
    # 7xxxxxxxx — keep it 9 digits after the leading 0
    suffix = uuid.uuid4().int % 1_000_000_000
    return f"07{suffix:08d}"[:10]


def _new_patient(client: httpx.Client, cookies: dict, surname: str = "ZZ_PHARM_Test") -> dict:
    """Create a patient via the registry. Returns the response JSON (has
    patient_id + outpatient_no). Caller is responsible for cleanup via
    _cleanup_patient."""
    payload = {
        "surname": surname,
        "other_names": f"Auto {uuid.uuid4().hex[:6]}",
        "sex": "Female",
        "date_of_birth": "1990-01-01",
        "telephone_1": _unique_phone(),
    }
    r = client.post("/api/patients/", json=payload, cookies=cookies)
    assert r.status_code in (200, 201), f"patient create failed: {r.status_code} {r.text}"
    return r.json()


def _cleanup_patient(client: httpx.Client, cookies: dict, patient_id: int) -> None:
    """Soft-delete a test patient. Errors are swallowed — cleanup is
    best-effort."""
    try:
        client.delete(f"/api/patients/{patient_id}", cookies=cookies)
    except Exception:
        pass


def _get_first_available_batch(client: httpx.Client, cookies: dict, min_qty: int = 5) -> dict:
    """Pick a pharmacy batch with at least `min_qty` units. Skip the
    calling test if the seed doesn't have one — these tests rely on
    real inventory being present."""
    r = client.get("/api/pharmacy/inventory", cookies=cookies)
    assert r.status_code == 200, r.text
    rows = r.json()
    eligible = [row for row in rows if (row.get("quantity") or 0) >= min_qty]
    if not eligible:
        pytest.skip(f"No pharmacy inventory seeded with quantity ≥ {min_qty}")
    return eligible[0]


def _dispense(
    client: httpx.Client,
    cookies: dict,
    batch_id: int,
    *,
    quantity: int = 1,
    patient_id: int | None = None,
    idempotency_key: str | None = None,
    notes: str | None = None,
) -> httpx.Response:
    payload = {
        "idempotency_key": idempotency_key or uuid.uuid4().hex,
        "batch_id": batch_id,
        "quantity": quantity,
        "patient_id": patient_id,
        "notes": notes,
    }
    return client.post("/api/pharmacy/dispense", json=payload, cookies=cookies)


# ─── 1. Auth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_inventory_without_cookies_is_401(self, client):
        r = client.get("/api/pharmacy/inventory")
        assert r.status_code == 401, r.text

    def test_dispense_without_cookies_is_401(self, client):
        r = client.post("/api/pharmacy/dispense", json={
            "idempotency_key": uuid.uuid4().hex,
            "batch_id": 1,
            "quantity": 1,
        })
        assert r.status_code == 401, r.text

    def test_pay_without_cookies_is_401(self, client):
        r = client.post("/api/pharmacy/dispense/1/pay", json={
            "method": "cash", "amount": 100.0,
        })
        assert r.status_code == 401, r.text

    def test_transactions_without_cookies_is_401(self, client):
        r = client.get("/api/pharmacy/transactions")
        assert r.status_code == 401, r.text


# ─── 2. Inventory list ─────────────────────────────────────────────────────

class TestInventoryList:
    def test_pharmacist_lists_inventory_with_expected_shape(self, client, pharmacist_cookies):
        r = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("Pharmacy inventory empty in this seed run")
        expected_keys = {
            "item_id", "name", "category", "unit_price",
            "batch_id", "batch_number", "quantity", "expiry_date",
        }
        first = rows[0]
        missing = expected_keys - set(first.keys())
        assert not missing, f"Missing keys in inventory row: {missing}; got {first}"

    def test_zero_quantity_batches_are_excluded(self, client, pharmacist_cookies):
        r = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies)
        assert r.status_code == 200, r.text
        for row in r.json():
            assert (row.get("quantity") or 0) > 0, (
                f"Batch with quantity==0 leaked through: {row}"
            )


# ─── 3. Dispense — happy path ──────────────────────────────────────────────

class TestDispenseHappyPath:
    def test_dispense_returns_full_payload(self, client, pharmacist_cookies, admin_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            r = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            assert r.status_code == 200, r.text
            body = r.json()
            for key in ("dispense_id", "item_id", "quantity_dispensed",
                        "total_cost", "dispensed_at", "invoice_id",
                        "invoice_balance"):
                assert key in body, f"missing key {key} in {body}"
            assert body["quantity_dispensed"] == 1
            assert body["item_id"] == batch["item_id"]
            assert body["invoice_id"] is not None
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_inventory_quantity_drops_after_dispense(self, client, pharmacist_cookies, admin_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies, min_qty=5)
        start_qty = batch["quantity"]
        patient = _new_patient(client, admin_cookies)
        qty = 2
        try:
            r = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=qty,
                patient_id=patient["patient_id"],
            )
            assert r.status_code == 200, r.text

            inv = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies).json()
            after = next((b for b in inv if b["batch_id"] == batch["batch_id"]), None)
            # Batch may drop off the list if quantity hits zero — but with
            # min_qty=5 and qty=2 it should still be there.
            assert after is not None, "Batch disappeared from inventory list"
            assert after["quantity"] == start_qty - qty, (
                f"Expected {start_qty - qty}, got {after['quantity']}"
            )
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_second_dispense_to_same_patient_appends_same_invoice(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies, min_qty=5)
        patient = _new_patient(client, admin_cookies)
        try:
            r1 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            assert r1.status_code == 200, r1.text
            r2 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            assert r2.status_code == 200, r2.text
            assert r1.json()["invoice_id"] == r2.json()["invoice_id"], (
                f"Expected same invoice across two dispenses to one patient: "
                f"{r1.json()['invoice_id']} vs {r2.json()['invoice_id']}"
            )
            # Second invoice_balance should be >= first total_cost (we
            # appended a second line item without paying).
            assert r2.json()["invoice_balance"] >= r1.json()["total_cost"]
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])


# ─── 4. Dispense — idempotency ─────────────────────────────────────────────

class TestDispenseIdempotency:
    def test_same_idempotency_key_returns_same_dispense_no_double_deduct(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies, min_qty=5)
        start_qty = batch["quantity"]
        patient = _new_patient(client, admin_cookies)
        key = uuid.uuid4().hex
        try:
            r1 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=2,
                patient_id=patient["patient_id"], idempotency_key=key,
            )
            assert r1.status_code == 200, r1.text
            r2 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=2,
                patient_id=patient["patient_id"], idempotency_key=key,
            )
            assert r2.status_code == 200, r2.text
            assert r1.json()["dispense_id"] == r2.json()["dispense_id"]

            # Stock should reflect ONE deduction of 2, not two.
            inv = client.get("/api/pharmacy/inventory", cookies=pharmacist_cookies).json()
            after = next((b for b in inv if b["batch_id"] == batch["batch_id"]), None)
            if after is None:
                # Hit zero — would only happen if start_qty was exactly 2.
                assert start_qty == 2
            else:
                assert after["quantity"] == start_qty - 2, (
                    f"Double-deducted on idempotent retry: {after['quantity']} vs expected {start_qty - 2}"
                )
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_different_idempotency_keys_create_distinct_dispenses(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies, min_qty=5)
        patient = _new_patient(client, admin_cookies)
        try:
            r1 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            r2 = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            assert r1.status_code == 200 and r2.status_code == 200
            assert r1.json()["dispense_id"] != r2.json()["dispense_id"]
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])


# ─── 5. Dispense — validation ──────────────────────────────────────────────

class TestDispenseValidation:
    def test_unknown_batch_id_is_404(self, client, pharmacist_cookies):
        r = client.post("/api/pharmacy/dispense", cookies=pharmacist_cookies, json={
            "idempotency_key": uuid.uuid4().hex,
            "batch_id": 9_999_999,
            "quantity": 1,
        })
        assert r.status_code == 404, r.text
        assert "Stock batch not found" in r.text

    def test_insufficient_stock_is_400(self, client, pharmacist_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        r = client.post("/api/pharmacy/dispense", cookies=pharmacist_cookies, json={
            "idempotency_key": uuid.uuid4().hex,
            "batch_id": batch["batch_id"],
            "quantity": batch["quantity"] + 1_000_000,
        })
        assert r.status_code == 400, r.text
        assert "Insufficient stock" in r.text

    def test_quantity_zero_is_422(self, client, pharmacist_cookies):
        r = client.post("/api/pharmacy/dispense", cookies=pharmacist_cookies, json={
            "idempotency_key": uuid.uuid4().hex,
            "batch_id": 1,
            "quantity": 0,
        })
        assert r.status_code == 422, r.text

    def test_missing_idempotency_key_is_422(self, client, pharmacist_cookies):
        r = client.post("/api/pharmacy/dispense", cookies=pharmacist_cookies, json={
            "batch_id": 1,
            "quantity": 1,
        })
        assert r.status_code == 422, r.text


# ─── 6. Walk-in OTC ────────────────────────────────────────────────────────

class TestWalkInOTC:
    def test_walkin_dispense_creates_invoice(self, client, pharmacist_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        r = _dispense(
            client, pharmacist_cookies,
            batch_id=batch["batch_id"], quantity=1,
            patient_id=None,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["invoice_id"] is not None, (
            f"Walk-in dispense should still create an invoice: {body}"
        )
        assert body["invoice_balance"] is not None

    def test_walkin_receipt_shows_walk_in_label(self, client, pharmacist_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        r = _dispense(
            client, pharmacist_cookies,
            batch_id=batch["batch_id"], quantity=1,
            patient_id=None,
        )
        assert r.status_code == 200, r.text
        dispense_id = r.json()["dispense_id"]

        receipt = client.get(
            f"/api/pharmacy/dispense/{dispense_id}/receipt",
            cookies=pharmacist_cookies,
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["patient"] == "Walk-in"


# ─── 7. Payment — cash / card ──────────────────────────────────────────────

class TestPaymentCashCard:
    def test_cash_full_payment_flips_status_to_paid(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            assert d.status_code == 200, d.text
            total = d.json()["total_cost"]
            pay = client.post(
                f"/api/pharmacy/dispense/{d.json()['dispense_id']}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": total},
            )
            assert pay.status_code == 200, pay.text
            body = pay.json()
            assert body["invoice_status"] == "Paid"
            assert body["amount_paid_total"] == pytest.approx(total)
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_cash_partial_payment_keeps_status_partially_paid(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            if total <= 1:
                pytest.skip("Unit price too small to test partial payment")
            partial = round(total / 2, 2)
            pay = client.post(
                f"/api/pharmacy/dispense/{d.json()['dispense_id']}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": partial},
            )
            assert pay.status_code == 200, pay.text
            body = pay.json()
            assert body["invoice_status"] == "Partially Paid"
            assert body["amount_paid_total"] < total
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_overpay_is_rejected_with_400(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            pay = client.post(
                f"/api/pharmacy/dispense/{d.json()['dispense_id']}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": total + 1_000_000},
            )
            assert pay.status_code == 400, pay.text
            assert "exceeds outstanding" in pay.text.lower()
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_paying_already_paid_invoice_is_400(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            dispense_id = d.json()["dispense_id"]

            pay1 = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": total},
            )
            assert pay1.status_code == 200, pay1.text

            pay2 = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": 1.0},
            )
            assert pay2.status_code == 400, pay2.text
            assert "already fully paid" in pay2.text.lower()
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])


# ─── 8. Payment — M-Pesa STK ───────────────────────────────────────────────

class TestPaymentMpesa:
    def test_mpesa_stk_push_returns_init_shape_or_502(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            pay = client.post(
                f"/api/pharmacy/dispense/{d.json()['dispense_id']}/pay",
                cookies=pharmacist_cookies,
                json={"method": "mpesa", "amount": total,
                      "phone_number": "0712345678"},
            )
            # STK may legitimately fail with 502 in CI if Safaricom creds
            # aren't configured for this tenant. Either shape is acceptable.
            if pay.status_code == 200:
                body = pay.json()
                assert body["status"] == "stk_push_sent"
                assert body["checkout_request_id"]
                assert body["mpesa_transaction_id"]
            else:
                assert pay.status_code == 502, (
                    f"Expected 200 or 502, got {pay.status_code}: {pay.text}"
                )
                # Bare-bones credentials check on the error path.
                assert (
                    "M-Pesa" in pay.text
                    or "mpesa" in pay.text.lower()
                    or "credentials" in pay.text.lower()
                ), pay.text
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_mpesa_without_phone_is_400(self, client, pharmacist_cookies, admin_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            pay = client.post(
                f"/api/pharmacy/dispense/{d.json()['dispense_id']}/pay",
                cookies=pharmacist_cookies,
                json={"method": "mpesa", "amount": total},
            )
            assert pay.status_code == 400, pay.text
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_mpesa_repost_with_pending_returns_same_checkout_id(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            dispense_id = d.json()["dispense_id"]

            pay1 = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "mpesa", "amount": total,
                      "phone_number": "0712345678"},
            )
            if pay1.status_code != 200:
                pytest.skip(
                    f"M-Pesa STK push not viable in this env: {pay1.status_code} {pay1.text}"
                )
            first_id = pay1.json()["checkout_request_id"]

            pay2 = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "mpesa", "amount": total,
                      "phone_number": "0712345678"},
            )
            assert pay2.status_code == 200, pay2.text
            assert pay2.json()["checkout_request_id"] == first_id
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])


# ─── 9. Payment-status poll ────────────────────────────────────────────────

class TestPaymentStatus:
    def test_status_after_cash_payment_shows_paid(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            dispense_id = d.json()["dispense_id"]

            pay = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": total},
            )
            assert pay.status_code == 200, pay.text

            status = client.get(
                f"/api/pharmacy/dispense/{dispense_id}/payment-status",
                cookies=pharmacist_cookies,
            )
            assert status.status_code == 200, status.text
            assert status.json()["invoice_status"] == "Paid"
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_status_for_unknown_dispense_is_404(self, client, pharmacist_cookies):
        r = client.get(
            "/api/pharmacy/dispense/9999999/payment-status",
            cookies=pharmacist_cookies,
        )
        assert r.status_code == 404, r.text


# ─── 10. Receipt ───────────────────────────────────────────────────────────

class TestReceipt:
    def test_receipt_after_full_cash_payment(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
            )
            total = d.json()["total_cost"]
            dispense_id = d.json()["dispense_id"]

            pay = client.post(
                f"/api/pharmacy/dispense/{dispense_id}/pay",
                cookies=pharmacist_cookies,
                json={"method": "cash", "amount": total,
                      "transaction_reference": "TILL-AUTO"},
            )
            assert pay.status_code == 200, pay.text

            r = client.get(
                f"/api/pharmacy/dispense/{dispense_id}/receipt",
                cookies=pharmacist_cookies,
            )
            assert r.status_code == 200, r.text
            body = r.json()

            assert len(body["items"]) >= 1
            assert len(body["payments"]) >= 1
            assert body["totals"]["status"] == "Paid"
            assert body["totals"]["paid"] == pytest.approx(total)
            assert body["totals"]["balance"] == pytest.approx(0.0)
            # receipt_no format RCP-NNNNNNNN (8-digit zero-padded invoice id).
            assert body["receipt_no"].startswith("RCP-")
            tail = body["receipt_no"].split("-", 1)[1]
            assert len(tail) == 8 and tail.isdigit(), body["receipt_no"]
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_walkin_receipt_patient_is_walk_in(self, client, pharmacist_cookies):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        d = _dispense(
            client, pharmacist_cookies,
            batch_id=batch["batch_id"], quantity=1,
            patient_id=None,
        )
        assert d.status_code == 200, d.text

        r = client.get(
            f"/api/pharmacy/dispense/{d.json()['dispense_id']}/receipt",
            cookies=pharmacist_cookies,
        )
        assert r.status_code == 200, r.text
        assert r.json()["patient"] == "Walk-in"

    def test_receipt_unknown_dispense_is_404(self, client, pharmacist_cookies):
        r = client.get(
            "/api/pharmacy/dispense/9999999/receipt",
            cookies=pharmacist_cookies,
        )
        assert r.status_code == 404, r.text


# ─── 11. Transactions ledger ───────────────────────────────────────────────

class TestTransactionsLedger:
    def test_pagination_limit_and_offset(self, client, pharmacist_cookies):
        r0 = client.get(
            "/api/pharmacy/transactions?limit=5&offset=0",
            cookies=pharmacist_cookies,
        )
        assert r0.status_code == 200, r0.text
        body0 = r0.json()
        assert isinstance(body0.get("items"), list)
        assert len(body0["items"]) <= 5
        # On offset=0 total is a real count.
        assert isinstance(body0["total"], int)

        r1 = client.get(
            "/api/pharmacy/transactions?limit=5&offset=5",
            cookies=pharmacist_cookies,
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert len(body1["items"]) <= 5
        # On offset>0 the endpoint skips the count() to save a query.
        assert body1["total"] is None

    def test_date_filters_narrow_to_recent_dispense(
        self, client, pharmacist_cookies, admin_cookies
    ):
        batch = _get_first_available_batch(client, pharmacist_cookies)
        patient = _new_patient(client, admin_cookies)
        try:
            d = _dispense(
                client, pharmacist_cookies,
                batch_id=batch["batch_id"], quantity=1,
                patient_id=patient["patient_id"],
                notes="ZZ_TXN_marker",
            )
            assert d.status_code == 200, d.text
            dispense_id = d.json()["dispense_id"]

            today = date.today().isoformat()
            r = client.get(
                f"/api/pharmacy/transactions?from_date={today}&to_date={today}&limit=500",
                cookies=pharmacist_cookies,
            )
            assert r.status_code == 200, r.text
            ids = {row["dispense_id"] for row in r.json()["items"]}
            assert dispense_id in ids, (
                f"Today-only filter should include the dispense we just created (id={dispense_id})"
            )

            # A window strictly before today must NOT include it.
            old_day = (date.today() - timedelta(days=30)).isoformat()
            r2 = client.get(
                f"/api/pharmacy/transactions?from_date={old_day}&to_date={old_day}&limit=500",
                cookies=pharmacist_cookies,
            )
            assert r2.status_code == 200, r2.text
            ids2 = {row["dispense_id"] for row in r2.json()["items"]}
            assert dispense_id not in ids2
        finally:
            _cleanup_patient(client, admin_cookies, patient["patient_id"])

    def test_bad_date_format_is_400(self, client, pharmacist_cookies):
        r = client.get(
            "/api/pharmacy/transactions?from_date=not-a-date",
            cookies=pharmacist_cookies,
        )
        assert r.status_code == 400, r.text
        text_lower = r.text.lower()
        assert "bad from_date" in text_lower or "bad to_date" in text_lower

    def test_limit_is_clamped_to_500(self, client, pharmacist_cookies):
        r = client.get(
            "/api/pharmacy/transactions?limit=9999",
            cookies=pharmacist_cookies,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["limit"] <= 500, f"Expected limit clamp to <=500, got {body['limit']}"


# ─── 12. RBAC ──────────────────────────────────────────────────────────────

class TestRBAC:
    def test_receptionist_cannot_read_inventory(self, client, receptionist_cookies):
        # Receptionist role does NOT carry pharmacy:read per
        # tenant_provisioning.ROLE_GRANTS, so this must 403.
        r = client.get("/api/pharmacy/inventory", cookies=receptionist_cookies)
        assert r.status_code == 403, r.text

    def test_receptionist_cannot_dispense(self, client, receptionist_cookies):
        r = client.post("/api/pharmacy/dispense", cookies=receptionist_cookies, json={
            "idempotency_key": uuid.uuid4().hex,
            "batch_id": 1,
            "quantity": 1,
        })
        assert r.status_code == 403, r.text

    def test_doctor_can_read_inventory(self, client, doctor_cookies):
        # Doctor role HAS pharmacy:read (see ROLE_GRANTS) — so the
        # endpoint must let them in. Asserting 200 (not 403) is the
        # RBAC contract; the body shape is asserted elsewhere.
        r = client.get("/api/pharmacy/inventory", cookies=doctor_cookies)
        assert r.status_code == 200, r.text
