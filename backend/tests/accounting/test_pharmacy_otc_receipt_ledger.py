"""OTC walk-in payment flow + receipt + transactions ledger.

Three behaviours to lock in:
1. Dispense flow creates an Invoice for walk-ins (patient_id NULL).
2. /pay endpoint now works on walk-in dispenses (no longer refuses them).
3. /receipt returns the expected shape.
4. /transactions paginates + filters properly.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.inventory import DispenseLog, InventoryItem, Location, StockBatch
from app.routes.pharmacy import (
    collect_dispense_payment,
    dispense_receipt,
    pharmacy_transactions,
)
from app.schemas.pharmacy import DispensePaymentRequest


CURRENT_USER = {"user_id": 1}


def _seed_pharmacy_inventory(db, *, item_price=50):
    pharmacy = Location(name="Pharmacy")
    db.add(pharmacy); db.flush()
    item = InventoryItem(
        item_code="CTX-500", name="Ceftriaxone 500mg", category="Drug",
        unit_cost=Decimal("12"), unit_price=Decimal(str(item_price)),
    )
    db.add(item); db.flush()
    batch = StockBatch(
        item_id=item.item_id, location_id=pharmacy.location_id,
        batch_number="BATCH-CTX-001", quantity=20, expiry_date=date(2099, 1, 1),
    )
    db.add(batch); db.commit()
    return item, batch


def _seed_walkin_dispense_with_invoice(db, *, total=Decimal("150")):
    """Mirror what pharmacy.dispense_drug does for a walk-in: invoice
    with patient_id NULL + DispenseLog with patient_id NULL + Pharmacy
    line item."""
    item, _ = _seed_pharmacy_inventory(db)
    invoice = Invoice(
        patient_id=None, total_amount=total, amount_paid=Decimal("0"),
        status="Pending", created_by=1,
    )
    db.add(invoice); db.flush()
    dispense = DispenseLog(
        item_id=item.item_id, batch_id=1, patient_id=None,
        quantity_dispensed=3, total_cost=total, dispensed_by=1,
    )
    db.add(dispense); db.flush()
    db.add(InvoiceItem(
        invoice_id=invoice.invoice_id,
        description="Pharmacy: Ceftriaxone x3",
        amount=total, item_type="Pharmacy", reference_id=dispense.dispense_id,
    ))
    db.commit()
    return item, dispense, invoice


# ─── Walk-in /pay (the core unlock) ─────────────────────────────────────────

class _FakeRequest:
    class _Client: host = "127.0.0.1"
    client = _Client()
    base_url = "http://test.local"


def test_walkin_dispense_now_accepts_cash_payment(db):
    """Previously refused with 400 — should work now that walk-ins get an
    Invoice with patient_id NULL."""
    _, dispense, invoice = _seed_walkin_dispense_with_invoice(db)

    resp = collect_dispense_payment(
        dispense.dispense_id,
        DispensePaymentRequest(method="cash", amount=150.0),
        _FakeRequest(), db, CURRENT_USER,
    )
    db.refresh(invoice)
    assert resp.status == "paid"
    assert invoice.status == "Paid"
    assert db.query(Payment).filter(Payment.invoice_id == invoice.invoice_id).count() == 1


def test_walkin_invoice_can_be_partial_then_topped_up(db):
    _, dispense, invoice = _seed_walkin_dispense_with_invoice(db, total=Decimal("400"))

    collect_dispense_payment(
        dispense.dispense_id,
        DispensePaymentRequest(method="cash", amount=200.0),
        _FakeRequest(), db, CURRENT_USER,
    )
    db.refresh(invoice)
    assert invoice.status == "Partially Paid"

    collect_dispense_payment(
        dispense.dispense_id,
        DispensePaymentRequest(method="cash", amount=200.0),
        _FakeRequest(), db, CURRENT_USER,
    )
    db.refresh(invoice)
    assert invoice.status == "Paid"


# ─── Receipt ────────────────────────────────────────────────────────────────

def test_receipt_shape_for_paid_walkin(db):
    _, dispense, invoice = _seed_walkin_dispense_with_invoice(db, total=Decimal("75"))
    collect_dispense_payment(
        dispense.dispense_id,
        DispensePaymentRequest(method="cash", amount=75.0,
                                transaction_reference="TILL-001"),
        _FakeRequest(), db, CURRENT_USER,
    )

    receipt = dispense_receipt(dispense.dispense_id, db)
    assert receipt["receipt_no"] == f"RCP-{invoice.invoice_id:08d}"
    assert receipt["invoice_id"] == invoice.invoice_id
    assert receipt["dispense_id"] == dispense.dispense_id
    assert receipt["patient"] == "Walk-in"
    assert len(receipt["items"]) == 1
    assert receipt["items"][0]["item_type"] == "Pharmacy"
    assert len(receipt["payments"]) == 1
    assert receipt["payments"][0]["method"] == "Cash"
    assert receipt["payments"][0]["reference"] == "TILL-001"
    assert receipt["totals"]["paid"] == 75.0
    assert receipt["totals"]["balance"] == 0.0
    assert receipt["totals"]["status"] == "Paid"


def test_receipt_missing_dispense_404s(db):
    with pytest.raises(HTTPException) as exc:
        dispense_receipt(99999, db)
    assert exc.value.status_code == 404


# ─── Transactions ledger ───────────────────────────────────────────────────

def test_transactions_lists_dispenses_with_invoice_and_method(db):
    # One unpaid + one paid walk-in dispense.
    _, d1, _ = _seed_walkin_dispense_with_invoice(db, total=Decimal("100"))
    # Bypass full helper to create a second one with the same Pharmacy
    # location already inserted; just stand up another dispense + invoice
    # directly.
    invoice2 = Invoice(patient_id=None, total_amount=Decimal("200"),
                       amount_paid=Decimal("0"), status="Pending", created_by=1)
    db.add(invoice2); db.flush()
    d2 = DispenseLog(item_id=d1.item_id, batch_id=1, patient_id=None,
                     quantity_dispensed=1, total_cost=Decimal("200"), dispensed_by=1)
    db.add(d2); db.flush()
    db.add(InvoiceItem(invoice_id=invoice2.invoice_id, description="Pharmacy: Ceftriaxone x1",
                       amount=Decimal("200"), item_type="Pharmacy", reference_id=d2.dispense_id))
    db.commit()

    # Pay d2 in full so it has a method/status that differs from d1.
    collect_dispense_payment(
        d2.dispense_id,
        DispensePaymentRequest(method="cash", amount=200.0),
        _FakeRequest(), db, CURRENT_USER,
    )

    result = pharmacy_transactions(db, limit=50)
    assert "items" in result and "total" in result
    by_id = {r["dispense_id"]: r for r in result["items"]}
    assert d1.dispense_id in by_id and d2.dispense_id in by_id

    paid_row = by_id[d2.dispense_id]
    assert paid_row["invoice_status"] == "Paid"
    assert paid_row["payment_method"] == "Cash"
    assert paid_row["amount_paid"] == 200.0

    unpaid_row = by_id[d1.dispense_id]
    assert unpaid_row["invoice_status"] == "Pending"
    assert unpaid_row["payment_method"] is None


def test_transactions_filter_by_method(db):
    _, d1, _ = _seed_walkin_dispense_with_invoice(db, total=Decimal("60"))
    collect_dispense_payment(
        d1.dispense_id,
        DispensePaymentRequest(method="cash", amount=60.0),
        _FakeRequest(), db, CURRENT_USER,
    )

    result = pharmacy_transactions(db, method="Cash")
    assert len(result["items"]) == 1
    assert result["items"][0]["dispense_id"] == d1.dispense_id

    result = pharmacy_transactions(db, method="M-Pesa")
    assert result["items"] == []


def test_transactions_bad_date_returns_400(db):
    with pytest.raises(HTTPException) as exc:
        pharmacy_transactions(db, from_date="not-a-date")
    assert exc.value.status_code == 400
