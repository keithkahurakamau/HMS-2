from datetime import date
from decimal import Decimal

from app.models.subscription_billing import SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices


def test_raises_an_invoice_when_the_date_has_arrived(master_db, make_tenant):
    tenant, sub = make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    created = ensure_invoices(master_db, date(2026, 8, 1))
    assert len(created) == 1
    inv = created[0]
    assert inv.tenant_id == tenant.tenant_id
    assert inv.amount_kes == Decimal("15000.00")
    # Monthly in advance, due on issue.
    assert inv.issued_on == inv.due_on == date(2026, 8, 1)
    assert inv.period_start == date(2026, 8, 1)
    assert inv.status == "open"


def test_does_not_raise_before_the_date(master_db, make_tenant):
    make_tenant(next_on=date(2026, 9, 1))
    assert ensure_invoices(master_db, date(2026, 8, 20)) == []


def test_running_twice_creates_one_invoice(master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    assert master_db.query(SubscriptionInvoice).count() == 1


def test_catches_up_every_missed_period(master_db, make_tenant):
    # Down since June: June, July and August are all owed.
    make_tenant(next_on=date(2026, 6, 1))
    created = ensure_invoices(master_db, date(2026, 8, 15))
    assert len(created) == 3
    assert [i.period_start for i in created] == [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]


def test_skips_a_paused_subscription(master_db, make_tenant):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1))
    sub.status = "paused"
    master_db.commit()
    assert ensure_invoices(master_db, date(2026, 8, 1)) == []


def test_numbers_are_unique_and_sequential(master_db, make_tenant):
    make_tenant(name="A Hospital", next_on=date(2026, 8, 1))
    make_tenant(name="B Hospital", next_on=date(2026, 8, 1))
    created = ensure_invoices(master_db, date(2026, 8, 1))
    numbers = sorted(i.number for i in created)
    assert numbers == ["MF-2026-0001", "MF-2026-0002"]
