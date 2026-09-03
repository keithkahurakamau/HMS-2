"""app/routes/mpesa_events.py: the read API.

Covers the two properties the task calls out explicitly: the list view
masks phone numbers, the detail view shows them in full, and a quarantined
event's detail carries the requested amount next to the claimed one so a
human can compare them without decoding a JSON blob.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config.database import get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.services.daraja.events import record_event
from tests.daraja.conftest import make_invoice, make_pending_transaction


@pytest.fixture()
def _client(db) -> Iterator[TestClient]:
    def _get_db():
        yield db

    def _fake_user():
        return {
            "user_id": 1,
            "email": "events.test@hms.local",
            "role": "Admin",
            "full_name": "Events Test User",
            "permissions": ["billing:read", "billing:manage"],
        }

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_list_masks_phone_number(db, _client):
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(db, invoice_id=invoice.invoice_id, amount=Decimal("500.00"), phone_number="254712345678")
    db.commit()
    record_event(
        db, flow="stk_push", direction="outbound", outcome="success",
        mpesa_transaction_id=txn.id, checkout_request_id=txn.checkout_request_id,
    )
    db.commit()

    resp = _client.get("/api/mpesa/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    row = next(r for r in body["items"] if r["mpesa_transaction_id"] == txn.id)
    assert row["phone_masked"] == "254***78"
    assert "254712345678" not in str(body)


def test_detail_shows_full_phone_number(db, _client):
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(db, invoice_id=invoice.invoice_id, amount=Decimal("500.00"), phone_number="254712345678")
    db.commit()
    event = record_event(
        db, flow="stk_push", direction="outbound", outcome="success",
        mpesa_transaction_id=txn.id,
    )
    db.commit()

    resp = _client.get(f"/api/mpesa/events/{event.id}")
    assert resp.status_code == 200
    assert resp.json()["phone_number"] == "254712345678"


def test_quarantined_detail_shows_requested_and_claimed_side_by_side(db, _client):
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(db, invoice_id=invoice.invoice_id, amount=Decimal("500.00"))
    db.commit()
    event = record_event(
        db, flow="stk_callback", direction="inbound", outcome="quarantined",
        mpesa_transaction_id=txn.id,
        daraja_result_desc="Callback claimed KES 60000, we requested KES 500",
        response_payload={
            "Body": {"stkCallback": {"CallbackMetadata": {"Item": [
                {"Name": "Amount", "Value": 60000},
            ]}}}
        },
    )
    db.commit()

    resp = _client.get(f"/api/mpesa/events/{event.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_amount"] == "500.00"
    assert body["claimed_amount"] == "60000"


def test_filter_by_outcome_and_flow(db, _client):
    record_event(db, flow="stk_push", direction="outbound", outcome="success")
    record_event(db, flow="b2c_result", direction="inbound", outcome="failure")
    db.commit()

    resp = _client.get("/api/mpesa/events", params={"outcome": "failure"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(r["outcome"] == "failure" for r in body["items"])

    resp = _client.get("/api/mpesa/events", params={"flow": "stk_push"})
    assert all(r["flow"] == "stk_push" for r in resp.json()["items"])


def test_search_by_receipt(db, _client):
    record_event(db, flow="c2b_confirmation", direction="inbound", outcome="success", receipt_number="QGR7ABC123")
    record_event(db, flow="c2b_confirmation", direction="inbound", outcome="success", receipt_number="OTHERXYZ")
    db.commit()

    resp = _client.get("/api/mpesa/events", params={"search": "QGR7"})
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["receipt_number"] == "QGR7ABC123"


def test_event_not_found_returns_404(_client):
    resp = _client.get("/api/mpesa/events/999999")
    assert resp.status_code == 404
