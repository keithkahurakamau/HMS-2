"""Daraja reconciliation run: ask Safaricom about every stuck STK, C2B and
refund row, resolve what it answers, and surface what it does not.

Invoked by the Render cron service every 15 minutes (see render.yaml). Both
this cron and any future operator console "Run reconciliation now" control
should call the same run_reconciliation, the same shape run_billing.py
already established for subscription billing.

run_reconciliation wraps the whole run in reconcile_lock: if another run
already holds it, the result comes back with skipped=True and this exits 0
without doing anything, since a skipped duplicate run is the correct
outcome, not an error. A run that executes but has failures (a tenant whose
database could not be reached, an unexpected exception on one row) is a
different case: every failure is logged at ERROR and the process exits 1,
since a cron's exit code is the only way that kind of failure becomes
visible.
"""
from __future__ import annotations

import logging
import sys

# Unlike run_billing.py, no separate noqa'd model-registration import is
# needed here: app.services.daraja.reconcile itself imports
# app.models.master.Tenant and app.models.mpesa at module level, and
# transitively (via settlement.py, b2c.py, status.py) app.models.billing
# too, so the full model graph SQLAlchemy's configure_mappers() needs is
# already registered by the time the import below completes, well before
# this module's first query runs.
from app.config.database import get_master_db
from app.services.daraja.reconcile import run_reconciliation

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_reconcile")


def main() -> int:
    db = next(get_master_db())
    try:
        result = run_reconciliation(db)

        if result.skipped:
            log.info("Reconciliation run already in progress, exiting")
            return 0

        log.info(
            "Resolved %d STK transaction(s) synchronously", result.transactions_resolved
        )
        log.info(
            "Re-queried %d C2B transaction(s) (answer, if any, arrives later)",
            result.transactions_requeried,
        )
        log.info(
            "Re-dispatched %d refund(s) (answer, if any, arrives later)",
            result.refunds_requeried,
        )
        if result.surfaced:
            log.warning("Surfaced %d row(s) stuck over 24 hours:", len(result.surfaced))
            for line in result.surfaced:
                log.warning("  - %s", line)

        if not result.ok:
            for failure in result.failures:
                log.error(failure)
            return 1

        return 0
    except Exception:
        log.exception("Reconciliation run failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
