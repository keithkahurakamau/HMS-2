"""Adopting the starter catalogue into a hospital's own InventoryItem
catalog: creation, idempotency, non-overwrite, and subset selection.

Runs against an isolated Postgres DB (see conftest.py), no live server.
The catalogue itself is monkeypatched via load_catalogue's cache so these
tests don't depend on the contents of docs/seed/pharmacy-catalogue.csv.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

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
