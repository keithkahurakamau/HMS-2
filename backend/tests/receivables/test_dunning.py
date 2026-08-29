from datetime import date
from decimal import Decimal

from app.models.subscription_billing import DunningEvent, InvoicePayment, SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices, run_dunning


def _overdue(master_db, make_tenant, **kw):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1), **kw)
    ensure_invoices(master_db, date(2026, 8, 1))
    return tenant, sub


def test_sends_at_the_first_milestone(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    sent = []
    events = run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: sent.append(a) or 2)
    assert len(events) == 1
    assert events[0].day_offset == 1
    assert events[0].recipients == 2


def test_nothing_before_the_first_milestone(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    assert run_dunning(master_db, date(2026, 8, 1), notifier=lambda *a, **k: 1) == []


def test_running_twice_sends_once(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 1)
    run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 1)
    assert master_db.query(DunningEvent).count() == 1


def test_a_catch_up_run_sends_only_the_highest_milestone(master_db, make_tenant):
    # 45 days late, so 1, 7, 14 and 30 have all passed.
    _overdue(master_db, make_tenant)
    events = run_dunning(master_db, date(2026, 9, 15), notifier=lambda *a, **k: 1)
    assert len(events) == 1, "a month of downtime must not deliver four notifications at once"
    assert events[0].day_offset == 30


def test_a_paid_invoice_is_never_chased(master_db, make_tenant):
    tenant, sub = _overdue(master_db, make_tenant)
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=inv.amount_kes,
                                 paid_on=date(2026, 8, 1), method="mpesa"))
    master_db.commit()
    assert run_dunning(master_db, date(2026, 8, 20), notifier=lambda *a, **k: 1) == []


def test_a_paused_tenant_is_not_chased(master_db, make_tenant):
    tenant, sub = _overdue(master_db, make_tenant)
    sub.reminders_paused = True
    master_db.commit()
    assert run_dunning(master_db, date(2026, 8, 20), notifier=lambda *a, **k: 1) == []


def test_one_failing_tenant_does_not_stop_the_others(master_db, make_tenant):
    make_tenant(name="Good Hospital", next_on=date(2026, 8, 1))
    make_tenant(name="Broken Hospital", next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))

    def flaky(tenant_db_name, *a, **k):
        if "broken" in tenant_db_name:
            raise RuntimeError("database unreachable")
        return 1

    events = run_dunning(master_db, date(2026, 8, 2), notifier=flaky)
    assert len(events) == 1, "the reachable tenant is still notified"
    # The failing tenant has no event, so the next run retries it.
    assert master_db.query(DunningEvent).count() == 1
