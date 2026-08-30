"""The settlement cross-check: the single most important test suite in the
migration. Daraja does not sign its callbacks, so apply_stk_callback must
never settle on a callback's own word about the amount. See
app/services/daraja/settlement.py's module docstring for the full order of
operations this file is checking.
"""
from decimal import Decimal

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


def test_matching_amount_settles_and_posts_to_the_ledger(db, monkeypatch):
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
