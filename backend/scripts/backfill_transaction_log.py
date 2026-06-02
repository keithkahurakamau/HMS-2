"""
Backfill the accounting ledger from every source table, for every tenant, so
the Transaction Log shows every transaction that ever happened — including
history from before the accounting module's go-live date.

Idempotent: it reuses the auto-poster's ``(source_type, source_id)``
de-duplication, so running it repeatedly never double-posts and never disturbs
entries already written by the live system. Safe to re-run any time.

Usage (from backend/):

    # All active tenants (reads the master `tenants` registry):
    python scripts/backfill_transaction_log.py

    # A single tenant database:
    python scripts/backfill_transaction_log.py --db-name tenant_acme

The same logic is exposed in-app at ``POST /api/accounting/transaction-log/
rebuild`` (gated by ``accounting:settings.manage``) for finance admins who'd
rather click a button than run a script.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make `app` importable when run as `python scripts/backfill_transaction_log.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config.database import DATABASE_URL  # noqa: E402
from app.services.accounting_backfill import backfill_all  # noqa: E402
from scripts.migrate_all_tenants import (  # noqa: E402
    _master_db_url,
    _tenant_db_url,
    _list_tenant_db_names,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
LOG = logging.getLogger("backfill_transaction_log")


def _run_for_url(database_url: str) -> dict:
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        summary = backfill_all(db, user_id=None, commit=True)
        return summary
    finally:
        db.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the accounting transaction log.")
    parser.add_argument("--db-name", help="Run against a single tenant database instead of all.")
    args = parser.parse_args()

    default_url = os.environ.get("DATABASE_URL", DATABASE_URL)

    if args.db_name:
        targets = [_tenant_db_url(default_url, args.db_name)]
    else:
        master_url = _master_db_url(default_url)
        names = _list_tenant_db_names(master_url)
        if not names:
            LOG.warning("No active tenants found in the master registry — nothing to do.")
            return 0
        targets = [_tenant_db_url(default_url, n) for n in names]

    exit_code = 0
    for url in targets:
        safe = url.rsplit("/", 1)[-1]
        try:
            summary = _run_for_url(url)
            totals = summary["totals"]
            LOG.info("✓ %s — posted=%s skipped=%s errors=%s",
                     safe, totals["posted"], totals["skipped"], totals["errors"])
            for name, stats in summary["sources"].items():
                if stats.get("error"):
                    LOG.warning("    %s: ERROR %s", name, stats["error"])
                else:
                    LOG.info("    %s: posted=%s skipped=%s", name, stats["posted"], stats["skipped"])
            if totals["errors"]:
                exit_code = 1
        except Exception:  # noqa: BLE001
            LOG.exception("✗ %s — backfill failed", safe)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
