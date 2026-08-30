"""The settlement cross-check: the single most important test suite in the
migration. Daraja does not sign its callbacks, so apply_stk_callback must
never settle on a callback's own word about the amount. See
app/services/daraja/settlement.py's module docstring for the full order of
operations this file is checking.
"""
from decimal import Decimal

import pytest

from app.models.billing import Payment
from app.models.mpesa import MpesaTransaction
from app.services.daraja.settlement import apply_stk_callback, settle_invoice_match
from tests.daraja.conftest import (
    make_invoice,
    make_pending_transaction,
    seed_mpesa_ledger_mapping,
    stk_callback_payload,
)


# ─── The five required tests ────────────────────────────────────────────────


def test_callback_claiming_a_different_amount_is_quarantined_not_settled(db):
    """Daraja callbacks are unsigned. If a callback claims KES 50,000 against
    a push we made for KES 500, the only safe response is to refuse to settle
    and flag it. Trusting the callback here is the whole attack."""
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_mismatch",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("50000.00"),
        receipt="ABC123",
    )

    result = apply_stk_callback(db, payload)

    assert result.status == "Quarantined"
    assert db.query(Payment).count() == 0
    assert result.receipt_number is None  # nothing claimed against the receipt
    assert "50000" in result.result_desc or "50,000" in result.result_desc
    # The invoice must be untouched: no partial credit, no status change.
    db.refresh(invoice)
    assert invoice.amount_paid == 0
    assert invoice.status == "Pending"


def test_callback_with_no_matching_pending_transaction_is_ignored(db):
    """No pending record means we never initiated this. It is either a
    forgery or a callback for another deployment."""
    payload = stk_callback_payload(
        checkout_request_id="ws_CO_never_created", amount=Decimal("500.00"), receipt="XYZ999",
    )

    result = apply_stk_callback(db, payload)

    assert result is None
    assert db.query(MpesaTransaction).count() == 0
    assert db.query(Payment).count() == 0


def test_replayed_callback_is_a_no_op(db):
    """Safaricom retries. A second delivery of a settled receipt must not
    create a second Payment."""
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_replay",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("500.00"),
        receipt="REPLAY001",
    )

    apply_stk_callback(db, payload)
    first = db.query(Payment).count()
    assert first == 1

    apply_stk_callback(db, payload)
    assert db.query(Payment).count() == first


def test_matching_amount_settles_and_calls_post_from_event_with_the_mpesa_source_key(db, monkeypatch):
    """Settles the Payment/Invoice side end to end, and confirms
    settle_invoice_match calls post_from_event with the mpesa source key.

    This does NOT prove a JournalEntry lands: no LedgerMapping is seeded by
    this test (see the db fixture's docstring for why), so the real
    post_from_event the spy delegates to hits its own "no mapping
    configured" branch and returns None. The real-ledger-write assertion
    lives in test_settle_invoice_match_posts_a_real_ledger_entry_with_a_user.
    """
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_settle",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("500.00"),
        receipt="SETTLE001",
    )

    posted = {}
    import app.services.accounting_posting as accounting_posting
    real_post_from_event = accounting_posting.post_from_event

    def spy(db_, **kwargs):
        posted.update(kwargs)
        return real_post_from_event(db_, **kwargs)

    monkeypatch.setattr(accounting_posting, "post_from_event", spy)

    result = apply_stk_callback(db, payload)

    assert result.status == "Success"
    assert result.receipt_number == "SETTLE001"
    assert result.verification_source == "stk_callback"
    assert result.verified_at is not None

    payment = db.query(Payment).filter(Payment.transaction_reference == "SETTLE001").first()
    assert payment is not None
    assert payment.amount == Decimal("500.00")
    assert payment.invoice_id == invoice.invoice_id

    db.refresh(invoice)
    assert invoice.status == "Paid"
    assert invoice.amount_paid == Decimal("500.00")

    # settle_invoice_match must post through the mpesa source key, not the
    # retired payhero one.
    assert posted["source_key"] == "billing.payment.mpesa"
    assert posted["source_id"] == txn.id
    assert posted["amount"] == Decimal("500.00")
    assert "\u2014" not in posted["memo"]


def test_string_result_code_zero_is_treated_as_success(db):
    """Daraja sends ResultCode as an int from the STK callback but as a
    string from STK Query. A bare `!= 0` comparison would mark a genuinely
    successful "0" (string) payment Failed, self-contradicting the row
    (status Failed, ResultDesc "processed successfully", invoice never
    settled). This matters beyond the callback itself: a reconciliation job
    routing STK Query results through apply_stk_callback would produce this
    on every successful payment, since that endpoint always returns
    ResultCode as a string."""
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_string_code",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        result_code="0",
        amount=Decimal("500.00"),
        receipt="STRCODE001",
    )

    result = apply_stk_callback(db, payload)

    assert result.status == "Success"
    assert result.receipt_number == "STRCODE001"
    payment = db.query(Payment).filter(Payment.transaction_reference == "STRCODE001").first()
    assert payment is not None
    db.refresh(invoice)
    assert invoice.status == "Paid"


