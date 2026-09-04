"""Daraja credential derivation: MSISDN, STK password, SecurityCredential.

Kept apart from client.py so the pure functions here are testable without
touching HTTP, and so the RSA certificate handling has one obvious home.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

_CERT_DIR = Path(__file__).resolve().parent.parent.parent / "vendor" / "safaricom"
_ENVIRONMENTS = {"sandbox", "production"}
_NAIROBI = ZoneInfo("Africa/Nairobi")

_DIGITS = re.compile(r"\D")


def normalize_msisdn(phone: str) -> str:
    """Return a Safaricom MSISDN as 2547XXXXXXXX / 2541XXXXXXXX.

    Daraja rejects anything else, and it rejects it with an opaque error, so
    normalise and validate here rather than letting the API tell us later.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("phone number is required")
    digits = _DIGITS.sub("", phone)
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        digits = "254" + digits
    if not digits.startswith("254") or len(digits) != 12:
        raise ValueError(f"not a Kenyan MSISDN: {phone!r}")
    return digits


def daraja_timestamp(now: datetime | None = None) -> str:
    """Daraja wants local Kenyan wall-clock time as YYYYMMDDHHMMSS.

    The default path is pinned to Africa/Nairobi explicitly: a bare
    ``.astimezone()`` would instead follow the host's configured timezone,
    which on Render is UTC, three hours off Nairobi and outside Safaricom's
    Timestamp tolerance. Callers that pass their own ``now`` keep full
    control, unaffected by this pin.
    """
    moment = now or datetime.now(_NAIROBI)
    return moment.strftime("%Y%m%d%H%M%S")


def stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    """base64(shortcode + passkey + timestamp), per the Daraja STK spec."""
    raw = f"{shortcode}{passkey}{timestamp}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


@lru_cache(maxsize=2)
def _public_key(environment: str):
    if environment not in _ENVIRONMENTS:
        raise ValueError(f"unknown Daraja environment: {environment!r}")
    path = _CERT_DIR / f"{environment}.cer"
    if not path.exists():
        raise FileNotFoundError(f"Safaricom certificate missing: {path}")
    cert = load_pem_x509_certificate(path.read_bytes())
    return cert.public_key()


def security_credential(initiator_password: str, environment: str) -> str:
    """RSA-encrypt the initiator password with Safaricom's public certificate.

    Generated per call rather than stored, so a certificate rotation is a
    redeploy instead of a support ticket to every hospital.
    """
    if environment not in _ENVIRONMENTS:
        raise ValueError(f"unknown Daraja environment: {environment!r}")
    if not initiator_password:
        raise ValueError("initiator password is required")
    encrypted = _public_key(environment).encrypt(
        initiator_password.encode("utf-8"), padding.PKCS1v15()
    )
    return base64.b64encode(encrypted).decode("ascii")


def base_url(environment: str) -> str:
    if environment == "production":
        return "https://api.safaricom.co.ke"
    if environment == "sandbox":
        return "https://sandbox.safaricom.co.ke"
    raise ValueError(f"unknown Daraja environment: {environment!r}")
