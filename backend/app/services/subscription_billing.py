"""Subscription receivables: invoice generation and dunning.

Everything here is idempotent. Both entry points may be called any number of
times a day, by the cron and by the operator's button, and must converge on
the same state. The tests exist mainly to prove that property.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.subscription_billing import (
    DunningEvent, InvoicePayment, Subscription, SubscriptionInvoice,
)

logger = logging.getLogger("subscription_billing")

MILESTONES = (1, 7, 14, 30)

# Arbitrary but fixed: pg_advisory_lock keys are a single 64-bit namespace
# shared across the whole database, so this value must stay unique to the
# billing run and never be reused for another lock.
BILLING_LOCK_KEY = 7825001


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


@contextmanager
def billing_lock(db: Session) -> Iterator[bool]:
    """Serialise billing runs with a Postgres advisory lock.

    Two callers converge here: the daily cron and the operator console's
    "Run billing now" button. next_number picks the next invoice number by
    reading the highest existing one, so two runs at once can race and
    collide, in which case the unique constraint on `number` skips the
    losing subscription for the day rather than corrupting anything, but a
    skipped invoice is still a hospital not billed that day.

    Session-level (pg_advisory_lock/pg_advisory_unlock), not transaction-level,
    because a billing run spans multiple commits and a transaction-level
    lock would release at the first one. Acquisition is non-blocking
    (pg_try_advisory_lock): a caller that finds the lock held should skip
    its run rather than wait, so yields False instead of blocking.
    """
    acquired = bool(
        db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": BILLING_LOCK_KEY}).scalar()
    )
    try:
        yield acquired
    finally:
        if acquired:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": BILLING_LOCK_KEY})


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


def notify_tenant_admins(tenant_db_name: str, title: str, body: str) -> int:
    """Write one notification per Admin user in a tenant's own database.

    Notifications live in the tenant DB, keyed to a tenant user_id, so the
    reminder has to cross databases. Caller wraps this: a tenant we cannot
    reach must not abort the run for everyone else.
    """
    from sqlalchemy.orm import sessionmaker

    from app.config.database import get_tenant_engine
    from app.models.notification import Notification
    from app.models.user import Role, User

    session = sessionmaker(bind=get_tenant_engine(tenant_db_name))()
    try:
        admins = (
            session.query(User)
            .join(Role, User.role_id == Role.role_id)
            .filter(Role.name == "Admin", User.is_active == True)  # noqa: E712
            .all()
        )
        for admin in admins:
            session.add(Notification(user_id=admin.user_id, category="warning",
                                     title=title, body=body))
        session.commit()
        return len(admins)
    finally:
        session.close()


def run_dunning(db: Session, as_of: date, notifier=None) -> list[DunningEvent]:
    """Remind the admins of every hospital with an overdue balance.

    Only the highest milestone reached is sent, so a month of downtime does
    not deliver four notifications about one invoice at once.
    """
    from app.models.master import Tenant

    send = notifier or notify_tenant_admins
    events: list[DunningEvent] = []

    rows = (
        db.query(SubscriptionInvoice, Subscription, Tenant)
        .join(Subscription, SubscriptionInvoice.subscription_id == Subscription.id)
        .join(Tenant, SubscriptionInvoice.tenant_id == Tenant.tenant_id)
        .filter(SubscriptionInvoice.status == "open",
                SubscriptionInvoice.due_on < as_of)
        .all()
    )

    for invoice, sub, tenant in rows:
        if sub.reminders_paused:
            continue
        if outstanding_balance(db, invoice) <= 0:
            continue

        age = days_overdue(invoice, as_of)
        reached = [m for m in MILESTONES if age >= m]
        if not reached:
            continue
        milestone = max(reached)

        already = db.query(DunningEvent).filter(
            DunningEvent.invoice_id == invoice.id,
            DunningEvent.day_offset == milestone,
        ).first()
        if already:
            continue

        balance = outstanding_balance(db, invoice)
        title = "Subscription payment overdue"
        body = (
            f"Invoice {invoice.number} for {invoice.period_start:%B %Y} is "
            f"{age} days overdue. Balance KES {balance:,.0f}."
        )
        try:
            recipients = send(tenant.db_name, title, body)
        except Exception:
            # Log and skip. No DunningEvent is written, so the next run retries.
            logger.exception("Could not notify tenant %s", tenant.tenant_id)
            continue

        event = DunningEvent(invoice_id=invoice.id, tenant_id=tenant.tenant_id,
                             day_offset=milestone, recipients=recipients or 0)
        db.add(event)
        db.commit()
        events.append(event)

    return events
