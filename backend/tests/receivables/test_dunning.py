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


def test_zero_recipients_is_treated_as_a_failure_and_the_milestone_is_not_burned(
    master_db, make_tenant,
):
    """A tenant with no active Admin gets 0 recipients back from the
    notifier. Writing the DunningEvent anyway would permanently consume
    that milestone: it is unique per (invoice_id, day_offset), so it would
    never be retried and nobody would ever actually be told."""
    _overdue(master_db, make_tenant)

    failures: list[str] = []
    events = run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 0, failures=failures)

    assert events == []
    assert master_db.query(DunningEvent).count() == 0
    assert len(failures) == 1
    assert "no active admin" in failures[0].lower()

    # And the next run must actually retry it, not skip it as "already sent".
    events = run_dunning(master_db, date(2026, 8, 3), notifier=lambda *a, **k: 2)
    assert len(events) == 1
    assert events[0].recipients == 2


def test_a_failed_event_write_does_not_stop_the_other_tenants(master_db, make_tenant, monkeypatch):
    """db.add(event)/db.commit() used to sit outside the try around the
    notifier call: a commit failure there would escape the per-tenant loop,
    abort dunning for every remaining tenant, and (since the notifier had
    already run for the failing tenant) mean that tenant gets notified
    again on the very next run."""
    make_tenant(name="Hospital One", next_on=date(2026, 8, 1))
    make_tenant(name="Hospital Two", next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))

    real_commit = master_db.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("commit failed")
        return real_commit()

    monkeypatch.setattr(master_db, "commit", flaky_commit)

    failures: list[str] = []
    events = run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 1, failures=failures)

    # One tenant's event-write failure must not stop the other's.
    assert len(events) == 1
    assert len(failures) == 1
    assert "commit failed" in failures[0]


def test_reminder_body_formats_the_balance_to_two_decimal_places(master_db, make_tenant):
    """{balance:,.0f} used to round 45000.60 to "KES 45,001"; the reminder
    must show the real balance to the cent."""
    tenant, sub = make_tenant(price=Decimal("45000.60"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()

    sent = {}

    def capture(tenant_db_name, title, body):
        sent["title"] = title
        sent["body"] = body
        return 1

    run_dunning(master_db, date(2026, 8, 2), notifier=capture)

    assert sent["title"] == "Subscription payment overdue"
    assert sent["body"] == (
        f"Invoice {inv.number} for August 2026 is 1 days overdue. "
        f"Balance KES 45,000.60."
    )
