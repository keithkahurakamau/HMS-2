"""Dashboard cache warmer (rec #3).

These are in-process unit checks (no live server): they exercise the extracted
`compute_dashboard` aggregation and the warmer's per-tenant loop. Without Redis
the cache is a no-op, so the warmer must run cleanly and simply write nothing.
"""
from sqlalchemy.orm import sessionmaker

from app.core import dashboard_warmer
from app.routes.analytics import compute_dashboard
from app.config.database import get_tenant_engine

TENANT = "mayoclinic_db"


def test_compute_dashboard_shape():
    session = sessionmaker(bind=get_tenant_engine(TENANT))()
    try:
        data = compute_dashboard(session)
    finally:
        session.close()
    for key in ("total_patients", "total_staff", "today_revenue", "total_waiting", "queue_breakdown"):
        assert key in data
    assert isinstance(data["queue_breakdown"], dict)
    assert data["total_patients"] >= 0


def test_warm_lock_false_without_redis():
    # No Redis in the test env → no cache client → no lock acquired.
    assert dashboard_warmer._acquire_warm_lock(10) is False


def test_warm_once_runs_over_active_tenants_without_redis():
    # cache.set is a no-op without Redis; the warmer must still iterate active
    # tenants (mayoclinic is one) and return a count without raising.
    n = dashboard_warmer._warm_once()
    assert isinstance(n, int) and n >= 1
