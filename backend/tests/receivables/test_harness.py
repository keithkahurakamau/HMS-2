from decimal import Decimal


def test_fixture_creates_tenant_and_subscription(make_tenant, master_db):
    tenant, sub = make_tenant(price=Decimal("49500.00"))
    assert tenant.tenant_id is not None
    assert sub.tenant_id == tenant.tenant_id
    assert sub.price_kes == Decimal("49500.00")
    assert sub.status == "active"
