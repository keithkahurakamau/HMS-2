"""
Auto-posting bridge between source modules (Billing, Pharmacy, Cheques,
M-Pesa, …) and the ledger.

Design principles:

  * **Idempotent.** Calling `post_from_event` twice for the same
    (source_key, source_id) is a no-op the second time — it returns
    the previously-posted entry. Source modules can retry without fear.
  * **Non-fatal.** Posting failures NEVER raise out of this helper.
    The source operation (the patient already paid; the prescription
    was already dispensed) must not roll back because the bookkeeping
    layer hit an issue. Failures get logged with full context so
    operators can re-post manually.
  * **Honors go-live.** Events dated before the tenant's go_live_date
    are skipped silently — the tenant explicitly opted in to clean
    cutover.
  * **Mapping-driven.** Account ids come from `acc_ledger_mappings`,
    NOT hard-coded. Tenants who restructured their CoA can re-point
    via the Configuration UI without code changes.
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.accounting import (
    JournalEntry,
    JournalLine,
    LedgerMapping,
)
from app.services.accounting import (
    ensure_fiscal_period,
    get_base_currency_code,
    get_or_create_settings,
    resolve_fx_rate,
    _next_entry_number,
)

LOG = logging.getLogger(__name__)

ZERO = Decimal("0")
ROUND_QUANT = Decimal("0.0001")


def post_from_event(
    db: Session,
    *,
    source_key: str,
    source_id: int,
    amount,
    on_date: Optional[_date] = None,
    currency_code: Optional[str] = None,
    memo: Optional[str] = None,
    reference: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[JournalEntry]:
    """Post a 2-line journal entry derived from `source_key`'s mapping.

    Returns the posted entry on success, the existing entry on idempotent
    hit, or None when posting was deliberately skipped (no mapping, before
    go-live, zero amount, etc.). Never raises — exceptions are caught and
    logged. The caller's session is NOT committed here; the source
    transaction owns the commit so the entry lives or dies with the
    source row.
    """
    # Wrap the entire body in a SAVEPOINT. Without it, if any SQL inside
    # (the entry/lines INSERT, the FX rate lookup, anything) raises and we
    # silently swallow the exception, the caller's transaction is left in
    # `InFailedSqlTransaction` state — every subsequent statement (the
    # audit_log INSERT in the source route, for instance) then gets
    # rejected by Postgres. The savepoint lets us roll back ONLY this
    # posting attempt while leaving the outer transaction usable.
    try:
        sp = db.begin_nested()
    except Exception:
        # Caller never opened a transaction; fall back to no-savepoint mode.
        # The outer-transaction cascade is still possible here, but that's
        # the caller's problem to fix.
        sp = None

    try:
        amt = Decimal(str(amount)).quantize(ROUND_QUANT)
        if amt <= ZERO:
            LOG.debug("accounting: skip zero/negative amount source_key=%s source_id=%s amount=%s",
                      source_key, source_id, amount)
            if sp is not None and sp.is_active:
                sp.rollback()
            return None

        on = on_date or _date.today()
        settings = get_or_create_settings(db)

        # Go-live gate.
        if settings.go_live_date and on < settings.go_live_date:
            LOG.info("accounting: skip pre-go-live event source_key=%s source_id=%s on=%s go_live=%s",
                     source_key, source_id, on, settings.go_live_date)
            if sp is not None and sp.is_active:
                sp.rollback()
            return None

        # Idempotency: did we already post this exact event?
        existing = (
            db.query(JournalEntry)
            .filter(
                JournalEntry.source_type == source_key,
                JournalEntry.source_id == source_id,
                JournalEntry.status == "posted",
            )
            .first()
        )
        if existing is not None:
            LOG.debug("accounting: idempotent hit source_key=%s source_id=%s entry=%s",
                      source_key, source_id, existing.entry_id)
            if sp is not None and sp.is_active:
                sp.rollback()
            return existing

        # Look up mapping.
        mapping = (
            db.query(LedgerMapping)
            .filter(LedgerMapping.source_key == source_key,
                    LedgerMapping.is_active == True)  # noqa: E712
            .first()
        )
        if mapping is None:
            LOG.warning("accounting: no mapping configured for source_key=%s — skipping post",
                        source_key)
            if sp is not None and sp.is_active:
                sp.rollback()
            return None
        if not mapping.debit_account_id or not mapping.credit_account_id:
            LOG.warning("accounting: mapping for %s has unset Dr/Cr accounts — skipping post",
                        source_key)
            if sp is not None and sp.is_active:
                sp.rollback()
            return None

        cur = currency_code or settings.base_currency_code or "KES"
        base = get_base_currency_code(db)
        rate = Decimal("1") if cur == base else resolve_fx_rate(db, cur, base, on)

        period = ensure_fiscal_period(db, on)
        entry = JournalEntry(
            entry_number=_next_entry_number(db, on),
            entry_date=on,
            fiscal_period_id=period.period_id,
            currency_code=cur,
            fx_rate=rate,
            status="posted",
            memo=memo,
            reference=reference,
            source_type=source_key,
            source_id=source_id,
            created_by=user_id,
            posted_by=user_id,
            posted_at=datetime.utcnow(),
        )
        db.add(entry)
        db.flush()

        base_amt = (amt * rate).quantize(ROUND_QUANT)
        db.add(JournalLine(
            entry_id=entry.entry_id,
            line_number=1,
            account_id=mapping.debit_account_id,
            debit=amt, credit=ZERO,
            debit_base=base_amt, credit_base=ZERO,
            description=memo,
        ))
        db.add(JournalLine(
            entry_id=entry.entry_id,
            line_number=2,
            account_id=mapping.credit_account_id,
            debit=ZERO, credit=amt,
            debit_base=ZERO, credit_base=base_amt,
            description=memo,
        ))
        db.flush()

        if sp is not None:
            sp.commit()
        LOG.info("accounting: posted %s source_id=%s amount=%s entry=%s",
                 source_key, source_id, amt, entry.entry_number)
        return entry

    except Exception:  # noqa: BLE001 — auto-post must never break the source op
        # Roll back to the savepoint so the outer transaction is still
        # usable (audit log inserts, idempotency-key inserts, etc.).
        if sp is not None and sp.is_active:
            try:
                sp.rollback()
            except Exception:
                LOG.exception("accounting: savepoint rollback failed after posting error "
                              "source_key=%s source_id=%s", source_key, source_id)
        LOG.exception("accounting: failed to post source_key=%s source_id=%s amount=%s",
                      source_key, source_id, amount)
        return None


def post_dispense_pair(
    db: Session,
    *,
    dispense_id: int,
    revenue_amount,
    cogs_amount,
    on_date: Optional[_date] = None,
    memo: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Tuple[Optional[JournalEntry], Optional[JournalEntry]]:
    """Pharmacy dispenses post two entries: revenue + COGS.

    They share a source_id (the dispense_log id) but use different
    source_keys so the idempotency check fires per-entry.
    """
    rev = post_from_event(
        db,
        source_key="pharmacy.dispense.revenue",
        source_id=dispense_id,
        amount=revenue_amount,
        on_date=on_date,
        memo=memo or f"Pharmacy dispensation #{dispense_id} (revenue)",
        reference=f"DISP-{dispense_id}",
        user_id=user_id,
    )
    cogs = post_from_event(
        db,
        source_key="pharmacy.dispense.cogs",
        source_id=dispense_id,
        amount=cogs_amount,
        on_date=on_date,
        memo=memo or f"Pharmacy dispensation #{dispense_id} (COGS)",
        reference=f"DISP-{dispense_id}",
        user_id=user_id,
    )
    return rev, cogs


def payment_method_to_key(method: Optional[str]) -> str:
    """Translate a billing payment_method string into a source_key.

    Tolerant of common spellings. Defaults to 'billing.payment.cash'
    when the method isn't recognised so a stray value still gets
    posted somewhere visible — better than dropping it on the floor.
    """
    if not method:
        return "billing.payment.cash"
    m = method.strip().lower()
    if m in ("mpesa", "m-pesa", "mobile money", "mobile_money"):
        return "billing.payment.mpesa"
    if m in ("bank", "bank transfer", "card", "credit card", "debit card", "eft", "cheque", "check"):
        return "billing.payment.bank"
    if m in ("cash",):
        return "billing.payment.cash"
    LOG.warning("accounting: unknown payment_method %r — defaulting to billing.payment.cash", method)
    return "billing.payment.cash"
