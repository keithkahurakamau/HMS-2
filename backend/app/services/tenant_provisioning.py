"""
End-to-end tenant provisioning.

Replaces the previous mocked POST /public/hospitals which only inserted a row
in the master registry. The real flow:

    1. Validate inputs and reserve the master-registry row.
    2. Create the tenant's PostgreSQL database (if absent).
    3. Build the schema (Base.metadata.create_all on the tenant engine).
    4. Seed the baseline RBAC roles + permissions and a single Admin user
       with a one-time temporary password and `must_change_password=True`.
    5. Return the temporary password to the caller exactly once. We never
       persist the plaintext temp credential.

If any post-master step fails, we roll back the master tenant row to keep the
registry honest. PostgreSQL CREATE DATABASE itself cannot run inside a
transaction, so steps 2–4 are best-effort with explicit cleanup on failure.
"""
import logging
import secrets
import string
from typing import Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config.database import DATABASE_URL, Base, get_tenant_engine
from app.config.settings import settings  # noqa: F401 — kept for forward-compat
from app.core.security import get_password_hash
from app.models.master import Tenant
from app.models.user import User, Role, Permission
from app.models.inventory import Location
from app.models.settings import HospitalSetting

# Re-import every model so Base.metadata is fully populated when we build the
# tenant schema. SQLAlchemy collects table metadata at import time, and these
# imports must run before Base.metadata.create_all on a fresh engine.
from app.models import patient as _patient  # noqa: F401
from app.models import inventory as _inventory  # noqa: F401
from app.models import wards as _wards  # noqa: F401
from app.models import laboratory as _laboratory  # noqa: F401
from app.models import clinical as _clinical  # noqa: F401
from app.models import billing as _billing  # noqa: F401
from app.models import audit as _audit  # noqa: F401
from app.models import medical_history as _medical_history  # noqa: F401
from app.models import radiology as _radiology  # noqa: F401
from app.models import auth_tokens as _auth_tokens  # noqa: F401
from app.models import idempotency as _idempotency  # noqa: F401
from app.models import mpesa as _mpesa  # noqa: F401
from app.models import breach as _breach  # noqa: F401
from app.models import notification as _notification  # noqa: F401
from app.models import messaging as _messaging  # noqa: F401
from app.models import settings as _settings  # noqa: F401
from app.models import referral as _referral  # noqa: F401

logger = logging.getLogger(__name__)


# RBAC seed used for every new tenant. Mirrors what seed.py installs.
# Default inventory locations every tenant ships with. Kept in lockstep with
# the alembic migration d8b46e91527a so existing tenants get the same rows.
DEFAULT_LOCATIONS = [
    ("Main Store", "Central inventory store — receives all procurements"),
    ("Pharmacy", "Dispensing point for prescriptions and OTC sales"),
    ("Laboratory", "Reagents and consumables for diagnostic testing"),
    ("Wards", "Bedside consumables and PRN drug stock"),
]


