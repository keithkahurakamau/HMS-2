"""Daily billing run: raise what is due, then chase what is late.

Invoked by the Render cron service and by the console's 'Run billing now'
control. Both paths call the same two idempotent functions, so a manual run
can never produce a state the scheduled run would not.

The whole run is wrapped in billing_lock: if another run (the cron or the
console button) already holds the lock, this exits 0 without doing anything,
since a skipped duplicate run is the correct outcome, not an error.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

# Importing these registers Tenant and User on the shared declarative Base
# before any ORM flush touches subscription_invoices.tenant_id or dunning's
# join to tenants and users. This module runs standalone, outside the
# FastAPI app's full model import graph, so without these imports
# SQLAlchemy cannot resolve those foreign keys: ensure_invoices then fails
# for every subscription inside its own per-subscription try/except,
# logs the error, and the run still reports 0 invoices and exits 0.
import app.models.master  # noqa: F401
import app.models.user  # noqa: F401
from app.config.database import get_master_db
from app.services.subscription_billing import billing_lock, ensure_invoices, run_dunning

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_billing")


def main() -> int:
    today = date.today()
    db = next(get_master_db())
    try:
        with billing_lock(db) as acquired:
            if not acquired:
                log.info("Billing run already in progress, exiting")
                return 0
            invoices = ensure_invoices(db, today)
            log.info("Raised %d invoice(s)", len(invoices))
            events = run_dunning(db, today)
            log.info("Sent %d reminder(s)", len(events))
        return 0
    except Exception:
        log.exception("Billing run failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
