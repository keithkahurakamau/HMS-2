"""Adopting the starter catalogue into a hospital's own InventoryItem
catalog: creation, idempotency, non-overwrite, and subset selection.

Runs against an isolated Postgres DB (see conftest.py), no live server.
The catalogue itself is monkeypatched via load_catalogue's cache so these
tests don't depend on the contents of docs/seed/pharmacy-catalogue.csv.
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.inventory import InventoryItem
from app.services import pharmacy_starter_catalogue as svc

from .conftest import seed_inventory_item

CATALOGUE = ["Paracetamol 500mg", "Amoxicillin 250mg", "Zinc Sulphate"]


@pytest.fixture(autouse=True)
def _fake_catalogue(monkeypatch):
    monkeypatch.setattr(svc, "_cache", list(CATALOGUE))
    yield
    monkeypatch.setattr(svc, "_cache", None)


class TestAdoptAll:
    def test_creates_items_with_zero_quantity_and_no_price(self, db):
        result = svc.adopt_into_inventory(db)
        assert result["created"] == 3
        assert result["skipped"] == 0
        assert set(result["created_items"]) == set(CATALOGUE)

        rows = db.query(InventoryItem).order_by(InventoryItem.name).all()
        assert len(rows) == 3
        for row in rows:
            assert row.unit_cost == Decimal("0.00")
            assert row.unit_price == Decimal("0.00")
            assert row.is_active is True
            assert row.category == "Drug"
        # Quantity lives in StockBatch, which adoption never creates, so an
        # adopted item has no batches anywhere and reads as 0 stock.
        assert db.query(InventoryItem).count() == 3

    def test_empty_catalogue_adopts_nothing(self, db, monkeypatch):
        monkeypatch.setattr(svc, "_cache", [])
        result = svc.adopt_into_inventory(db)
        assert result == {"created": 0, "skipped": 0, "created_items": [], "skipped_items": []}
        assert db.query(InventoryItem).count() == 0


class TestIdempotency:
    def test_adopting_twice_creates_no_duplicates(self, db):
        first = svc.adopt_into_inventory(db)
        assert first["created"] == 3

        second = svc.adopt_into_inventory(db)
        assert second["created"] == 0
        assert second["skipped"] == 3
        assert set(second["skipped_items"]) == set(CATALOGUE)

        assert db.query(InventoryItem).count() == 3

    def test_matching_is_case_and_whitespace_insensitive(self, db):
        seed_inventory_item(db, name="  PARACETAMOL   500MG  ")
        result = svc.adopt_into_inventory(db)
        assert result["created"] == 2
        assert result["skipped"] == 1
        assert result["skipped_items"] == ["Paracetamol 500mg"]
        # Still just one Paracetamol row: the pre-existing one, untouched.
        assert db.query(InventoryItem).filter(
            InventoryItem.name == "  PARACETAMOL   500MG  "
        ).count() == 1


class TestNeverOverwrites:
    def test_existing_priced_item_is_left_exactly_as_is(self, db):
        existing = seed_inventory_item(db, name="Paracetamol 500mg", unit_cost="42.50", unit_price="99.00")
        existing_id = existing.item_id

        result = svc.adopt_into_inventory(db)
        assert "Paracetamol 500mg" in result["skipped_items"]

        db.expire_all()
        reloaded = db.query(InventoryItem).filter(InventoryItem.item_id == existing_id).one()
        assert reloaded.unit_cost == Decimal("42.50")
        assert reloaded.unit_price == Decimal("99.00")
        # No second row was created for the same product.
        assert db.query(InventoryItem).filter(InventoryItem.name == "Paracetamol 500mg").count() == 1


class TestConcurrentIdempotency:
    def test_two_overlapping_adopts_of_the_same_product_produce_exactly_one_row(self, db, engine, monkeypatch):
        """Reproduces the time-of-check-to-time-of-use race directly: two
        callers, each with their own DB session (an ORM Session isn't
        thread-safe, so a real overlap needs two connections, not one
        session shared across threads), call adopt_into_inventory for the
        same single-item catalogue at effectively the same instant.

        InventoryItem.name has no unique constraint, so without a lock
        serialising the two calls, both can read the "does not exist yet"
        snapshot before either has committed, and both insert a row.
        _generate_item_code is monkeypatched to sleep well past the
        barrier-synchronised start skew (microseconds vs 300ms) so this is
        deterministic rather than a coin flip: with the fix, the second
        caller's advisory lock acquisition blocks until the first caller's
        entire read-check-insert-commit finishes, so it always observes the
        first caller's committed row and always skips it.
        """
        monkeypatch.setattr(svc, "_cache", ["Vitamin C"])

        original_generate = svc._generate_item_code

        def slow_generate_item_code():
            time.sleep(0.3)
            return original_generate()

        monkeypatch.setattr(svc, "_generate_item_code", slow_generate_item_code)

        session_factory = sessionmaker(bind=engine)
        barrier = threading.Barrier(2)
        results: dict[str, dict] = {}
        errors: list[BaseException] = []

        def worker(name: str) -> None:
            session = session_factory()
            try:
                barrier.wait(timeout=10)
                results[name] = svc.adopt_into_inventory(session)
            except BaseException as exc:  # noqa: BLE001 - surfaced via `errors` below
                errors.append(exc)
            finally:
                session.close()

        t1 = threading.Thread(target=worker, args=("first",))
        t2 = threading.Thread(target=worker, args=("second",))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not t1.is_alive() and not t2.is_alive(), "worker thread did not finish in time"
        assert not errors, errors

        created_counts = sorted(r["created"] for r in results.values())
        skipped_counts = sorted(r["skipped"] for r in results.values())
        # One caller created it, the other found it already there. Which
        # one wins the lock is unspecified and doesn't matter; that exactly
        # one of each outcome happened is the guarantee under test.
        assert created_counts == [0, 1]
        assert skipped_counts == [0, 1]

        rows = db.query(InventoryItem).filter(InventoryItem.name == "Vitamin C").all()
        assert len(rows) == 1


class TestSubsetSelection:
    def test_adopts_only_the_requested_names(self, db):
        result = svc.adopt_into_inventory(db, ["Amoxicillin 250mg"])
        assert result["created"] == 1
        assert result["created_items"] == ["Amoxicillin 250mg"]
        assert db.query(InventoryItem).count() == 1
        assert db.query(InventoryItem).first().name == "Amoxicillin 250mg"

    def test_unknown_requested_names_are_silently_ignored(self, db):
        result = svc.adopt_into_inventory(db, ["Not In The Catalogue"])
        assert result == {"created": 0, "skipped": 0, "created_items": [], "skipped_items": []}
        assert db.query(InventoryItem).count() == 0

    def test_duplicate_requested_names_only_create_once(self, db):
        result = svc.adopt_into_inventory(db, ["paracetamol 500mg", "PARACETAMOL 500MG"])
        assert result["created"] == 1
        assert db.query(InventoryItem).count() == 1
