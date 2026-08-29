"""Tests for the collected-this-month figure on the superadmin Global
Overview endpoint (Task 10).

The endpoint's mrr/arr numbers are a price-list projection: they read the
same whether every hospital has paid or none of them have. collected_this_month
is the antidote, an actual sum of InvoicePayment rows for the current
calendar month, so the two figures can never be confused for one another.
"""
from datetime import date, timedelta
from decimal import Decimal

# The overview endpoint queries SupportTicket for the open-ticket count.
# tests/receivables/conftest.py only imports the model modules the rest of
# the suite needs, so support_tickets is otherwise absent from this test
# database's Base.metadata and the endpoint 500s on a missing table. This
# import registers it before the session-scoped engine fixture runs
# Base.metadata.create_all.
import app.models.support  # noqa: F401
from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice

OVERVIEW = "/api/public/superadmin/overview"


def _make_invoice(master_db, tenant, subscription, *, number, period_start,
                   amount=Decimal("18500.00")):
    inv = SubscriptionInvoice(
        tenant_id=tenant.tenant_id,
        subscription_id=subscription.id,
        number=number,
        period_start=period_start,
        period_end=period_start.replace(day=28),
        amount_kes=amount,
        issued_on=period_start,
        due_on=period_start + timedelta(days=7),
        status="open",
    )
    master_db.add(inv)
    master_db.commit()
    return inv


def _first_of_previous_month(today: date) -> date:
    last_day_prev_month = today.replace(day=1) - timedelta(days=1)
    return last_day_prev_month.replace(day=1)


def test_collected_this_month_counts_only_current_month_payments(
    client_superadmin, master_db, make_tenant,
):
    tenant, sub = make_tenant()
    today = date.today()
    this_month_invoice = _make_invoice(
        master_db, tenant, sub, number="INV-THIS", period_start=today.replace(day=1),
    )
    prev_month_day = _first_of_previous_month(today)
    prev_month_invoice = _make_invoice(
        master_db, tenant, sub, number="INV-PREV", period_start=prev_month_day,
    )

    master_db.add(InvoicePayment(
        invoice_id=this_month_invoice.id, amount_kes=Decimal("18500.00"),
        paid_on=today, method="bank",
    ))
    master_db.add(InvoicePayment(
        invoice_id=prev_month_invoice.id, amount_kes=Decimal("9999.00"),
        paid_on=prev_month_day, method="bank",
    ))
    master_db.commit()

    res = client_superadmin.get(OVERVIEW)
    assert res.status_code == 200
    body = res.json()
    assert body["revenue"]["collected_this_month"] == "18500.00"
    # mrr/arr are untouched by this change.
    assert "mrr" in body["revenue"]
    assert "arr" in body["revenue"]


def test_collected_this_month_is_zero_string_with_no_payments(
    client_superadmin, master_db, make_tenant,
):
    make_tenant()

    res = client_superadmin.get(OVERVIEW)
    assert res.status_code == 200
    assert res.json()["revenue"]["collected_this_month"] == "0.00"


def test_collected_this_month_excludes_a_waiver(
    client_superadmin, master_db, make_tenant,
):
    """A waiver is money written off, not cash collected. collected_this_month
    exists specifically so real cash can be compared against projected MRR;
    a waiver counting toward it would misrepresent that reality."""
    tenant, sub = make_tenant()
    today = date.today()
    invoice = _make_invoice(
        master_db, tenant, sub, number="INV-WAIVED", period_start=today.replace(day=1),
    )
    master_db.add(InvoicePayment(
        invoice_id=invoice.id, amount_kes=Decimal("18500.00"),
        paid_on=today, method="waiver",
    ))
    master_db.commit()

    res = client_superadmin.get(OVERVIEW)
    assert res.status_code == 200
    assert res.json()["revenue"]["collected_this_month"] == "0.00"
