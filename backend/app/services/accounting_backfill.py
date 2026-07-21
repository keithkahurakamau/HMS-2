"""
Historical ledger backfill — "see every transaction that ever happened".

The live auto-poster (``accounting_posting.post_from_event``) only records
events that occur *after* the tenant's go-live date and while a ledger mapping
exists. Transactions that predate go-live — or that happened before the
accounting module was switched on — never reached the journal, so they don't
show up in the Transaction Log.

This module replays the source tables into the ledger:

  * **Idempotent.** Every pass reuses ``post_from_event``'s
    ``(source_type, source_id)`` idempotency, keyed *exactly* the way the live
    call site keys it. Re-running never double-posts, and entries already
    written live are left untouched.
  * **Go-live blind.** Passes call ``post_from_event(ignore_go_live=True)`` so
    pre-cutover history is included.
  * **Double-count safe.** A single ``payments`` row can map to different
    source keys depending on how it was created (cheque clearance keys on
    ``cheque_id``, Pay Hero keys on the txn id, deposit applications key on the
    application's payment). The ``payments`` pass therefore *skips* rows owned
    by another pass, and each entity table is replayed under its own key.
  * **Non-fatal per source.** A missing optional table (a tenant without the
    Pay Hero or cheque module) is caught so the rest of the backfill still runs.

The orchestrator returns a per-source ``{posted, skipped, errors}`` summary.
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.billing import Payment, Invoice, InvoiceItem
from app.models.inventory import DispenseLog, InventoryItem
from app.models.accounting import ClaimSchedule, ClientDeposit
from app.services.accounting_posting import post_from_event, payment_method_to_key

LOG = logging.getLogger(__name__)


def _as_date(value) -> Optional[_date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _tally() -> dict:
    return {"posted": 0, "skipped": 0}


def _bump(stats: dict, entry) -> None:
    # post_from_event returns the entry on a fresh post / idempotent hit, or
    # None when it deliberately skipped (no mapping, zero amount, …). We can't
    # tell a fresh post from an idempotent hit here, and that's fine — the
    # caller cares about "did this land in the ledger" (posted) vs "nothing to
    # record" (skipped).
    if entry is not None:
        stats["posted"] += 1
    else:
        stats["skipped"] += 1


# ─── Per-source passes ───────────────────────────────────────────────────────

def _payhero_receipt_refs(db: Session) -> set:
    """Transaction references of Pay Hero receipts. Payments carrying one of
    these were posted live under the Pay Hero txn id, so the payments pass must
    not re-post them under their payment_id."""
    try:
        from app.models.payhero import PayHeroTransaction
        rows = db.query(PayHeroTransaction.receipt_number).filter(
            PayHeroTransaction.receipt_number.isnot(None)
        ).all()
        return {r[0] for r in rows if r[0]}
    except Exception:  # noqa: BLE001 — tenant may not have the Pay Hero module
        return set()


def backfill_payments(db: Session, *, user_id: Optional[int] = None) -> dict:
    """``payments`` table → the payment_id-keyed postings (direct billing &
    pharmacy OTC receipts, plus deposit applications). Cheque- and Pay Hero-
    originated payments are skipped; their own passes own those keys."""
    stats = _tally()
    payhero_refs = _payhero_receipt_refs(db)
    for p in db.query(Payment).all():
        ref = p.transaction_reference or ""
        method = p.payment_method or ""
        # Owned by the cheque pass (keyed on cheque_id).
        if method.lower() == "cheque" or ref.startswith("CHQ-"):
            stats["skipped"] += 1
            continue
        # Owned by the Pay Hero pass (keyed on the txn id).
        if ref and ref in payhero_refs:
            stats["skipped"] += 1
            continue
        # Deposit application — distinct source key, still keyed on payment_id.
        if method.lower() == "deposit" or ref.startswith("DEP-"):
            source_key = "billing.deposit.applied"
        else:
            source_key = payment_method_to_key(p.payment_method)
        entry = post_from_event(
            db,
            source_key=source_key,
            source_id=p.payment_id,
            amount=p.amount,
            on_date=_as_date(p.payment_date),
            memo=f"Payment against Invoice #{p.invoice_id}",
            reference=f"INV-{p.invoice_id}",
            user_id=user_id,
            ignore_go_live=True,
        )
        _bump(stats, entry)
    return stats


def backfill_invoice_charges(db: Session, *, user_id: Optional[int] = None) -> dict:
    """Consultation + Maternity invoice items → ``billing.invoice.created``
    (keyed on the invoice-item id). Only these item types are posted live via
    this key (``charge_consultation_fee`` / ``raise_maternity_charge``);
    pharmacy revenue rides the dispense pass and other item types never post."""
    stats = _tally()
    rows = (
        db.query(InvoiceItem, Invoice.billing_date)
        .join(Invoice, Invoice.invoice_id == InvoiceItem.invoice_id)
        .filter(InvoiceItem.item_type.in_(("Consultation", "Maternity")))
        .all()
    )
    for item, billing_date in rows:
        entry = post_from_event(
            db,
            source_key="billing.invoice.created",
            source_id=item.id,
            amount=item.amount,
            on_date=_as_date(billing_date),
            memo=f"{item.description or item.item_type} · Invoice #{item.invoice_id}",
            reference=f"INV-{item.invoice_id}",
            user_id=user_id,
            ignore_go_live=True,
        )
        _bump(stats, entry)
    return stats


def backfill_dispenses(db: Session, *, user_id: Optional[int] = None) -> dict:
    """``dispense_logs`` → revenue + COGS pair (keyed on dispense_id)."""
    stats = _tally()
    rows = (
        db.query(DispenseLog, InventoryItem.unit_cost)
        .join(InventoryItem, InventoryItem.item_id == DispenseLog.item_id)
        .all()
    )
    for d, unit_cost in rows:
        on = _as_date(d.dispensed_at)
        rev = post_from_event(
            db, source_key="pharmacy.dispense.revenue", source_id=d.dispense_id,
            amount=d.total_cost, on_date=on,
            memo=f"Pharmacy dispensation #{d.dispense_id} (revenue)",
            reference=f"DISP-{d.dispense_id}", user_id=user_id, ignore_go_live=True,
        )
        _bump(stats, rev)
        cogs_amount = Decimal(str(unit_cost or 0)) * Decimal(d.quantity_dispensed or 0)
        cogs = post_from_event(
            db, source_key="pharmacy.dispense.cogs", source_id=d.dispense_id,
            amount=cogs_amount, on_date=on,
            memo=f"Pharmacy dispensation #{d.dispense_id} (COGS)",
            reference=f"DISP-{d.dispense_id}", user_id=user_id, ignore_go_live=True,
        )
        _bump(stats, cogs)
    return stats


def backfill_payhero(db: Session, *, user_id: Optional[int] = None) -> dict:
    """Matched Pay Hero receipts → ``billing.payment.mpesa`` (keyed on txn id)."""
    stats = _tally()
    try:
        from app.models.payhero import PayHeroTransaction
    except Exception:  # noqa: BLE001
        return stats
    rows = db.query(PayHeroTransaction).filter(
        PayHeroTransaction.invoice_id.isnot(None)
    ).all()
    for t in rows:
        entry = post_from_event(
            db, source_key="billing.payment.mpesa", source_id=t.id,
            amount=t.amount, on_date=_as_date(getattr(t, "transaction_date", None)),
            memo=f"Pay Hero receipt {t.receipt_number or getattr(t, 'external_reference', '')}",
            reference=f"INV-{t.invoice_id}", user_id=user_id, ignore_go_live=True,
        )
        _bump(stats, entry)
    return stats


def backfill_cheques(db: Session, *, user_id: Optional[int] = None) -> dict:
    """Cleared cheques → ``cheques.{deposit,dispatch}.cleared`` (keyed on cheque_id)."""
    stats = _tally()
    try:
        from app.models.cheque import Cheque
    except Exception:  # noqa: BLE001
        return stats
    rows = db.query(Cheque).filter(Cheque.status == "Cleared").all()
    for c in rows:
        source_key = (
            "cheques.deposit.cleared" if c.direction == "incoming"
            else "cheques.dispatch.cleared"
        )
        entry = post_from_event(
            db, source_key=source_key, source_id=c.cheque_id,
            amount=c.amount, on_date=_as_date(c.clearance_date),
            memo=f"Cheque cleared #{c.cheque_id}",
            reference=f"CHQ-{c.cheque_id}", user_id=user_id, ignore_go_live=True,
        )
        _bump(stats, entry)
    return stats


def backfill_claims(db: Session, *, user_id: Optional[int] = None) -> dict:
    """Insurance claim schedules → submitted + settled (keyed on schedule_id)."""
    stats = _tally()
    for s in db.query(ClaimSchedule).all():
        if s.status in ("submitted", "settled") and s.submitted_at:
            _bump(stats, post_from_event(
                db, source_key="insurance.claim.submitted", source_id=s.schedule_id,
                amount=s.total_amount, on_date=_as_date(s.submitted_at),
                memo=f"Insurance claim {s.schedule_number} submitted",
                reference=s.schedule_number, user_id=user_id, ignore_go_live=True,
            ))
        if s.status == "settled" and s.settled_at:
            _bump(stats, post_from_event(
                db, source_key="insurance.claim.settled", source_id=s.schedule_id,
                amount=s.settled_amount, on_date=_as_date(s.settled_at),
                memo=f"Insurance claim {s.schedule_number} settled",
                reference=s.schedule_number, user_id=user_id, ignore_go_live=True,
            ))
    return stats


def backfill_deposits(db: Session, *, user_id: Optional[int] = None) -> dict:
    """Client deposits received → ``billing.deposit.received`` (keyed on
    deposit_id). Deposit *applications* are covered by the payments pass."""
    stats = _tally()
    for dep in db.query(ClientDeposit).all():
        _bump(stats, post_from_event(
            db, source_key="billing.deposit.received", source_id=dep.deposit_id,
            amount=dep.amount, on_date=_as_date(dep.deposit_date),
            memo=f"Client deposit {dep.deposit_number} received",
            reference=dep.deposit_number, user_id=user_id, ignore_go_live=True,
        ))
    return stats


# ─── Orchestrator ────────────────────────────────────────────────────────────

_PASSES = {
    "billing_payments": backfill_payments,
    "invoice_charges": backfill_invoice_charges,
    "pharmacy_dispenses": backfill_dispenses,
    "payhero_receipts": backfill_payhero,
    "cheques": backfill_cheques,
    "insurance_claims": backfill_claims,
    "deposits": backfill_deposits,
}


def _resolve_actor(db: Session, user_id: Optional[int]) -> Optional[int]:
    """Journal entries require a non-null ``created_by`` FK. The in-app
    rebuild passes the finance admin's id; the CLI script has no request user,
    so fall back to the lowest-id (i.e. founding) user in the tenant DB."""
    if user_id is not None:
        return user_id
    from app.models.user import User
    row = db.query(User.user_id).order_by(User.user_id.asc()).first()
    return row[0] if row else None


def backfill_all(db: Session, *, user_id: Optional[int] = None, commit: bool = True) -> dict:
    """Replay every source table into the ledger. Idempotent and go-live blind.

    Returns ``{"sources": {name: {posted, skipped[, error]}}, "totals": {...}}``.
    A pass that raises (e.g. a missing optional table) records an ``error`` and
    does not abort the others.
    """
    user_id = _resolve_actor(db, user_id)
    summary = {"sources": {}, "totals": {"posted": 0, "skipped": 0, "errors": 0}}
    for name, fn in _PASSES.items():
        try:
            stats = fn(db, user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — one bad source must not sink the rest
            LOG.exception("backfill: pass %s failed", name)
            summary["sources"][name] = {"posted": 0, "skipped": 0, "error": str(exc)}
            summary["totals"]["errors"] += 1
            continue
        summary["sources"][name] = stats
        summary["totals"]["posted"] += stats["posted"]
        summary["totals"]["skipped"] += stats["skipped"]

    if commit:
        db.commit()
    return summary