def test_success_with_no_receipt_number_is_quarantined_not_settled(db):
    """A "successful" ResultCode 0 callback with no MpesaReceiptNumber must
    not settle. The receipt is the one artifact tying an unsigned,
    attacker-reachable claim to a real Safaricom transaction; a Payment
    with a NULL transaction_reference would also slip past the unique-index
    replay backstop, since Postgres allows unlimited NULLs in a unique
    index."""
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_noreceipt",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("500.00"),
        receipt=None,
    )

    result = apply_stk_callback(db, payload)

    assert result.status == "Quarantined"
    assert result.receipt_number is None
    assert "MpesaReceiptNumber" in result.result_desc
    assert db.query(Payment).count() == 0
    db.refresh(invoice)
    assert invoice.status == "Pending"
    assert invoice.amount_paid == 0


def test_a_raising_settlement_leaves_the_transaction_pending_and_retryable(db, monkeypatch):
    """C1: apply_stk_callback commits the whole unit (status, receipt, and
    settlement) exactly once. If something inside settlement raises, the
    single commit means NOTHING from this delivery is persisted: the
    transaction stays Pending on disk, so Safaricom's retry finds a live
    row and settles cleanly on the next delivery, rather than finding a
    transaction permanently stuck at Success with a receipt, an unpaid
    invoice, and nobody alerted.

    Deliberately does NOT call db.rollback() itself after the raise: that
    would only prove the data is fine once someone else cleans up, not that
    apply_stk_callback guarantees the cleanup. It must roll back on its own,
    both to make the single-commit promise true and to release the
    pg_advisory_xact_lock taken on the receipt (that lock is
    transaction-scoped, so only ending the transaction, whether by commit
    or rollback, frees it; a lock left on an open, never-rolled-back
    transaction sitting on a pooled connection is exactly the shape of bug
    that has silently disabled a billing feature on another branch of this
    project before). This test checks pg_locks directly for that, not just
    the row data.

    Simulated by making the ledger post itself raise, the same shape as the
    real (separately tracked) accounting_posting.py bug: with a split
    commit that bug is terminal; with a single commit it is a failed
    delivery that gets retried."""
    import app.services.accounting_posting as accounting_posting
    from sqlalchemy import text

    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_raises",
    )
    # Commit the setup first: in production this row was already committed
    # by a prior, separate request (initiate_stk_push's own commit). Only
    # what happens after this point belongs to the callback delivery under
    # test.
    db.commit()
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        amount=Decimal("500.00"),
        receipt="RAISES001",
    )

    def boom(db_, **kwargs):
        raise RuntimeError("simulated ledger failure")

    monkeypatch.setattr(accounting_posting, "post_from_event", boom)

    with pytest.raises(RuntimeError):
        apply_stk_callback(db, payload)

    # No db.rollback() here. If apply_stk_callback did not roll back on its
    # own, either of the two checks below would show it: the row would
    # still read whatever this session's uncommitted, un-rolled-back
    # transaction left it as (Success, in the broken version of this fix),
    # and/or the advisory lock would still be held.
    # Scoped to the current database (advisory locks are per-database, and
    # pg_locks.database records which one), so this is not a false positive
    # from some unrelated connection elsewhere on the same Postgres
    # instance holding an advisory lock of its own.
    held_locks = db.execute(text(
        "SELECT count(*) FROM pg_locks l JOIN pg_database d ON l.database = d.oid "
        "WHERE l.locktype = 'advisory' AND d.datname = current_database()"
    )).scalar()
    assert held_locks == 0, "advisory lock was not released after the exception"

    reloaded = (
        db.query(MpesaTransaction)
        .filter(MpesaTransaction.checkout_request_id == "ws_CO_raises")
        .first()
    )
    assert reloaded.status == "Pending"
    assert reloaded.receipt_number is None
    assert reloaded.verified_at is None
    assert db.query(Payment).count() == 0
    db.refresh(invoice)
    assert invoice.status == "Pending"
    assert invoice.amount_paid == 0

    # Safaricom's retry: the exact same payload, delivered again, now
    # against the real post_from_event. Because nothing committed above,
    # step 2's Pending filter still finds this row and the retry settles.
    monkeypatch.undo()
    retried = apply_stk_callback(db, payload)

    assert retried.status == "Success"
    assert retried.receipt_number == "RAISES001"
    payment = db.query(Payment).filter(Payment.transaction_reference == "RAISES001").first()
    assert payment is not None
    db.refresh(invoice)
    assert invoice.status == "Paid"


