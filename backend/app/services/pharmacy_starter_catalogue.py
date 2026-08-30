"""Starter pharmacy catalogue: adopt a ready-made product list into a
hospital's own inventory.

Hospitals starting on MediFleet face an empty pharmacy and must type every
drug in by hand before they can dispense anything. This service reads a
static, repo-shipped list of pharmacy product NAMES (no batches, no
expiry, no prices: that's per-hospital data) from
``docs/seed/pharmacy-catalogue.csv`` and lets a hospital adopt some or all
of it into its own inventory catalog as zero-quantity, zero-price items
the hospital then prices and stocks itself.

Deliberately not a database table: there is nothing tenant-specific about
the catalogue itself (every hospital with the feature on sees the same
static list), so it is read from disk and cached in process. The only
per-tenant state is the ``pharmacy_starter_catalogue`` feature flag (see
``app.core.modules``) and the InventoryItem rows a hospital chooses to
adopt into its own database.

A missing or empty CSV is a normal, expected state for hospitals the
operator hasn't loaded a real catalogue for yet: every function here
degrades to "catalogue not available" rather than raising.
"""
from __future__ import annotations

import csv
import logging
import os
import threading
import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem

logger = logging.getLogger(__name__)

# backend/app/services/pharmacy_starter_catalogue.py -> repo root/docs/seed/...
_CSV_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "seed", "pharmacy-catalogue.csv")
)

# Adopted items land in the master inventory catalog under this category.
# It's one of the values the existing Inventory UI already understands
# (Drug/Consumable/Reagent/Equipment) so adopted items sort and filter the
# same way as anything a hospital keys in by hand.
_ADOPTED_CATEGORY = "Drug"

_lock = threading.Lock()
_cache: Optional[List[str]] = None


def normalize_name(name: str) -> str:
    """Normalise a product name for duplicate/idempotency matching: trim
    surrounding whitespace, collapse internal whitespace runs, casefold.
    """
    return " ".join(name.strip().split()).casefold()


def _read_csv(path: str) -> List[str]:
    """Parse the CSV into a deduplicated, order-preserving list of names.

    A sparse or malformed file collapses to an empty list rather than
    raising: the operator may not have loaded the real catalogue yet, and
    that's a normal state, not an error.
    """
    names: List[str] = []
    seen = set()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            logger.warning("pharmacy-catalogue.csv has no 'name' column; treating catalogue as empty.")
            return []
        for row in reader:
            raw = (row.get("name") or "").strip()
            if not raw:
                continue
            key = normalize_name(raw)
            if key in seen:
                continue
            seen.add(key)
            names.append(raw)
    return names


def load_catalogue(force_reload: bool = False) -> List[str]:
    """Return the cached list of starter-catalogue product names.

    The file is static repo data, not something that changes at runtime,
    so it's read once per process. A missing file, unreadable file, or a
    file with no usable rows all collapse to an empty list.
    """
    global _cache
    if _cache is not None and not force_reload:
        return _cache
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        try:
            _cache = _read_csv(_CSV_PATH)
        except (OSError, csv.Error, UnicodeDecodeError) as exc:
            logger.info("Starter pharmacy catalogue not available (%s): %s", _CSV_PATH, exc)
            _cache = []
    return _cache


def catalogue_available() -> bool:
    """Whether there is at least one product to show/adopt."""
    return len(load_catalogue()) > 0


def adopt_into_inventory(db: Session, requested_names: Optional[List[str]] = None) -> Dict[str, object]:
    """Adopt starter-catalogue products into the hospital's inventory
    catalog as zero-quantity, zero-price items ready for the hospital to
    price and stock itself.

    ``requested_names`` selects a subset (matched against the catalogue by
    normalised name); omit or pass an empty list to adopt everything.

    Idempotent and non-destructive: matches existing InventoryItem rows by
    normalised name (trim + casefold) and never touches one that already
    exists, so a hospital that has already priced an item never loses that
    work by clicking adopt twice. Quantity lives in StockBatch, which this
    never creates, so an adopted item's quantity is 0 everywhere until the
    hospital receives stock for it through the normal procurement flow.
    """
    catalogue = load_catalogue()
    catalogue_by_key = {normalize_name(n): n for n in catalogue}

    if requested_names:
        ordered_keys: List[str] = []
        seen_requested = set()
        for raw in requested_names:
            key = normalize_name(raw)
            if key in catalogue_by_key and key not in seen_requested:
                seen_requested.add(key)
                ordered_keys.append(key)
    else:
        ordered_keys = list(catalogue_by_key.keys())

    if not ordered_keys:
        return {"created": 0, "skipped": 0, "created_items": [], "skipped_items": []}

    existing_keys = {normalize_name(name) for (name,) in db.query(InventoryItem.name).all()}

    created_items: List[str] = []
    skipped_items: List[str] = []
    for key in ordered_keys:
        display_name = catalogue_by_key[key]
        if key in existing_keys:
            skipped_items.append(display_name)
            continue
        db.add(InventoryItem(
            item_code=f"STC-{uuid.uuid4().hex[:6].upper()}",
            name=display_name,
            category=_ADOPTED_CATEGORY,
            unit_cost=0,
            unit_price=0,
            reorder_threshold=10,
            is_active=True,
        ))
        # Guard against duplicate names within the same adopt request (e.g.
        # a caller passing the same name twice under different casing).
        existing_keys.add(key)
        created_items.append(display_name)

    db.commit()
    return {
        "created": len(created_items),
        "skipped": len(skipped_items),
        "created_items": created_items,
        "skipped_items": skipped_items,
    }
