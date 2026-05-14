"""Apply Alembic migrations to every tenant database in the platform.

Why this exists
---------------
Each hospital runs in its own Postgres database. Pre-existing tenants were
provisioned by ``Base.metadata.create_all`` — that gave them schema but never
populated ``alembic_version``, so a fresh ``alembic upgrade head`` against
those DBs tries to run the initial migration on top of an already-built
schema and fails with "relation already exists".

This script reconciles both worlds in one pass, every time. Run it on every
deploy (``render-start.sh`` does this automatically) and after writing any
new Alembic revision.

For each tenant in the master ``tenants`` table:

  * If ``alembic_version`` is missing, the tenant was provisioned legacy-style.
    We bring it under Alembic's control by:
        1. Running ``Base.metadata.create_all`` (idempotent — only adds tables
           that don't already exist).
        2. Re-running idempotent data seeds for the most recent migrations
           (currently: messaging permissions + role grants).
        3. Stamping ``alembic_version`` at the current head so later runs
           treat the tenant as fully migrated.
  * If ``alembic_version`` is present, we just run ``alembic upgrade head``
    against the tenant URL — pending migrations roll forward normally.

The script exits non-zero if any tenant fails so a CI/CD step that calls it
can stop a bad deploy. Individual failures don't abort the loop — every
tenant gets a chance.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# Make ``app`` importable when invoked from anywhere.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import create_engine, inspect, text  # noqa: E402

# Triggers SQLAlchemy metadata population for every model so create_all
# below covers tables added by future migrations.
from app.config.database import Base, DATABASE_URL  # noqa: E402,F401
from app.models import (  # noqa: E402,F401
    audit, auth_tokens, billing, breach, clinical, idempotency, inventory,
    laboratory, master, medical_history, messaging, mpesa, notification,
    patient, radiology, user, wards,
)


LOG = logging.getLogger("migrate_all_tenants")
logging.basicConfig(
    level=os.getenv("MIGRATE_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# Idempotent SQL that mirrors the data-seeding portion of recent migrations.
# Kept here (not imported from migration files) because Alembic migrations
# are designed to run once per revision; re-importing them sideways risks
# mutating their assumed-fresh state. These statements are guarded with
# WHERE NOT EXISTS so re-running them on a fully-seeded DB is a no-op.
# Master-DB-only schema patches. The ``tenants`` table lives in hms_master,
# not in tenant DBs, and migrate_all_tenants.py only iterates tenant URLs —
# so without these explicit DDLs the master schema would drift behind the
# model. Every statement is idempotent (IF NOT EXISTS / WHERE NOT EXISTS),
# so re-running on every deploy is a no-op once converged.
MASTER_DB_PATCHES: list[str] = [
    # c7a2e94d318f — tenant flexibility fields
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS feature_flags TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS plan_limits TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS notes TEXT;",
    # Branding columns — uploaded logos, custom backgrounds, brand colours,
    # and printed-document template configuration. All are nullable so the
    # platform default applies when a tenant has not customised anything.
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS logo_data_url TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS background_data_url TEXT;",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS brand_primary VARCHAR(16);",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS brand_accent VARCHAR(16);",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS print_templates TEXT;",
    # Support tickets — master DB only. Two tables, fully self-contained.
    """
    CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id            SERIAL PRIMARY KEY,
        tenant_id            INTEGER NOT NULL,
        tenant_name          VARCHAR(255) NOT NULL,
        submitter_email      VARCHAR(255) NOT NULL,
        submitter_name       VARCHAR(255) NOT NULL,
        submitter_user_id    INTEGER,
        subject              VARCHAR(200) NOT NULL,
        category             VARCHAR(40) NOT NULL DEFAULT 'Other',
        priority             VARCHAR(20) NOT NULL DEFAULT 'Normal',
        status               VARCHAR(40) NOT NULL DEFAULT 'Open',
        assigned_to_admin_id INTEGER REFERENCES superadmins(admin_id) ON DELETE SET NULL,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at           TIMESTAMPTZ,
        first_response_at    TIMESTAMPTZ,
        resolved_at          TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_support_tickets_tenant_id        ON support_tickets (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_support_tickets_status           ON support_tickets (status);",
    "CREATE INDEX IF NOT EXISTS ix_support_tickets_created_at       ON support_tickets (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_support_tickets_assigned_admin   ON support_tickets (assigned_to_admin_id);",
    "CREATE INDEX IF NOT EXISTS idx_support_status_created          ON support_tickets (status, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_support_tenant_status           ON support_tickets (tenant_id, status);",
    """
    CREATE TABLE IF NOT EXISTS support_messages (
        message_id   SERIAL PRIMARY KEY,
        ticket_id    INTEGER NOT NULL REFERENCES support_tickets(ticket_id) ON DELETE CASCADE,
        author_kind  VARCHAR(20) NOT NULL,
        author_name  VARCHAR(255) NOT NULL,
        author_id    INTEGER,
        body         TEXT NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_id  ON support_messages (ticket_id);",
    "CREATE INDEX IF NOT EXISTS ix_support_messages_created_at ON support_messages (created_at);",
]


LEGACY_BOOTSTRAP_SEEDS: list[str] = [
    # f7a9c2d1e480_add_messaging_and_departments — permissions catalogue
    """
    INSERT INTO permissions (codename, description)
    SELECT v.codename, v.description
    FROM (VALUES
        ('messaging:read',     'Read internal staff messages'),
        ('messaging:write',    'Send internal staff messages'),
        ('departments:manage', 'Create and manage departments'),
        ('roles:manage',       'Create and manage custom roles')
    ) AS v(codename, description)
    WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.codename = v.codename);
    """,
    # Grant messaging:read/write to every existing role.
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT r.role_id, p.permission_id
    FROM roles r CROSS JOIN permissions p
    WHERE p.codename IN ('messaging:read', 'messaging:write')
      AND NOT EXISTS (
          SELECT 1 FROM role_permissions rp
          WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
      );
    """,
    # Grant departments:manage + roles:manage to Admin only.
    """
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT r.role_id, p.permission_id
    FROM roles r CROSS JOIN permissions p
    WHERE r.name = 'Admin'
      AND p.codename IN ('departments:manage', 'roles:manage')
      AND NOT EXISTS (
          SELECT 1 FROM role_permissions rp
          WHERE rp.role_id = r.role_id AND rp.permission_id = p.permission_id
      );
    """,
    # d8b46e91527a_seed_default_inventory_locations — the four standard
    # locations the Inventory page expects to exist by name.
    """
    INSERT INTO locations (name, description)
    SELECT v.name, v.description
    FROM (VALUES
        ('Main Store', 'Central inventory store — receives all procurements'),
        ('Pharmacy',   'Dispensing point for prescriptions and OTC sales'),
        ('Laboratory', 'Reagents and consumables for diagnostic testing'),
        ('Wards',      'Bedside consumables and PRN drug stock')
    ) AS v(name, description)
    WHERE NOT EXISTS (SELECT 1 FROM locations l WHERE l.name = v.name);
    """,
]


