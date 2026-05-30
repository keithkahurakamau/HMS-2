"""Transaction log — the read-only, system-wide register over journal entries.

Every monetary event auto-posts a balanced journal entry tagged with a
``source_type``, so the journal IS the transaction record. These tests cover
the service helper that powers the ``GET /api/accounting/transaction-log``
endpoint: aggregation (amount = balanced debit total), source/status/date/
amount filtering, free-text search, and pagination.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.services.accounting import transaction_log
from .conftest import post_simple_entry


def _seed_mixed(db):
    """A spread of transactions across sources, amounts and dates."""
    today = date.today()
    post_simple_entry(db, "1110", "4100", 1000, on_date=today,
                      source_key="billing.invoice.created", source_id=1,
                      reference="INV-001", memo="Consultation invoice")
    post_simple_entry(db, "1110", "4100", 250, on_date=today,
                      source_key="billing.payment.mpesa", source_id=2,
                      reference="MPESA-XYZ", memo="Mobile money receipt")
    post_simple_entry(db, "1110", "4100", 500, on_date=today - timedelta(days=10),
                      source_key="pharmacy.dispense.charge", source_id=3,
                      reference="RX-77", memo="Drug dispense")
    post_simple_entry(db, "1110", "4100", 75, on_date=today,
                      reference="ADJ-1", memo="Manual adjustment")  # no source


def test_returns_all_transactions_with_balanced_amount(db):
    _seed_mixed(db)
    rows, total = transaction_log(db)
    assert total == 4
    assert len(rows) == 4
    # amount == balanced debit total in base currency
    by_ref = {e.reference: amount for (e, amount) in rows}
    assert by_ref["INV-001"] == Decimal("1000.0000")
    assert by_ref["ADJ-1"] == Decimal("75.0000")


def test_source_group_filter_matches_prefix(db):
    _seed_mixed(db)
    rows, total = transaction_log(db, source="billing")
    assert total == 2
    assert all((e.source_type or "").startswith("billing") for (e, _) in rows)


def test_manual_source_selects_entries_without_source(db):
    _seed_mixed(db)
    rows, total = transaction_log(db, source="manual")
    assert total == 1
    assert rows[0][0].source_type is None
    assert rows[0][0].reference == "ADJ-1"


def test_date_window_filter(db):
    _seed_mixed(db)
    cutoff = date.today() - timedelta(days=1)
    rows, total = transaction_log(db, from_date=cutoff)
    # The 10-day-old pharmacy row falls outside the window.
    assert total == 3
    assert all(e.entry_date >= cutoff for (e, _) in rows)


def test_amount_range_filter(db):
    _seed_mixed(db)
    rows, total = transaction_log(db, min_amount=300, max_amount=600)
    assert total == 1
    assert rows[0][0].reference == "RX-77"


def test_search_matches_reference_and_memo(db):
    _seed_mixed(db)
    rows, _ = transaction_log(db, q="mpesa")
    assert len(rows) == 1
    assert rows[0][0].reference == "MPESA-XYZ"

    rows2, _ = transaction_log(db, q="adjustment")  # memo match
    assert len(rows2) == 1
    assert rows2[0][0].reference == "ADJ-1"


def test_status_filter_excludes_reversed(db):
    _seed_mixed(db)
    rows_posted, total_posted = transaction_log(db, status="posted")
    assert total_posted == 4
    rows_draft, total_draft = transaction_log(db, status="draft")
    assert total_draft == 0


def test_pagination_limit_and_offset(db):
    _seed_mixed(db)
    page1, total = transaction_log(db, limit=2, offset=0)
    page2, _ = transaction_log(db, limit=2, offset=2)
    assert total == 4
    assert len(page1) == 2 and len(page2) == 2
    # No overlap between pages.
    ids1 = {e.entry_id for (e, _) in page1}
    ids2 = {e.entry_id for (e, _) in page2}
    assert ids1.isdisjoint(ids2)


def test_ordered_newest_first(db):
    _seed_mixed(db)
    rows, _ = transaction_log(db)
    dates = [e.entry_date for (e, _) in rows]
    assert dates == sorted(dates, reverse=True)
