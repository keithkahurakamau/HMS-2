"""Idempotent maternity price-list seed.

Mirrored into scripts/migrate_all_tenants.migrate_one so legacy tenants get
the codes too (same convention as lab_catalog_seed). All services seed at
unit_price=0 — zero-priced services raise no charge until the hospital sets
real prices in Admin → Pricing.
"""
from sqlalchemy import text

MATERNITY_SERVICES = (
    ("MAT-ANC-VISIT",    "Antenatal Clinic Visit"),
    ("MAT-PNC-VISIT",    "Postnatal Clinic Visit"),
    ("MAT-DEL-SVD",      "Normal Delivery (SVD)"),
    ("MAT-DEL-ASSISTED", "Assisted Delivery"),
    ("MAT-DEL-CS",       "Caesarean Section"),
    ("MAT-DEL-BREECH",   "Breech Delivery"),
)


def seed_maternity_price_list(db) -> int:
    """Insert missing MAT-* price-list rows. Returns number inserted.

    Works with SQLAlchemy Session or Connection objects.
    """
    # Get revenue account ID for code 4700 (nullable — legacy tenants may
    # lack the account; the FK column allows NULL).
    result = db.execute(text(
        "SELECT account_id FROM acc_accounts WHERE code = '4700'"
    )).first()
    revenue_account_id = result[0] if result else None

    # Check which codes already exist
    codes_in = [c for c, _ in MATERNITY_SERVICES]
    placeholders = ", ".join(f":{i}" for i in range(len(codes_in)))
    existing = set()
    for row in db.execute(text(
        f"SELECT service_code FROM acc_price_list WHERE service_code IN ({placeholders})"
    ), {str(i): c for i, c in enumerate(codes_in)}):
        existing.add(row[0])

    # Insert missing entries
    inserted = 0
    for code, name in MATERNITY_SERVICES:
        if code in existing:
            continue
        db.execute(text(
            "INSERT INTO acc_price_list "
            "(service_code, name, category, unit_price, revenue_account_id, "
            " tax_rate_pct, is_active) "
            "VALUES (:code, :name, :cat, :price, :rev_id, 0, TRUE)"
        ), {
            "code": code,
            "name": name,
            "cat": "Maternity",
            "price": 0,
            "rev_id": revenue_account_id,
        })
        inserted += 1
    return inserted
