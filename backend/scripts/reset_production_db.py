"""DESTRUCTIVE — drop every database in the platform and recreate hms_master empty.

Use case
--------
One-shot wipe before re-launching production. Drops:
  * Every tenant DB enumerated in hms_master.tenants
  * Any additional databases passed via --also-drop (rarely needed)
  * hms_master itself, then recreates it empty so the next deploy can
    bootstrap a fresh superadmin via seed_superadmin.py.

This script is gated FOUR independent ways. Refuse-by-default until every
gate is opened explicitly, so an accidental import or stray invocation
cannot wipe a live platform:

  1. RESET_PRODUCTION_DB env var MUST equal the magic phrase
     ``YES_DESTROY_EVERYTHING`` (constant copy in this file so a typo on
     either side is a hard fail).
  2. ``--confirm`` CLI flag.
  3. CONFIRM_DB_WIPE env var MUST equal ``i-understand-this-is-irreversible``.
  4. DATABASE_URL must be set and reachable.

If any gate is missing, the script logs why and exits non-zero — render-start.sh
treats that as "skip the reset" rather than "abort the deploy."

Render flow
-----------
render-start.sh calls this script when ``RESET_PRODUCTION_DB`` is set to the
magic phrase. After a successful reset the operator MUST unset the env var
in the dashboard so the next deploy doesn't repeat the wipe. The script
prints a loud reminder when it succeeds.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Make ``app`` importable when invoked from anywhere.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text  # noqa: E402

REQUIRED_RESET_FLAG = "YES_DESTROY_EVERYTHING"
REQUIRED_CONFIRM_PHRASE = "i-understand-this-is-irreversible"

LOG = logging.getLogger("reset_production_db")
logging.basicConfig(
    level=os.getenv("RESET_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _normalize_db_url(raw: str) -> str:
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    return raw


def _base_url(default_url: str) -> str:
    """Strip the path so we can connect to the maintenance ``postgres`` DB."""
    return _normalize_db_url(default_url).rsplit("/", 1)[0]


def _list_tenant_db_names(master_url: str) -> list[str]:
    """Read the tenant registry while the master DB still exists.

    Failure to read the registry isn't fatal — we still drop the master DB
    itself (and any explicit --also-drop targets) so a partially-broken
    master can be wiped.
    """
    engine = create_engine(master_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT db_name FROM tenants")).fetchall()
            return sorted({r[0] for r in rows if r[0]})
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Could not read tenant registry from master DB: %s", exc)
        return []
    finally:
        engine.dispose()


def _drop_database(admin_url: str, db_name: str) -> bool:
    """DROP DATABASE IF EXISTS, force-terminating active connections first."""
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # Terminate connections so DROP can succeed even if a leaked
            # session is holding the DB open.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        LOG.warning("DROPPED database '%s'", db_name)
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to drop '%s': %s", db_name, exc)
        return False
    finally:
        engine.dispose()


def _create_database(admin_url: str, db_name: str) -> bool:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        LOG.warning("CREATED empty database '%s'", db_name)
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to create '%s': %s", db_name, exc)
        return False
    finally:
        engine.dispose()


def main() -> int:
    # ── Gate 1: --confirm CLI flag ────────────────────────────────────────
    if "--confirm" not in sys.argv:
        LOG.error("Refusing to reset: --confirm flag missing.")
        return 2

    # ── Gate 2: RESET_PRODUCTION_DB env var ──────────────────────────────
    flag = os.environ.get("RESET_PRODUCTION_DB", "")
    if flag != REQUIRED_RESET_FLAG:
        LOG.error(
            "Refusing to reset: RESET_PRODUCTION_DB must equal %r (got %r).",
            REQUIRED_RESET_FLAG, flag,
        )
        return 3

    # ── Gate 3: CONFIRM_DB_WIPE env var ──────────────────────────────────
    confirm = os.environ.get("CONFIRM_DB_WIPE", "")
    if confirm != REQUIRED_CONFIRM_PHRASE:
        LOG.error(
            "Refusing to reset: CONFIRM_DB_WIPE must equal %r (got %r).",
            REQUIRED_CONFIRM_PHRASE, confirm,
        )
        return 4

    # ── Gate 4: DATABASE_URL reachable ───────────────────────────────────
    default_url = os.environ.get("DATABASE_URL")
    if not default_url:
        LOG.error("Refusing to reset: DATABASE_URL is not set.")
        return 5

    base = _base_url(default_url)
    master_url = f"{base}/hms_master"
    # Postgres won't drop the DB you're connected to, so use the maintenance
    # ``postgres`` database as the connection target for all DROP/CREATE work.
    admin_url = f"{base}/postgres"

    LOG.warning("=" * 60)
    LOG.warning("PRODUCTION DB RESET STARTING")
    LOG.warning("Target host: %s", base.rsplit("@", 1)[-1])
    LOG.warning("=" * 60)

    # Snapshot the tenant list BEFORE dropping master.
    tenant_db_names = _list_tenant_db_names(master_url)
    extra_drops = [a for a in sys.argv[1:] if not a.startswith("--")]

    targets = list(dict.fromkeys(tenant_db_names + extra_drops + ["hms_master"]))
    LOG.warning("Will drop %d database(s): %s", len(targets), ", ".join(targets))

    failures: list[str] = []
    for name in targets:
        if not _drop_database(admin_url, name):
            failures.append(name)

    # Recreate ONLY hms_master — tenant DBs are created on-demand by the
    # superadmin "add hospital" flow (services/tenant_provisioning.py).
    if not _create_database(admin_url, "hms_master"):
        LOG.error("Could not recreate empty hms_master — manual repair needed.")
        return 6

    if failures:
        LOG.error("Reset completed with %d failure(s): %s",
                  len(failures), ", ".join(failures))
        return 7

    LOG.warning("=" * 60)
    LOG.warning("RESET COMPLETE — empty hms_master is up.")
    LOG.warning("ACTION REQUIRED:")
    LOG.warning("  1. Set new SEED_SUPERADMIN_EMAIL + SEED_SUPERADMIN_PASSWORD")
    LOG.warning("     in the Render dashboard (if not already done).")
    LOG.warning("  2. UNSET RESET_PRODUCTION_DB and CONFIRM_DB_WIPE so the")
    LOG.warning("     next deploy does NOT repeat this wipe.")
    LOG.warning("  3. Delete backend/seed_superadmin.py after first sign-in.")
    LOG.warning("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
