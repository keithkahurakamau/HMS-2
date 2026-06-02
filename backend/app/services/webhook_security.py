"""
Svix-compatible webhook signature verification (EMAIL-003 / EMAIL-004).

Resend signs webhooks with the Svix scheme (secrets look like ``whsec_…``).
This is NOT a plain HMAC of the body — the signed content is
``{svix-id}.{svix-timestamp}.{body}``, the key is the base64-decoded secret,
and the signature header carries one or more space-separated ``v1,<base64>``
entries. We verify with stdlib only (no svix dependency).

Reference: https://docs.svix.com/receiving/verifying-payloads/how-manual
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Mapping

logger = logging.getLogger(__name__)

# Reject events whose timestamp is too far from now (replay protection).
_DEFAULT_TOLERANCE_SECONDS = 5 * 60


def _decode_secret(secret: str) -> bytes:
    """Svix secrets are ``whsec_<base64>``; the key is the decoded base64."""
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    return base64.b64decode(raw)


def verify_svix_webhook(
    raw_body: bytes,
    headers: Mapping[str, str],
    secret: str,
    *,
    tolerance_seconds: int = _DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """Constant-time verification of a Svix-signed webhook. Returns True/False;
    never raises. Header names are matched case-insensitively."""
    if not secret:
        return False

    # Case-insensitive header lookup (Starlette headers are already lower, but
    # be defensive for tests/other callers).
    lower = {k.lower(): v for k, v in headers.items()}
    svix_id = lower.get("svix-id") or lower.get("webhook-id")
    svix_ts = lower.get("svix-timestamp") or lower.get("webhook-timestamp")
    svix_sig = lower.get("svix-signature") or lower.get("webhook-signature")
    if not (svix_id and svix_ts and svix_sig):
        return False

    # Replay window.
    try:
        if abs(time.time() - int(svix_ts)) > tolerance_seconds:
            logger.warning("[webhook] timestamp %s outside tolerance — rejected", svix_ts)
            return False
    except (TypeError, ValueError):
        return False

    try:
        key = _decode_secret(secret)
    except Exception:
        logger.error("[webhook] signing secret is not valid base64")
        return False

    signed_content = b"%s.%s.%s" % (svix_id.encode(), svix_ts.encode(), raw_body)
    expected = base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode()

    # Header may carry multiple versioned sigs: "v1,<b64> v1,<b64> v2,<b64>".
    for part in svix_sig.split():
        version, _, value = part.partition(",")
        if version == "v1" and hmac.compare_digest(expected, value):
            return True
    return False