# Default hospital_settings rows new tenants get out of the box. Mirrored in
# alembic revision b27f4e91d563 for existing tenants.
DEFAULT_SETTINGS = [
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

PERMISSIONS = [
    "users:manage", "clinical:write", "clinical:read",
    "patients:read", "patients:write", "history:read", "history:manage",
    "pharmacy:manage", "pharmacy:read", "laboratory:manage", "laboratory:read",
    "wards:manage", "billing:read", "billing:manage",
    "radiology:manage",
    # Internal staff messaging — every role gets read/write by default so the
    # whole hospital can chat. Department + custom-role administration is
    # admin-only.
    "messaging:read", "messaging:write",
    "departments:manage", "roles:manage",
    # Hospital-wide settings: every role can read so the UI can react to
    # branding/hours/etc, but only Admin can write.
    "settings:read", "settings:manage",
    # Specialist referrals — clinical staff write, admin reads
    "referrals:manage",
]

# Baseline grants applied to every staff role so messaging works out of the box.
_MESSAGING_BASE = ["messaging:read", "messaging:write"]
_SETTINGS_READ = ["settings:read"]
_BASE = [*_MESSAGING_BASE, *_SETTINGS_READ]

ROLE_GRANTS = {
    "Admin": PERMISSIONS,
    "Doctor": ["clinical:write", "clinical:read", "patients:read", "patients:write",
               "pharmacy:read", "laboratory:read", "history:read", "history:manage",
               "referrals:manage", *_BASE],
    "Nurse": ["clinical:read", "patients:read", "wards:manage", "pharmacy:read", "history:read",
              *_BASE],
    "Pharmacist": ["pharmacy:manage", "pharmacy:read", "patients:read", *_BASE],
    "Lab Technician": ["laboratory:manage", "laboratory:read", "patients:read", *_BASE],
    "Radiologist": ["radiology:manage", "clinical:read", "patients:read", *_BASE],
    "Receptionist": ["patients:read", "patients:write", "billing:read", "billing:manage",
                     *_BASE],
}


def _generate_temp_password(length: int = 14) -> str:
    """Cryptographically random password that satisfies our complexity rules."""
    alphabet_lower = string.ascii_lowercase
    alphabet_upper = string.ascii_uppercase
    digits = string.digits
    specials = "!@#$%^&*"
    # Guarantee at least one of each class so password validation passes.
    seed = [
        secrets.choice(alphabet_lower),
        secrets.choice(alphabet_upper),
        secrets.choice(digits),
        secrets.choice(specials),
    ]
    pool = alphabet_lower + alphabet_upper + digits + specials
    seed += [secrets.choice(pool) for _ in range(max(0, length - len(seed)))]
    secrets.SystemRandom().shuffle(seed)
    return "".join(seed)


def _create_database_if_missing(db_name: str) -> None:
    """CREATE DATABASE has to live outside a transaction; use AUTOCOMMIT."""
    base_url = DATABASE_URL.rsplit('/', 1)[0]
    admin_engine = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": db_name},
            ).fetchone()
            if not exists:
                # Identifier interpolation is unavoidable for CREATE DATABASE; we've
                # validated db_name in the calling layer so it's safe.
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                logger.info("Provisioned new database '%s'", db_name)
    finally:
        admin_engine.dispose()


def _drop_database_silently(db_name: str) -> None:
    """Best-effort cleanup when post-CREATE steps fail."""
    base_url = DATABASE_URL.rsplit('/', 1)[0]
    admin_engine = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            # Terminate any leaked connections before dropping.
            conn.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    except Exception as exc:
        logger.error("Cleanup of database '%s' failed: %s", db_name, exc)
    finally:
        admin_engine.dispose()


def _build_schema(db_name: str) -> None:
    engine = get_tenant_engine(db_name)
    Base.metadata.create_all(bind=engine)


def _stamp_alembic_head(db_name: str) -> None:
    """Mark the freshly-built tenant DB as fully migrated.

    create_all builds the schema but doesn't populate alembic_version, which
    leaves the tenant in the "legacy bootstrap" state — future migrations
    would refuse to run because alembic thinks the DB is empty. Stamping at
    head right after seed avoids the trap entirely: from this point on,
    scripts/migrate_all_tenants.py just runs `alembic upgrade head` against
    the tenant URL whenever a new revision is added.
    """
    import os
    import subprocess
    from pathlib import Path
    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_bin = backend_dir / "venv" / "bin" / "alembic"
    cmd = [str(alembic_bin) if alembic_bin.exists() else "alembic", "stamp", "head"]
    base_url = DATABASE_URL.rsplit("/", 1)[0]
    env = os.environ.copy()
    env["DATABASE_URL"] = f"{base_url}/{db_name}"
    result = subprocess.run(cmd, env=env, cwd=str(backend_dir), check=False)
    if result.returncode != 0:
        # Don't fail provisioning over a stamp failure — the migrate-all
        # script will retry next deploy. Just log loudly so it's visible.
        logger.warning(
            "Could not stamp alembic_version for tenant '%s' (exit %d). "
            "scripts/migrate_all_tenants.py will reconcile on next run.",
            db_name, result.returncode,
        )


