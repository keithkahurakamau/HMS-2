"""Platform-level Daraja STK settlement, the operator's OWN subscription
billing rail, the Daraja counterpart to platform_payhero_service.py.

Everything here operates on the MASTER database against
platform_mpesa_transactions (app.models.platform_mpesa), never a tenant
database: MediFleet's own shortcode receives the money, not a hospital's.

Only the callback side is implemented here. No route or service yet
initiates a platform Daraja STK push (that rail currently runs on Pay Hero;
see platform_payhero_service.py); this module exists so the callback path
Task 9 wires (POST /api/payments/mpesa/platform/stk/callback/{tenant_hint}/
{token}, matched against the reserved platform routing hint in
app/core/daraja_callback.py) has somewhere real to settle a receipt once
that push does exist, instead of acknowledging Safaricom and discarding the
money record.

subscription_invoice_id is deliberately left unset here: matching a
settled charge to a specific subscription invoice is a further step this
module does not attempt (the column is nullable for exactly this reason,
per its own docstring). A future task wires that match; this one only
makes sure a genuine, cross-checked receipt is recorded rather than lost.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.platform_mpesa import PlatformMpesaTransaction
from app.services.daraja.settlement import _callback_metadata, _parse_callback_amount
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


def _snapshot(txn: PlatformMpesaTransaction) -> dict[str, Any]:
    return {
        "type": "platform_payment_update",
        "transaction_id": txn.id,
        "tenant_id": txn.tenant_id,
        "external_reference": txn.external_reference,
        "status": txn.status,
        "receipt_number": txn.receipt_number,
        "result_desc": txn.result_desc,
        "amount": str(txn.amount or 0),
    }


def apply_platform_stk_callback(
    master_db: Session, payload: dict,
) -> Optional[dict[str, Any]]:
    """Apply a platform STK callback, cross-checking its claimed amount
    against the amount we ourselves requested, the same discipline
    app/services/daraja/settlement.py's apply_stk_callback uses for the
    tenant rail. Never trusts the callback's claimed amount on its own
    word: Daraja does not sign callbacks.

    Returns a snapshot for a live feed, or None when nothing changed
    (already settled, unrecognised, or a lookup found no matching row).
    """
    stk_callback = ((payload or {}).get("Body") or {}).get("stkCallback") or {}
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    if not checkout_request_id:
        logger.warning("Platform STK callback missing CheckoutRequestID; ignoring")
        return None

    txn = (
        master_db.query(PlatformMpesaTransaction)
        .filter(
            PlatformMpesaTransaction.checkout_request_id == checkout_request_id,
            PlatformMpesaTransaction.status == "Pending",
        )
        .first()
    )
    if txn is None:
        logger.warning(
            "Platform STK callback for an unrecognised or already-resolved "
            "CheckoutRequestID (%s); ignored",
            safe_repr(checkout_request_id),
        )
        return None

    result_code = stk_callback.get("ResultCode")
    if str(result_code) != "0":
        txn.status = "Failed"
        txn.result_desc = str(stk_callback.get("ResultDesc") or "")[:255]
        master_db.commit()
        return _snapshot(txn)

    metadata = _callback_metadata(stk_callback)
    receipt_number = metadata.get("MpesaReceiptNumber")
    expected_amount = Decimal(str(txn.amount or 0))

    try:
        callback_amount = _parse_callback_amount(metadata.get("Amount"))
    except ValueError as exc:
        txn.status = "Quarantined"
        txn.result_desc = f"Unparseable callback amount: {exc}"[:255]
        master_db.commit()
        return _snapshot(txn)

    # THE cross-check, same reasoning as the tenant rail: never settle a
    # claim we did not ourselves request.
    if callback_amount != expected_amount:
        txn.status = "Quarantined"
        txn.result_desc = (
            f"Callback claimed KES {callback_amount}, we requested KES {expected_amount}"
        )[:255]
        master_db.commit()
        return _snapshot(txn)

    if not receipt_number:
        txn.status = "Quarantined"
        txn.result_desc = "Callback reported success with no MpesaReceiptNumber"[:255]
        master_db.commit()
        return _snapshot(txn)

    lock_id = int(hashlib.sha1(receipt_number.encode("utf-8")).hexdigest()[:15], 16)
    master_db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        replay = (
            master_db.query(PlatformMpesaTransaction)
            .filter(PlatformMpesaTransaction.receipt_number == receipt_number)
            .first()
        )
        if replay is not None:
            master_db.commit()  # releases the advisory lock; nothing else to do
            return None

        txn.status = "Success"
        txn.receipt_number = receipt_number
        txn.settled_at = datetime.now(timezone.utc)
        snapshot = _snapshot(txn)
        master_db.commit()
        return snapshot
    except Exception:
        master_db.rollback()
        raise
