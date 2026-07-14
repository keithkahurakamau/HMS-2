"""Maternity charge helper — the consultation-fee pattern, parameterised.

Finds-or-creates the mother's Pending invoice under FOR UPDATE, appends a
Maternity line item, bumps the total, and GL-posts via post_from_event.
Zero-priced / missing / inactive service codes charge nothing (returns None).
The CALLER owns the commit — the charge lives or dies with the visit row.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.accounting import PriceListItem
from app.models.billing import Invoice, InvoiceItem
from app.services.accounting_posting import post_from_event


def raise_maternity_charge(
    db: Session,
    *,
    patient_id: int,
    service_code: str,
    clinician_name: str,
    user_id: int,
) -> Optional[InvoiceItem]:
    price = (
        db.query(PriceListItem)
        .filter(PriceListItem.service_code == service_code,
                PriceListItem.is_active == True)  # noqa: E712
        .first()
    )
    if not price or Decimal(price.unit_price or 0) <= 0:
        return None
    amt = Decimal(price.unit_price).quantize(Decimal("0.01"))

    invoice = (
        db.query(Invoice)
        .with_for_update()
        .filter(Invoice.patient_id == patient_id, Invoice.status == "Pending")
        .first()
    )
    if not invoice:
        invoice = Invoice(patient_id=patient_id, total_amount=Decimal(0),
                          status="Pending", created_by=user_id)
        db.add(invoice)
        db.flush()

    invoice.total_amount = (invoice.total_amount or Decimal(0)) + amt
    item = InvoiceItem(
        invoice_id=invoice.invoice_id,
        description=f"{price.name} — {clinician_name}"[:255],
        amount=amt,
        item_type="Maternity",
    )
    db.add(item)
    db.flush()

    post_from_event(
        db,
        source_key="billing.invoice.created",
        source_id=item.id,
        amount=amt,
        memo=f"{price.name} · Invoice #{invoice.invoice_id}",
        reference=f"INV-{invoice.invoice_id}",
        user_id=user_id,
    )
    return item
