"""Encrypt historical PHI rows at rest + populate blind indexes (audit M-1).

Switching the PHI columns to ``EncryptedString`` makes all NEW / UPDATED rows
encrypt automatically (and, for the searchable identifiers, the model event
listener fills the blind-index columns). Reads tolerate plaintext, so the app
keeps working the moment the model change ships. This one-shot, idempotent
script closes the gap for rows that already existed as plaintext.

It covers two kinds of column:
  * plain-encrypt PHI (allergies, notes, clinical narrative, …) — encrypt in place.
  * encrypted identifiers with a blind index (id_number / telephone_1 / email,
    phase 2) — encrypt the value AND compute the *_bidx hash so exact-match
    search keeps working on historical rows.

Idempotent + resumable: each value is inspected at the raw level and skipped if
already Fernet ciphertext; a missing blind index is still backfilled even when
the value was already encrypted by a prior forward write.

Usage:
    python scripts/backfill_phi_encryption.py                 # all active tenants
    python scripts/backfill_phi_encryption.py --dry-run       # report only
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

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.config.database import DATABASE_URL  # noqa: E402
from app.utils.encryption import encrypt_data, decrypt_data  # noqa: E402
from app.utils.blind_index import phone_bidx, id_bidx, email_bidx  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOG = logging.getLogger("backfill_phi")

# Fernet tokens always start with this (base64 of a version byte + timestamp).
_CIPHER_PREFIX = "gAAAAA"

# Plain-encrypt columns (no blind index): (table, pk, [columns]).
_ENCRYPT_ONLY: list[tuple[str, str, list[str]]] = [
    (
        "patients", "patient_id",
        ["allergies", "chronic_conditions", "notes",
         "postal_address", "residence", "occupation", "employer_name",
         "nok_name", "nok_contact"],
    ),
    ("medical_history_entries", "entry_id", ["title", "description"]),
]

# Encrypted columns that also carry a blind index:
# (table, pk, [(value_col, bidx_col, normalizer_fn)]).
_ENCRYPT_BIDX: list[tuple[str, str, list[tuple[str, str, object]]]] = [
    (
        "patients", "patient_id",
        [
            ("id_number", "id_number_bidx", id_bidx),
            ("telephone_1", "telephone_1_bidx", phone_bidx),
            ("email", "email_bidx", email_bidx),
        ],
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


def _as_plaintext(raw: str) -> str:
    """Decrypt if it's ciphertext; otherwise treat as plaintext."""
    if isinstance(raw, str) and raw.startswith(_CIPHER_PREFIX):
        try:
            return decrypt_data(raw)
        except Exception:  # noqa: BLE001 — coincidental prefix; treat as plaintext
            return raw
    return raw


def _backfill_tenant(tenant_url: str, dry_run: bool) -> tuple[int, int]:
    """Returns (rows_changed, values_skipped) for one tenant."""
    label = tenant_url.rsplit("@", 1)[-1].rsplit("/", 1)[-1]
    engine = create_engine(tenant_url)
    changed = skipped = 0
    try:
        with engine.begin() as conn:
            tables = set(inspect(conn).get_table_names())

            # --- plain-encrypt columns -------------------------------------
            for table, pk, cols in _ENCRYPT_ONLY:
                if table not in tables:
                    continue
                rows = conn.execute(text(f"SELECT {pk}, {', '.join(cols)} FROM {table}")).fetchall()
                for row in rows:
                    m = row._mapping
                    updates = {}
                    for col in cols:
                        val = m[col]
                        if val is None or val == "":
                            continue
                        if isinstance(val, str) and val.startswith(_CIPHER_PREFIX):
                            skipped += 1
                            continue
                        updates[col] = encrypt_data(val)
                    if updates:
                        changed += 1
                        if not dry_run:
                            set_clause = ", ".join(f"{c} = :{c}" for c in updates)
                            conn.execute(
                                text(f"UPDATE {table} SET {set_clause} WHERE {pk} = :_pk"),
                                {**updates, "_pk": m[pk]},
                            )

            # --- encrypted columns + blind index ---------------------------
            for table, pk, specs in _ENCRYPT_BIDX:
                if table not in tables:
                    continue
                value_cols = [s[0] for s in specs]
                bidx_cols = [s[1] for s in specs]
                select_cols = ", ".join([pk, *value_cols, *bidx_cols])
                rows = conn.execute(text(f"SELECT {select_cols} FROM {table}")).fetchall()
                for row in rows:
                    m = row._mapping
                    updates = {}
                    for vcol, bcol, norm in specs:
                        raw = m[vcol]
                        if raw is None or raw == "":
                            continue
                        already_enc = isinstance(raw, str) and raw.startswith(_CIPHER_PREFIX)
                        plaintext = _as_plaintext(raw)
                        if already_enc:
                            # Value is fine; only fix a missing blind index.
                            if not m[bcol]:
                                updates[bcol] = norm(plaintext)
                            else:
                                skipped += 1
                        else:
                            updates[vcol] = encrypt_data(plaintext)
                            updates[bcol] = norm(plaintext)
                    if updates:
                        changed += 1
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
    LOG.info("[%s] %s %d row(s); skipped %d already-done value(s)",
             label, "would change" if dry_run else "changed", changed, skipped)
    return changed, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Encrypt historical PHI rows + blind indexes (M-1).")
    ap.add_argument("--tenant", help="Only this tenant DB name (default: all active tenants)")
    ap.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = ap.parse_args()

    urls = _tenant_urls(args.tenant)
    if not urls:
        LOG.warning("No tenants found.")
        return 0
    LOG.info("Backfilling %d tenant(s)%s", len(urls), " (dry run)" if args.dry_run else "")
    total_changed = total_skip = failures = 0
    for url in urls:
        try:
            chg, skip = _backfill_tenant(url, args.dry_run)
            total_changed += chg
            total_skip += skip
        except Exception as exc:  # noqa: BLE001 — keep going across tenants
            failures += 1
            LOG.error("[%s] backfill failed: %s", url.rsplit("@", 1)[-1], exc)
    LOG.info("Done. %s %d row(s) total; skipped %d; %d tenant failure(s).",
             "Would change" if args.dry_run else "Changed", total_changed, total_skip, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