def _normalize_db_url(raw: str) -> str:
    """Match the normalization in app/config/database.py so URLs from env
    work regardless of postgres:// vs postgresql:// scheme."""
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://"):]
    return raw


def _master_db_url(default_url: str) -> str:
    return _normalize_db_url(default_url).rsplit("/", 1)[0] + "/hms_master"


def _tenant_db_url(default_url: str, tenant_db_name: str) -> str:
    base = _normalize_db_url(default_url).rsplit("/", 1)[0]
    return f"{base}/{tenant_db_name}"


def _apply_master_patches(master_url: str) -> None:
    """Apply idempotent DDL statements to the master DB.

    Tenant migrations don't reach hms_master (it has a different shape), so
    any model change touching the ``tenants`` or ``superadmins`` tables must
    be reflected here. Each statement is guarded with IF NOT EXISTS so
    re-running on a converged master is a no-op.
    """
    if not MASTER_DB_PATCHES:
        return
    engine = create_engine(master_url)
    try:
        with engine.begin() as conn:
            for stmt in MASTER_DB_PATCHES:
                conn.execute(text(stmt))
        LOG.info("master DB patched (%d statement%s applied).",
                 len(MASTER_DB_PATCHES),
                 "" if len(MASTER_DB_PATCHES) == 1 else "s")
    finally:
        engine.dispose()


def _list_tenant_db_names(master_url: str) -> list[str]:
    """Read tenant db_name values from the master registry."""
    engine = create_engine(master_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT db_name FROM tenants WHERE is_active = TRUE ORDER BY db_name")
            ).fetchall()
    finally:
        engine.dispose()
    return [r[0] for r in rows]


def _is_legacy_tenant(tenant_url: str) -> bool:
    """Return True if the tenant has no alembic_version table yet (i.e., was
    provisioned via create_all without ever being stamped)."""
    engine = create_engine(tenant_url)
    try:
        return not inspect(engine).has_table("alembic_version")
    finally:
        engine.dispose()


