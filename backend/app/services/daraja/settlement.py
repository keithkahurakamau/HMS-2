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
  3. ResultCode (normalised to a string, Daraja sends it as either an int
     or a string depending on the endpoint) != "0": mark Failed with
     ResultDesc, return.
  4. Read Amount and MpesaReceiptNumber from CallbackMetadata.Item.
  5. Compare the callback's amount against the amount WE requested
     (txn.amount). Mismatch: status Quarantined, record the claim, notify
     billing:manage, return WITHOUT settling.
  6. No MpesaReceiptNumber despite ResultCode 0: status Quarantined, notify,
     return WITHOUT settling. The receipt is the one artifact tying an
     unsigned, attacker-reachable callback to a real Safaricom transaction;
     a Payment with no receipt would also carry a NULL
     transaction_reference, and Postgres allows unlimited NULLs in a unique
     index, so the usual replay backstop would not even apply.
  7. Serialise on the receipt with a Postgres advisory transaction lock,
     THEN check whether it is already recorded on a settled transaction:
     return that transaction, it is a replay. Safaricom retries, and two
     concurrent deliveries of the same callback are also possible; either
     way a retry or a race must never double-credit. The lock is what makes
     this check-then-act safe against the race, not just the sequential
     retry: the unique index on receipt_number is a backstop that turns a
     lock failure into a 500, not a second Payment, but it is not a
     substitute for the lock.
  8. Only now set receipt_number, verified_at, verification_source, status
     Success, and settle via settle_invoice_match, ALL under one commit
     (the invoice, locked FOR UPDATE, if there is one). A single commit is
     load-bearing: if settlement raises, nothing here has been persisted,
     so the transaction is still Pending on disk and Safaricom's retry is
     free to try again cleanly. Committing the Success status separately,
     before settlement, would strand the transaction as a permanent,
     un-retryable "Success but never settled" row the moment settlement
     failed for any reason.

If anything from step 7 onward raises, apply_stk_callback rolls back and
re-raises before the exception leaves the function. This is not optional
tidiness: the advisory lock from step 7 is transaction-scoped, so only
ending the transaction (commit or rollback) releases it, and the
single-commit guarantee in step 8 is only true if a failed attempt is
actually rolled back rather than left open on whatever connection the
caller's session happens to be holding. apply_stk_callback does not own
that session, so it never closes it, only ends its own transaction and
lets the exception propagate.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.billing import Invoice, Payment
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.events import record_event
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


