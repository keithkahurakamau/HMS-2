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

logger = logging.getLogger(__name__)


# RBAC seed used for every new tenant. Mirrors what seed.py installs.
PERMISSIONS = [
    "users:manage", "clinical:write", "clinical:read",
    "patients:read", "patients:write", "history:read", "history:manage",
    "pharmacy:manage", "pharmacy:read", "laboratory:manage", "laboratory:read",
    "wards:manage", "billing:read", "billing:manage", "radiology:manage",
    # Internal staff messaging — every role gets read/write by default so the
    # whole hospital can chat. Department + custom-role administration is
    # admin-only.
    "messaging:read", "messaging:write",
    "departments:manage", "roles:manage",
]

# Baseline grants applied to every staff role so messaging works out of the box.
_MESSAGING_BASE = ["messaging:read", "messaging:write"]

ROLE_GRANTS = {
    "Admin": PERMISSIONS,
    "Doctor": ["clinical:write", "clinical:read", "patients:read", "patients:write",
               "pharmacy:read", "laboratory:read", "history:read", "history:manage",
               *_MESSAGING_BASE],
    "Nurse": ["clinical:read", "patients:read", "wards:manage", "pharmacy:read", "history:read",
              *_MESSAGING_BASE],
    "Pharmacist": ["pharmacy:manage", "pharmacy:read", "patients:read", *_MESSAGING_BASE],
    "Lab Technician": ["laboratory:manage", "laboratory:read", "patients:read", *_MESSAGING_BASE],
    "Radiologist": ["radiology:manage", "clinical:read", "patients:read", *_MESSAGING_BASE],
    "Receptionist": ["patients:read", "patients:write", "billing:read", "billing:manage",
                     *_MESSAGING_BASE],
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
    except Exception as exc:
        master_db.rollback()
        _drop_database_silently(db_name)
        logger.exception("Tenant provisioning failed for %s", db_name)
        raise RuntimeError(f"Failed to provision tenant: {exc}") from exc

    master_db.commit()
    master_db.refresh(tenant)
    return tenant, temp_password
