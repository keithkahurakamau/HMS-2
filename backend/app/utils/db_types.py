"""
Custom SQLAlchemy types for KDPA-compliant column-level encryption.

Caveats:
  - These columns cannot be searched with ILIKE/LIKE because the ciphertext is
    non-deterministic (Fernet uses an IV per encrypt call).
  - Apply only to fields that are NOT used in search filters. For id_number
    and other lookup fields, prefer a deterministic blind index alongside the
    plaintext (or apply DB-level transparent encryption).
  - Existing rows must be migrated; ALTER COLUMN + UPDATE in a migration script.
"""
from sqlalchemy.types import TypeDecorator, Text
from app.utils.encryption import encrypt_data, decrypt_data


class EncryptedString(TypeDecorator):
    """
    Stores values encrypted with the application's Fernet key (settings.ENCRYPTION_KEY).
    Reads transparently decrypt. NULLs pass through unchanged.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        # Tolerate already-encrypted strings during migration windows.
        if isinstance(value, str) and value.startswith("gAAAAA"):
            return value
        return encrypt_data(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        try:
            return decrypt_data(value)
        except Exception:
            # Pre-migration plaintext rows: return as-is so the app keeps working
            # until a backfill migration converts them.
            return value
