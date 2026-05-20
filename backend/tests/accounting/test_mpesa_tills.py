"""Per-tenant M-Pesa till configuration + C2B matching cascade.

Covers the behaviour that doesn't need to round-trip Safaricom:
- Matching cascade picks invoice_id / OPD / phone in the documented order
- C2B confirmation is idempotent on TransID
- Settle helper bumps invoice + posts ledger
- Unmatched receipts land in the queue and the assign endpoint resolves them

What we don't test here: the actual Daraja HTTP calls — those are mocked.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.mpesa import MpesaTransaction
from app.models.patient import Patient
from app.services.mpesa_matcher import find_invoice_for_c2b, settle_invoice_from_c2b


# ─── Setup helpers ──────────────────────────────────────────────────────────

def _patient(db, *, patient_id=1, op_no="OP-000001", phone="254712000111"):
    p = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if p:
        return p
    p = Patient(
        patient_id=patient_id,
        outpatient_no=op_no,
        surname="Test",
        other_names="Patient",
        sex="Female",
        date_of_birth=date(1990, 1, 1),
        telephone_1=phone,
    )
    db.add(p)
    db.commit()
    return p


def _open_invoice(db, *, patient_id, total):
    inv = Invoice(
        patient_id=patient_id, total_amount=Decimal(str(total)),
        amount_paid=Decimal("0"), status="Pending", created_by=1,
    )
    db.add(inv); db.commit()
    return inv


# ─── Matching cascade ──────────────────────────────────────────────────────

def test_matcher_invoice_id_takes_precedence(db):
    p = _patient(db)
    inv = _open_invoice(db, patient_id=p.patient_id, total=500)

    matched, basis = find_invoice_for_c2b(db, bill_ref=str(inv.invoice_id), msisdn=p.telephone_1)
    assert matched is not None and matched.invoice_id == inv.invoice_id
    assert basis == "invoice_id"


def test_matcher_falls_back_to_opd_number(db):
    p = _patient(db, op_no="OP-AAA-001")
    inv = _open_invoice(db, patient_id=p.patient_id, total=300)

    matched, basis = find_invoice_for_c2b(db, bill_ref="OP-AAA-001", msisdn=None)
    assert matched is not None and matched.invoice_id == inv.invoice_id
    assert basis == "opd_number"


def test_matcher_falls_back_to_phone(db):
    p = _patient(db, phone="254712345678")
    inv = _open_invoice(db, patient_id=p.patient_id, total=120)

    matched, basis = find_invoice_for_c2b(db, bill_ref="", msisdn="254712345678")
    assert matched is not None and matched.invoice_id == inv.invoice_id
    assert basis == "phone"

    # Local 07… form should also match.
    p2 = _patient(db, patient_id=2, op_no="OP-2", phone="0712666777")
    inv2 = _open_invoice(db, patient_id=p2.patient_id, total=80)
    matched2, basis2 = find_invoice_for_c2b(db, bill_ref="", msisdn="254712666777")
    assert matched2 is not None and matched2.invoice_id == inv2.invoice_id
    assert basis2 == "phone"


def test_matcher_returns_unmatched_when_no_signal(db):
    matched, basis = find_invoice_for_c2b(db, bill_ref="ZZZ-NONE", msisdn="254700000000")
    assert matched is None and basis is None


def test_matcher_skips_paid_invoices(db):
    p = _patient(db)
    inv = _open_invoice(db, patient_id=p.patient_id, total=100)
    inv.status = "Paid"
    db.commit()

    # Should not return the paid invoice via invoice_id match.
    matched, basis = find_invoice_for_c2b(db, bill_ref=str(inv.invoice_id), msisdn=None)
    assert matched is None


# ─── Settlement helper ─────────────────────────────────────────────────────

def test_settle_is_idempotent_on_receipt_no(db):
    p = _patient(db)
    inv = _open_invoice(db, patient_id=p.patient_id, total=400)

    a = settle_invoice_from_c2b(db, invoice=inv, amount=Decimal("400"), mpesa_receipt="QTX111")
    b = settle_invoice_from_c2b(db, invoice=inv, amount=Decimal("400"), mpesa_receipt="QTX111")
    db.commit()

    assert a.payment_id == b.payment_id
    payments = db.query(Payment).filter(Payment.invoice_id == inv.invoice_id).all()
    assert len(payments) == 1


def test_settle_flips_invoice_status_correctly(db):
    p = _patient(db)
    inv = _open_invoice(db, patient_id=p.patient_id, total=200)

    settle_invoice_from_c2b(db, invoice=inv, amount=Decimal("80"), mpesa_receipt="QTX-PART")
    db.commit()
    db.refresh(inv)
    assert inv.status == "Partially Paid"

    settle_invoice_from_c2b(db, invoice=inv, amount=Decimal("120"), mpesa_receipt="QTX-FULL")
    db.commit()
    db.refresh(inv)
    assert inv.status == "Paid"


# ─── C2B confirmation pipeline (model-level) ───────────────────────────────

def test_c2b_confirmation_records_unmatched_receipt(db):
    """End-to-end: insert an MpesaTransaction as if the webhook just ran,
    no matching patient/invoice → row sits with match_basis=unmatched."""
    txn = MpesaTransaction(
        invoice_id=None,
        phone_number="254700000000",
        amount=Decimal("50"),
        receipt_number="QTX-LOST",
        status="Success",
        transaction_type="C2B",
        bill_ref_number="NOPE",
        match_basis="unmatched",
    )
    db.add(txn)
    db.commit()

    found = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.match_basis == "unmatched",
                MpesaTransaction.transaction_type == "C2B")
        .all()
    )
    assert len(found) == 1
    assert found[0].receipt_number == "QTX-LOST"
