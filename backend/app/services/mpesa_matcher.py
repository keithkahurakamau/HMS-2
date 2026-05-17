"""C2B direct-to-till matching cascade.

When a customer pays directly to the till, Safaricom hits our
confirmation URL with `BillRefNumber` (what they typed as account
number — may be empty for tills/Buy-Goods) and `MSISDN` (their phone).
We try three matching strategies in order, then fall back to leaving
the receipt unmatched in a cashier review queue.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.billing import Invoice, Payment
from app.models.patient import Patient

logger = logging.getLogger(__name__)


def find_invoice_for_c2b(
    db: Session, *, bill_ref: Optional[str], msisdn: Optional[str]
) -> Tuple[Optional[Invoice], Optional[str]]:
    """Returns (invoice, match_basis). Both are None when unmatched."""
    bill_ref = (bill_ref or "").strip()
    msisdn = (msisdn or "").strip()

    # 1) BillRefNumber as numeric invoice_id — exact match
    if bill_ref.isdigit():
        inv = db.query(Invoice).filter(Invoice.invoice_id == int(bill_ref)).first()
        if inv and inv.status != "Paid":
            return inv, "invoice_id"

    # 2) BillRefNumber as an outpatient_no — find that patient's open invoice
    if bill_ref:
        patient = db.query(Patient).filter(
            or_(Patient.outpatient_no == bill_ref, Patient.inpatient_no == bill_ref)
        ).first()
        if patient:
            inv = (
                db.query(Invoice)
                .filter(Invoice.patient_id == patient.patient_id,
                        Invoice.status.in_(["Pending", "Partially Paid", "Pending M-Pesa"]))
                .order_by(Invoice.invoice_id.desc())
                .first()
            )
            if inv:
                return inv, "opd_number"

    # 3) MSISDN against patient.telephone_1 / telephone_2 — try both the
    #    Safaricom format (254…) and the local format (07…).
    if msisdn:
        zero_form = "0" + msisdn[3:] if msisdn.startswith("254") and len(msisdn) >= 4 else None
        clauses = [Patient.telephone_1 == msisdn, Patient.telephone_2 == msisdn]
        if zero_form:
            clauses.extend([Patient.telephone_1 == zero_form, Patient.telephone_2 == zero_form])
        patient = db.query(Patient).filter(or_(*clauses)).first()
        if patient:
            inv = (
                db.query(Invoice)
                .filter(Invoice.patient_id == patient.patient_id,
                        Invoice.status.in_(["Pending", "Partially Paid", "Pending M-Pesa"]))
                .order_by(Invoice.invoice_id.desc())
                .first()
            )
            if inv:
                return inv, "phone"

    return None, None


def settle_invoice_from_c2b(
    db: Session, *, invoice: Invoice, amount: Decimal, mpesa_receipt: Optional[str]
) -> Payment:
    """Apply a matched C2B payment to an invoice — idempotent on
    Payment.transaction_reference (the M-Pesa receipt no.)."""
    if mpesa_receipt:
        existing = db.query(Payment).filter(Payment.transaction_reference == mpesa_receipt).first()
        if existing:
            return existing

    payment = Payment(
        invoice_id=invoice.invoice_id,
        amount=amount,
        payment_method="M-Pesa",
        transaction_reference=mpesa_receipt,
    )
    db.add(payment)
    db.flush()

    invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amount
    invoice.status = "Paid" if invoice.amount_paid >= invoice.total_amount else "Partially Paid"
    invoice.payment_method = "M-Pesa"
    return payment
