"""Idempotent theatre reference-data seed: the WHO Surgical Safety Checklist
(SignIn/TimeOut/SignOut items), a demo theatre room, and theatre service price
codes. Mirrored into scripts/migrate_all_tenants.migrate_one so legacy tenants
get them too (same convention as dialysis_seed / maternity_seed).
"""
from typing import Union

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

# WHO Surgical Safety Checklist — (phase, item).
WHO_CHECKLIST = (
    ("SignIn", "Patient identity, site, procedure and consent confirmed"),
    ("SignIn", "Surgical site marked"),
    ("SignIn", "Anaesthesia safety check completed"),
    ("SignIn", "Pulse oximeter on the patient and functioning"),
    ("SignIn", "Known allergy reviewed"),
    ("SignIn", "Difficult airway / aspiration risk reviewed"),
    ("SignIn", "Risk of >500ml (7ml/kg in children) blood loss reviewed"),
    ("TimeOut", "All team members introduced by name and role"),
    ("TimeOut", "Surgeon, anaesthetist and nurse confirm patient, site, procedure"),
    ("TimeOut", "Antibiotic prophylaxis given within the last 60 minutes"),
    ("TimeOut", "Anticipated critical events reviewed"),
    ("TimeOut", "Essential imaging displayed"),
    ("SignOut", "Name of the procedure recorded"),
    ("SignOut", "Instrument, sponge and needle counts correct"),
    ("SignOut", "Specimen labelled (incl. patient name)"),
    ("SignOut", "Equipment problems identified and addressed"),
    ("SignOut", "Key concerns for recovery and management reviewed"),
)

DEFAULT_ROOMS = (("Theatre 1",),)

THEATRE_SERVICES = (
    ("THEATRE-MAJOR", "Major Surgery (Theatre)"),
    ("THEATRE-MINOR", "Minor Surgery (Theatre)"),
)


def seed_theatre_reference(db: Union[Session, Connection]) -> int:
    """Insert missing WHO checklist items + a demo theatre room. Returns count."""
    inserted = 0

    existing = {
        (row[0], row[1])
        for row in db.execute(text("SELECT phase, name FROM surgical_checklists"))
    }
    for phase, name in WHO_CHECKLIST:
        if (phase, name) in existing:
            continue
        db.execute(text(
            "INSERT INTO surgical_checklists (phase, name, is_active) "
            "VALUES (:phase, :name, TRUE)"
        ), {"phase": phase, "name": name})
        inserted += 1

    if not db.execute(text("SELECT 1 FROM theatre_rooms LIMIT 1")).first():
        for (name,) in DEFAULT_ROOMS:
            db.execute(text(
                "INSERT INTO theatre_rooms (name, is_active) VALUES (:name, TRUE)"
            ), {"name": name})
            inserted += 1

    return inserted


def seed_theatre_price_list(db: Union[Session, Connection]) -> int:
    """Insert missing THEATRE-* price-list rows (zero-priced until set). Returns count."""
    result = db.execute(text("SELECT account_id FROM acc_accounts WHERE code = '4700'")).first()
    revenue_account_id = result[0] if result else None

    codes = [c for c, _ in THEATRE_SERVICES]
    placeholders = ", ".join(f":{i}" for i in range(len(codes)))
    existing = {
        row[0]
        for row in db.execute(text(
            f"SELECT service_code FROM acc_price_list WHERE service_code IN ({placeholders})"
        ), {str(i): c for i, c in enumerate(codes)})
    }

    inserted = 0
    for code, name in THEATRE_SERVICES:
        if code in existing:
            continue
        db.execute(text(
            "INSERT INTO acc_price_list "
            "(service_code, name, category, unit_price, revenue_account_id, tax_rate_pct, is_active) "
            "VALUES (:code, :name, :cat, 0, :rev_id, 0, TRUE)"
        ), {"code": code, "name": name, "cat": "Theatre", "rev_id": revenue_account_id})
        inserted += 1
    return inserted
