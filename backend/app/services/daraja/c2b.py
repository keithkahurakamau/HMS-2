"""C2B: the flow where a patient walks up and pays the hospital's till
directly, rather than being sent an STK prompt.

**Why this is the most dangerous flow in the migration.** Every other
settlement path in this codebase has a prior record to check an unsigned
callback against: an STK callback must match a Pending row WE created, and
its claimed amount is compared to the amount WE requested. C2B has no such
anchor by definition. The customer just walked up and paid; there is nothing
local to compare a confirmation against. So handle_confirmation's third
defence is different: verify_receipt (app/services/daraja/status.py) asks
Safaricom's Transaction Status API directly, for the exact receipt the
confirmation claims, and REQUIRES both that Safaricom knows it and that the
amount matches, before anything is posted to the ledger. An unverified
receipt is recorded, shown on the unmatched/unverified queue for a human, and
settles nothing. See test_c2b.py's first test for the property this exists
to prove.

**Validation vs confirmation.** Safaricom enables the Validation URL only on
request; until a hospital asks for that, only Confirmation ever fires, for
an already-completed payment. handle_validation must therefore be safe to
call in both worlds: it never assumes it ran, and handle_confirmation never
assumes it did not. Validation only gets to make a real decision here
(accept/decline the payment before it completes) because TransID is not yet
issued at that point, so it can only sanity-check the shortcode and amount,
never verify a receipt that does not exist yet.

**Match order for a confirmation**, in the order this module tries them, and
nothing is guessed: the PayBill account number the customer typed
(BillRefNumber) as either a bare invoice id or an "INV-" prefixed one; then
an OPD number (Patient.outpatient_no); then the paying phone number. Anything
that matches none of the three is recorded verified but unmatched, and left
for a human: a wrong guess posts real money against the wrong patient's
invoice, which is worse than doing nothing.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaTransaction
from app.models.patient import Patient
from app.services.daraja.client import DarajaError
from app.services.daraja.credentials import normalize_msisdn
from app.services.daraja.settlement import settle_invoice_match
from app.services.daraja.status import _base_hint_token, _daraja_client, verify_receipt
from app.utils.blind_index import phone_bidx
from app.utils.log_redact import safe_repr

logger = logging.getLogger(__name__)

# A bare invoice id, optionally "INV-" prefixed, case-insensitive. Anything
# else (an OPD number containing letters, a name, garbage a customer typed)
# does not match here at all: stripping non-digit characters out of an
# arbitrary string and treating what's left as an invoice id would risk
# matching an unrelated invoice by coincidence, which is exactly the kind of
# guess this module exists to refuse.
_INVOICE_REF_RE = re.compile(r"^(?:INV-)?(\d+)$", re.IGNORECASE)

_OUTSTANDING_STATUSES = ("Pending", "Partially Paid")


# ─── Till registration ──────────────────────────────────────────────────────


def register_c2b_urls(db: Session, *, callback_tenant: Optional[str] = None) -> dict:
    """Register the Confirmation and Validation URLs for EVERY active till in
    this tenant, not once per tenant. With per-department tills, each config
    row owns its own shortcode and its own callback token, so each one must
    register its own pair of URLs against Safaricom; nothing is shared.

    Records c2b_urls_registered_at per config on success. A failure on one
    config does not stop the others: an operator adding a fifth department
    till should not be blocked by an unrelated fourth till's bad credentials.
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
            results.append({"config_id": config.id, "shortcode": config.shortcode, "registered": False})
            continue

        config.c2b_urls_registered_at = datetime.now(timezone.utc)
        results.append({
            "config_id": config.id,
            "shortcode": config.shortcode,
            "registered": True,
            "response_description": data.get("ResponseDescription"),
        })

    db.commit()
    return {"results": results}


# ─── Validation ─────────────────────────────────────────────────────────────


def handle_validation(db: Session, payload: dict) -> bool:
    """True to accept the payment at the till, False to decline it.

    Only ever called if a hospital asked Safaricom to enable the Validation
    URL; if not, Safaricom skips straight to Confirmation and this function
    is simply never invoked. Either way the behaviour here must be correct
    on its own: no state elsewhere depends on validation having run.

    Deliberately shallow. TransID does not exist yet at validation time (the
    payment has not completed), so there is no receipt to verify and nothing
    to match against an invoice yet; that all happens at confirmation. This
    only rejects what can be known to be wrong right now: an amount that
    is not a positive number, or a shortcode that does not belong to any
    active till in this tenant.
    """
    try:
        amount = Decimal(str(payload.get("TransAmount")))
    except (InvalidOperation, ValueError, TypeError):
        return False
    if amount <= 0:
        return False

    shortcode = str(payload.get("BusinessShortCode") or "").strip()
    if not shortcode:
        return False

    config = (
        db.query(MpesaConfig)
        .filter(MpesaConfig.shortcode == shortcode, MpesaConfig.is_active == True)  # noqa: E712
        .first()
    )
    return config is not None


