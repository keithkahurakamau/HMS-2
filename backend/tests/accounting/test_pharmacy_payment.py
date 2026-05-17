"""Pharmacy post-dispense payment flow.

Exercises the cash + M-Pesa branches of /api/pharmacy/dispense/{id}/pay
without going over HTTP — we call the route function directly with a
fake `current_user` dict. Each test sets up the inventory + patient +
dispense scaffolding it needs.

What we DON'T test here: the actual Safaricom STK push (it's mocked at
the service boundary), because that's an external API call.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.inventory import DispenseLog, InventoryItem, Location, StockBatch
from app.models.mpesa import MpesaTransaction
from app.models.patient import Patient
from app.routes.pharmacy import collect_dispense_payment, dispense_payment_status
from app.schemas.pharmacy import DispensePaymentRequest


CURRENT_USER = {"user_id": 1}


# ─── Test scaffolding ──────────────────────────────────────────────────────

def _seed_patient(db, patient_id=1):
    p = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if p:
        return p
    p = Patient(
        patient_id=patient_id,
        outpatient_no=f"OP-{patient_id:06d}",
        surname="Test",
        other_names="Patient",
        sex="Female",
        date_of_birth=date(1990, 1, 1),
    )
    db.add(p)
    db.commit()
    return p


def _seed_pharmacy_inventory(db, *, item_price=100, qty=10):
    """Drop in one inventory item + batch at the Pharmacy location."""
    pharmacy = Location(name="Pharmacy")
    db.add(pharmacy)
    db.flush()
    item = InventoryItem(
        item_code="PARA-500",
        name="Paracetamol 500mg",
        category="Drug",
        unit_cost=Decimal("20"),
        unit_price=Decimal(str(item_price)),
    )
    db.add(item)
    db.flush()
    batch = StockBatch(
        item_id=item.item_id,
        location_id=pharmacy.location_id,
        batch_number="BATCH-001",
        quantity=qty,
        expiry_date=date(2099, 1, 1),
    )
    db.add(batch)
    db.commit()
    return item, batch


def _seed_dispense_with_invoice(db, *, patient_id=1, total=Decimal("250")):
    """Mirror what pharmacy.dispense_drug does: a DispenseLog + an
    Invoice with a Pharmacy line item referencing the dispense.
    """
    item, _ = _seed_pharmacy_inventory(db)
    p = _seed_patient(db, patient_id)

    invoice = Invoice(
        patient_id=p.patient_id,
        total_amount=total,
        amount_paid=Decimal("0"),
        status="Pending",
        created_by=1,
    )
    db.add(invoice)
    db.flush()

    dispense = DispenseLog(
        item_id=item.item_id,
        batch_id=1,
        patient_id=p.patient_id,
        quantity_dispensed=2,
        total_cost=total,
        dispensed_by=1,
    )
    db.add(dispense)
    db.flush()

    db.add(InvoiceItem(
        invoice_id=invoice.invoice_id,
        description="Pharmacy: Paracetamol",
        amount=total,
        item_type="Pharmacy",
        reference_id=dispense.dispense_id,
    ))
    db.commit()
    return dispense, invoice


class _FakeRequest:
    """Stand-in for the FastAPI Request just enough that log_audit works."""
    class _Client:
        host = "127.0.0.1"
    client = _Client()
    base_url = "http://test.local"


# ─── Cash flow ─────────────────────────────────────────────────────────────

def test_cash_payment_full_settles_invoice(db):
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("250"))

    payload = DispensePaymentRequest(method="cash", amount=250.0)
    resp = collect_dispense_payment(
        dispense.dispense_id, payload, _FakeRequest(), db, CURRENT_USER,
    )
    db.refresh(invoice)

    assert resp.status == "paid"
    assert resp.invoice_status == "Paid"
    assert invoice.amount_paid == Decimal("250")
    assert invoice.status == "Paid"

    payments = db.query(Payment).filter(Payment.invoice_id == invoice.invoice_id).all()
    assert len(payments) == 1
    assert payments[0].payment_method == "Cash"

    # Ledger entry must exist for this payment.
    from app.models.accounting import JournalEntry
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "billing.payment.cash",
                JournalEntry.source_id == payments[0].payment_id)
        .first()
    )
    assert entry is not None
    assert entry.status == "posted"


def test_cash_partial_payment_keeps_invoice_partially_paid(db):
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("500"))

    resp = collect_dispense_payment(
        dispense.dispense_id,
        DispensePaymentRequest(method="cash", amount=200.0),
        _FakeRequest(), db, CURRENT_USER,
    )
    db.refresh(invoice)
    assert resp.status == "partial"
    assert invoice.status == "Partially Paid"
    assert invoice.amount_paid == Decimal("200")


def test_cash_payment_rejects_overpayment(db):
    dispense, _ = _seed_dispense_with_invoice(db, total=Decimal("100"))
    with pytest.raises(HTTPException) as exc:
        collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="cash", amount=150.0),
            _FakeRequest(), db, CURRENT_USER,
        )
    assert exc.value.status_code == 400
    assert "exceeds" in exc.value.detail.lower()


def test_cannot_pay_already_paid_invoice(db):
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("100"))
    invoice.status = "Paid"
    invoice.amount_paid = Decimal("100")
    db.commit()

    with pytest.raises(HTTPException) as exc:
        collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="cash", amount=10.0),
            _FakeRequest(), db, CURRENT_USER,
        )
    assert exc.value.status_code == 400
    assert "already" in exc.value.detail.lower()


def test_walk_in_dispense_cannot_be_paid_via_endpoint(db):
    """Walk-ins (no patient_id, no invoice) are handled at the cashier."""
    item, _ = _seed_pharmacy_inventory(db)
    dispense = DispenseLog(
        item_id=item.item_id, batch_id=1, patient_id=None,
        quantity_dispensed=1, total_cost=Decimal("50"),
        dispensed_by=1,
    )
    db.add(dispense)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="cash", amount=50.0),
            _FakeRequest(), db, CURRENT_USER,
        )
    assert exc.value.status_code == 400


# ─── Card stub ─────────────────────────────────────────────────────────────

def test_card_payment_returns_501(db):
    dispense, _ = _seed_dispense_with_invoice(db, total=Decimal("100"))
    with pytest.raises(HTTPException) as exc:
        collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="card", amount=100.0),
            _FakeRequest(), db, CURRENT_USER,
        )
    assert exc.value.status_code == 501


# ─── M-Pesa flow ───────────────────────────────────────────────────────────

def test_mpesa_requires_phone_number(db):
    dispense, _ = _seed_dispense_with_invoice(db, total=Decimal("100"))
    with pytest.raises(HTTPException) as exc:
        collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="mpesa", amount=100.0, phone_number=None),
            _FakeRequest(), db, CURRENT_USER,
        )
    assert exc.value.status_code == 400


def test_mpesa_stk_push_creates_pending_transaction_and_links_dispense(db):
    """Mock the Safaricom call; just verify our state transitions."""
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("300"))

    def _fake_stk(*, db, phone_number, amount, invoice_id, callback_url):
        # Mirror what the real service does: insert an MpesaTransaction row
        # with the checkout_request_id and Pending status.
        txn = MpesaTransaction(
            invoice_id=invoice_id,
            phone_number=phone_number,
            amount=Decimal(str(amount)),
            merchant_request_id="MRQ-TEST-001",
            checkout_request_id="CKO-TEST-001",
            status="Pending",
        )
        db.add(txn)
        db.commit()
        return {"checkout_request_id": "CKO-TEST-001"}

    with patch("app.routes.pharmacy.initiate_stk_push", side_effect=_fake_stk):
        resp = collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="mpesa", amount=300.0, phone_number="0712345678"),
            _FakeRequest(), db, CURRENT_USER,
        )

    assert resp.status == "stk_push_sent"
    assert resp.checkout_request_id == "CKO-TEST-001"

    txn = db.query(MpesaTransaction).filter(MpesaTransaction.id == resp.mpesa_transaction_id).first()
    assert txn is not None
    assert txn.dispense_id == dispense.dispense_id
    assert txn.status == "Pending"
    # Invoice still unpaid until the callback fires.
    db.refresh(invoice)
    assert invoice.status == "Pending"
    assert invoice.amount_paid == Decimal("0")


def test_mpesa_idempotent_returns_existing_pending(db):
    """Second STK push attempt for the same dispense returns the existing
    pending txn (no fresh Safaricom call)."""
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("100"))
    txn = MpesaTransaction(
        invoice_id=invoice.invoice_id,
        dispense_id=dispense.dispense_id,
        phone_number="254712345678",
        amount=Decimal("100"),
        merchant_request_id="MRQ-X",
        checkout_request_id="CKO-EXISTING",
        status="Pending",
    )
    db.add(txn)
    db.commit()

    call_count = {"n": 0}
    def _fake_stk(**kwargs):
        call_count["n"] += 1
        return {"checkout_request_id": "CKO-NEW"}

    with patch("app.routes.pharmacy.initiate_stk_push", side_effect=_fake_stk):
        resp = collect_dispense_payment(
            dispense.dispense_id,
            DispensePaymentRequest(method="mpesa", amount=100.0, phone_number="0712345678"),
            _FakeRequest(), db, CURRENT_USER,
        )

    assert resp.checkout_request_id == "CKO-EXISTING"
    assert call_count["n"] == 0, "Safaricom should NOT be re-called for a pending txn"


# ─── Status endpoint ───────────────────────────────────────────────────────

def test_payment_status_reflects_invoice_and_mpesa(db):
    dispense, invoice = _seed_dispense_with_invoice(db, total=Decimal("100"))
    db.add(MpesaTransaction(
        dispense_id=dispense.dispense_id, invoice_id=invoice.invoice_id,
        phone_number="254712345678", amount=Decimal("100"),
        checkout_request_id="CKO-S", status="Success",
        receipt_number="QKT123",
    ))
    db.commit()

    status = dispense_payment_status(dispense.dispense_id, db)
    assert status["invoice_id"] == invoice.invoice_id
    assert status["invoice_status"] == "Pending"  # not flipped yet — callback would do that
    assert status["mpesa_status"] == "Success"
    assert status["mpesa_receipt_number"] == "QKT123"
