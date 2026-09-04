"""Till resolution and Postgres-constraint reservation for M-Pesa pushes.

This module owns two separate concerns that both sit below stk.py's
idempotency-coupled logic, and reference nothing from app.core.idempotency
(no fingerprint, no cache, no advisory lock):

* config_for: which MpesaConfig (till) a payment should be pushed from.
* _find_pending / _reserve_pending / _PENDING_GUARD_CONSTRAINTS: the
  insert-and-catch reservation of the one Pending slot per invoice/dispense,
  enforced by a partial unique index in Postgres, not by application logic.

Moved out of stk.py (Task 14) purely to keep that file under this project's
~500 line preference; no behaviour changed in the move.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mpesa import MpesaConfig, MpesaTransaction

# The two partial unique indexes _reserve_pending is reacting to. Any OTHER
# IntegrityError (an unknown invoice_id violating the FK, a NOT NULL slip,
# a totally unrelated constraint) must never be silently treated as "someone
# else already has this slot": that swallows a real bug behind a 409 that
# can never succeed on retry. See _reserve_pending.
_PENDING_GUARD_CONSTRAINTS = frozenset({
    "uq_mpesa_txn_one_pending_per_invoice",
    "uq_mpesa_txn_one_pending_per_dispense",
})


def config_for(db: Session, *, department_id: Optional[int] = None) -> MpesaConfig:
    """The till that should take this payment.

    Resolution order: the department's own active row when one exists,
    otherwise the hospital-wide default (department_id IS NULL), otherwise
    the "not configured" error. Every STK/query/settlement path that needs
    a MpesaConfig must call this, not query MpesaConfig directly, so a
    later change to how a config is chosen only has to change here.

    An INACTIVE department row falls back to the default rather than
    raising: a department that switches its till off should keep
    collecting through the hospital till, not stop collecting.

    Caveat this does NOT cover: deactivating a department's config does
    not retroactively help a push already sent from it. Each config's
    callback is authenticated by that config's OWN token, and
    app/core/daraja_callback.py's _lookup_token_in_tenant requires
    is_active=True on the matching row; it never falls back to the
    hospital default the way config_for does. So a prompt already on a
    patient's handset, sent from a till that is deactivated before the
    callback arrives, has its callback rejected as unauthenticated, not
    routed to the default. This function's fallback only ever applies to a
    NEW push, never to settling one already in flight.
    """
    if department_id is not None:
        dept_config = (
            db.query(MpesaConfig)
            .filter(
                MpesaConfig.department_id == department_id,
                MpesaConfig.is_active == True,  # noqa: E712
            )
            .first()
        )
        if dept_config:
            return dept_config

    default_config = (
        db.query(MpesaConfig)
        .filter(
            MpesaConfig.department_id.is_(None),
            MpesaConfig.is_active == True,  # noqa: E712
        )
        .first()
    )
    if default_config:
        return default_config

    raise HTTPException(
        status_code=400,
        detail="M-Pesa is not configured for this hospital. Set it up under Settings -> M-Pesa.",
    )


def _find_pending(
    db: Session, *, invoice_id: Optional[int], dispense_id: Optional[int]
) -> Optional[MpesaTransaction]:
    """The live Pending row (if any) blocking a reservation for this
    invoice/dispense. At most one can exist by construction of the partial
    unique index this function's caller is reacting to.

    Matches on invoice_id OR dispense_id, not just whichever is checked
    first: a row carrying both is blocked by either partial index, and a
    conflict on one must still be found by a caller that only supplied
    the other.
    """
    conditions = []
    if invoice_id is not None:
        conditions.append(MpesaTransaction.invoice_id == invoice_id)
    if dispense_id is not None:
        conditions.append(MpesaTransaction.dispense_id == dispense_id)
    if not conditions:
        return None
    return (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.status == "Pending")
        .filter(or_(*conditions))
        .first()
    )


def _reserve_pending(
    db: Session,
    *,
    invoice_id: Optional[int],
    dispense_id: Optional[int],
    phone_number: str,
    charged_amount: Decimal,
    external_reference: str,
    bill_ref_number: str,
    config: MpesaConfig,
) -> tuple[Optional[MpesaTransaction], bool]:
    """Reserve the one Pending slot for this invoice/dispense.

    Insert-and-catch, never check-then-insert: a check-then-insert has a gap
    between the check and the insert, which is the precise race this exists
    to close. The partial unique index on mpesa_transactions is what
    actually enforces "at most one Pending row per invoice/dispense" across
    every worker and every terminal; this function only reacts to it.

    Returns (txn, reserved). reserved=True means the caller owns a fresh
    Pending row and should go ahead and push to Daraja. reserved=False means
    a DIFFERENT, still-live Pending transaction already exists for this
    invoice/dispense: txn is that transaction, and the caller must not push
    a second prompt to the patient's handset.

    There is deliberately NO local staleness timer here any more. An
    earlier version aged a Pending row out to a manufactured "Expired"
    status so a retry was never blocked; that is a guess about the
    original push's outcome, and apply_stk_callback only ever matches
    status == "Pending", so a late genuine success callback for an
    "Expired" row fell into the unrecognised branch and settled nothing:
    money reached the till and the invoice was never credited. A stale
    Pending now correctly BLOCKS a retry (the caller is told a prompt is
    already on its way, which is true) until Task 8's reconciliation job
    resolves it by asking Safaricom via STK Query, never by guessing here.

    CONTRACT the caller must know: when this returns reserved=True, it has
    ALREADY COMMITTED `db` (see the comment at that call site for why:
    responsiveness against a second terminal, not correctness of the guard
    itself), ending whatever transaction was open when this was called,
    including releasing any Postgres advisory lock taken inside it. The
    caller resumes in a new transaction. When it returns reserved=False,
    no commit happens: the only DB effect was an insert attempt rolled
    back to a SAVEPOINT, so the caller's transaction (and any lock it
    holds) is untouched.

    Only the two partial unique indexes this guard owns are treated as
    "someone else already has this slot". Any other IntegrityError (an
    unknown invoice_id violating its FK, for example) is re-raised: a 409
    "try again" for a request that can never succeed is worse than the raw
    error.
    """
    txn = MpesaTransaction(
        invoice_id=invoice_id,
        dispense_id=dispense_id,
        phone_number=phone_number,
        amount=charged_amount,
        external_reference=external_reference,
        status="Pending",
        transaction_type="STK",
        bill_ref_number=bill_ref_number,
        mpesa_config_id=config.id,
    )
    try:
        with db.begin_nested():
            db.add(txn)
            db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint not in _PENDING_GUARD_CONSTRAINTS:
            raise
        existing = _find_pending(db, invoice_id=invoice_id, dispense_id=dispense_id)
        return existing, False
    else:
        # Commit NOW, before the slow Daraja network call, so a second
        # terminal hitting the same invoice/dispense gets an immediate
        # constraint violation instead of blocking on our uncommitted
        # row for however long Safaricom takes to answer.
        db.commit()
        return txn, True