class SettlementExceedsBalance(Exception):
    """Raised by settle_invoice_match when crediting a receipt would push
    invoice.amount_paid past invoice.total_amount.

    By the time any caller of settle_invoice_match runs, the money has
    already reached Safaricom (an STK callback, a verified C2B receipt, or
    an operator manually assigning an unmatched one): rejecting the
    settlement outright, the way app/routes/receivables.py's record_payment
    does for a manual entry, would silently lose track of real money.
    Task 10 made exactly this ruling for the platform rail
    (app/services/daraja/platform.py's _settle_subscription_invoice); this
    is the tenant rail's own guard, closing the gap that let a second
    genuine settlement against one invoice (two independent pushes, each
    with its own real receipt, so the receipt-keyed replay check in
    apply_stk_callback never catches it) drive amount_paid past
    total_amount with no guard, no matter which rail or route reached
    settle_invoice_match. The caller quarantines the transaction instead
    of marking it Success; amount_paid is left untouched.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


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


def _till_label(db: Session, mpesa_config_id: Optional[int]) -> str:
    """A human-readable till label for a quarantine notification. Never
    raises: a failed lookup here must not turn a notification failure into
    a settlement failure, which is exactly the guarantee _notify_quarantine
    itself exists to provide for its own caller."""
    if mpesa_config_id is None:
        return "an unrecorded till"
    try:
        config = db.query(MpesaConfig).filter(MpesaConfig.id == mpesa_config_id).first()
    except Exception:  # noqa: BLE001, see the docstring
        return f"till #{mpesa_config_id}"
    if config is None:
        return f"till #{mpesa_config_id}"
    return f"till {config.shortcode}"


def _notify_quarantine(db: Session, txn: MpesaTransaction, *, reason: str) -> None:
    """Notify billing:manage that `txn` was quarantined, not settled.

    Shared by both the STK callback path (apply_stk_callback, below) and
    the C2B Transaction Status result path
    (app/services/daraja/status.py's handle_transaction_status_result): a C2B
    row never has a CheckoutRequestID, so a message built only around that
    field would read "CheckoutRequestID None: ..." for every C2B
    quarantine, which tells a cashier nothing they can act on. The
    identifier here is whichever of receipt_number or checkout_request_id
    the row actually carries, plus the till, so a cashier standing at a
    counter can find the exact payment this refers to.
    """
    try:
        from app.utils.notify import notify_permission
        identifier = (
            f"receipt {txn.receipt_number}" if txn.receipt_number
            else f"CheckoutRequestID {txn.checkout_request_id}"
        )
        till = _till_label(db, txn.mpesa_config_id)
        notify_permission(
            db, "billing:manage",
            title="M-Pesa payment quarantined",
            body=(
                f"{identifier} on {till}: {reason}. Not settled, needs review."
            ),
            link="/app/billing",
            category="danger",
        )
    except Exception:  # noqa: BLE001, a notification failure must never
        # be allowed to look like a settlement failure, or vice versa.
        logger.warning("_notify_quarantine: quarantine notification failed", exc_info=True)


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
        # anything. Logged with the (redacted) CheckoutRequestID so a
        # pattern of forged or replayed ids is at least correlatable.
        logger.warning(
            "Daraja STK callback for an unrecognised or already-resolved "
            "CheckoutRequestID (%s); ignored",
            safe_repr(checkout_request_id),
        )
        return None

    # Daraja sends ResultCode as an int from the STK callback but as a
    # string from STK Query; normalise once so a string "0" (a genuinely
    # successful payment) is never mistaken for a truthy != 0 and marked
    # Failed.
    def _emit(outcome: str) -> None:
        record_event(
            db, flow="stk_callback", direction="inbound", outcome=outcome,
            daraja_result_code=str(result_code) if result_code is not None else None,
            daraja_result_desc=txn.result_desc,
            mpesa_transaction_id=txn.id, mpesa_config_id=txn.mpesa_config_id,
            checkout_request_id=checkout_request_id, receipt_number=txn.receipt_number,
            request_payload=payload,
        )

    result_code = stk_callback.get("ResultCode")
    if str(result_code) != "0":
        txn.status = "Failed"
        txn.result_desc = str(stk_callback.get("ResultDesc") or "")[:255]
        _emit("failure")
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
        _emit("quarantined")
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
        _emit("quarantined")
        db.commit()
        _notify_quarantine(db, txn, reason=txn.result_desc)
        return txn

    if not receipt_number:
        # A "successful" callback with no receipt number is not settleable:
        # the receipt is the one artifact tying this unsigned claim to a
        # real Safaricom transaction, and a Payment with no
        # transaction_reference would also slip past the unique-index
        # replay backstop (Postgres allows unlimited NULLs in a unique
        # index).
        txn.status = "Quarantined"
        txn.result_desc = "Callback reported success with no MpesaReceiptNumber"[:255]
        _emit("quarantined")
        db.commit()
        _notify_quarantine(db, txn, reason=txn.result_desc)
        return txn

    # Serialise concurrent deliveries of this exact receipt before the
    # check-then-act replay lookup below. Without this, two callbacks
    # racing each other (a genuine Safaricom retry, or a forged duplicate)
    # can both observe "not yet settled" and both proceed; the unique index
    # on receipt_number then turns the loser into an IntegrityError and a
    # poisoned session instead of a clean no-op. Transaction-scoped, so it
    # releases automatically on this function's own commit below.
    lock_id = int(hashlib.sha1(receipt_number.encode("utf-8")).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    # Everything from here on holds that advisory lock. pg_advisory_xact_lock
    # is transaction-scoped: only a commit or a rollback ends the current
    # transaction and frees it. A bare try/finally would not be enough,
    # because the exception still needs to reach the caller (see below), so
    # this is try/except-rollback-reraise rather than try/finally.
    try:
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
            db.commit()  # releases the advisory lock cleanly
            return replay

        txn.receipt_number = receipt_number
        txn.verified_at = datetime.now(timezone.utc)
        txn.verification_source = "stk_callback"

        if txn.invoice_id:
            invoice = (
                db.query(Invoice)
                .filter(Invoice.invoice_id == txn.invoice_id)
                .populate_existing()
                .with_for_update()
                .first()
            )
            if invoice is not None:
                try:
                    settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback")
                except SettlementExceedsBalance as exc:
                    # The money already reached Safaricom (this callback IS
                    # its confirmation); quarantine, never mark Success on
                    # an over-the-balance settlement. See
                    # SettlementExceedsBalance's own docstring.
                    txn.status = "Quarantined"
                    txn.result_desc = str(exc)[:255]
                    _emit("quarantined")
                    db.commit()
                    _notify_quarantine(db, txn, reason=txn.result_desc)
                    return txn

        txn.status = "Success"
        _emit("success")
        # ONE commit for the whole unit (status, receipt, and settlement
        # together). If settle_invoice_match raises, nothing above is
        # persisted: the transaction is still Pending on disk, so Safaricom's
        # retry finds a live row and can settle cleanly, instead of finding a
        # transaction already stuck at Success with no Payment and no invoice
        # update to show for it.
        db.commit()
        return txn
    except Exception:
        # A mid-settlement exception (settle_invoice_match, or
        # post_from_event inside it) must not leave the transaction open
        # with the advisory lock still held. db.rollback() does two things
        # at once here: it undoes any uncommitted writes above, which is
        # what makes the single-commit guarantee above actually true (the
        # transaction stays Pending on disk, not just "would have, if
        # someone eventually rolled back"), and it ends the transaction,
        # which is the only thing that frees a transaction-scoped advisory
        # lock. Re-raise: the caller must still learn the settlement
        # failed, never swallow this.
        #
        # Deliberately NOT db.close() here. apply_stk_callback is handed a
        # session, it does not own one: closing it would be a second,
        # different bug (a caller that still holds a reference to this
        # session, or a route middleware that closes it again). Session
        # lifecycle stays with whoever opened it.
        db.rollback()
        raise


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
    unchanged: the logic was already correct, and it already posted through
    the provider-neutral billing.payment.mpesa source key (that key did not
    change here). What changed is the notification body's fallback for a
    missing receipt, which no longer uses an em dash.
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

    # THE guard this function shipped without. amount_paid + amount must
    # never exceed total_amount: two independent, genuinely verified
    # settlements against the same invoice (two real receipts, so the
    # receipt-keyed replay check above never fires for either) previously
    # had nothing stopping the second from driving the balance negative-
    # equivalent (amount_paid > total_amount) while the invoice quietly
    # stayed "Paid". Quarantine, do not raise a plain rejection: the money
    # already reached Safaricom by the time any caller gets here, so
    # losing track of it is the actual failure mode, not the settlement
    # itself. See SettlementExceedsBalance's own docstring.
    balance = (invoice.total_amount or Decimal(0)) - (invoice.amount_paid or Decimal(0))
    if amount > balance:
        raise SettlementExceedsBalance(
            f"settlement of KES {amount} exceeds outstanding balance KES {balance} "
            f"on invoice {invoice.invoice_id}; money received but NOT credited, "
            "needs manual review"
        )

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
                f"({'paid in full' if fully_paid else 'partial'}), "
                f"receipt {txn.receipt_number or 'not recorded'}"
            ),
            link="/app/billing",
            category="success",
        )
    except Exception:  # noqa: BLE001, notification must never break settlement
        logger.warning("settle_invoice_match: notify failed", exc_info=True)

    return payment
