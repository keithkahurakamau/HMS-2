"""Deterministic blind indexes for searchable-but-encrypted columns (M-1 ph.2).

The PHI columns telephone_1 / id_number / email are encrypted with Fernet
(non-deterministic ciphertext), so they can no longer be matched in SQL. To keep
*exact-match* lookups working (duplicate detection, "find patient by phone/ID"),
we store a deterministic keyed hash — a "blind index" — alongside each encrypted
column and query on that.

  blind index = HMAC-SHA256(key, normalized_value)   -> 64-char hex

Properties:
  * Deterministic: the same input always yields the same index, so equality
    search works. It does NOT support substring/ILIKE (that capability was
    intentionally dropped — see the M-1 phase 2 decision).
  * Keyed: without the key an attacker with DB read access can't brute-force the
    (low-entropy) phone/ID space offline as easily as a plain SHA-256 would
    allow. The key is derived from ENCRYPTION_KEY via HMAC with a fixed label so
    no new secret/env var is required, while keeping it cryptographically
    separate from the Fernet encryption key (key-separation principle).

Normalization is per-field and MUST be identical on write and on query, or the
hashes won't match. Always go through the typed helpers below.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from app.config.settings import settings

_LABEL = b"hms-blind-index-v1|"


def _key() -> bytes:
    base = settings.ENCRYPTION_KEY.get_secret_value().encode("utf-8")
    return hashlib.sha256(_LABEL + base).digest()


def _digest(normalized: str) -> str:
    return hmac.new(_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def phone_bidx(value: str | None) -> str | None:
    """Blind index for a phone number — digits only, so formatting differences
    (spaces, +254 vs 0…) don't break matching as long as the digits line up."""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return _digest(digits) if digits else None


def email_bidx(value: str | None) -> str | None:
    if not value:
        return None
    norm = value.strip().lower()
    return _digest(norm) if norm else None


def id_bidx(value: str | None) -> str | None:
    """Blind index for a national / ID number — trimmed + lower-cased."""
    if not value:
        return None
    norm = value.strip().lower()
    return _digest(norm) if norm else None
