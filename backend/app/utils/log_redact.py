"""PII/secret redaction helpers for structured logging.

CACHE-003: callback handlers previously logged Daraja payloads
verbatim (full MSISDN, receipt no., amount, BillRefNumber). On Render those
go to the shared log stream and any operator with log-read access can
harvest patient phone numbers and payment receipts. Always pass payloads
through `redact()` before formatting.
"""
from __future__ import annotations

import logging
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
    # B2C (app/services/daraja/b2c.py) is the first Daraja flow to build a
    # payload containing a SecurityCredential, the RSA-encrypted initiator
    # password Safaricom requires on every B2C request. Redacted here even
    # though nothing currently logs the raw payload, so the planned event
    # log gets this for free rather than needing to remember it later.
    "securitycredential", "initiator_password", "initiator_password_encrypted",
    "callback_token",
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


# --- Daraja callback token in a request path or URL ------------------------
# The token is a path segment, not a dict field, so `redact()` above never
# sees it: it walks structured payloads, not free-text request lines. This
# covers the other place a callback token reaches a log line, gunicorn's
# access log ("METHOD /path HTTP/1.1" status) and any handler that logs
# request.url.path directly (app/main.py's unhandled-exception handler).
#
# The token is the last path segment on every one of these routes
# (app/routes/mpesa_payment.py's six callbacks plus the two B2C routes in
# app/routes/mpesa_refunds.py); the tenant routing hint just before it is
# kept, since app/core/daraja_callback.py's own module docstring explains
# why the hint is safe to disclose (it names a tenant db_name, already
# publicly enumerable via GET /api/public/hospitals) while the token is the
# actual secret.
_CALLBACK_TOKEN_PATH_RE = re.compile(
    r"(/api/payments/mpesa/(?:"
    r"stk/callback|c2b/validation|c2b/confirmation|"
    r"status/result|status/timeout|platform/stk/callback|"
    r"b2c/result|b2c/timeout"
    r")/[^/\s\"?#]+/)[^/\s\"?#]+"
)


def redact_callback_token_path(text: str) -> str:
    """Rewrite the trailing token segment of any Daraja callback path found
    in `text` to a placeholder. Safe to call on any string, including one
    with no such path at all (returned unchanged)."""
    return _CALLBACK_TOKEN_PATH_RE.sub(r"\1<redacted>", text)


class CallbackTokenPathFilter(logging.Filter):
    """A `logging.Filter` that redacts a Daraja callback token wherever a
    log record's already-formatted message names one of the callback
    paths above.

    Attach this to loggers that record whole request lines or URLs rather
    than structured fields: `redact()` cannot help there, since there is no
    dict for it to walk. app/main.py attaches this to "gunicorn.access"
    (the production access log gunicorn writes on every request) and to
    its own module logger (the unhandled-exception handler logs
    `request.url.path` directly). One filter, attached in one place,
    covers both call sites plus the B2C routes that predate this task.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_callback_token_path(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (redact_callback_token_path(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            else:
                record.args = tuple(
                    redact_callback_token_path(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
