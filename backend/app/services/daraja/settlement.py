"""STK callback settlement, and the invoice-match helper it settles through.

**The safety property this module exists to establish.** Daraja does not
sign its callbacks. Anyone who reaches a callback URL can POST a fabricated
"payment received" body. The token in the callback path and the Safaricom
IP allow-list (see app/core/daraja_callback.py) are the first two defences;
this module is the third and last: apply_stk_callback never settles on a
callback's own word about an amount. If we pushed an STK prompt for KES 500
and a callback claims KES 50,000 against it, the only safe response is to
refuse to settle, mark the transaction Quarantined, and tell a human.

Order of operations in apply_stk_callback, which IS the safety property:

  1. Extract CheckoutRequestID from Body.stkCallback.
  2. Find the Pending transaction by that id. No row: log and return None.
     Never create one here; a callback is never itself proof we initiated
     anything.
  3. ResultCode != 0: mark Failed with ResultDesc, return.
  4. Read Amount and MpesaReceiptNumber from CallbackMetadata.Item.
  5. Compare the callback's amount against the amount WE requested
     (txn.amount). Mismatch: status Quarantined, record the claim, notify
     billing:manage, return WITHOUT settling.
  6. Receipt already recorded on a settled transaction: return, it is a
     replay. Safaricom retries, and a retry must never double-credit.
  7. Only now set receipt_number, verified_at, verification_source, status
     Success, and settle via settle_invoice_match.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Invoice, Payment
from app.models.mpesa import MpesaTransaction

logger = logging.getLogger(__name__)


# ─── STK callback ──────────────────────────────────────────────────────────


def _callback_metadata(stk_callback: dict) -> dict:
    items = ((stk_callback.get("CallbackMetadata") or {}).get("Item")) or []
    return {
        item.get("Name"): item.get("Value")
        for item in items
        if isinstance(item, dict) and item.get("Name")
    }


def _parse_callback_amount(raw) -> Decimal:
    """Parse Amount from CallbackMetadata, fail loud on garbage.

    A present but non-numeric, negative or non-finite value is treated the
    same as a mismatch, never as zero: silently flooring it would dodge the
    cross-check this module exists to enforce.
    """
    if raw is None:
        raise ValueError("missing Amount in callback metadata")
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"non-numeric callback amount: {raw!r}")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"invalid callback amount: {raw!r}")
    return amount


def _notify_quarantine(db: Session, txn: MpesaTransaction, *, reason: str) -> None:
    try:
        from app.utils.notify import notify_permission
        notify_permission(
            db, "billing:manage",
            title="M-Pesa payment quarantined",
            body=(
                f"CheckoutRequestID {txn.checkout_request_id}: {reason}. "
                "Not settled, needs review."
            ),
            link="/app/billing",
            category="danger",
        )
    except Exception:  # noqa: BLE001, a notification failure must never
        # be allowed to look like a settlement failure, or vice versa.
        logger.warning("apply_stk_callback: quarantine notification failed", exc_info=True)


def apply_stk_callback(db: Session, payload: dict) -> Optional[MpesaTransaction]:
    """Apply an STK callback body, cross-checking its claimed amount first.

    See the module docstring for the full order of operations. Returns the
    affected MpesaTransaction, or None when the callback matched no Pending
    transaction we ourselves created.
    """
    stk_callback = ((payload or {}).get("Body") or {}).get("stkCallback") or {}
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    if not checkout_request_id:
        logger.warning("Daraja STK callback missing CheckoutRequestID; ignoring")
        return None

    txn = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.checkout_request_id == checkout_request_id,
            MpesaTransaction.status == "Pending",
        )
        .first()
    )
    if txn is None:
        # No row means we never initiated this, or it was already resolved
        # by an earlier delivery of the same callback. Either way there is
        # nothing to create: a callback is never itself proof we pushed
        # anything.
        logger.warning(
            "Daraja STK callback for a CheckoutRequestID with no matching "
            "Pending transaction; ignored"
        )
        return None

    result_code = stk_callback.get("ResultCode")
    if result_code != 0:
        txn.status = "Failed"
        txn.result_desc = str(stk_callback.get("ResultDesc") or "")[:255]
        db.commit()
        return txn

    metadata = _callback_metadata(stk_callback)
    receipt_number = metadata.get("MpesaReceiptNumber")
    expected_amount = Decimal(str(txn.amount or 0))

    try:
        callback_amount = _parse_callback_amount(metadata.get("Amount"))
    except ValueError as exc:
        txn.status = "Quarantined"
        txn.result_desc = f"Unparseable callback amount: {exc}"[:255]
        db.commit()
        _notify_quarantine(db, txn, reason=txn.result_desc)
        return txn

    # THE cross-check. Daraja callbacks are unsigned, so the amount claimed
    # here is never trusted on its own word. A mismatch is quarantined, not
    # settled, and nothing is claimed against the receipt.
    if callback_amount != expected_amount:
        txn.result_desc = (
            f"Callback claimed KES {callback_amount}, we requested KES {expected_amount}"
        )[:255]
        txn.status = "Quarantined"
        db.commit()
        _notify_quarantine(db, txn, reason=txn.result_desc)
        return txn

    if receipt_number:
        replay = (
            db.query(MpesaTransaction)
            .filter(
                MpesaTransaction.receipt_number == receipt_number,
                MpesaTransaction.status == "Success",
            )
            .first()
        )
        if replay is not None:
            # Safaricom retries; a retry must never double-credit.
            logger.info("Daraja STK callback replay for an already-settled receipt; no-op")
            return replay

    txn.receipt_number = receipt_number
    txn.verified_at = datetime.now(timezone.utc)
    txn.verification_source = "stk_callback"
    txn.status = "Success"
    db.commit()

    if txn.invoice_id:
        invoice = db.query(Invoice).filter(Invoice.invoice_id == txn.invoice_id).first()
        if invoice is not None:
            settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback")
            db.commit()

    return txn


# ─── Invoice settlement ─────────────────────────────────────────────────────


def settle_invoice_match(
    db: Session,
    *,
    invoice: Invoice,
    txn: MpesaTransaction,
    match_basis: str,
    user_id: Optional[int] = None,
) -> Payment:
    """Apply a verified M-Pesa receipt to an invoice and post to the ledger.

    Idempotent on Payment.transaction_reference == txn.receipt_number, so
    calling this twice for the same receipt (e.g. once from the callback,
    once from a reconciliation pass) returns the existing Payment rather
    than creating a second one.

    Ported from services/payhero_service.py's settle_invoice_match, largely
    unchanged: the logic was already correct. What changed is the
    post_from_event source key (billing.payment.mpesa, provider-neutral
    since this ledger entry no longer says which aggregator moved the
    money) and the notification body, which no longer uses an em dash.
    """
    from app.services.accounting_posting import post_from_event

    amount = Decimal(str(txn.amount or 0))
    if amount <= 0:
        raise HTTPException(400, detail="Cannot settle a zero-amount receipt.")

    existing = None
    if txn.receipt_number:
        existing = (
            db.query(Payment)
            .filter(Payment.transaction_reference == txn.receipt_number)
            .first()
        )

    if existing:
        return existing

    payment = Payment(
        invoice_id=invoice.invoice_id,
        amount=amount,
        payment_method="M-Pesa",
        transaction_reference=txn.receipt_number,
    )
    db.add(payment)
    db.flush()

    invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + amount
    invoice.status = (
        "Paid" if invoice.amount_paid >= invoice.total_amount else "Partially Paid"
    )
    invoice.payment_method = "M-Pesa"

    txn.invoice_id = invoice.invoice_id
    txn.match_basis = match_basis

    post_from_event(
        db,
        source_key="billing.payment.mpesa",
        source_id=txn.id,
        amount=amount,
        memo=f"M-Pesa receipt {txn.receipt_number or txn.external_reference}",
        reference=f"INV-{invoice.invoice_id}",
        user_id=user_id,
    )

    # M-Pesa settles asynchronously via callback, the cashier isn't
    # watching the STK screen, so the bell is how they learn the money
    # landed.
    try:
        from app.utils.notify import notify_permission
        fully_paid = invoice.status == "Paid"
        notify_permission(
            db, "billing:manage",
            title="M-Pesa payment received",
            body=(
                f"KES {amount} on Invoice #{invoice.invoice_id} "
                f"({'paid in full' if fully_paid else 'partial'}) . "
                f"receipt {txn.receipt_number or 'not recorded'}"
            ),
            link="/app/billing",
            category="success",
        )
    except Exception:  # noqa: BLE001, notification must never break settlement
        logger.warning("settle_invoice_match: notify failed", exc_info=True)

    return payment