def _bootstrap_legacy_tenant(tenant_url: str) -> None:
    """Bring a legacy tenant under Alembic control without dropping data.

    Does three things in order:
      1. create_all to add any tables introduced after the original bootstrap.
      2. run idempotent data seeds for migrations that ship them.
      3. stamp alembic_version at head.
    """
    engine = create_engine(tenant_url)
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            for stmt in LEGACY_BOOTSTRAP_SEEDS:
                conn.execute(text(stmt))
    finally:
        engine.dispose()
    _run_alembic("stamp", "head", database_url=tenant_url)


def _run_alembic(*args: str, database_url: str) -> None:
    """Invoke the alembic CLI against the supplied database URL.

    A subprocess is used (rather than ``alembic.command``) so we get clean
    isolation between tenants — alembic env.py loads the connection via
    DATABASE_URL at module-import time, and the env var pattern is the
    least-surprising way to redirect it per call.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    alembic_bin = BACKEND_DIR / "venv" / "bin" / "alembic"
    cmd: Iterable[str]
    if alembic_bin.exists():
        cmd = [str(alembic_bin), *args]
    else:
        # Fallback for environments where alembic is on PATH (Render uses
        # the system venv installed by the build step).
        cmd = ["alembic", *args]
    LOG.debug("alembic %s (DB: %s)", " ".join(args), database_url.rsplit("@", 1)[-1])
    result = subprocess.run(cmd, env=env, cwd=BACKEND_DIR, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed (exit {result.returncode})")


def migrate_one(tenant_db_name: str, default_url: str) -> None:
    tenant_url = _tenant_db_url(default_url, tenant_db_name)
    safe_label = tenant_url.rsplit("@", 1)[-1]  # hide creds in logs

    if _is_legacy_tenant(tenant_url):
        LOG.info("[%s] no alembic_version — running legacy bootstrap", safe_label)
        _bootstrap_legacy_tenant(tenant_url)
        return

    LOG.info("[%s] alembic upgrade head", safe_label)
    _run_alembic("upgrade", "head", database_url=tenant_url)


def main() -> int:
    default_url = os.environ.get("DATABASE_URL")
    if not default_url:
        LOG.error("DATABASE_URL is not set; nothing to migrate.")
        return 2

    master_url = _master_db_url(default_url)

    # 1. Patch the master DB first. Doing this before reading the tenant
    #    registry means the SELECT below tolerates a master schema that hasn't
    #    yet been extended — the SELECT only touches columns that always exist.
    try:
        _apply_master_patches(master_url)
    except Exception as exc:
        LOG.error("Master DB patching failed: %s", exc)
        return 4

    try:
        tenant_db_names = _list_tenant_db_names(master_url)
    except Exception as exc:
        LOG.error("Could not read tenant registry from master DB: %s", exc)
        return 3

    if not tenant_db_names:
        LOG.warning("No active tenants found in master DB. Nothing to do.")
        return 0

    LOG.info("Found %d active tenant(s): %s",
             len(tenant_db_names), ", ".join(tenant_db_names))

    failures: list[tuple[str, str]] = []
    for db_name in tenant_db_names:
        try:
            migrate_one(db_name, default_url)
        except Exception as exc:  # noqa: BLE001 — surface and continue
            LOG.exception("[%s] migration failed: %s", db_name, exc)
            failures.append((db_name, str(exc)))
            continue

        # After the schema is at head, backfill any new permissions onto
        # the Admin role. This keeps existing tenants' admins in sync with
        # the canonical PERMISSIONS catalogue without requiring a manual
        # SQL nudge per release. The function is idempotent — when nothing
        # is missing it's a no-op.
        try:
            from app.services.tenant_provisioning import backfill_admin_permissions
            result = backfill_admin_permissions(db_name)
            if result.get("created_permissions") or result.get("granted_to_admin"):
                LOG.info(
                    "[%s] admin backfill: +%d permission(s), +%d Admin grant(s)",
                    db_name,
                    result["created_permissions"],
                    result["granted_to_admin"],
                )
        except Exception as exc:  # noqa: BLE001 — non-fatal
            LOG.warning("[%s] admin permission backfill failed: %s", db_name, exc)

    if failures:
        LOG.error("Migration completed with %d failure(s):", len(failures))
        for db_name, msg in failures:
            LOG.error("  - %s: %s", db_name, msg)
        return 1

    LOG.info("All %d tenants migrated successfully.", len(tenant_db_names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
