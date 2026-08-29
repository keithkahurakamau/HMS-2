"""Subscription receivables: invoice generation and dunning.

Everything here is idempotent. Both entry points may be called any number of
times a day, by the cron and by the operator's button, and must converge on
the same state. The tests exist mainly to prove that property.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.subscription_billing import (
    DunningEvent, InvoicePayment, Subscription, SubscriptionInvoice,
)

logger = logging.getLogger("subscription_billing")

MILESTONES = (1, 7, 14, 30)


def outstanding_balance(db: Session, invoice: SubscriptionInvoice) -> Decimal:
    """Amount still owed. Derived, never stored: a cached total is a second
    source of truth that drifts the first time a payment is corrected."""
    paid = db.query(func.coalesce(func.sum(InvoicePayment.amount_kes), 0)).filter(
        InvoicePayment.invoice_id == invoice.id
    ).scalar()
    return Decimal(invoice.amount_kes) - Decimal(paid)


def days_overdue(invoice: SubscriptionInvoice, as_of: date) -> int:
    return (as_of - invoice.due_on).days


def ageing_bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _advance_one_month(d: date, billing_day: int) -> date:
    """Next occurrence of the billing day. A subscription anchored to the 31st
    bills on the last day of a shorter month rather than skipping it."""
    year = d.year + (d.month // 12)
    month = (d.month % 12) + 1
    last = _month_end(date(year, month, 1)).day
    return date(year, month, min(billing_day, last))


def next_number(db: Session, on: date) -> str:
    """Sequential within the year: MF-2026-0001."""
    prefix = f"MF-{on.year}-"
    latest = (
        db.query(SubscriptionInvoice.number)
        .filter(SubscriptionInvoice.number.like(f"{prefix}%"))
        .order_by(SubscriptionInvoice.number.desc())
        .first()
    )
    seq = int(latest[0].split("-")[-1]) + 1 if latest else 1
    return f"{prefix}{seq:04d}"


def ensure_invoices(db: Session, as_of: date) -> list[SubscriptionInvoice]:
    """Raise every invoice now due. Safe to run repeatedly: the unique
    constraint on (subscription_id, period_start) is the guard, and
    next_invoice_on advances in the same transaction."""
    created: list[SubscriptionInvoice] = []
    subs = db.query(Subscription).filter(
        Subscription.status == "active",
        Subscription.next_invoice_on <= as_of,
    ).order_by(Subscription.id).all()

    for sub in subs:
        try:
            billing_day = sub.started_on.day
            while sub.next_invoice_on <= as_of:
                period_start = sub.next_invoice_on
                exists = db.query(SubscriptionInvoice).filter(
                    SubscriptionInvoice.subscription_id == sub.id,
                    SubscriptionInvoice.period_start == period_start,
                ).first()
                next_billing = _advance_one_month(period_start, billing_day)
                if not exists:
                    inv = SubscriptionInvoice(
                        tenant_id=sub.tenant_id,
                        subscription_id=sub.id,
                        number=next_number(db, period_start),
                        period_start=period_start,
                        # The day before the next billing date, not the calendar
                        # month end: an anchor other than the 1st (the common
                        # case, since started_on comes from tenant.created_at)
                        # must produce a period that is exactly one billing
                        # cycle long, with no gap or overlap between periods.
                        period_end=next_billing - timedelta(days=1),
                        amount_kes=sub.price_kes,
                        issued_on=period_start,
                        due_on=period_start,      # monthly in advance, due on issue
                        status="open",
                    )
                    db.add(inv)
                    db.flush()
                    created.append(inv)
                sub.next_invoice_on = next_billing
            db.commit()
        except Exception:
            # One bad subscription must not stop the rest.
            db.rollback()
            logger.exception("Invoice generation failed for subscription %s", sub.id)
    return created
