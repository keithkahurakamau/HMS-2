"""The safety net for a callback we accepted but failed to apply.

This covers the exact live failure that stranded two confirmed sandbox
payments: settlement raised, its session rolled back (taking the event row
with it), Safaricom never retried, and STK Query's bare ResultCode 0 carries
no receipt, so nothing could ever settle the row again.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.mpesa_events import MpesaEvent
from app.services.daraja.events import (
    INBOUND_APPLIED,
    INBOUND_RECEIVED,
    journal_inbound,
    redact_payload,
)
from app.services.daraja.reconcile_queries import replay_unapplied_callbacks

from .conftest import make_invoice, make_pending_transaction, seed_mpesa_ledger_mapping


def _callback(checkout_id: str, *, receipt: str, amount: str) -> dict:
    return {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mr-1",
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": float(amount)},
                        {"Name": "MpesaReceiptNumber", "Value": receipt},
                        {"Name": "PhoneNumber", "Value": 254700000000},
                    ]
                },
            }
        }
    }


def _journal_row(session, payload: dict, *, age: timedelta) -> MpesaEvent:
    """Write the journal row directly, standing in for the route's own
    journal_inbound call (which owns a separate session this test cannot
    share a transaction with)."""
    event = MpesaEvent(
        flow="stk_callback",
        direction="inbound",
        outcome=INBOUND_RECEIVED,
        request_payload=json.dumps(redact_payload(payload)),
        created_at=datetime.now(timezone.utc) - age,
    )
    session.add(event)
    session.commit()
    return event


def test_redaction_keeps_everything_a_replay_needs():
    """The journal stores the redacted payload, so replay is only possible if
    the allowlist preserves the fields apply_stk_callback actually reads. If
    someone tightens the allowlist, this fails before the safety net silently
    stops working."""
    payload = _callback("ws_CO_KEEP", receipt="RCPT001", amount="250.00")
    kept = redact_payload(payload)

    stk = kept["Body"]["stkCallback"]
    assert stk["CheckoutRequestID"] == "ws_CO_KEEP"
    assert stk["ResultCode"] == 0
    items = {i["Name"]: i["Value"] for i in stk["CallbackMetadata"]["Item"]}
    assert items["MpesaReceiptNumber"] == "RCPT001"
    assert items["Amount"] == 250.0


def test_replay_settles_a_callback_that_was_never_applied(db):
    """The headline case: money arrived, the handler died, and the next
    reconciliation run settles the invoice from the stored callback."""
    seed_mpesa_ledger_mapping(db)
    invoice = make_invoice(db, total_amount=Decimal("250.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("250.00"), invoice_id=invoice.invoice_id
    )
    txn.checkout_request_id = "ws_CO_REPLAY"
    db.commit()

    payload = _callback("ws_CO_REPLAY", receipt="RPLY0001", amount="250.00")
    event = _journal_row(db, payload, age=timedelta(minutes=10))

    replayed = replay_unapplied_callbacks(db, older_than=timedelta(minutes=2))

    assert replayed == 1
    db.refresh(invoice)
    db.refresh(txn)
    db.refresh(event)
    assert invoice.status == "Paid"
    assert invoice.amount_paid == Decimal("250.00")
    assert txn.receipt_number == "RPLY0001"
    assert event.outcome == INBOUND_APPLIED, "a replayed row must not be replayed again"


def test_replay_leaves_a_fresh_callback_alone(db):
    """Inside the grace period the ordinary callback path must win. Replaying
    immediately would race the handler that is very likely still running."""
    seed_mpesa_ledger_mapping(db)
    invoice = make_invoice(db, total_amount=Decimal("120.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("120.00"), invoice_id=invoice.invoice_id
    )
    txn.checkout_request_id = "ws_CO_FRESH"
    db.commit()

    _journal_row(
        db,
        _callback("ws_CO_FRESH", receipt="FRSH0001", amount="120.00"),
        age=timedelta(seconds=5),
    )

    assert replay_unapplied_callbacks(db, older_than=timedelta(minutes=2)) == 0
    db.refresh(invoice)
    assert invoice.status == "Pending"


def test_replay_is_idempotent_on_a_second_run(db):
    """Settlement is idempotent on the receipt, so a replay that somehow runs
    twice must not credit the invoice twice. This is the guard that makes the
    whole safety net safe to run on a 15 minute cron."""
    seed_mpesa_ledger_mapping(db)
    invoice = make_invoice(db, total_amount=Decimal("400.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("400.00"), invoice_id=invoice.invoice_id
    )
    txn.checkout_request_id = "ws_CO_TWICE"
    db.commit()

    payload = _callback("ws_CO_TWICE", receipt="TWCE0001", amount="400.00")
    _journal_row(db, payload, age=timedelta(minutes=10))
    replay_unapplied_callbacks(db, older_than=timedelta(minutes=2))

    # A second journalled copy of the very same callback, as a duplicate
    # delivery would look.
    _journal_row(db, payload, age=timedelta(minutes=10))
    replay_unapplied_callbacks(db, older_than=timedelta(minutes=2))

    db.refresh(invoice)
    assert invoice.amount_paid == Decimal("400.00"), "replay double-credited the invoice"
    assert invoice.status == "Paid"


def test_journal_inbound_survives_a_bad_tenant_name():
    """journal_inbound must never raise: a journal failure cannot be allowed to
    cost us the 200 that stops Safaricom retrying into a duplicate payment."""
    assert journal_inbound("no_such_tenant_db", flow="stk_callback", payload={"a": 1}) is None
