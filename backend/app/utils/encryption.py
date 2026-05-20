"""Fernet wrapper used for stored M-Pesa credentials and any future PHI at rest.

Audit SEC-001: the previous derivation silently padded a short ENCRYPTION_KEY
with zeros, so an operator who forgot to set the env var ended up encrypting
under Fernet(base64(b"0" * 32)) — a globally-known key. We now refuse to
build a Fernet from a key that wasn't supplied as a proper 44-char Fernet
key (or 32 bytes of strong entropy that we hash to that length).
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from app.config.settings import settings


def _derive_key() -> bytes:
    raw = settings.ENCRYPTION_KEY.get_secret_value().encode("utf-8")
    # If the operator supplied a real Fernet key (44 url-safe base64 chars),
    # use it directly. Otherwise hash whatever they supplied to a deterministic
    # 32-byte key — but only after the strength validator in settings.py has
    # rejected weak inputs. NO zero-padding fallback.
    if len(raw) == 44:
        try:
            base64.urlsafe_b64decode(raw)
            return raw
        except (ValueError, base64.binascii.Error):  # noqa: BLE001
            pass
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    return Fernet(_derive_key())


def encrypt_data(data: str) -> str | None:
    if not data:
        return None
    return get_fernet().encrypt(data.encode("utf-8")).decode("utf-8")


def decrypt_data(encrypted_data: str) -> str | None:
    if not encrypted_data:
        return None
    return get_fernet().decrypt(encrypted_data.encode("utf-8")).decode("utf-8")
