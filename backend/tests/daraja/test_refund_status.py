"""refund_status.handle_transaction_status_result_for_refund: the module
C1 turns on. Its single most load-bearing claim, that no path here ever
writes Completed or Failed from a reconciliation status result, was
previously asserted only by reading the source (New-8). These tests pin
that rule directly.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from decimal import Decimal

from app.models.mpesa import MpesaRefund, MpesaTransaction
from app.services.daraja.status import handle_transaction_status_result
from tests.daraja.conftest import make_mpesa_config


def _make_settled_txn(db, *, config, amount=Decimal("1000.00")):
    txn = MpesaTransaction(
        phone_number="254712345678",
        amount=amount,
        receipt_number=f"RCPT{secrets.token_hex(4).upper()}",
        status="Success",
        transaction_type="STK",
        mpesa_config_id=config.id,
        verified_at=datetime.now(timezone.utc),
        verification_source="stk_callback",
    )
    db.add(txn)
    db.flush()
    return txn


def _make_refund(
    db, *, source_txn, status, conversation_id=None, status_query_conversation_id=None,
    result_desc=None, amount=Decimal("200.00"),
):
    refund = MpesaRefund(
        source_transaction_id=source_txn.id,
        phone_number=source_txn.phone_number,
        amount=amount,
        reason="refund_status test",
        status=status,
        originator_conversation_id=f"AG_{secrets.token_hex(8)}",
        conversation_id=conversation_id,
        status_query_conversation_id=status_query_conversation_id,
        result_desc=result_desc,
        requested_by=1,
        approved_by=1,
        first_dispatch_attempted_at=datetime.now(timezone.utc),
    )
    db.add(refund)
    db.flush()
    return refund


def _status_result_payload(
    *, conversation_id, result_code=0, receipt=None, amount=None, status="Completed",
    result_desc="The service request is processed successfully.",
):
    params = []
    if receipt is not None:
        params.append({"Key": "TransactionReceipt", "Value": receipt})
    if amount is not None:
        params.append({"Key": "TransactionAmount", "Value": amount})
    if status is not None:
        params.append({"Key": "TransactionStatus", "Value": status})
    return {
        "Result": {
            "ResultType": 0,
            "ResultCode": result_code,
            "ResultDesc": result_desc,
            "ConversationID": conversation_id,
            "OriginatorConversationID": f"AG_ORIG_{conversation_id}",
            "ResultParameters": {"ResultParameter": params},
        }
    }


def test_a_completed_looking_result_never_completes_the_refund(db):
    """THE rule this module exists to pin. A ResultCode 0 result carrying a
    receipt, an amount, and TransactionStatus 'Completed' looks exactly
    like a genuine completion, and must still never resolve the refund:
    only handle_b2c_result (correlated on originator_conversation_id, with
    its own cross-checks) may ever write Completed."""
    config = make_mpesa_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        conversation_id="AG_DISPATCH_ORIGINAL",
        status_query_conversation_id="AG_STATUS_QUERY_1",
    )
    db.commit()

    payload = _status_result_payload(
        conversation_id="AG_STATUS_QUERY_1", result_code=0,
        receipt="RCPT_REFUND_1", amount="200", status="Completed",
    )
    resolved = handle_transaction_status_result(db, payload)

    assert resolved is not None
    assert resolved.id == refund.id
    db.refresh(refund)
    assert refund.status == "Processing"                      # never resolved
    assert refund.transaction_receipt is None                  # never written
    assert refund.completed_at is None
    assert refund.conversation_id == "AG_DISPATCH_ORIGINAL"     # B2C id untouched
    assert "RCPT_REFUND_1" in refund.result_desc                # but recorded, for a human


def test_a_failure_looking_result_never_fails_the_refund(db):
    """The counterpart: a ResultCode reporting Safaricom does not know this
    instruction (or rejects it) must not write Failed either. Only
    handle_b2c_result / dispatch_refund's own first-attempt rejection may."""
    config = make_mpesa_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        conversation_id="AG_DISPATCH_ORIGINAL",
        status_query_conversation_id="AG_STATUS_QUERY_2",
    )
    db.commit()

    payload = _status_result_payload(
        conversation_id="AG_STATUS_QUERY_2", result_code=1,
        result_desc="The transaction could not be found.",
    )
    resolved = handle_transaction_status_result(db, payload)

    assert resolved is not None
    db.refresh(refund)
    assert refund.status == "Processing"
    assert "could not be found" in refund.result_desc


def test_result_for_an_already_completed_refund_does_not_clobber_its_audit_text(db):
    """New-6. handle_b2c_result can genuinely complete a refund before this
    reconciliation status query's own, separately fired answer arrives. A
    late answer must not overwrite the real completion's own result_desc,
    and must not fire a needs-review notification for a refund that is
    already finished."""
    config = make_mpesa_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Completed",
        conversation_id="AG_DISPATCH_ORIGINAL",
        status_query_conversation_id="AG_STATUS_QUERY_3",
        result_desc="Genuine completion via handle_b2c_result",
    )
    db.commit()

    payload = _status_result_payload(
        conversation_id="AG_STATUS_QUERY_3", result_code=0,
        receipt="LATE_RECEIPT", amount="200", status="Completed",
    )
    resolved = handle_transaction_status_result(db, payload)

    assert resolved is not None
    db.refresh(refund)
    assert refund.status == "Completed"
    assert refund.result_desc == "Genuine completion via handle_b2c_result"


def test_correlates_on_status_query_conversation_id_not_the_b2c_dispatch_id(db):
    """A ConversationID matching MpesaRefund.conversation_id (the B2C
    dispatch's own id), rather than status_query_conversation_id, must not
    be mistaken for this reconciliation query's own answer."""
    config = make_mpesa_config(db)
    source_txn = _make_settled_txn(db, config=config)
    refund = _make_refund(
        db, source_txn=source_txn, status="Processing",
        conversation_id="AG_DISPATCH_ORIGINAL",
        status_query_conversation_id=None,
    )
    db.commit()

    payload = _status_result_payload(conversation_id="AG_DISPATCH_ORIGINAL", result_code=0)
    resolved = handle_transaction_status_result(db, payload)

    assert resolved is None
    db.refresh(refund)
    assert refund.status == "Processing"
    assert refund.result_desc is None
