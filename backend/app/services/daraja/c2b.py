"""C2B: the flow where a patient walks up and pays the hospital's till
directly, rather than being sent an STK prompt.

**Why this is the most dangerous flow in the migration.** Every other
settlement path in this codebase has a prior record to check an unsigned
callback against: an STK callback must match a Pending row WE created, and
its claimed amount is compared to the amount WE requested. C2B has no such
anchor by definition. The customer just walked up and paid; there is nothing
local to compare a confirmation against.

**Verification, and settlement with it, is DEFERRED.** An earlier version of
this module called a "verify_receipt" helper inline, inside
handle_confirmation, and settled immediately if it returned True. That was
wrong: Safaricom's Transaction Status query is asynchronous, its synchronous
response is only an acknowledgment, and the actual verdict arrives later, on
a separate result callback. Treating the acknowledgment as a verdict verified
nothing at all. So the real flow is:

  1. handle_confirmation records the payment Unverified and posts NOTHING:
     no Payment, no ledger entry, no invoice credit. It fires a Transaction
     Status query for the receipt and stores the ConversationID and
     OriginatorConversationID Safaricom hands back, so the later result can
     find its way back to this row.
  2. handle_transaction_status_result is what Safaricom's result callback
     reaches, at a NEW endpoint the callback URL for the query points at.
     It correlates by ConversationID against a row THIS tenant created,
     compares the amount Safaricom reports against the amount the
     confirmation claimed, and is the ONLY place that decides: match,
     settle via the existing settle_invoice_match, and mark Success; or a
     mismatch, quarantine, notify, and settle nothing.
  3. handle_transaction_status_timeout decides NOTHING. A timeout means
     Safaricom gave up waiting on the query, not that the money is not
     real; the row stays Unverified.
  4. If no result and no timeout ever arrive, the row stays Unverified
     forever, on the unmatched queue for a human. No local timer resolves
     it: this branch already deleted exactly that pattern from the STK
     reservation path (see reservation.py's docstring) for causing silent
     money loss, and the same reasoning applies here.

**Validation vs confirmation.** Safaricom enables the Validation URL only on
request; until a hospital asks for that, only Confirmation ever fires, for
an already-completed payment. handle_validation must therefore be safe to
call in both worlds: it never assumes it ran, and handle_confirmation never
assumes it did not. Validation only gets to make a real decision here
(accept/decline the payment before it completes) because TransID is not yet
issued at that point, so it can only sanity-check the shortcode and amount,
never verify a receipt that does not exist yet.

**Match order**, tried only once a Transaction Status result has actually
corroborated a receipt, in the order this module tries them, and nothing is
guessed: the PayBill account number the customer typed (BillRefNumber) as
either a bare invoice id or an "INV-" prefixed one; then an OPD number
(Patient.outpatient_no); then the paying phone number. Anything that matches
none of the three is recorded verified but unmatched, and left for a human:
a wrong guess posts real money against the wrong patient's invoice, which is
worse than doing nothing.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.services.daraja.c2b_match import match_c2b_invoice
from app.services.daraja.client import DarajaError
from app.services.daraja.credentials import normalize_msisdn
from app.services.daraja.settlement import _notify_quarantine, settle_invoice_match
from app.services.daraja.status import (
    _base_hint_token,
    _daraja_client,
    _result_parameters,
    query_transaction_status,
)
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)


# ─── Till registration ──────────────────────────────────────────────────────


def _verification_ready(config: MpesaConfig) -> bool:
    """True only when a Transaction Status query can actually be SIGNED for
    this till: both initiator fields must be set. Safaricom's
    /mpesa/c2b/v1/registerurl endpoint neither needs nor validates initiator
    credentials, so registration succeeding says nothing about whether a
    payment on this till can ever be verified; this is the separate check
    that closes that gap. Shared by register_c2b_urls and c2b_readiness so
    the two can never disagree about what "ready" means.
    """
    return bool(config.initiator_name) and bool(config.initiator_password_encrypted)


def register_c2b_urls(db: Session, *, callback_tenant: Optional[str] = None) -> dict:
    """Register the Confirmation and Validation URLs for EVERY active till in
    this tenant, not once per tenant. With per-department tills, each config
    row owns its own shortcode and its own callback token, so each one must
    register its own pair of URLs against Safaricom; nothing is shared.

    Records c2b_urls_registered_at per config on success. A failure on one
    config does not stop the others: an operator adding a fifth department
    till should not be blocked by an unrelated fourth till's bad credentials.

    Registers a till REGARDLESS of whether it has initiator credentials:
    Safaricom's registerurl call does not need them and does not check for
    them, so refusing to register without them would only make the
    problem harder to see, not solve it. Instead each result carries
    verification_ready, so the admin surface that calls this can stop
    claiming setup is "complete" the moment registration succeeds, when in
    fact a till with no initiator credentials can be registered, take real
    money, and never verify or settle a single payment: the only trace
    left is a receipt on the unmatched queue with a result_desc explaining
    why (see handle_confirmation's credential-failure handling).
    """
    configs = db.query(MpesaConfig).filter(MpesaConfig.is_active == True).all()  # noqa: E712
    results = []
    for config in configs:
        try:
            base, hint, token = _base_hint_token(config, callback_tenant)
            confirmation_url = f"{base}/api/payments/mpesa/c2b/confirmation/{hint}/{token}"
            validation_url = f"{base}/api/payments/mpesa/c2b/validation/{hint}/{token}"
            payload = {
                "ShortCode": config.shortcode,
                "ResponseType": "Completed",
                "ConfirmationURL": confirmation_url,
                "ValidationURL": validation_url,
            }
            client = _daraja_client(config)
            data = client.post("/mpesa/c2b/v1/registerurl", payload)
        except (DarajaError, HTTPException) as exc:
            logger.warning(
                "C2B URL registration failed for config %s: %s", config.id, safe_repr(str(exc))
            )
            results.append({
                "config_id": config.id,
                "shortcode": config.shortcode,
                "registered": False,
                "verification_ready": _verification_ready(config),
            })
            continue

        config.c2b_urls_registered_at = datetime.now(timezone.utc)
        results.append({
            "config_id": config.id,
            "shortcode": config.shortcode,
            "registered": True,
            "verification_ready": _verification_ready(config),
            "response_description": data.get("ResponseDescription"),
        })

    db.commit()
    return {"results": results}


def c2b_readiness(db: Session) -> list[dict]:
    """Per-till C2B readiness: registered-with-Safaricom status alongside
    verification_ready, for a health panel (or any other operator-facing
    surface) to report an ACTIVE till that has C2B registered and shows
    green, but has no initiator credentials and so can never verify a
    payment it receives. This is a pure read, unlike register_c2b_urls: it
    never calls Safaricom and never writes anything, so it can be polled
    freely without re-registering URLs or risking a rate limit.
    """
    configs = db.query(MpesaConfig).filter(MpesaConfig.is_active == True).all()  # noqa: E712
    return [
        {
            "config_id": config.id,
            "shortcode": config.shortcode,
            "department_id": config.department_id,
            "c2b_urls_registered_at": config.c2b_urls_registered_at,
            "verification_ready": _verification_ready(config),
        }
        for config in configs
    ]


# ─── Validation ─────────────────────────────────────────────────────────────


def handle_validation(db: Session, payload: dict) -> bool:
    """True to accept the payment at the till, False to decline it.

    Only ever called if a hospital asked Safaricom to enable the Validation
    URL; if not, Safaricom skips straight to Confirmation and this function
    is simply never invoked. Either way the behaviour here must be correct
    on its own: no state elsewhere depends on validation having run.

    This is the one Daraja path where a rejection reaches a real patient
    standing at a counter, so it fails toward ACCEPT on anything it cannot
    be certain is wrong, and only ever declines a genuinely malformed
    amount:

    - An unknown or inactive shortcode is NOT declined. Safaricom only ever
      calls the URL we ourselves registered for a specific till's own
      shortcode, so reaching this function with a shortcode that matches no
      active till means OUR configuration drifted (a till deactivated
      after registering its URLs, a shortcode edited without
      re-registering), not that the payment is illegitimate. Confirmation
      plus the Transaction Status cross-check downstream is already the
      gate that stops unverified money from posting to an invoice; it
      costs nothing to accept here and let that gate do its job, and it
      costs a real patient their payment to decline.
    - A database error looking up the config is likewise not a decline: no
      route exists yet to decide what an exception here should become, so
      guarding it explicitly here and accepting is the only choice that
      does not leave that decision to code that has not been written.

    TransID does not exist yet at validation time (the payment has not
    completed), so there is no receipt to verify and nothing to match
    against an invoice yet; that all happens at confirmation.

    NOTE for the go-live smoke test: shortcode_type (paybill vs till) is
    never consulted here, and for a Buy Goods till the shortcode Safaricom
    includes in a C2B payload may not be the exact one registration used.
    Flagged rather than guessed at: a real Buy Goods validation payload
    from sandbox or production is what will show whether this needs to
    widen, not speculation now.
    """
    try:
        amount = Decimal(str(payload.get("TransAmount")))
    except (InvalidOperation, ValueError, TypeError):
        return False
    if amount <= 0:
        return False

    shortcode = str(payload.get("BusinessShortCode") or "").strip()
    try:
        config = (
            db.query(MpesaConfig)
            .filter(MpesaConfig.shortcode == shortcode, MpesaConfig.is_active == True)  # noqa: E712
            .first()
        )
    except Exception:  # noqa: BLE001, see the docstring: a lookup failure must accept, not decline
        logger.warning(
            "C2B validation: config lookup failed for shortcode %s; accepting by default",
            safe_repr(shortcode), exc_info=True,
        )
        return True

    if config is None:
        logger.warning(
            "C2B validation for shortcode %s matches no active till in this tenant; "
            "accepting anyway (see handle_validation's docstring)",
            safe_repr(shortcode),
        )
    return True


# ─── Matching ───────────────────────────────────────────────────────────────
# Moved to c2b_match.py (Task 6 fix round 2, pure move, no behaviour change)
# purely to keep this file under the project's ~500 line preference.
# match_c2b_invoice is imported here so every existing caller (including
# this module's own handle_transaction_status_result) and every existing
# test import path keeps working unchanged.


# ─── Confirmation ───────────────────────────────────────────────────────────


def handle_confirmation(
    db: Session, payload: dict, *, callback_tenant: Optional[str] = None
) -> MpesaTransaction:
    """Record a completed C2B payment and fire off its Transaction Status
    verification. Never settles anything itself. Always returns a row:
    unlike an STK callback (which can be for a prompt we never sent, and is
    safely ignored), a C2B confirmation is always real money that reached
    this hospital's till and must be on the books somewhere, verified or
    not, matched or not.

    Order of operations:
      1. Parse TransID/TransAmount/BusinessShortCode/BillRefNumber/MSISDN.
      2. A receipt already recorded: return it, this is a replay. The query
         is not re-fired; the earlier delivery already fired it.
      3. Create the row, status Unverified. No Payment, no ledger entry, no
         invoice credit happens here or ever will from this function.
      4. Fire a Transaction Status query for the receipt and store the
         ConversationID/OriginatorConversationID it hands back. That is ALL
         this does with Safaricom's response: it is an acknowledgment, not
         a verdict (see the module docstring). The row stays Unverified.

    handle_transaction_status_result is what later decides settle,
    quarantine, or leave unverified, when (if) Safaricom's real answer
    arrives.
    """
    receipt = str(payload.get("TransID") or "").strip()
    if not receipt:
        # A genuine Confirmation always carries a receipt; only Validation
        # can arrive with one blank, before the payment has completed. There
        # is nothing to key a record on, so refuse rather than fabricate one.
        raise HTTPException(status_code=400, detail="C2B confirmation missing TransID.")

    try:
        amount = Decimal(str(payload.get("TransAmount")))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="C2B confirmation has an unparseable amount.")

    shortcode = str(payload.get("BusinessShortCode") or "").strip()
    bill_ref = str(payload.get("BillRefNumber") or "").strip() or None

    raw_msisdn = str(payload.get("MSISDN") or "").strip()
    try:
        msisdn = normalize_msisdn(raw_msisdn)
    except ValueError:
        # Keep whatever Safaricom sent rather than dropping it: it still
        # identifies the payer for the record even if it cannot drive a
        # phone match.
        msisdn = raw_msisdn or None

    config = (
        db.query(MpesaConfig)
        .filter(MpesaConfig.shortcode == shortcode, MpesaConfig.is_active == True)  # noqa: E712
        .first()
    )

    # Serialise concurrent deliveries of this exact receipt (a genuine
    # Safaricom retry, or two near-simultaneous forged duplicates) before the
    # check-then-act replay lookup below, the same discipline
    # apply_stk_callback uses for the same reason: without it, two callbacks
    # can both observe "not yet recorded" and both try to insert.
    lock_id = int(hashlib.sha1(receipt.encode("utf-8")).hexdigest()[:15], 16)

    try:
        # The lock acquisition itself is inside this try/except: a failure
        # here (a poisoned session, a lost connection) must roll back the
        # same way a failure anywhere else in this unit does, rather than
        # leaving the session in an unrolled-back state for whatever caller
        # happens to reuse it next.
        db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

        existing = (
            db.query(MpesaTransaction)
            .filter(MpesaTransaction.receipt_number == receipt)
            .first()
        )
        if existing is not None:
            db.commit()  # releases the advisory lock; nothing else to do
            return existing

        txn = MpesaTransaction(
            phone_number=msisdn or "unknown",
            amount=amount,
            receipt_number=receipt,
            status="Unverified",
            transaction_type="C2B",
            bill_ref_number=bill_ref,
            mpesa_config_id=config.id if config is not None else None,
        )
        db.add(txn)
        db.flush()

        if config is None:
            # No till in this tenant claims this shortcode: there is no
            # config to sign a Transaction Status request with. The money
            # still happened, so the row stays on record, unverified, for a
            # human to reconcile.
            logger.warning(
                "C2B confirmation for shortcode %s matches no active till in this tenant",
                safe_repr(shortcode),
            )
            db.commit()
            return txn

        # Fire the query and record what Safaricom handed back. This is an
        # acknowledgment, never a verdict: nothing here sets verified_at,
        # attempts a match, or touches an invoice. The row stays Unverified
        # regardless of what this call returns, including if it fails
        # outright: a network hiccup submitting the query is not a reason
        # to lose the record of money that already reached the till.
        try:
            ack = query_transaction_status(db, receipt=receipt, callback_tenant=callback_tenant)
        except (DarajaError, HTTPException) as exc:
            logger.warning(
                "C2B Transaction Status query failed for receipt %s: %s",
                safe_repr(receipt), safe_repr(str(exc)),
            )
            # A cashier reading the unmatched queue cannot see this log line.
            # The most common cause here is a till missing its initiator
            # credentials (register_c2b_urls happily registers a till that
            # can never verify a payment; see its own docstring), and
            # without this the only clue a hospital gets is a receipt with
            # no explanation at all. Both an HTTPException.detail from this
            # module's own credential checks and a DarajaError's message are
            # already written to be safe to display: neither ever carries a
            # secret.
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            txn.result_desc = str(detail)[:255]
            ack = None

        if ack is not None:
            txn.conversation_id = ack.get("ConversationID")
            txn.originator_conversation_id = ack.get("OriginatorConversationID")

        db.commit()
        return txn
    except Exception:
        db.rollback()
        raise


# ─── Transaction Status result (the actual verdict) ─────────────────────────


def handle_transaction_status_result(db: Session, payload: dict) -> Optional[MpesaTransaction]:
    """Apply Safaricom's asynchronous Transaction Status result: the real
    verdict on a C2B receipt, arriving separately from (and generally much
    later than) the acknowledgment query_transaction_status received when
    handle_confirmation fired the query. This IS the third defence C2B
    relies on, since the confirmation itself carried no anchor to check
    against; nothing here is guessed.

    Correlated by ConversationID against a row THIS tenant created and is
    still waiting on (status == "Unverified"). A ConversationID matching no
    such row, whether a forged value, one for another deployment, or a
    repeat delivery of a result already applied, is ignored, never acted
    on: Safaricom retries deliveries the same way it does for every other
    callback, and a second delivery of an already-settled result must not
    settle twice or overturn a decision already made.

    Amount comparison is the whole point: matching settles via the existing
    settle_invoice_match, exactly as any other verified receipt would.
    A mismatch quarantines and notifies, and settles nothing: Safaricom's
    own Transaction Status disagreeing with what the confirmation claimed is
    precisely the forged-or-malformed-callback shape this flow exists to
    catch.
    """
    result = (payload or {}).get("Result") or {}
    conversation_id = result.get("ConversationID")
    if not conversation_id:
        logger.warning("Transaction Status result missing ConversationID; ignored")
        return None

    txn = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.conversation_id == conversation_id,
            MpesaTransaction.status == "Unverified",
        )
        .first()
    )
    if txn is None:
        logger.warning(
            "Transaction Status result for an unrecognised or "
            "already-resolved ConversationID; ignored"
        )
        return None

    # Serialise concurrent deliveries of this exact result before acting on
    # it, the same discipline apply_stk_callback and handle_confirmation
    # both use: without it, two near-simultaneous deliveries could both
    # observe status == "Unverified" and both try to settle.
    lock_id = int(hashlib.sha1(conversation_id.encode("utf-8")).hexdigest()[:15], 16)
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
        # Re-check inside the lock: a concurrent delivery could have
        # resolved this row between the query above and the lock being
        # granted.
        db.refresh(txn)
        if txn.status != "Unverified":
            db.commit()
            return txn

        result_code = result.get("ResultCode")
        if str(result_code) != "0":
            # Safaricom itself does not confirm this receipt (not found, or
            # an error on Safaricom's side). This is the same resting state
            # as no result ever arriving: stays Unverified, not a rejection
            # to act on.
            txn.result_desc = str(result.get("ResultDesc") or "")[:255]
            db.commit()
            return txn

        params = _result_parameters(result)

        # I3: ResultCode 0 only means the QUERY succeeded, not that the
        # transaction itself did. The transaction's own outcome lives in
        # TransactionStatus. A receipt Safaricom knows about but marks
        # Failed or Reversed must never settle just because the query
        # worked; anything other than Completed is quarantined, the same
        # as a disagreeing amount, because a "successful-looking" query
        # result for a transaction Safaricom itself did not complete is
        # exactly the kind of thing a human needs to see, not silently
        # leave Unverified.
        transaction_status = params.get("TransactionStatus")
        if transaction_status != "Completed":
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported status {transaction_status!r}, not Completed"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        # C1: Safaricom's key names for the amount and the receipt are not
        # settled between documentation sources (Amount vs TransactionAmount,
        # ReceiptNo vs TransactionReceipt); public sources disagree and the
        # authoritative docs need a login this task cannot obtain. Reading
        # only one spelling risks EVERY genuine result missing the field,
        # quarantining every real payment and training staff to distrust
        # (and bypass) this queue. Read whichever spelling is present.
        reported_receipt = params.get("TransactionReceipt")
        if reported_receipt is None:
            reported_receipt = params.get("ReceiptNo")
        raw_amount = params.get("TransactionAmount")
        if raw_amount is None:
            raw_amount = params.get("Amount")

        if reported_receipt is None or raw_amount is None:
            # Neither spelling was found for one of the fields. This is not
            # "the values disagree", it is "we could not find the value at
            # all": reporting a mismatch against a fabricated None would
            # read as a wrong-amount claim Safaricom never made. Naming the
            # keys that actually arrived is what turns the first real
            # sandbox delivery into a one-line answer instead of a mystery.
            missing = []
            if reported_receipt is None:
                missing.append("receipt (checked TransactionReceipt, ReceiptNo)")
            if raw_amount is None:
                missing.append("amount (checked TransactionAmount, Amount)")
            keys_present = sorted(params.keys())
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status result missing {' and '.join(missing)}; "
                f"keys present: {keys_present}"
            )[:255]
            logger.error(
                "C2B Transaction Status result for receipt %s missing expected "
                "field(s) (%s); keys present: %s",
                safe_repr(txn.receipt_number), " and ".join(missing), keys_present,
            )
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        # I2: correlate on the receipt too, not ConversationID alone.
        # conversation_id carries no unique constraint, so if two rows ever
        # shared one, settling purely by ConversationID would apply
        # Safaricom's answer to whichever row Postgres happened to return
        # first, posting real money against a different patient's invoice.
        # The receipt this query answers must be the exact one this row
        # recorded at confirmation time.
        if reported_receipt != txn.receipt_number:
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported receipt {reported_receipt}, "
                f"this row recorded {txn.receipt_number}"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        try:
            reported_amount = Decimal(str(raw_amount))
        except (InvalidOperation, ValueError, TypeError):
            txn.status = "Quarantined"
            txn.result_desc = f"Transaction Status reported an unparseable amount: {raw_amount!r}"[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        expected_amount = Decimal(str(txn.amount or 0))
        if reported_amount != expected_amount:
            # THE cross-check. Safaricom's own Transaction Status disagrees
            # with the amount the confirmation claimed: settle nothing,
            # quarantine, tell a human.
            txn.status = "Quarantined"
            txn.result_desc = (
                f"Transaction Status reported KES {reported_amount}, "
                f"confirmation claimed KES {expected_amount}"
            )[:255]
            db.commit()
            _notify_quarantine(db, txn, reason=txn.result_desc)
            return txn

        txn.verified_at = datetime.now(timezone.utc)
        txn.verification_source = "transaction_status"

        invoice, match_basis = match_c2b_invoice(
            db, bill_ref_number=txn.bill_ref_number, msisdn=txn.phone_number,
        )
        if invoice is None:
            txn.status = "Unmatched"
            txn.match_basis = "unmatched"
            db.commit()
            return txn

        invoice = (
            db.query(Invoice)
            .filter(Invoice.invoice_id == invoice.invoice_id)
            .with_for_update()
            .first()
        )
        txn.status = "Success"
        settle_invoice_match(db, invoice=invoice, txn=txn, match_basis=match_basis)

        # ONE commit for the whole verified-and-matched unit, same reasoning
        # as apply_stk_callback: if settle_invoice_match raises, nothing
        # above persists, so the row is retryable rather than stuck
        # half-applied.
        db.commit()
        return txn
    except Exception:
        db.rollback()
        raise


def handle_transaction_status_timeout(db: Session, payload: dict) -> Optional[MpesaTransaction]:
    """Acknowledge a Transaction Status timeout. Decides NOTHING: a timeout
    means Safaricom gave up waiting on the query, not that the money is not
    real. The row stays Unverified, the same resting state as if no result
    had arrived at all. A human resolves it from the unmatched queue, or a
    future reconciliation job re-fires the query; this function does
    neither, on purpose, for the same reason a local expiry timer was
    removed from the STK reservation path (reservation.py): a guessed
    outcome here is how a real payment goes missing silently.
    """
    result = (payload or {}).get("Result") or {}
    conversation_id = result.get("ConversationID")
    if not conversation_id:
        logger.warning("Transaction Status timeout missing ConversationID; ignored")
        # This function never writes, but the query above still opened a
        # transaction on this session (any SELECT does under Postgres's
        # default isolation), and nothing else here will ever end it.
        # Commit rather than leave the caller holding an idle-in-transaction
        # session.
        db.commit()
        return None

    txn = (
        db.query(MpesaTransaction)
        .filter(
            MpesaTransaction.conversation_id == conversation_id,
            MpesaTransaction.status == "Unverified",
        )
        .first()
    )
    if txn is None:
        logger.warning(
            "Transaction Status timeout for an unrecognised or "
            "already-resolved ConversationID; ignored"
        )
        db.commit()
        return None

    logger.info(
        "Transaction Status query timed out for MpesaTransaction %s; left Unverified", txn.id
    )
    db.commit()
    return txn
