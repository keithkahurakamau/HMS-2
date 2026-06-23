"""Encrypt historical PHI rows at rest (audit M-1).

Switching the PHI columns to ``EncryptedString`` makes all NEW / UPDATED rows
encrypt automatically, and reads tolerate plaintext — so the app keeps working
the moment the model change ships. This one-shot, idempotent script closes the
gap by encrypting rows that already existed as plaintext.

Why it is a SEPARATE script (not run on deploy):
  * It rewrites every PHI row in every tenant — potentially a lot of churn —
    so it must be run deliberately, off the hot deploy path.
  * It is idempotent: each value is inspected at the raw level and skipped if
    it is already Fernet ciphertext (``gAAAAA`` prefix), so re-running is safe
    and resumable after an interruption.

Usage:
    # all active tenants:
    python scripts/backfill_phi_encryption.py
    # dry run (report counts, change nothing):
    python scripts/backfill_phi_encryption.py --dry-run
    # a single tenant DB:
    python scripts/backfill_phi_encryption.py --tenant mayoclinic_db

Requires the same env as the app (DATABASE_URL, ENCRYPTION_KEY, SECRET_KEY).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Make ``app`` importable when invoked from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import create_engine, text  # noqa: E402

from app.config.database import DATABASE_URL  # noqa: E402
from app.utils.encryption import encrypt_data  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOG = logging.getLogger("backfill_phi")

# Fernet tokens always start with this (base64 of a version byte + timestamp).
_CIPHER_PREFIX = "gAAAAA"

# Columns switched to EncryptedString in the M-1 model change. Each entry is
# (table, primary_key_column, [encrypted_columns]).
_TARGETS: list[tuple[str, str, list[str]]] = [
    (
        "patients",
        "patient_id",
        [
            "allergies", "chronic_conditions", "notes",
            "postal_address", "residence", "occupation", "employer_name",
            "nok_name", "nok_contact",
        ],
    ),
    (
        "medical_history_entries",
        "entry_id",
        ["title", "description"],
    ),
]


def _tenant_urls(only: str | None) -> list[str]:
    base = DATABASE_URL.rsplit("/", 1)[0]
    if only:
        return [f"{base}/{only}"]
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT db_name FROM tenants WHERE is_active = TRUE ORDER BY db_name")
            ).fetchall()
    finally:
        engine.dispose()
    return [f"{base}/{r[0]}" for r in rows]


def _existing_tables(conn) -> set[str]:
    from sqlalchemy import inspect
    return set(inspect(conn).get_table_names())


def _backfill_tenant(tenant_url: str, dry_run: bool) -> tuple[int, int]:
    """Returns (rows_encrypted, rows_skipped) for one tenant."""
    label = tenant_url.rsplit("@", 1)[-1].rsplit("/", 1)[-1]
    engine = create_engine(tenant_url)
    encrypted = skipped = 0
    try:
        with engine.begin() as conn:
            tables = _existing_tables(conn)
            for table, pk, cols in _TARGETS:
                if table not in tables:
                    continue
                cols_csv = ", ".join(cols)
                rows = conn.execute(
                    text(f"SELECT {pk}, {cols_csv} FROM {table}")
                ).fetchall()
                for row in rows:
                    m = row._mapping
                    updates: dict[str, str] = {}
                    for col in cols:
                        val = m[col]
                        if val is None or val == "":
                            continue
                        if isinstance(val, str) and val.startswith(_CIPHER_PREFIX):
                            skipped += 1
                            continue
                        updates[col] = encrypt_data(val)
                    if not updates:
                        continue
                    encrypted += 1
                    if not dry_run:
                        set_clause = ", ".join(f"{c} = :{c}" for c in updates)
                        conn.execute(
                            text(f"UPDATE {table} SET {set_clause} WHERE {pk} = :_pk"),
                            {**updates, "_pk": m[pk]},
                        )
            if dry_run:
                conn.rollback()
    finally:
        engine.dispose()
    LOG.info("[%s] %s %d row(s); skipped %d already-encrypted value(s)",
             label, "would encrypt" if dry_run else "encrypted", encrypted, skipped)
    return encrypted, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Encrypt historical PHI rows at rest (M-1).")
    ap.add_argument("--tenant", help="Only this tenant DB name (default: all active tenants)")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = ap.parse_args()

    urls = _tenant_urls(args.tenant)
    if not urls:
        LOG.warning("No tenants found.")
        return 0
    LOG.info("Backfilling %d tenant(s)%s", len(urls), " (dry run)" if args.dry_run else "")
    total_enc = total_skip = 0
    failures = 0
    for url in urls:
        try:
            enc, skip = _backfill_tenant(url, args.dry_run)
            total_enc += enc
            total_skip += skip
        except Exception as exc:  # noqa: BLE001 — keep going across tenants
            failures += 1
            LOG.error("[%s] backfill failed: %s", url.rsplit("@", 1)[-1], exc)
    LOG.info("Done. %s %d row(s) total; skipped %d; %d tenant failure(s).",
             "Would encrypt" if args.dry_run else "Encrypted", total_enc, total_skip, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
