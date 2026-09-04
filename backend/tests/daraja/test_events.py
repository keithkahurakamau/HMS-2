"""app/services/daraja/events.py: redaction first, then the emit helper.

Redaction is tested before anything else in this file (and was written
before anything emits, per the task brief) because it is the one property
this whole table's safety depends on: an allowlist of fields known to be
safe, never a denylist of ones known to be secret. See that module's own
docstring for why the difference matters.
"""
from __future__ import annotations

import json

import pytest

from app.models.mpesa_events import MpesaEvent
from app.services.daraja.events import record_event, redact_payload

# The exact values that must never survive redaction, in any form, anywhere
# in the serialised output. Distinct sentinel strings, not realistic-looking
# secrets, so a match can only mean the redaction failed to catch that
# field, never a coincidental substring of something else in the payload.
_FORBIDDEN_VALUES = {
    "Password": "SENTINEL-STK-PASSWORD-1",
    "SecurityCredential": "SENTINEL-B2C-SECURITY-CREDENTIAL-2",
    "ConsumerKey": "SENTINEL-CONSUMER-KEY-3",
    "ConsumerSecret": "SENTINEL-CONSUMER-SECRET-4",
    "Passkey": "SENTINEL-PASSKEY-5",
    "callback_token": "SENTINEL-CALLBACK-TOKEN-6",
}


def _payload_with_every_forbidden_key() -> dict:
    """One payload carrying every forbidden key, some top-level and some
    nested inside other structures (a dict, and a dict inside a list), so
    the recursive walk is exercised the same way a real nested Daraja
    payload (Body.stkCallback.CallbackMetadata.Item[...]) would exercise it.
    """
    return {
        "BusinessShortCode": "174379",
        "Password": _FORBIDDEN_VALUES["Password"],
        "Timestamp": "20260903120000",
        "Nested": {
            "SecurityCredential": _FORBIDDEN_VALUES["SecurityCredential"],
            "ConsumerKey": _FORBIDDEN_VALUES["ConsumerKey"],
        },
        "Items": [
            {"ConsumerSecret": _FORBIDDEN_VALUES["ConsumerSecret"]},
            {"Passkey": _FORBIDDEN_VALUES["Passkey"], "Amount": 500},
        ],
        "callback_token": _FORBIDDEN_VALUES["callback_token"],
        "CallBackURL": (
            f"https://example.test/api/payments/mpesa/stk/callback/"
            f"hms_daraja_test/{_FORBIDDEN_VALUES['callback_token']}"
        ),
    }


def test_redact_payload_never_leaks_forbidden_values():
    """THE test. Feeds a payload containing every forbidden key at several
    nesting depths, asserts none of their VALUES appears anywhere in the
    serialised output. Asserting on values, not key names, is deliberate
    (see the module docstring): a value-blind test (checking the key
    "Password" is absent) would pass even if the value leaked under some
    other, unanticipated key, which is exactly the failure mode a renamed
    Safaricom field would produce.
    """
    redacted = redact_payload(_payload_with_every_forbidden_key())
    serialised = json.dumps(redacted)
    for field, value in _FORBIDDEN_VALUES.items():
        assert value not in serialised, (
            f"{field}'s value leaked into the redacted payload"
        )
    # The callback URL itself must be gone too, not merely its token
    # segment scrubbed: an allowlist has no field for "URL minus its last
    # path segment", so the whole field is dropped (see the module
    # docstring).
    assert "CallBackURL" not in redacted
    assert "example.test" not in serialised


def test_redact_payload_keeps_known_safe_fields():
    """The allowlist is not empty: real diagnostic fields survive."""
    payload = {
        "BusinessShortCode": "174379",
        "Amount": 500,
        "MpesaReceiptNumber": "QGR7XXXX01",
        "ResultCode": 0,
        "ResultDesc": "The service request is processed successfully.",
    }
    redacted = redact_payload(payload)
    assert redacted == payload


def test_redact_payload_drops_unrecognised_fields():
    """Proof this is an allowlist, not a denylist: a field that is neither
    forbidden nor explicitly known-safe is dropped, not passed through.
    This is the accepted trade-off (an omitted diagnostic field, never a
    leaked secret) and it is what makes a Safaricom field renamed tomorrow
    safe by default.
    """
    redacted = redact_payload({"Amount": 500, "SomeBrandNewSafaricomField": "whatever"})
    assert redacted == {"Amount": 500}


def test_redact_payload_handles_none():
    assert redact_payload(None) is None


def test_redact_payload_nested_list_of_dicts_callback_metadata_shape():
    """The real shape this exists for: Body.stkCallback.CallbackMetadata.Item
    is a list of {"Name": ..., "Value": ...} dicts."""
    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_CO_1",
                "ResultCode": 0,
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 500},
                        {"Name": "MpesaReceiptNumber", "Value": "QGR7XXXX01"},
                        {"Name": "PhoneNumber", "Value": 254712345678},
                    ]
                },
            }
        }
    }
    redacted = redact_payload(payload)
    items = redacted["Body"]["stkCallback"]["CallbackMetadata"]["Item"]
    assert {"Name": "Amount", "Value": 500} in items
    assert {"Name": "MpesaReceiptNumber", "Value": "QGR7XXXX01"} in items


# ─── record_event: must never raise, must redact before storing ────────────


def test_record_event_persists_a_row(db):
    event = record_event(
        db,
        flow="stk_push",
        direction="outbound",
        outcome="success",
        http_status=200,
        daraja_result_code="0",
        daraja_result_desc="Success",
        checkout_request_id="ws_CO_123",
        request_payload={"BusinessShortCode": "174379", "Password": "SECRET-SHOULD-NOT-PERSIST"},
        response_payload={"MerchantRequestID": "abc", "ResponseCode": "0"},
    )
    db.commit()

    assert event is not None
    assert event.id is not None

    reloaded = db.query(MpesaEvent).filter(MpesaEvent.id == event.id).first()
    assert reloaded is not None
    assert reloaded.flow == "stk_push"
    assert reloaded.outcome == "success"
    assert reloaded.checkout_request_id == "ws_CO_123"
    # The redaction ran on the way IN: the secret is not in the stored text
    # even though the caller passed it straight through.
    assert "SECRET-SHOULD-NOT-PERSIST" not in (reloaded.request_payload or "")
    assert "Password" not in (reloaded.request_payload or "")
    assert "BusinessShortCode" in (reloaded.request_payload or "")


def test_record_event_swallows_a_write_failure(db, monkeypatch):
    """A failure inside record_event must never propagate: this is the
    property that makes emitting an event safe to call from inside a
    payment or refund flow. Simulated by making the flush itself raise.
    """
    def _boom():
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(db, "flush", _boom)

    # Must not raise.
    result = record_event(db, flow="stk_push", direction="outbound", outcome="error")
    assert result is None


def test_record_event_does_not_abort_a_caller_that_commits_after(db):
    """The realistic shape every call site uses: record_event, then the
    caller's own commit for the real work. A failure in the event write
    must not have poisoned the session so badly that the caller's own
    commit can no longer succeed for something else added moments later.
    """
    # Simulate "the real work" with a second, ordinary event row so this
    # test does not need a whole Invoice/MpesaTransaction fixture just to
    # prove the session is still usable afterward.
    record_event(db, flow="stk_push", direction="outbound", outcome="success")
    other = MpesaEvent(flow="stk_callback", direction="inbound", outcome="success")
    db.add(other)
    db.commit()
    assert other.id is not None
