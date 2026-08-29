from datetime import date
from decimal import Decimal

import pytest

from app.services.subscription_billing import ageing_bucket, days_overdue, outstanding_balance
from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice


@pytest.mark.parametrize("days,expected", [
    (0, "current"), (1, "1-30"), (30, "1-30"), (31, "31-60"), (60, "31-60"),
    (61, "61-90"), (90, "61-90"), (91, "90+"), (365, "90+"),
])
def test_ageing_bucket_boundaries(days, expected):
    assert ageing_bucket(days) == expected


def test_bucket_treats_not_yet_due_as_current():
    assert ageing_bucket(-5) == "current"


def _invoice(master_db, sub, tenant, amount="15000.00", due=date(2026, 8, 1)):
    inv = SubscriptionInvoice(
        tenant_id=tenant.tenant_id, subscription_id=sub.id, number="MF-2026-0001",
        period_start=due, period_end=date(2026, 8, 31), amount_kes=Decimal(amount),
        issued_on=due, due_on=due, status="open",
    )
    master_db.add(inv)
    master_db.commit()
    return inv


def test_balance_is_amount_when_nothing_paid(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    assert outstanding_balance(master_db, inv) == Decimal("15000.00")


def test_balance_subtracts_every_allocation(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    master_db.add_all([
        InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("5000.00"), paid_on=date(2026, 8, 2), method="mpesa"),
        InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("2500.00"), paid_on=date(2026, 8, 5), method="bank"),
    ])
    master_db.commit()
    assert outstanding_balance(master_db, inv) == Decimal("7500.00")


def test_a_waiver_closes_the_balance_like_any_payment(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("15000.00"),
                                 paid_on=date(2026, 8, 9), method="waiver", note="goodwill"))
    master_db.commit()
    assert outstanding_balance(master_db, inv) == Decimal("0.00")


def test_days_overdue_counts_from_due_date(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant, due=date(2026, 8, 1))
    assert days_overdue(inv, date(2026, 8, 1)) == 0
    assert days_overdue(inv, date(2026, 8, 15)) == 14
