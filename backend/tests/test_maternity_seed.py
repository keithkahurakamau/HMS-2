"""Maternity price-list seed: inserts the six MAT-* codes, idempotently."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings

CODES = {
    "MAT-ANC-VISIT", "MAT-PNC-VISIT", "MAT-DEL-SVD",
    "MAT-DEL-ASSISTED", "MAT-DEL-CS", "MAT-DEL-BREECH",
}


def _db():
    base = settings.DATABASE_URL.rsplit("/", 1)[0]
    return sessionmaker(bind=create_engine(f"{base}/mayoclinic_db"))()


def test_seed_inserts_all_codes_and_is_idempotent():
    from app.models.accounting import PriceListItem
    from app.services.maternity_seed import seed_maternity_price_list

    db = _db()
    try:
        seed_maternity_price_list(db)
        db.commit()
        rows = db.query(PriceListItem).filter(PriceListItem.service_code.in_(CODES)).all()
        assert {r.service_code for r in rows} == CODES
        assert all(r.category == "Maternity" for r in rows)

        # Second run inserts nothing new.
        inserted = seed_maternity_price_list(db)
        db.commit()
        assert inserted == 0
    finally:
        db.close()
