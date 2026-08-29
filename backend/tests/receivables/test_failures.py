"""Failure visibility: ensure_invoices and run_billing_cycle must let a
caller tell "nothing was due" apart from "every subscription failed",
since both used to look identical, zero counts and a clean exit.

Failures are forced by monkeypatching _advance_one_month (called inside the
per-subscription loop, keyed off the subscription's billing anchor day),
never by corrupting the database: the goal is to prove the isolation and
reporting contract, not to exercise a specific crash cause.

Invoices in these tests are deliberately not overdue (due_on == as_of), so
run_billing_cycle's call to run_dunning never has anything to chase and
never reaches out to a tenant database that doesn't really exist here.
"""
from datetime import date

import app.services.subscription_billing as billing
from app.services.subscription_billing import ensure_invoices, run_billing_cycle


def _flaky_advance_one_month(fails_for_billing_day: int):
    """An _advance_one_month stand-in that raises only for one
    subscription's billing anchor day, so exactly one subscription in a
    multi-subscription run fails while the rest bill normally."""
    real_advance = billing._advance_one_month

    def _inner(d, billing_day):
        if billing_day == fails_for_billing_day:
            raise RuntimeError("simulated failure")
        return real_advance(d, billing_day)

    return _inner


def test_a_failing_subscription_is_recorded_and_does_not_stop_the_others(
    master_db, make_tenant, monkeypatch,
):
    good_tenant, good_sub = make_tenant(
        name="Good Hospital", started=date(2026, 1, 1), next_on=date(2026, 8, 1),
    )
    bad_tenant, bad_sub = make_tenant(
        name="Bad Hospital", started=date(2026, 1, 15), next_on=date(2026, 8, 1),
    )

    monkeypatch.setattr(billing, "_advance_one_month", _flaky_advance_one_month(15))

    failures: list[str] = []
    created = ensure_invoices(master_db, date(2026, 8, 1), failures=failures)

    # The good subscription still got its invoice: one bad subscription
    # must not stop the rest.
    assert len(created) == 1
    assert created[0].tenant_id == good_tenant.tenant_id

    # The failure is recorded, in the documented format, instead of being
    # swallowed silently by the per-subscription try/except.
    assert failures == [
        f"subscription {bad_sub.id} (tenant {bad_tenant.tenant_id}): simulated failure"
    ]


def test_run_billing_cycle_reports_not_ok_when_a_subscription_fails(
    master_db, make_tenant, monkeypatch,
):
    make_tenant(name="Good Hospital", started=date(2026, 1, 1), next_on=date(2026, 8, 1))
    _, bad_sub = make_tenant(
        name="Bad Hospital", started=date(2026, 1, 15), next_on=date(2026, 8, 1),
    )

    monkeypatch.setattr(billing, "_advance_one_month", _flaky_advance_one_month(15))

    result = run_billing_cycle(master_db, date(2026, 8, 1))

    assert result.skipped is False
    assert result.ok is False
    assert result.invoices_created == 1
    assert len(result.failures) == 1
    assert str(bad_sub.id) in result.failures[0]


def test_run_billing_cycle_reports_ok_on_a_clean_run(master_db, make_tenant):
    make_tenant(name="Hospital One", next_on=date(2026, 8, 1))
    make_tenant(name="Hospital Two", next_on=date(2026, 8, 1))

    result = run_billing_cycle(master_db, date(2026, 8, 1))

    assert result.skipped is False
    assert result.ok is True
    assert result.invoices_created == 2
    assert result.failures == []
