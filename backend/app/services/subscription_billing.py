"""Subscription receivables: invoice generation and dunning.

Everything here is idempotent. Both entry points may be called any number of
times a day, by the cron and by the operator's button, and must converge on
the same state. The tests exist mainly to prove that property.
"""
from __future__ import annotations

import logging
from datetime import date
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
