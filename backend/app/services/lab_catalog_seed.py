"""Standard lab-catalogue seeding + price-list sync.

Two idempotent steps, shared by the migrate-all-tenants pipeline (every
tenant, every deploy) and the Accounting "Preload lab tests" button:

  1. ``seed_standard_lab_catalog`` — inserts any missing tests from
     ``app.data.standard_lab_tests`` into ``lab_test_catalog``, keyed
     case-insensitively on test_name. Existing rows (renamed prices,
     deactivated tests, hospital-specific additions) are never touched.
  2. ``sync_lab_prices_to_price_list`` — mirrors every *active* catalogue
     test into ``acc_price_list`` as ``LAB-<catalog_id>`` priced at the
     test's base_price. Only missing rows are inserted, so prices an
     accountant hand-tuned in the price list are never clobbered.

Both run on a plain SQLAlchemy ``Session``/``Connection`` via textual SQL —
deliberately ORM-free so the migrate script can call them against tenant
DBs without importing the model graph.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from app.data.standard_lab_tests import STANDARD_LAB_TESTS

LOG = logging.getLogger(__name__)

_INSERT_CATALOG = text("""
    INSERT INTO lab_test_catalog
        (test_name, category, default_specimen_type, base_price,
         turnaround_hours, is_active, requires_barcode)
    SELECT :name, :category, :specimen, :price, :tat, TRUE, FALSE
    WHERE NOT EXISTS (
        SELECT 1 FROM lab_test_catalog WHERE lower(test_name) = lower(:name)
    )
""")

_SYNC_PRICES = text("""
    INSERT INTO acc_price_list
        (service_code, name, category, unit_price, tax_rate_pct,
         is_active, description)
    SELECT 'LAB-' || c.catalog_id, left(c.test_name, 200), 'Lab',
           c.base_price, 0, TRUE, c.description
    FROM lab_test_catalog c
    WHERE c.is_active = TRUE
      AND NOT EXISTS (
          SELECT 1 FROM acc_price_list p
          WHERE p.service_code = 'LAB-' || c.catalog_id
      )
""")


def seed_standard_lab_catalog(conn) -> int:
    """Insert missing standard tests. Returns the number of rows created."""
    created = 0
    for name, category, specimen, price, tat in STANDARD_LAB_TESTS:
        result = conn.execute(_INSERT_CATALOG, {
            "name": name, "category": category, "specimen": specimen,
            "price": price, "tat": tat,
        })
        created += result.rowcount or 0
    return created


def sync_lab_prices_to_price_list(conn) -> int:
    """Mirror active catalogue tests into the price list. Returns rows created."""
    result = conn.execute(_SYNC_PRICES)
    return result.rowcount or 0
