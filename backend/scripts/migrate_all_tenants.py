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
# Triggers SQLAlchemy metadata population for EVERY model so the legacy-tenant
# create_all path below adds tables introduced by later migrations (e.g.
# accounting Phase 6's acc_bank_accounts). Missing imports here mean the
# corresponding tables are silently skipped and only surface as runtime 500s.
# Keep this list in sync with app/models/ — every .py file there belongs here.
from app.models import (  # noqa: E402,F401
    accounting, audit, auth_tokens, billing, breach, calendar, cheque, clinical,
    dialysis, email_events, idempotency, inventory, laboratory, master, maternity as _maternity,
    medical_history, messaging, notification, patient, payhero, radiology, referral,
    settings as _settings, support, user, wards,
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
    # Master-DB tables that the seed normally creates via SQLAlchemy
    # create_all on first boot. Migrations run BEFORE the seed in
    # render-start.sh (and in CI we don't run the seed at all), so on a
    # fresh master DB we have to bootstrap these ourselves or downstream
    # patches that FK into them will fail with `relation … does not
    # exist`. Every CREATE here is IF NOT EXISTS so re-running on an
    # already-seeded DB is a no-op.
    """
    CREATE TABLE IF NOT EXISTS superadmins (
        admin_id        SERIAL PRIMARY KEY,
        email           VARCHAR(255) UNIQUE NOT NULL,
        full_name       VARCHAR(255) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    # H-1 — superadmin brute-force lockout (mirrors tenant User columns).
    "ALTER TABLE superadmins ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0;",
    "ALTER TABLE superadmins ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;",
    """
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id        SERIAL PRIMARY KEY,
        name             VARCHAR(255) NOT NULL,
        domain           VARCHAR(255) UNIQUE NOT NULL,
        db_name          VARCHAR(100) UNIQUE NOT NULL,
        theme_color      VARCHAR(50) DEFAULT 'blue',
        is_premium       BOOLEAN DEFAULT FALSE,
        is_active        BOOLEAN DEFAULT TRUE,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
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
    # EMAIL-003 inbound support email. tenant attribution becomes optional
    # (inbound from unrecognised-tenant contacts lands in an Unassigned bucket),
    # plus message-level fields for email threading/dedupe. All idempotent.
    "ALTER TABLE support_tickets  ALTER COLUMN tenant_id   DROP NOT NULL;",
    "ALTER TABLE support_tickets  ALTER COLUMN tenant_name DROP NOT NULL;",
    "ALTER TABLE support_tickets  ADD COLUMN IF NOT EXISTS origin VARCHAR(20) NOT NULL DEFAULT 'app';",
    "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'app';",
    "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS external_message_id VARCHAR(255);",
    "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS from_email VARCHAR(255);",
    "ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS from_name VARCHAR(255);",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_support_messages_external_id ON support_messages (external_message_id);",
    # EMAIL-004 outbound delivery tracking (master DB only). Idempotent.
    """
    CREATE TABLE IF NOT EXISTS email_events (
        event_id    SERIAL PRIMARY KEY,
        event_type  VARCHAR(64) NOT NULL,
        email       VARCHAR(255),
        message_id  VARCHAR(255),
        reason      VARCHAR(255),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_email_events_event_type ON email_events (event_type);",
    "CREATE INDEX IF NOT EXISTS ix_email_events_email      ON email_events (email);",
    "CREATE INDEX IF NOT EXISTS ix_email_events_message_id ON email_events (message_id);",
    "CREATE INDEX IF NOT EXISTS ix_email_events_created_at ON email_events (created_at);",
    "CREATE INDEX IF NOT EXISTS idx_email_events_type_created ON email_events (event_type, created_at);",
    """
    CREATE TABLE IF NOT EXISTS email_suppressions (
        email       VARCHAR(255) PRIMARY KEY,
        reason      VARCHAR(64) NOT NULL,
        detail      TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    # ab3c9e5d27f8 — platform Pay Hero (superadmin subscription billing).
    # These tables + the tenants billing columns live in the MASTER DB. The
    # alembic revision only runs against tenant DBs, so without these explicit
    # master patches the platform billing tables would never be created in
    # production. Every statement is idempotent.
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_contact_msisdn VARCHAR(20);",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_contact_name VARCHAR(120);",
    """
    CREATE TABLE IF NOT EXISTS platform_payhero_configs (
        id                          SERIAL PRIMARY KEY,
        shortcode                   VARCHAR(20)  NOT NULL DEFAULT '',
        shortcode_type              VARCHAR(20)  NOT NULL DEFAULT 'paybill',
        payhero_channel_id          VARCHAR(40),
        payhero_username_encrypted  VARCHAR(255),
        payhero_password_encrypted  VARCHAR(255),
        payhero_webhook_secret_encrypted VARCHAR(255),
        settlement_bank_code        VARCHAR(20)  NOT NULL DEFAULT '',
        settlement_bank_name        VARCHAR(80)  NOT NULL DEFAULT '',
        settlement_account_number   VARCHAR(40)  NOT NULL DEFAULT '',
        settlement_account_name     VARCHAR(120),
        account_reference           VARCHAR(50)  DEFAULT 'MEDIFLEET',
        transaction_desc            VARCHAR(100) DEFAULT 'MediFleet Subscription',
        is_active                   BOOLEAN      DEFAULT TRUE,
        last_test_at                TIMESTAMPTZ,
        last_test_status            VARCHAR(40),
        last_test_message           TEXT,
        created_at                  TIMESTAMPTZ  DEFAULT now(),
        updated_at                  TIMESTAMPTZ,
        updated_by                  INTEGER REFERENCES superadmins(admin_id)
    );
    """,
    # The encrypted-secret column post-dates the original CREATE above, so add
    # it separately for master DBs provisioned before this column existed.
    "ALTER TABLE platform_payhero_configs ADD COLUMN IF NOT EXISTS payhero_webhook_secret_encrypted VARCHAR(255);",
    """
    CREATE TABLE IF NOT EXISTS platform_payhero_transactions (
        id                  SERIAL PRIMARY KEY,
        tenant_id           INTEGER NOT NULL REFERENCES tenants(tenant_id),
        phone_number        VARCHAR(20)  NOT NULL,
        amount              NUMERIC(10, 2) NOT NULL,
        payhero_reference   VARCHAR(100),
        external_reference  VARCHAR(100) NOT NULL UNIQUE,
        receipt_number      VARCHAR(50)  UNIQUE,
        status              VARCHAR(50)  DEFAULT 'Pending',
        result_desc         VARCHAR(255),
        period_label        VARCHAR(120),
        initiated_by        INTEGER REFERENCES superadmins(admin_id),
        initiated_at        TIMESTAMPTZ DEFAULT now(),
        settled_at          TIMESTAMPTZ
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_plat_payhero_txn_tenant   ON platform_payhero_transactions (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_plat_payhero_txn_extref   ON platform_payhero_transactions (external_reference);",
    "CREATE INDEX IF NOT EXISTS ix_plat_payhero_txn_receipt  ON platform_payhero_transactions (receipt_number);",
    "CREATE INDEX IF NOT EXISTS ix_plat_payhero_txn_status   ON platform_payhero_transactions (status);",
    "CREATE INDEX IF NOT EXISTS ix_plat_payhero_txn_initiated ON platform_payhero_transactions (initiated_at);",
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


# Default rows for hospital_settings — mirrored from alembic revision
# b27f4e91d563. Kept here in lockstep so the safety net can re-seed an empty
# table on tenants that lost the rows (or never had them). Each tuple:
# (category, key, label, description, data_type, value, is_sensitive, sort_order).
# Re-running this seed on a converged tenant is a no-op (WHERE NOT EXISTS).
_HOSPITAL_SETTING_DEFAULTS: list[tuple] = [
    ("branding", "hospital_name", "Hospital name", "Displayed on every print-out and dashboard.", "string", "", False, 1),
    ("branding", "tagline", "Tagline", "Short subtitle below the hospital name on letterheads.", "string", "", False, 2),
    ("branding", "primary_color", "Primary brand color", "Hex code used for UI accents.", "string", "#2563eb", False, 3),
    ("branding", "logo_url", "Logo URL", "Public URL of the hospital logo (PNG/SVG).", "string", "", False, 4),
    ("working_hours", "weekday_open", "Weekday opening", "Front-desk opens (24-hour, HH:MM).", "string", "08:00", False, 1),
    ("working_hours", "weekday_close", "Weekday closing", "Front-desk closes (24-hour, HH:MM).", "string", "17:00", False, 2),
    ("working_hours", "saturday_open", "Saturday opening", "", "string", "09:00", False, 3),
    ("working_hours", "saturday_close", "Saturday closing", "", "string", "13:00", False, 4),
    ("working_hours", "sunday_open", "Sunday opening", "Leave blank if closed.", "string", "", False, 5),
    ("working_hours", "sunday_close", "Sunday closing", "Leave blank if closed.", "string", "", False, 6),
    ("working_hours", "appointment_slot_minutes", "Appointment slot (min)", "", "number", "30", False, 7),
    ("billing", "currency", "Currency code", "ISO 4217 (KES, USD…).", "string", "KES", False, 1),
    ("billing", "tax_rate_pct", "VAT / tax rate (%)", "Applied on taxable invoices.", "number", "16", False, 2),
    ("billing", "invoice_prefix", "Invoice prefix", "Goes on every printed invoice number.", "string", "INV-", False, 3),
    ("billing", "lock_pricing_on_order", "Lock pricing on order", "Once a lab/imaging order is placed, the price won't change.", "boolean", "true", False, 4),
    ("laboratory", "default_turnaround_hours", "Default turnaround (h)", "Used when a catalog entry doesn't specify its own.", "number", "24", False, 1),
    ("laboratory", "barcode_default", "Barcode by default", "Default value for the catalog 'Requires barcode' checkbox.", "boolean", "false", False, 2),
    ("laboratory", "critical_value_notify", "Notify critical values", "Auto-DM the ordering doctor for out-of-range flags.", "boolean", "true", False, 3),
    ("radiology", "default_modality", "Default modality", "Pre-selects this modality in new exam dialogs.", "string", "X-Ray", False, 1),
    ("radiology", "report_signing_required", "Require radiologist sign-off", "", "boolean", "true", False, 2),
    ("notifications", "email_from", "Outbound email From:", "RFC-5321 address used by transactional mail.", "string", "no-reply@hospital.local", False, 1),
    ("notifications", "sms_sender_id", "SMS sender ID", "Letterhead the SMS gateway shows on the patient's phone.", "string", "HMS", False, 2),
    ("notifications", "remind_before_hours", "Appointment reminder (h)", "Hours before the appointment to send a reminder.", "number", "24", False, 3),
    ("privacy", "kdpa_dpo_email", "Data protection officer email", "Used in subject access response letters.", "string", "", False, 1),
    ("privacy", "breach_notify_minutes", "Breach window (minutes)", "KDPA Section 43 default is 72 hours = 4320.", "number", "4320", False, 2),
]


# Idempotent column patches that mirror the ADD COLUMN IF NOT EXISTS
# statements from alembic migrations. Each entry is (table_name, ddl). The
# table-existence guard in _apply_tenant_column_patches skips tables that
# don't live in this tenant (e.g. mpesa_configs was dropped after the
# Pay Hero swap). Sourced from migrations:
#   f3d8e91a64b2_lab_flexibility_revamp
#   c8e21f47a309_pharmacy_payment_link
#   a91c3d27e845_radiology_revamp
#   c7a2e94d318f_tenant_flexibility_fields (master only)
#   c9d4ea7b1f02_tenant_branding_columns (master only)
#   e7c63a82d51f_mpesa_per_tenant_tills (legacy, table may not exist post-swap)
# Re-running on a converged tenant is a no-op (every statement uses
# `ADD COLUMN IF NOT EXISTS`).
TENANT_COLUMN_PATCHES: list[tuple[str, str]] = [
    # f3d8e91a64b2 — lab flexibility + reusable inventory
    ("inventory_items",
        "ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS is_reusable BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("inventory_usage_logs",
        "ALTER TABLE inventory_usage_logs ADD COLUMN IF NOT EXISTS is_reusable_use BOOLEAN NOT NULL DEFAULT FALSE;"),
    ("lab_test_catalog",
        "ALTER TABLE lab_test_catalog ADD COLUMN IF NOT EXISTS requires_barcode BOOLEAN NOT NULL DEFAULT FALSE;"),
    # c8e21f47a309 — pharmacy/billing linkage
    ("pharmacy_invoices",
        "ALTER TABLE pharmacy_invoices ADD COLUMN IF NOT EXISTS dispense_id INTEGER REFERENCES dispense_logs(dispense_id) ON DELETE SET NULL;"),
    # a91c3d27e845 — radiology revamp
    ("radiology_exams",
        "ALTER TABLE radiology_exams ADD COLUMN IF NOT EXISTS catalog_id INTEGER REFERENCES radiology_exam_catalog(catalog_id) ON DELETE SET NULL;"),
    ("radiology_exams",
        "ALTER TABLE radiology_exams ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'Routine';"),
    ("radiology_exams",
        "ALTER TABLE radiology_exams ADD COLUMN IF NOT EXISTS billed_price NUMERIC(10, 2);"),
    ("radiology_exams",
        "ALTER TABLE radiology_exams ADD COLUMN IF NOT EXISTS contrast_used VARCHAR(120);"),
    # e7c63a82d51f — mpesa per-tenant tills (skipped automatically if the
    # table doesn't exist; safe to keep in the list for tenants that still
    # have legacy mpesa_configs from before the Pay Hero swap)
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS environment VARCHAR(20) NOT NULL DEFAULT 'sandbox';"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS shortcode_type VARCHAR(20) NOT NULL DEFAULT 'paybill';"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_short_code VARCHAR(20);"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_response_type VARCHAR(20) NOT NULL DEFAULT 'Completed';"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS c2b_registered_at TIMESTAMPTZ;"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_at TIMESTAMPTZ;"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_status VARCHAR(40);"),
    ("mpesa_configs",
        "ALTER TABLE mpesa_configs ADD COLUMN IF NOT EXISTS last_test_message TEXT;"),
    # c4e62d8a1f37 — bidirectional cheque register
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS direction VARCHAR(20) NOT NULL DEFAULT 'incoming';"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS payee_name VARCHAR(255);"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS payee_type VARCHAR(40);"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS date_issued TIMESTAMPTZ;"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS dispatch_date TIMESTAMPTZ;"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS return_reason VARCHAR(255);"),
    ("cheques",
        "ALTER TABLE cheques ADD COLUMN IF NOT EXISTS stop_reason VARCHAR(255);"),
    # drawer_* must be nullable for outgoing rows (the hospital is the
    # implicit drawer for those). Idempotent — DROP NOT NULL on a column
    # that's already nullable is a no-op.
    ("cheques",
        "ALTER TABLE cheques ALTER COLUMN drawer_name DROP NOT NULL;"),
    ("cheques",
        "ALTER TABLE cheques ALTER COLUMN drawer_type DROP NOT NULL;"),
    # d7a1f9c34b85 — per-tenant Pay Hero webhook secret (each hospital owns
    # its own Pay Hero account and signs callbacks with its own secret).
    ("payhero_configs",
        "ALTER TABLE payhero_configs ADD COLUMN IF NOT EXISTS payhero_webhook_secret_encrypted VARCHAR(255);"),
    # f1a2c7d9e3b6 — patient-portal brute-force lockout (audit M-3)
    ("patients",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS portal_failed_attempts INTEGER NOT NULL DEFAULT 0;"),
    ("patients",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS portal_locked_until TIMESTAMPTZ;"),
    # c3e8b1f4a7d2 — widen PHI columns to TEXT for column-level encryption
    # (audit M-1). ALTER ... TYPE TEXT on an already-TEXT column is a no-op, so
    # these are safe to re-run. (No new columns added, so the patch runner logs
    # nothing — that's expected.)
    ("patients", "ALTER TABLE patients ALTER COLUMN postal_address TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN residence TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN occupation TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN employer_name TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN nok_name TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN nok_contact TYPE TEXT;"),
    ("medical_history_entries", "ALTER TABLE medical_history_entries ALTER COLUMN title TYPE TEXT;"),
    # a6f2d9c4e7b1 — encrypt searchable identifiers + blind indexes (audit M-1
    # phase 2). Widen to TEXT, drop the now-useless plaintext indexes, add the
    # *_bidx columns + their indexes. All idempotent / guarded.
    ("patients", "ALTER TABLE patients ALTER COLUMN id_number TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN telephone_1 TYPE TEXT;"),
    ("patients", "ALTER TABLE patients ALTER COLUMN email TYPE TEXT;"),
    ("patients", "DROP INDEX IF EXISTS ix_patients_id_number;"),
    ("patients", "DROP INDEX IF EXISTS ix_patients_telephone_1;"),
    ("patients", "ALTER TABLE patients ADD COLUMN IF NOT EXISTS id_number_bidx VARCHAR(64);"),
    ("patients", "ALTER TABLE patients ADD COLUMN IF NOT EXISTS telephone_1_bidx VARCHAR(64);"),
    ("patients", "ALTER TABLE patients ADD COLUMN IF NOT EXISTS email_bidx VARCHAR(64);"),
    ("patients", "CREATE INDEX IF NOT EXISTS ix_patients_id_number_bidx ON patients (id_number_bidx);"),
    ("patients", "CREATE INDEX IF NOT EXISTS ix_patients_telephone_1_bidx ON patients (telephone_1_bidx);"),
    ("patients", "CREATE INDEX IF NOT EXISTS ix_patients_email_bidx ON patients (email_bidx);"),
]


def _apply_tenant_column_patches(tenant_url: str) -> None:
    """Apply idempotent ALTER TABLE ADD COLUMN IF NOT EXISTS statements.

    Each patch is skipped when the target table doesn't exist on this tenant
    (e.g. mpesa_configs was dropped during the Pay Hero swap). When a patch
    actually adds a column, we log a WARNING so the operator sees the drift
    in deploy logs.
    """
    if not TENANT_COLUMN_PATCHES:
        return
    engine = create_engine(tenant_url)
    label = tenant_url.rsplit("@", 1)[-1]
    try:
        # MIGRATE-BUG-001: this used to be `engine.connect()` + a nested
        # `conn.begin()`. Under SQLAlchemy 2.x the `inspect(conn)` call
        # autobegins a transaction, so the explicit begin() always raised
        # "connection has already initialized a Transaction" — every column
        # patch pass failed (caught + logged) and the patches NEVER applied.
        # `engine.begin()` gives one transaction for the whole pass.
        with engine.begin() as conn:
            existing_tables = set(inspect(conn).get_table_names())
            applied = 0
            for table, ddl in TENANT_COLUMN_PATCHES:
                if table not in existing_tables:
                    continue
                # Snapshot column set before applying so we can detect
                # whether the patch actually changed anything (the DDL
                # itself is silent on IF NOT EXISTS no-ops).
                cols_before = {c["name"] for c in inspect(conn).get_columns(table)}
                conn.execute(text(ddl))
                cols_after = {c["name"] for c in inspect(conn).get_columns(table)}
                if cols_after - cols_before:
                    added_cols = ", ".join(sorted(cols_after - cols_before))
                    LOG.warning(
                        "[%s] added column(s) to %s: %s",
                        label, table, added_cols,
                    )
                    applied += 1
            if applied == 0:
                LOG.debug("[%s] column patches: no drift", label)
    except Exception as exc:  # noqa: BLE001
        LOG.error("[%s] column patch pass failed: %s", label, exc)
    finally:
        engine.dispose()


def _ensure_tenant_metadata(tenant_url: str) -> None:
    """Create any tables in Base.metadata that are missing on this tenant.

    Pure safety net. create_all is idempotent — only creates tables that
    don't already exist — so calling it after `alembic upgrade head` adds
    nothing on a converged tenant but recovers a tenant that's stamped at
    head yet missing a table (e.g. hospital_settings on BriAfya).
    """
    engine = create_engine(tenant_url)
    try:
        before = set(inspect(engine).get_table_names())
        Base.metadata.create_all(bind=engine)
        after = set(inspect(engine).get_table_names())
        added = sorted(after - before)
        if added:
            LOG.warning(
                "[%s] create_all backfilled %d missing table(s): %s",
                tenant_url.rsplit("@", 1)[-1], len(added), ", ".join(added),
            )
    finally:
        engine.dispose()


def _seed_hospital_settings_defaults(tenant_url: str) -> None:
    """Re-seed the hospital_settings defaults, idempotently.

    Required for tenants whose hospital_settings table was freshly created
    by the safety net above — `create_all` only creates the schema, never
    rows. The alembic migration's INSERT … WHERE NOT EXISTS pattern is
    repeated here so re-running on a converged tenant is a no-op.
    """
    engine = create_engine(tenant_url)
    try:
        with engine.begin() as conn:
            # Skip cleanly if the table somehow still isn't there (shouldn't
            # happen after _ensure_tenant_metadata, but defensive).
            if not inspect(conn).has_table("hospital_settings"):
                LOG.error(
                    "[%s] hospital_settings still missing after create_all — skipping seed",
                    tenant_url.rsplit("@", 1)[-1],
                )
                return
            inserted = 0
            for (category, key, label, description, data_type, value, is_sensitive, sort_order) in _HOSPITAL_SETTING_DEFAULTS:
                result = conn.execute(
                    text(
                        "INSERT INTO hospital_settings "
                        "(category, key, label, description, data_type, value, is_sensitive, sort_order) "
                        "SELECT :c, :k, :l, :d, :t, :v, :s, :o "
                        "WHERE NOT EXISTS (SELECT 1 FROM hospital_settings WHERE category = :c AND key = :k)"
                    ),
                    {
                        "c": category, "k": key, "l": label, "d": description,
                        "t": data_type, "v": value, "s": is_sensitive, "o": sort_order,
                    },
                )
                inserted += result.rowcount or 0
            if inserted:
                LOG.warning(
                    "[%s] seeded %d hospital_settings default row(s)",
                    tenant_url.rsplit("@", 1)[-1], inserted,
                )
    finally:
        engine.dispose()


def _seed_accounting_defaults(tenant_url: str) -> None:
    """Seed base currency, settings, default CoA, and ledger mappings.

    TENANT-DRIFT-003: legacy-bootstrapped tenants were stamped at alembic
    head without ever running the accounting migrations' data seeds — empty
    acc_accounts/acc_ledger_mappings means post_from_event skips every
    payment and the transaction log stays empty. Idempotent, never touches
    accounts/mappings a tenant customised.
    """
    from app.services.accounting_defaults_seed import seed_accounting_defaults

    engine = create_engine(tenant_url)
    safe_label = tenant_url.rsplit("@", 1)[-1]
    try:
        with engine.begin() as conn:
            insp = inspect(conn)
            needed = ("acc_currencies", "acc_settings", "acc_accounts", "acc_ledger_mappings")
            if not all(insp.has_table(t) for t in needed):
                LOG.error("[%s] accounting tables missing after migrate — skipping accounting seed", safe_label)
                return
            created = seed_accounting_defaults(conn)
            if created["accounts"] or created["mappings"]:
                LOG.warning(
                    "[%s] seeded %d CoA account(s), %d ledger mapping(s)",
                    safe_label, created["accounts"], created["mappings"],
                )
    finally:
        engine.dispose()


def _seed_standard_lab_catalog(tenant_url: str) -> None:
    """Preload the standard lab-test catalogue + price-list mirror, idempotently.

    Every tenant ships with the full standard test menu (app/data/
    standard_lab_tests.py) in both the lab catalogue and the billing price
    list (LAB-<catalog_id> rows). Inserts are guarded WHERE NOT EXISTS /
    keyed on test_name + service_code, so hospitals that renamed prices,
    deactivated tests, or added their own are never disturbed — re-running
    on a converged tenant is a no-op.
    """
    from app.services.lab_catalog_seed import (
        seed_standard_lab_catalog,
        sync_lab_prices_to_price_list,
    )

    engine = create_engine(tenant_url)
    safe_label = tenant_url.rsplit("@", 1)[-1]
    try:
        with engine.begin() as conn:
            insp = inspect(conn)
            if not insp.has_table("lab_test_catalog") or not insp.has_table("acc_price_list"):
                LOG.error(
                    "[%s] lab_test_catalog/acc_price_list missing after migrate — skipping lab seed",
                    safe_label,
                )
                return
            created_tests = seed_standard_lab_catalog(conn)
            created_prices = sync_lab_prices_to_price_list(conn)
            if created_tests or created_prices:
                LOG.warning(
                    "[%s] seeded %d standard lab test(s), %d price-list row(s)",
                    safe_label, created_tests, created_prices,
                )
    finally:
        engine.dispose()


def _seed_maternity_price_list(tenant_url: str) -> None:
    """Maternity MAT-* service codes (idempotent; zero-priced until set)."""
    from app.services.maternity_seed import seed_maternity_price_list

    engine = create_engine(tenant_url)
    safe_label = tenant_url.rsplit("@", 1)[-1]
    try:
        with engine.begin() as conn:
            insp = inspect(conn)
            if not insp.has_table("acc_price_list"):
                LOG.error(
                    "[%s] acc_price_list missing after migrate — skipping maternity seed",
                    safe_label,
                )
                return
            n = seed_maternity_price_list(conn)
            if n:
                LOG.warning("[%s] seeded %d maternity price-list row(s)", safe_label, n)
    finally:
        engine.dispose()


def _seed_dialysis(tenant_url: str) -> None:
    """Dialysis checklists + demo machine + DIA-* price codes (idempotent)."""
    from app.services.dialysis_seed import seed_dialysis_checklists, seed_dialysis_price_list

    engine = create_engine(tenant_url)
    safe_label = tenant_url.rsplit("@", 1)[-1]
    try:
        with engine.begin() as conn:
            insp = inspect(conn)
            if insp.has_table("dialysis_checklists"):
                n = seed_dialysis_checklists(conn)
                if n:
                    LOG.warning("[%s] seeded %d dialysis reference row(s)", safe_label, n)
            else:
                LOG.error(
                    "[%s] dialysis_checklists missing after migrate — skipping dialysis seed",
                    safe_label,
                )
            if insp.has_table("acc_price_list"):
                p = seed_dialysis_price_list(conn)
                if p:
                    LOG.warning("[%s] seeded %d dialysis price-list row(s)", safe_label, p)
    finally:
        engine.dispose()


def migrate_one(tenant_db_name: str, default_url: str) -> None:
    tenant_url = _tenant_db_url(default_url, tenant_db_name)
    safe_label = tenant_url.rsplit("@", 1)[-1]  # hide creds in logs

    if _is_legacy_tenant(tenant_url):
        LOG.info("[%s] no alembic_version — running legacy bootstrap", safe_label)
        _bootstrap_legacy_tenant(tenant_url)
        # Even the legacy bootstrap path benefits from the safety net below —
        # in practice we've seen tenants stamped at head with a stale model
        # registry that was missing the hospital_settings table. Fall through.
    else:
        LOG.info("[%s] alembic upgrade head", safe_label)
        _run_alembic("upgrade", "head", database_url=tenant_url)

    # Safety net (TENANT-DRIFT-001): re-run create_all + idempotent seeds so
    # any table that an older migrate_all_tenants run missed gets backfilled.
    # Concrete incident: BriAfya_db lost hospital_settings because the model
    # was added to app/models/ AFTER its legacy bootstrap had already stamped
    # alembic head — every subsequent `alembic upgrade head` was a no-op
    # because alembic believed the schema was current. create_all is
    # idempotent (only creates missing tables); the seed inserts are guarded
    # WHERE NOT EXISTS.
    _ensure_tenant_metadata(tenant_url)
    _seed_hospital_settings_defaults(tenant_url)
    # Safety net (TENANT-DRIFT-002): create_all only adds missing tables —
    # never columns to existing tables. Apply the same set of idempotent
    # ADD COLUMN IF NOT EXISTS statements the relevant migrations carry so
    # legacy-stamped tenants pick up columns added since their bootstrap.
    _apply_tenant_column_patches(tenant_url)
    # Accounting reference data (CoA, currency, settings, ledger mappings) —
    # without it post_from_event skips every payment and the transaction log
    # stays empty (idempotent; customised tenants untouched).
    _seed_accounting_defaults(tenant_url)
    # Preload the standard lab-test catalogue + price-list mirror so every
    # tenant ships with the full test menu out of the box (idempotent).
    _seed_standard_lab_catalog(tenant_url)
    # Maternity service codes so ANC/PNC/delivery charges can price (idempotent).
    _seed_maternity_price_list(tenant_url)
    # Dialysis machine-safety checklists + demo machine (idempotent).
    _seed_dialysis(tenant_url)


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
            if (result.get("created_permissions") or result.get("granted_to_admin")
                    or result.get("granted_to_roles") or result.get("updated_descriptions")):
                LOG.info(
                    "[%s] rbac backfill: +%d permission(s), +%d desc update(s), "
                    "+%d Admin grant(s), +%d built-in role grant(s)",
                    db_name,
                    result.get("created_permissions", 0),
                    result.get("updated_descriptions", 0),
                    result.get("granted_to_admin", 0),
                    result.get("granted_to_roles", 0),
                )
        except Exception as exc:  # noqa: BLE001 — non-fatal
            LOG.warning("[%s] rbac backfill failed: %s", db_name, exc)

    if failures:
        LOG.error("Migration completed with %d failure(s):", len(failures))
        for db_name, msg in failures:
            LOG.error("  - %s: %s", db_name, msg)
        return 1

    LOG.info("All %d tenants migrated successfully.", len(tenant_db_names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
