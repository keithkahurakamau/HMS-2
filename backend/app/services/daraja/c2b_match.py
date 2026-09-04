"""Invoice matching for a verified C2B receipt.

Split out of c2b.py (Task 6 fix round 2) purely to keep that file under
this project's ~500 line preference; no behaviour changed in the move. See
c2b.py's module docstring for the match order this implements and why it
matters: a wrong guess here posts real money against the wrong patient's
invoice, so nothing here ever falls back to a guess.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing import Invoice
from app.models.patient import Patient
from app.utils.blind_index import phone_bidx

# A bare invoice id, optionally "INV-" prefixed, case-insensitive. Anything
# else (an OPD number containing letters, a name, garbage a customer typed)
# does not match here at all: stripping non-digit characters out of an
# arbitrary string and treating what's left as an invoice id would risk
# matching an unrelated invoice by coincidence, which is exactly the kind of
# guess this module exists to refuse.
#
# This relies on OP numbers never satisfying this pattern: they are minted
# by routes/patients.py as "OP-{year}-{nnnn}" (a literal "OP-", not "INV-",
# with a hyphen still inside the numeric tail), which the regex's anchored
# ^...$ and optional-"INV-"-only prefix can never match. If that generation
# format ever changes, this invariant needs re-checking.
_INVOICE_REF_RE = re.compile(r"^(?:INV-)?(\d+)$", re.IGNORECASE)

_OUTSTANDING_STATUSES = ("Pending", "Partially Paid")


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
    # Same status filter as the OPD and phone matchers, not "any invoice with
    # this id": Cancelled means voided with the ledger posting reversed in
    # this codebase, and a fully Paid invoice needs no further payment
    # either. Without this, a patient typing an old or voided invoice number
    # at the till gets real money posted against it, and settle_invoice_match
    # then marks a voided invoice Paid again, resurrecting it.
    return (
        db.query(Invoice)
        .filter(
            Invoice.invoice_id == int(match.group(1)),
            Invoice.status.in_(_OUTSTANDING_STATUSES),
        )
        .first()
    )


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
