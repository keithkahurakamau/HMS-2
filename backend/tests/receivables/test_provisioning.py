"""A tenant onboarded today must be billed from day one.

Before this fix, tenant_provisioning.provision_tenant created the Tenant
row and stopped: nothing created a Subscription, so the new hospital was
silently skipped by ensure_invoices (which filters on active subscriptions)
and did not even appear on the ageing page (which joins Subscription to
Tenant), until a deploy happened to run the backfill in
scripts/migrate_all_tenants.py.

The real database-creation, schema-build, and RBAC-seed steps talk to the
Postgres cluster admin connection and build a full tenant schema; none of
that is relevant to whether the master-DB transaction ends up with a
correctly-priced Subscription row, so those steps are stubbed out here.
"""
from decimal import Decimal

from app.models.subscription_billing import Subscription
from app.services import tenant_provisioning


def _provision(master_db, monkeypatch, **overrides):
    monkeypatch.setattr(tenant_provisioning, "_create_database_if_missing", lambda db_name: None)
    monkeypatch.setattr(tenant_provisioning, "_build_schema", lambda db_name: None)
    monkeypatch.setattr(tenant_provisioning, "_seed_baseline", lambda **kw: None)
    monkeypatch.setattr(tenant_provisioning, "_stamp_alembic_head", lambda db_name: None)

    kwargs = dict(
        name="New Hospital", domain="newhospital.test", db_name="db_new_hospital",
        admin_email="admin@newhospital.test", admin_full_name="Admin",
    )
    kwargs.update(overrides)
    return tenant_provisioning.provision_tenant(master_db, **kwargs)


def test_provisioning_creates_exactly_one_subscription_at_the_standard_price(master_db, monkeypatch):
    tenant, _temp_password = _provision(master_db, monkeypatch, is_premium=False)

    subs = master_db.query(Subscription).filter(Subscription.tenant_id == tenant.tenant_id).all()
    assert len(subs) == 1
    sub = subs[0]
    assert sub.plan == "standard"
    assert sub.price_kes == Decimal("18500")
    assert sub.status == "active"
    assert sub.cycle == "monthly"
    assert sub.reminders_paused is False
    # started_on anchors to the tenant's own creation date, not an arbitrary
    # default, and the first next_invoice_on is that same day so the new
    # hospital is billed starting now, not months from now.
    assert sub.started_on == tenant.created_at.date()
    assert sub.next_invoice_on == sub.started_on


def test_provisioning_a_premium_tenant_prices_the_subscription_at_the_premium_tier(master_db, monkeypatch):
    tenant, _temp_password = _provision(
        master_db, monkeypatch,
        name="Premium Hospital", domain="premiumhospital.test", db_name="db_premium_hospital",
        is_premium=True,
    )

    sub = master_db.query(Subscription).filter(Subscription.tenant_id == tenant.tenant_id).first()
    assert sub.plan == "premium"
    assert sub.price_kes == Decimal("49500")


def test_a_failure_after_the_subscription_is_created_rolls_back_the_tenant_too(master_db, monkeypatch):
    """The subscription is created inside the same try/except as the
    database/schema/seed steps: a failure anywhere in that block must undo
    the whole tenant, not leave an orphaned Tenant+Subscription pair with a
    database that was never built."""
    from app.models.master import Tenant

    monkeypatch.setattr(tenant_provisioning, "_create_database_if_missing", lambda db_name: None)
    monkeypatch.setattr(tenant_provisioning, "_build_schema", lambda db_name: None)

    def _boom(**kw):
        raise RuntimeError("seed failed")

    monkeypatch.setattr(tenant_provisioning, "_seed_baseline", _boom)
    monkeypatch.setattr(tenant_provisioning, "_stamp_alembic_head", lambda db_name: None)
    monkeypatch.setattr(tenant_provisioning, "_drop_database_silently", lambda db_name: None)

    try:
        tenant_provisioning.provision_tenant(
            master_db,
            name="Doomed Hospital", domain="doomed.test", db_name="db_doomed",
            admin_email="admin@doomed.test", admin_full_name="Admin",
        )
        assert False, "expected provisioning to raise"
    except RuntimeError:
        pass

    assert master_db.query(Tenant).filter(Tenant.domain == "doomed.test").first() is None
    assert master_db.query(Subscription).join(
        Tenant, Subscription.tenant_id == Tenant.tenant_id
    ).filter(Tenant.domain == "doomed.test").first() is None
