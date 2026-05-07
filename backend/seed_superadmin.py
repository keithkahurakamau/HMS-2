"""
Minimal bootstrap seed for the HMS platform.

Replaces the previous multi-hospital demo seed. Responsibilities:

  1. (Re)create the central ``hms_master`` database.
  2. Apply the master-only schema (Tenant + SuperAdmin tables).
  3. Insert exactly one platform-level superadmin row.

Tenant databases are NOT created here — they are provisioned at runtime via
POST /api/public/hospitals once the superadmin signs in.

Usage:
    python seed_superadmin.py                # idempotent: skip if superadmin exists
    python seed_superadmin.py --reset        # DROP and recreate hms_master first

Optional environment overrides:
    SEED_SUPERADMIN_EMAIL      (default: superadmin@hms.co.ke)
    SEED_SUPERADMIN_NAME       (default: HMS Platform Superadmin)
    SEED_SUPERADMIN_PASSWORD   (default: SuperAdmin@2026)
"""
import argparse
import os
import sys

from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker

from app.config.database import DATABASE_URL
from app.core.security import get_password_hash
from app.models.master import SuperAdmin, Tenant  # noqa: F401 — Tenant table needs to exist


MASTER_DB = "hms_master"


def _admin_engine():
    """AUTOCOMMIT engine bound to the cluster's `postgres` DB so we can
    CREATE/DROP databases (which cannot run inside a transaction)."""
    base_url = DATABASE_URL.rsplit("/", 1)[0]
    return create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")


def _master_engine():
    base_url = DATABASE_URL.rsplit("/", 1)[0]
    return create_engine(f"{base_url}/{MASTER_DB}")


def database_exists(name: str) -> bool:
    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            ).fetchone()
            return row is not None
    finally:
        eng.dispose()


def drop_database(name: str) -> None:
    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            # Terminate anyone still attached so DROP doesn't block.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        eng.dispose()


def create_database(name: str) -> None:
    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        eng.dispose()


def apply_master_schema() -> None:
    """Build only the master-side tables (SuperAdmin + Tenant), nothing else.

    We explicitly avoid `Base.metadata.create_all` here to keep the master
    database lean — tenant tables (patients, billing, etc.) belong in tenant
    databases, not in the registry DB.
    """
    from app.config.database import Base

    master_meta = MetaData()
    for table_name in ("superadmins", "tenants"):
        if table_name in Base.metadata.tables:
            Base.metadata.tables[table_name].to_metadata(master_meta)

    eng = _master_engine()
    try:
        master_meta.create_all(bind=eng)
    finally:
        eng.dispose()


def seed_superadmin_row(email: str, full_name: str, password: str) -> str:
    """Insert (or refresh) the single platform superadmin. Returns one of
    'created' | 'exists' | 'updated'."""
    eng = _master_engine()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    db = Session()
    try:
        existing = db.query(SuperAdmin).filter(SuperAdmin.email == email).first()
        if existing:
            return "exists"

        db.add(
            SuperAdmin(
                email=email,
                full_name=full_name,
                hashed_password=get_password_hash(password),
                is_active=True,
            )
        )
        db.commit()
        return "created"
    finally:
        db.close()
        eng.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the HMS platform superadmin.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DROP hms_master if it exists, then recreate it from scratch.",
    )
    args = parser.parse_args()

    email = os.environ.get("SEED_SUPERADMIN_EMAIL", "superadmin@hms.co.ke")
    full_name = os.environ.get("SEED_SUPERADMIN_NAME", "HMS Platform Superadmin")
    password = os.environ.get("SEED_SUPERADMIN_PASSWORD", "SuperAdmin@2026")

    print("=" * 60)
    print("  HMS PLATFORM — SUPERADMIN BOOTSTRAP")
    print("=" * 60)

    if args.reset and database_exists(MASTER_DB):
        print(f"-> dropping existing '{MASTER_DB}' database…")
        drop_database(MASTER_DB)

    if not database_exists(MASTER_DB):
        print(f"-> creating '{MASTER_DB}' database…")
        create_database(MASTER_DB)
    else:
        print(f"-> '{MASTER_DB}' already exists; reusing.")

    print("-> applying master schema (SuperAdmin + Tenant)…")
    apply_master_schema()

    print(f"-> seeding superadmin <{email}>…")
    status = seed_superadmin_row(email, full_name, password)
    if status == "exists":
        print("   (already present — leaving the existing row untouched)")
    else:
        print("   (inserted)")

    print()
    print("Superadmin login:")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print("Sign in at /superadmin/login.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
