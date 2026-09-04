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
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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

# Arbitrary but fixed: pg_advisory_lock keys share a 64-bit namespace that is
# scoped to the current Postgres database (this codebase is database-per-
# tenant, so this key only ever contends with itself within one hospital's
# own database). Kept distinct from BILLING_LOCK_KEY in
# app.services.subscription_billing so the two features never contend with
# each other by accident. Must stay unique to this lock and never be reused.
_ADOPT_LOCK_KEY = 7825101

# Random component of a generated item_code: 12 hex characters is 2**48
# possibilities, wide enough that a collision inside one adopt batch is
# effectively impossible while still handled gracefully below if it ever
# happens (see _MAX_ITEM_CODE_ATTEMPTS).
_ITEM_CODE_RANDOM_HEX_CHARS = 12
_MAX_ITEM_CODE_ATTEMPTS = 5


@contextmanager
def _adopt_lock(db: Session) -> Iterator[None]:
    """Serialise adopt_into_inventory calls within one tenant database with
    a Postgres advisory lock.

    InventoryItem.name has no unique constraint (only item_code, a
    generated code unrelated to the product name, is unique), and adding
    one is out of scope: this feature is deliberately schema-free (see the
    module docstring). Without a lock, two overlapping adopt calls for the
    same product, for example two staff clicking "Adopt all" moments apart,
    can both read the "does not already exist" snapshot before either
    commits, and both insert a row, breaking the documented never-duplicate
    guarantee. A lock held for the whole call closes that window.

    Mirrors billing_lock in app.services.subscription_billing: opens and
    holds its OWN dedicated connection for the whole call rather than
    locking on *db*. Locking on the request's pooled ORM session risks the
    lock stranding on a connection returned to the pool the moment any
    commit happens before the lock is released, silently disabling the
    guarantee forever with no visible error. Here the dedicated
    connection's transaction stays open (uncommitted) for the whole `with`
    block, and closing the connection in `finally` releases the lock even
    if the explicit unlock below never runs, because Postgres always drops
    a session's advisory locks when its backend disconnects.

    Unlike billing_lock's non-blocking pg_try_advisory_lock (where a busy
    lock means "skip this run, the next cron tick will do it"), acquisition
    here is the blocking pg_advisory_lock: a caller that finds the lock
    held is a user waiting on a request, not a cron job, so it must wait
    its turn and then still adopt correctly, seeing the first call's
    now-committed rows, rather than silently doing nothing.
    """
    conn = db.get_bind().connect()
    try:
        conn.begin()
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADOPT_LOCK_KEY})
        try:
            yield
        finally:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADOPT_LOCK_KEY})
            except Exception:
                logger.exception(
                    "Explicit pg_advisory_unlock failed for the starter-catalogue "
                    "adopt lock; closing the dedicated connection below still "
                    "releases it."
                )
    finally:
        conn.close()


def _generate_item_code() -> str:
    return f"STC-{uuid.uuid4().hex[:_ITEM_CODE_RANDOM_HEX_CHARS].upper()}"


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

    created_items: List[str] = []
    skipped_items: List[str] = []

    with _adopt_lock(db):
        existing_keys = {normalize_name(name) for (name,) in db.query(InventoryItem.name).all()}

        for key in ordered_keys:
            display_name = catalogue_by_key[key]
            if key in existing_keys:
                skipped_items.append(display_name)
                continue

            # item_code is UNIQUE (see backend/app/models/inventory.py) but
            # generated at random, so a collision is possible in principle.
            # Insert inside a SAVEPOINT per attempt so a collision only
            # discards this one insert, retrying with a fresh code, rather
            # than raising IntegrityError up through db.commit() and
            # aborting every other item already staged in this batch.
            for attempt in range(1, _MAX_ITEM_CODE_ATTEMPTS + 1):
                savepoint = db.begin_nested()
                try:
                    db.add(InventoryItem(
                        item_code=_generate_item_code(),
                        name=display_name,
                        category=_ADOPTED_CATEGORY,
                        unit_cost=0,
                        unit_price=0,
                        reorder_threshold=10,
                        is_active=True,
                    ))
                    db.flush()
                except IntegrityError:
                    savepoint.rollback()
                    logger.warning(
                        "pharmacy_starter_catalogue: item_code collision adopting %r "
                        "(attempt %d/%d), retrying with a new code.",
                        display_name, attempt, _MAX_ITEM_CODE_ATTEMPTS,
                    )
                    continue
                else:
                    savepoint.commit()
                    # Guard against duplicate names within the same adopt
                    # request (e.g. a caller passing the same name twice
                    # under different casing).
                    existing_keys.add(key)
                    created_items.append(display_name)
                    break
            else:
                logger.error(
                    "pharmacy_starter_catalogue: could not generate a unique item_code "
                    "for %r after %d attempts; skipping it, rest of the batch continues.",
                    display_name, _MAX_ITEM_CODE_ATTEMPTS,
                )
                skipped_items.append(display_name)

        db.commit()

    return {
        "created": len(created_items),
        "skipped": len(skipped_items),
        "created_items": created_items,
        "skipped_items": skipped_items,
    }
