"""Daily billing run: raise what is due, then chase what is late.

Invoked by the Render cron service and by the console's 'Run billing now'
control. Both paths call the same run_billing_cycle, so a manual run can
never produce a state the scheduled run would not.

run_billing_cycle wraps the whole run in billing_lock: if another run (the
cron or the console button) already holds the lock, the result comes back
with skipped=True and this exits 0 without doing anything, since a skipped
duplicate run is the correct outcome, not an error. A run that executes but
has failures (a bad subscription, a tenant that could not be notified, a
future schema drift) is a different case: every failure is logged at ERROR
and the process exits 1, since a cron's exit code is the only way that
kind of failure becomes visible.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

# Registers Tenant on the shared declarative Base before ensure_invoices's
# first flush touches subscription_invoices.tenant_id. This module runs
# standalone, outside the FastAPI app's full model import graph, so without
# this import SQLAlchemy cannot resolve that foreign key: ensure_invoices
# then fails for every subscription inside its own per-subscription
# try/except. run_billing_cycle's failures list is what makes that visible
# now, but the run would still needlessly fail without this import.
import app.models.master  # noqa: F401
from app.config.database import get_master_db
from app.services.subscription_billing import run_billing_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_billing")


def main() -> int:
    today = date.today()
    db = next(get_master_db())
    try:
        result = run_billing_cycle(db, today)

        if result.skipped:
            log.info("Billing run already in progress, exiting")
            return 0

        log.info("Raised %d invoice(s)", result.invoices_created)
        log.info("Sent %d reminder(s)", result.reminders_sent)

        if not result.ok:
            for failure in result.failures:
                log.error(failure)
            return 1

        return 0
    except Exception:
        log.exception("Billing run failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
