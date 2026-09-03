"""Platform-level Daraja STK settlement, the operator's OWN subscription
billing rail, the Daraja counterpart to platform_payhero_service.py.

Everything here operates on the MASTER database against
platform_mpesa_transactions (app.models.platform_mpesa), never a tenant
database: MediFleet's own shortcode receives the money, not a hospital's.

The push side lives in app/services/daraja/platform_stk.py; this module is
the callback/settlement side the route in app/routes/mpesa_payment.py
already calls (POST /api/payments/mpesa/platform/stk/callback/{tenant_hint}/
{token}, matched against the reserved platform routing hint in
app/core/daraja_callback.py).

THE POINT OF THIS MODULE: a settled subscription STK must land as an
InvoicePayment row in the receivables ledger
(app.models.subscription_billing), against the exact SubscriptionInvoice
platform_stk.py named at push time via subscription_invoice_id. Without
that, a paid subscription settles Success here and nowhere else, and
app/services/subscription_billing.py's dunning cron, which reads only
InvoicePayment rows to compute outstanding_balance, keeps chasing a
hospital that has already paid.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.platform_mpesa import PlatformMpesaTransaction
from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice
from app.services.daraja.settlement import _callback_metadata, _parse_callback_amount
from app.services.subscription_billing import outstanding_balance
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


def _notify_quarantine(txn: PlatformMpesaTransaction, *, reason: str) -> None:
    """Surface a quarantined subscription charge loudly, not silently.

    Defect fixed here: this module had no equivalent of
    app/services/daraja/settlement.py's _notify_quarantine, so a
    quarantined platform charge previously sat in
    platform_mpesa_transactions with nothing telling anyone.

    It cannot reuse settlement.py's _notify_quarantine as-is:
    notify_permission writes a Notification row into a TENANT database
    (app.models.notification.Notification, resolved via a tenant's own
    Permission/Role/User tables), and this module runs entirely on the
    MASTER database, which has no such table and no per-user permission
    graph for "billing:manage" to resolve against. There is currently no
    superadmin-facing notification store to write into instead, so the two
    things this CAN do, and does, are: log at ERROR (not the silent-commit
    this module had before, and a level distinct from the routine
    INFO/WARNING traffic every callback produces, so it is easy to alert
    on), and make sure a quarantined row is something a route actually
    lists (see app/routes/platform_mpesa.py's GET /transactions) instead of
    sitting in a table nothing reads.
    """
    logger.error(
        "Platform subscription charge quarantined, NOT settled: tenant_id=%s "
        "external_reference=%s reason=%s",
        txn.tenant_id, safe_repr(txn.external_reference), reason,
    )


def _settle_subscription_invoice(master_db: Session, *, txn: PlatformMpesaTransaction) -> None:
    """Post a settled platform receipt into the receivables ledger as an
    InvoicePayment against subscription_invoice_id.

    This is the fix for the third defect this module shipped with:
    settlement never populated subscription_invoice_id, so a paid
    subscription STK settled Success on this row and nowhere else. The
    column itself is populated at push time now
    (app/services/daraja/platform_stk.py sets it when the superadmin names
    an invoice to charge); this function is what actually USES it to write
    the ledger row app/services/subscription_billing.py's outstanding_balance
    and dunning cron read.

    A no-op when the push was never tied to an invoice
    (subscription_invoice_id is nullable for exactly that reason, e.g. a
    bare connectivity test charge): the receipt still settles as a real
    PlatformMpesaTransaction, it is just not applied against any specific
    invoice's balance.

    Idempotent on platform_transaction_id, matching InvoicePayment's own
    provenance column: a replay that somehow reached this far (the
    receipt-number advisory lock and replay check above should already
    have caught it) must still never double-credit the invoice.
    """
    if not txn.subscription_invoice_id:
        return

    invoice = (
        master_db.query(SubscriptionInvoice)
        .filter(SubscriptionInvoice.id == txn.subscription_invoice_id)
        .with_for_update()
        .first()
    )
    if invoice is None:
        logger.error(
            "Platform STK settled for subscription_invoice_id=%s which no "
            "longer exists; receipt recorded, ledger not updated. Needs review.",
            txn.subscription_invoice_id,
        )
        return
    if invoice.status == "void":
        logger.error(
            "Platform STK settled against void subscription invoice id=%s; "
            "receipt recorded, ledger not updated. Needs manual review.",
            invoice.id,
        )
        return

    existing = (
        master_db.query(InvoicePayment)
        .filter(InvoicePayment.platform_transaction_id == txn.id)
        .first()
    )
    if existing is not None:
        return

    payment = InvoicePayment(
        invoice_id=invoice.id,
        platform_transaction_id=txn.id,
        amount_kes=txn.amount,
        paid_on=date.today(),
        method="mpesa",
    )
    master_db.add(payment)
    master_db.flush()

    if outstanding_balance(master_db, invoice) <= 0:
        invoice.status = "paid"


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
        _notify_quarantine(txn, reason=txn.result_desc)
        return _snapshot(txn)

    # THE cross-check, same reasoning as the tenant rail: never settle a
    # claim we did not ourselves request.
    if callback_amount != expected_amount:
        txn.status = "Quarantined"
        txn.result_desc = (
            f"Callback claimed KES {callback_amount}, we requested KES {expected_amount}"
        )[:255]
        master_db.commit()
        _notify_quarantine(txn, reason=txn.result_desc)
        return _snapshot(txn)

    if not receipt_number:
        txn.status = "Quarantined"
        txn.result_desc = "Callback reported success with no MpesaReceiptNumber"[:255]
        master_db.commit()
        _notify_quarantine(txn, reason=txn.result_desc)
        return _snapshot(txn)

    lock_id = int(hashlib.sha1(receipt_number.encode("utf-8")).hexdigest()[:15], 16)
    master_db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        # Defect fix: this replay check used to omit status == "Success",
        # unlike its tenant twin (settlement.py:258-265). Benign only while
        # nothing wrote a receipt on the success path; now that settlement
        # actually posts to the ledger below, a Quarantined row that
        # happens to share a receipt_number (e.g. two callbacks disputing
        # the same claimed receipt) must never be mistaken for "already
        # settled" and cause a genuine settlement to be skipped.
        replay = (
            master_db.query(PlatformMpesaTransaction)
            .filter(
                PlatformMpesaTransaction.receipt_number == receipt_number,
                PlatformMpesaTransaction.status == "Success",
            )
            .first()
        )
        if replay is not None:
            master_db.commit()  # releases the advisory lock; nothing else to do
            return None

        txn.status = "Success"
        txn.receipt_number = receipt_number
        txn.settled_at = datetime.now(timezone.utc)
        # THE point of this module: land the receipt in the receivables
        # ledger against a real invoice, not just Success on this row.
        _settle_subscription_invoice(master_db, txn=txn)
        snapshot = _snapshot(txn)
        # ONE commit for the whole settled unit (status, receipt, and the
        # InvoicePayment together), same discipline as
        # settlement.py's apply_stk_callback: if _settle_subscription_invoice
        # raises, nothing above is persisted, so Safaricom's retry finds
        # the transaction still Pending and can settle cleanly, instead of
        # a permanent "Success but never credited to any invoice" row.
        master_db.commit()
        return snapshot
    except Exception:
        master_db.rollback()
        raise