def test_failed_result_code_marks_failed_without_a_payment(db):
    invoice = make_invoice(db, total_amount=Decimal("500.00"))
    txn = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_failed",
    )
    payload = stk_callback_payload(
        checkout_request_id=txn.checkout_request_id,
        result_code=1032,
        result_desc="Request cancelled by user",
    )

    result = apply_stk_callback(db, payload)

    assert result.status == "Failed"
    assert result.result_desc == "Request cancelled by user"
    assert result.receipt_number is None
    assert db.query(Payment).count() == 0


# ─── Extra coverage: the concurrent-delivery guard (step 6) ─────────────────


def test_receipt_already_settled_on_another_transaction_is_treated_as_a_replay(db):
    """Step 6 is a second, independent guard from step 2's Pending filter:
    it protects against two Pending rows (or two concurrent deliveries)
    converging on the same already-used receipt number, not just a retry of
    the exact same row. Simulated here by hand-settling one transaction and
    then running the callback for a *different* Pending transaction that
    happens to carry the same receipt number."""
    invoice = make_invoice(db, total_amount=Decimal("500.00"))

    already_settled = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_first",
    )
    already_settled.receipt_number = "SHARED001"
    already_settled.status = "Success"
    db.commit()

    second = make_pending_transaction(
        db, amount=Decimal("500.00"), invoice_id=invoice.invoice_id,
        checkout_request_id="ws_CO_second",
    )
    payload = stk_callback_payload(
        checkout_request_id=second.checkout_request_id,
        amount=Decimal("500.00"),
        receipt="SHARED001",
    )

    result = apply_stk_callback(db, payload)

    assert result.id == already_settled.id
    assert db.query(Payment).count() == 0
    db.refresh(second)
    assert second.status == "Pending"  # untouched, not silently marked Success


# ─── settle_invoice_match, ported from payhero_service.py ──────────────────


def test_settle_invoice_match_is_idempotent_on_receipt(db):
    invoice = make_invoice(db, total_amount=Decimal("200.00"))
    txn = make_pending_transaction(db, amount=Decimal("200.00"), invoice_id=invoice.invoice_id)
    txn.receipt_number = "IDEMP001"
    txn.status = "Success"
    db.commit()

    first = settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback")
    second = settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback")

    assert first.payment_id == second.payment_id
    assert db.query(Payment).count() == 1


def test_settle_invoice_match_posts_a_real_ledger_entry_with_a_user(db):
    """With an acting user_id (unlike the anonymous webhook path),
    post_from_event's NOT NULL created_by is satisfiable, so this proves the
    ledger side of the port actually produces a JournalEntry, not just that
    it is called."""
    from app.models.accounting import JournalEntry

    seed_mpesa_ledger_mapping(db)
    invoice = make_invoice(db, total_amount=Decimal("300.00"))
    txn = make_pending_transaction(db, amount=Decimal("300.00"), invoice_id=invoice.invoice_id)
    txn.receipt_number = "LEDGER001"
    txn.status = "Success"
    db.commit()

    settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback", user_id=1)

    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "billing.payment.mpesa", JournalEntry.source_id == txn.id)
        .first()
    )
    assert entry is not None
    assert entry.status == "posted"
    lines = {l.account.code: l for l in entry.lines}
    assert lines["1130"].debit == Decimal("300.00")
    assert lines["1140"].credit == Decimal("300.00")


def test_settle_invoice_match_notification_body_has_no_em_dash_when_receipt_missing(db, monkeypatch):
    """Ported from payhero_service.py, whose notify body fell back to an
    em dash when the receipt was missing. That character must be gone,
    replaced with 'not recorded'."""
    import app.utils.notify as notify_module

    captured = {}

    def fake_notify_permission(db_, codename, **kwargs):
        captured["body"] = kwargs.get("body")
        return 0

    monkeypatch.setattr(notify_module, "notify_permission", fake_notify_permission)

    invoice = make_invoice(db, total_amount=Decimal("100.00"))
    txn = make_pending_transaction(db, amount=Decimal("100.00"), invoice_id=invoice.invoice_id)
    txn.status = "Success"
    # No receipt_number set: exercises the "or ..." fallback in the body.
    db.commit()

    settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="stk_callback")

    payment = db.query(Payment).filter(Payment.invoice_id == invoice.invoice_id).first()
    assert payment is not None
    assert payment.transaction_reference is None
    assert "body" in captured
    assert "not recorded" in captured["body"]
    assert "\u2014" not in captured["body"]


# ─── Proof the two critical tests actually test something ──────────────────
# See task-5-report.md for the revert-and-confirm-red evidence: the two
# tests above (amount-mismatch quarantine, replay no-op) were run against a
# deliberately broken settlement.py (cross-check / replay guard commented
# out) and failed, then passed again once restored.
