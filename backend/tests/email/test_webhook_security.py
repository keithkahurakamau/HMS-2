"""Unit tests for Svix-compatible webhook verification (no network).

Replicates Svix's signing on the test side so we verify the real scheme Resend
uses (whsec_ secrets, {id}.{ts}.{body} signed content, v1,<b64> header).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.services.webhook_security import verify_svix_webhook

SECRET = "whsec_" + base64.b64encode(b"super-secret-key-bytes").decode()


def _sign(body: bytes, svix_id: str, ts: str, secret: str = SECRET) -> str:
    key = base64.b64decode(secret.split("_", 1)[1])
    signed = b"%s.%s.%s" % (svix_id.encode(), ts.encode(), body)
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def _headers(body: bytes, svix_id="msg_1", ts=None, secret=SECRET):
    ts = ts or str(int(time.time()))
    return {
        "svix-id": svix_id,
        "svix-timestamp": ts,
        "svix-signature": _sign(body, svix_id, ts, secret),
    }


def test_accepts_valid_signature():
    body = b'{"type":"email.delivered"}'
    assert verify_svix_webhook(body, _headers(body), SECRET) is True


def test_rejects_tampered_body():
    body = b'{"type":"email.delivered"}'
    headers = _headers(body)
    assert verify_svix_webhook(b'{"type":"email.bounced"}', headers, SECRET) is False


def test_rejects_wrong_secret():
    body = b'{"x":1}'
    other = "whsec_" + base64.b64encode(b"different-key").decode()
    assert verify_svix_webhook(body, _headers(body), other) is False


def test_rejects_missing_headers():
    body = b'{"x":1}'
    assert verify_svix_webhook(body, {}, SECRET) is False


def test_rejects_stale_timestamp():
    body = b'{"x":1}'
    old = str(int(time.time()) - 3600)  # 1h ago, outside 5-min window
    assert verify_svix_webhook(body, _headers(body, ts=old), SECRET) is False


def test_rejects_empty_secret():
    body = b'{"x":1}'
    assert verify_svix_webhook(body, _headers(body), "") is False


def test_accepts_multiple_space_separated_signatures():
    body = b'{"x":1}'
    h = _headers(body)
    h["svix-signature"] = "v1,badbadbad " + h["svix-signature"]  # 2nd one is valid
    assert verify_svix_webhook(body, h, SECRET) is True


def test_header_lookup_is_case_insensitive():
    body = b'{"x":1}'
    h = _headers(body)
    upper = {k.upper(): v for k, v in h.items()}
    assert verify_svix_webhook(body, upper, SECRET) is True
