"""PII/secret redaction helpers for structured logging.

CACHE-003: callback handlers previously logged Pay Hero / Daraja payloads
verbatim (full MSISDN, receipt no., amount, BillRefNumber). On Render those
go to the shared log stream and any operator with log-read access can
harvest patient phone numbers and payment receipts. Always pass payloads
through `redact()` before formatting.
"""
from __future__ import annotations

import re
from typing import Any

# Kenyan MSISDN forms: 2547XXXXXXXX, 2541XXXXXXXX, 07XXXXXXXX, 01XXXXXXXX.
_MSISDN_RE = re.compile(r"\b(?:254|0)[17]\d{8}\b")
# Safaricom receipt numbers (alpha prefix + 6-10 digits/letters).
_RECEIPT_RE = re.compile(r"\b[A-Z]{2,4}[A-Z0-9]{6,12}\b")
# Bearer / cookie value sniff — drop the value portion only.
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_SET_COOKIE_VALUE = re.compile(r"(=)[^;\s]{6,}")

# Field names whose values should be masked when nested in dicts.
_SENSITIVE_KEYS = {
    "password", "current_password", "new_password",
    "consumer_key", "consumer_secret", "passkey",
    "consumer_key_encrypted", "consumer_secret_encrypted", "passkey_encrypted",
    "access_token", "refresh_token", "superadmin_token",
    "authorization", "x-csrf-token",
    "payhero_username", "payhero_password", "payhero_webhook_secret",
}


def _mask_msisdn(match: re.Match) -> str:
    raw = match.group()
    if len(raw) < 6:
        return "***"
    return raw[:3] + "***" + raw[-2:]


def redact(value: Any) -> Any:
    """Recursively redact a value for safe logging.

    Strings are scrubbed of MSISDN, receipt, and bearer-token patterns.
    Mappings have known-sensitive keys replaced with ``<redacted>``.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                out[k] = "<redacted>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    if isinstance(value, str):
        s = _MSISDN_RE.sub(_mask_msisdn, value)
        s = _RECEIPT_RE.sub("<redacted-receipt>", s)
        s = _BEARER_RE.sub(r"\1<redacted>", s)
        s = _SET_COOKIE_VALUE.sub(r"\1<redacted>", s)
        return s
    return value


def safe_repr(value: Any, *, max_len: int = 512) -> str:
    """JSON-ish repr suitable for a single log line, truncated."""
    import json
    try:
        s = json.dumps(redact(value), default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — never raise from a log call
        s = repr(redact(value))
    return s[:max_len] + ("…(truncated)" if len(s) > max_len else "")