# ─── Matching ───────────────────────────────────────────────────────────────


def _outstanding_invoice_for_patient(db: Session, patient_id: int) -> Optional[Invoice]:
    return (
        db.query(Invoice)
        .filter(Invoice.patient_id == patient_id, Invoice.status.in_(_OUTSTANDING_STATUSES))
        .order_by(Invoice.billing_date.desc())
        .first()
    )


def _match_by_bill_ref(db: Session, bill_ref: Optional[str]) -> Optional[Invoice]:
    if not bill_ref:
        return None
    match = _INVOICE_REF_RE.match(bill_ref.strip())
    if not match:
        return None
    return db.query(Invoice).filter(Invoice.invoice_id == int(match.group(1))).first()


def _match_by_opd_number(db: Session, bill_ref: Optional[str]) -> Optional[Invoice]:
    if not bill_ref:
        return None
    patient = db.query(Patient).filter(Patient.outpatient_no == bill_ref.strip()).first()
    if patient is None:
        return None
    return _outstanding_invoice_for_patient(db, patient.patient_id)


def _match_by_phone(db: Session, msisdn: Optional[str]) -> Optional[Invoice]:
    if not msisdn:
        return None
    # A patient's phone may be stored in local (0-prefixed) or MSISDN
    # (254-prefixed) form; phone_bidx hashes whatever digit string it is
    # given, so both candidate forms are checked rather than assuming the
    # patient record and the C2B payload happen to agree on format.
    candidates = {msisdn}
    if msisdn.startswith("254") and len(msisdn) == 12:
        candidates.add("0" + msisdn[3:])
    hashes = {h for h in (phone_bidx(c) for c in candidates) if h}
    if not hashes:
        return None
    patient = db.query(Patient).filter(Patient.telephone_1_bidx.in_(hashes)).first()
    if patient is None:
        return None
    return _outstanding_invoice_for_patient(db, patient.patient_id)


def match_c2b_invoice(
    db: Session, *, bill_ref_number: Optional[str], msisdn: Optional[str]
) -> tuple[Optional[Invoice], str]:
    """(invoice, match_basis) for a verified C2B receipt, trying each basis
    in order and stopping at the first hit. Returns (None, "unmatched") when
    none apply: the caller must never fall back to a guess."""
    invoice = _match_by_bill_ref(db, bill_ref_number)
    if invoice is not None:
        return invoice, "bill_ref_number"

    invoice = _match_by_opd_number(db, bill_ref_number)
    if invoice is not None:
        return invoice, "opd_number"

    invoice = _match_by_phone(db, msisdn)
    if invoice is not None:
        return invoice, "phone"

    return None, "unmatched"


# ─── Confirmation ───────────────────────────────────────────────────────────


def handle_confirmation(
    db: Session, payload: dict, *, callback_tenant: Optional[str] = None
) -> MpesaTransaction:
    """Record a completed C2B payment, verify it with Safaricom, then match
    and settle it. Always returns a row: unlike an STK callback (which can
    be for a prompt we never sent, and is safely ignored), a C2B confirmation
    is always real money that reached this hospital's till and must be on
    the books somewhere, verified or not, matched or not.

    Order of operations:
      1. Parse TransID/TransAmount/BusinessShortCode/BillRefNumber/MSISDN.
      2. A receipt already recorded: return it, this is a replay.
      3. Create the row, status Unverified.
      4. verify_receipt against Safaricom. Not verified: stop here, status
         stays Unverified, nothing is matched or settled.
      5. Verified: match_c2b_invoice in the documented order. No match:
         status Unmatched, nothing settled.
      6. Matched: settle_invoice_match, status Success.
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
    db.execute(text("SELECT pg_advisory_xact_lock(:lid)"), {"lid": lock_id})

    try:
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
            # No till in this tenant claims this shortcode: verify_receipt
            # cannot even build a request without a config's credentials.
            # The money still happened, so the row stays on record,
            # unverified, for a human to reconcile.
            logger.warning(
                "C2B confirmation for shortcode %s matches no active till in this tenant",
                safe_repr(shortcode),
            )
            db.commit()
            return txn

        verified = verify_receipt(db, txn=txn, callback_tenant=callback_tenant)
        if not verified:
            # Unverified: this is the property the whole module exists to
            # enforce. Nothing below this line runs. No match is attempted,
            # no Payment is created, no invoice is touched.
            db.commit()
            return txn

        txn.verified_at = datetime.now(timezone.utc)
        txn.verification_source = "transaction_status"

        invoice, match_basis = match_c2b_invoice(db, bill_ref_number=bill_ref, msisdn=msisdn)
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
        # above persists, so the transaction is retryable rather than stuck
        # half-applied.
        db.commit()
        return txn
    except Exception:
        db.rollback()
        raise