def _seed_baseline(db_name: str, admin_email: str, admin_full_name: str, temp_password: str) -> None:
    """Inserts roles, permissions, and the bootstrap Admin user with a temp password."""
    engine = get_tenant_engine(db_name)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    try:
        perms = {}
        for code in PERMISSIONS:
            p = Permission(codename=code, description=f"Allows {code}")
            db.add(p)
            perms[code] = p
        db.flush()

        roles = {}
        for name, codes in ROLE_GRANTS.items():
            r = Role(name=name, description=f"{name} access level")
            for c in codes:
                r.permissions.append(perms[c])
            db.add(r)
            roles[name] = r
        db.flush()

        admin = User(
            email=admin_email,
            full_name=admin_full_name,
            hashed_password=get_password_hash(temp_password),
            role_id=roles["Admin"].role_id,
            is_active=True,
            must_change_password=True,
        )
        db.add(admin)

        # Seed the default inventory locations. The Inventory page expects
        # these to exist by name; without them, adding a stock batch fails
        # with a FK violation against `locations`.
        for name, description in DEFAULT_LOCATIONS:
            db.add(Location(name=name, description=description))

        # Seed default hospital settings so the Settings page is immediately
        # usable.
        for category, key, label, description, data_type, value, is_sensitive, sort_order in DEFAULT_SETTINGS:
            db.add(HospitalSetting(
                category=category, key=key, label=label, description=description,
                data_type=data_type, value=value, is_sensitive=is_sensitive,
                sort_order=sort_order,
            ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def provision_tenant(
    master_db,
    *,
    name: str,
    domain: str,
    db_name: str,
    admin_email: str,
    admin_full_name: str,
    theme_color: str = "blue",
    is_premium: bool = False,
) -> Tuple[Tenant, str]:
    """
    Returns (tenant_row, temp_admin_password). Raises ValueError on validation
    failure (duplicate domain/db_name, malformed input) or RuntimeError on
    infra failure (with the master row rolled back and the half-built tenant
    database dropped).

    The caller is responsible for surfacing the temp password to the operator
    over a secure channel and discarding it afterwards. We do not persist it.
    """
    # 1. Strict validation — db_name flows into a SQL identifier downstream.
    if not db_name.replace("_", "").isalnum():
        raise ValueError("db_name must be alphanumeric (underscores allowed).")
    if not (3 <= len(db_name) <= 63):
        raise ValueError("db_name must be 3–63 characters long.")

    # Normalize the comparison fields so casing/whitespace can't slip a
    # "duplicate" past the pre-flight check.
    domain_norm = (domain or "").strip().lower()
    db_name_norm = (db_name or "").strip().lower()

    # 2. Reserve the master row first so a duplicate request fails fast.
    existing = master_db.query(Tenant).filter(
        (Tenant.db_name == db_name_norm) | (Tenant.domain == domain_norm)
    ).first()
    if existing:
        if existing.domain == domain_norm:
            raise ValueError(f"A tenant with domain '{domain_norm}' already exists.")
        raise ValueError(f"A tenant with database name '{db_name_norm}' already exists.")

    tenant = Tenant(
        name=name,
        domain=domain_norm,
        db_name=db_name_norm,
        theme_color=theme_color,
        is_premium=is_premium,
        is_active=True,
    )
    master_db.add(tenant)
    try:
        master_db.flush()  # gets us tenant_id without committing yet
    except IntegrityError as exc:
        # Lost a race against a concurrent provisioning request, or the
        # pre-flight read missed a row committed since this session opened.
        master_db.rollback()
        raise ValueError(
            "A tenant with this database name or domain already exists."
        ) from exc

    temp_password = _generate_temp_password()

    # 3. Database + schema + seed. If any step fails, undo cleanly.
    try:
        _create_database_if_missing(db_name)
        _build_schema(db_name)
        _seed_baseline(
            db_name=db_name,
            admin_email=admin_email,
            admin_full_name=admin_full_name,
            temp_password=temp_password,
        )
        _stamp_alembic_head(db_name)
    except Exception as exc:
        master_db.rollback()
        _drop_database_silently(db_name)
        logger.exception("Tenant provisioning failed for %s", db_name)
        raise RuntimeError(f"Failed to provision tenant: {exc}") from exc

    master_db.commit()
    master_db.refresh(tenant)
    return tenant, temp_password
