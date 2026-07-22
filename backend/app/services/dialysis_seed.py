"""Idempotent dialysis reference-data seed: default machine-safety checklists
and one demo machine/station.

Mirrored into scripts/migrate_all_tenants.migrate_one so legacy tenants get the
checklists too (same convention as maternity_seed / lab_catalog_seed). Inserts
are guarded WHERE NOT EXISTS by name, so customised tenants are untouched.
"""
from typing import Union

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

DEFAULT_CHECKLISTS = (
    ("Blood leak test", "Confirm the blood-leak detector is armed and functional."),
    ("Air detect test", "Confirm the air/foam detector is armed and functional."),
    ("Machine function test", "Run the machine self-test / functional check."),
    ("Conductivity check", "Verify dialysate conductivity is within range."),
    ("Dialysate temperature check", "Verify dialysate temperature is within range."),
)

DEFAULT_MACHINES = (
    ("HD-01", "Fresenius 4008S", "Station 1"),
)


def seed_dialysis_checklists(db: Union[Session, Connection]) -> int:
    """Insert missing default checklists + a demo machine. Returns rows inserted."""
    inserted = 0

    existing = {
        row[0]
        for row in db.execute(text("SELECT name FROM dialysis_checklists"))
    }
    for name, desc in DEFAULT_CHECKLISTS:
        if name in existing:
            continue
        db.execute(text(
            "INSERT INTO dialysis_checklists (name, description, is_active) "
            "VALUES (:name, :desc, TRUE)"
        ), {"name": name, "desc": desc})
        inserted += 1

    # Seed a demo machine only when the table is empty (never overwrite a
    # tenant's real machine list).
    have_machines = db.execute(text("SELECT 1 FROM dialysis_machines LIMIT 1")).first()
    if not have_machines:
        for name, model, station in DEFAULT_MACHINES:
            db.execute(text(
                "INSERT INTO dialysis_machines (name, model, station, is_active) "
                "VALUES (:name, :model, :station, TRUE)"
            ), {"name": name, "model": model, "station": station})
            inserted += 1

    return inserted
