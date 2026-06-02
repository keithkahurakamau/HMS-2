"""Historical ledger backfill — "see every transaction that ever happened".

The live auto-poster only records events *after* a tenant's go-live date and
while a mapping exists, so pre-cutover history never reached the journal. The
backfill (``app.services.accounting_backfill``) replays the source tables into
the ledger to fill that gap.

These tests cover the load-bearing behaviour:

  * each source pass posts the right ``source_type`` keyed the way the live
    call site keys it;
  * the whole thing is **idempotent** (re-running never double-posts);
  * it is **go-live blind** (pre-cutover rows still post);
  * the **double-count guards** hold — a single ``payments`` row owned by the
    cheque / Pay Hero / deposit passes is not re-posted under its payment id.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.accounting import (
    AccountingSettings,
    ClaimSchedule,
    ClientDeposit,
    InsuranceProvider,
    JournalEntry,
)
from app.models.billing import Invoice, InvoiceItem, Payment
from app.models.cheque import Cheque
from app.models.inventory import (
    DispenseLog,
    InventoryItem,
    Location,
    StockBatch,
)
from app.models.patient import Patient
from app.models.payhero import PayHeroTransaction
from app.services.accounting_backfill import backfill_all, backfill_payments


# ─── Fixtures / builders ─────────────────────────────────────────────────────

def _patient(db, opd="OP-001") -> Patient:
    p = Patient(
        outpatient_no=opd,
        surname="Doe",
        other_names="Jane",
        sex="Female",
        date_of_birth=date(1990, 1, 1),
    )
    db.add(p)
    db.flush()
    return p


def _invoice(db, *, total=1000, billing_date=None) -> Invoice:
    inv = Invoice(
        total_amount=Decimal(str(total)),
        status="Pending",
        created_by=1,
    )
    if billing_date is not None:
        inv.billing_date = billing_date
    db.add(inv)
    db.flush()
    return inv


def _payment(db, invoice_id, *, amount, method, reference=None, on=None) -> Payment:
    pay = Payment(
        invoice_id=invoice_id,
        amount=Decimal(str(amount)),
        payment_method=method,
        transaction_reference=reference,
    )
    if on is not None:
        pay.payment_date = on
    db.add(pay)
    db.flush()
    return pay


def _entries(db, source_type):
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == source_type)
        .all()
    )


# ─── Payments pass ───────────────────────────────────────────────────────────

def test_cash_payment_posts_keyed_on_payment_id(db):
    inv = _invoice(db)
    pay = _payment(db, inv.invoice_id, amount=500, method="Cash")
    db.commit()

    summary = backfill_all(db)

    rows = _entries(db, "billing.payment.cash")
    assert len(rows) == 1
    assert rows[0].source_id == pay.payment_id
    assert summary["sources"]["billing_payments"]["posted"] == 1


def test_backfill_is_idempotent(db):
    inv = _invoice(db)
    _payment(db, inv.invoice_id, amount=500, method="Cash")
    db.commit()

    backfill_all(db)
    first = len(_entries(db, "billing.payment.cash"))
    backfill_all(db)
    second = len(_entries(db, "billing.payment.cash"))

    assert first == 1
    assert second == 1  # re-run did not duplicate


def test_go_live_gate_is_bypassed(db):
    # Tenant went live today; the payment predates cutover by a year.
    db.query(AccountingSettings).update({"go_live_date": date.today()})
    db.commit()

    last_year = datetime.utcnow() - timedelta(days=365)
    inv = _invoice(db, billing_date=last_year)
    _payment(db, inv.invoice_id, amount=750, method="Cash", on=last_year)
    db.commit()

    backfill_all(db)

    rows = _entries(db, "billing.payment.cash")
    assert len(rows) == 1  # posted despite predating go-live
    assert rows[0].entry_date < date.today()


# ─── Double-count guards ─────────────────────────────────────────────────────

def test_cheque_payment_skipped_by_payments_pass(db):
    """A payment recorded as a cheque is owned by the cheque pass (keyed on
    cheque_id). The payments pass must not post it under its payment id."""
    inv = _invoice(db)
    _payment(db, inv.invoice_id, amount=1200, method="Cheque", reference="CHQ-9")
    db.commit()

    stats = backfill_payments(db, user_id=1)
    db.commit()

    assert stats["skipped"] == 1
    assert stats["posted"] == 0
    assert _entries(db, "billing.payment.bank") == []
    assert _entries(db, "billing.payment.cash") == []


def test_deposit_application_payment_routes_to_deposit_applied(db):
    """A payment funded by a client deposit posts under
    ``billing.deposit.applied`` (still keyed on payment id), never as a
    direct cash/bank receipt."""
    inv = _invoice(db)
    pay = _payment(db, inv.invoice_id, amount=400, method="Deposit", reference="DEP-3")
    db.commit()

    backfill_payments(db, user_id=1)
    db.commit()

    applied = _entries(db, "billing.deposit.applied")
    assert len(applied) == 1
    assert applied[0].source_id == pay.payment_id
    assert _entries(db, "billing.payment.cash") == []


def test_payhero_payment_keyed_on_txn_not_payment_id(db):
    """When a payment carries a Pay Hero receipt number, the Pay Hero pass
    owns it (keyed on the txn id). Exactly one mpesa entry must exist, keyed
    on the transaction — not a second one keyed on the payment."""
    inv = _invoice(db)
    txn = PayHeroTransaction(
        invoice_id=inv.invoice_id,
        phone_number="254700000000",
        amount=Decimal("950"),
        receipt_number="QGH7XYZ123",
        status="Success",
        transaction_type="STK",
    )
    db.add(txn)
    db.flush()
    # The billing-side payment row mirrors the receipt number.
    _payment(db, inv.invoice_id, amount=950, method="M-Pesa", reference="QGH7XYZ123")
    db.commit()

    backfill_all(db)

    mpesa = _entries(db, "billing.payment.mpesa")
    assert len(mpesa) == 1
    assert mpesa[0].source_id == txn.id


# ─── Invoice charges ─────────────────────────────────────────────────────────

def test_only_consultation_items_post(db):
    inv = _invoice(db)
    db.add(InvoiceItem(invoice_id=inv.invoice_id, description="OPD visit",
                       amount=Decimal("300"), item_type="Consultation"))
    db.add(InvoiceItem(invoice_id=inv.invoice_id, description="Paracetamol",
                       amount=Decimal("80"), item_type="Pharmacy"))
    db.commit()

    backfill_all(db)

    charges = _entries(db, "billing.invoice.created")
    assert len(charges) == 1  # the pharmacy line is NOT posted via this key
    assert charges[0].reference == f"INV-{inv.invoice_id}"


# ─── Pharmacy dispenses ──────────────────────────────────────────────────────

def test_dispense_posts_revenue_and_cogs(db):
    loc = Location(name="Pharmacy")
    db.add(loc)
    item = InventoryItem(item_code="DRG-1", name="Amoxicillin", category="Drug",
                         unit_cost=Decimal("10"), unit_price=Decimal("25"))
    db.add(item)
    db.flush()
    batch = StockBatch(item_id=item.item_id, location_id=loc.location_id,
                       batch_number="B1", quantity=100, expiry_date=date(2030, 1, 1))
    db.add(batch)
    db.flush()
    disp = DispenseLog(item_id=item.item_id, batch_id=batch.batch_id,
                       quantity_dispensed=4, total_cost=Decimal("100"),
                       dispensed_by=1)
    db.add(disp)
    db.commit()

    backfill_all(db)

    rev = _entries(db, "pharmacy.dispense.revenue")
    cogs = _entries(db, "pharmacy.dispense.cogs")
    assert len(rev) == 1 and rev[0].source_id == disp.dispense_id
    assert len(cogs) == 1 and cogs[0].source_id == disp.dispense_id


# ─── Cheques ─────────────────────────────────────────────────────────────────

def test_cleared_incoming_cheque_posts(db):
    chq = Cheque(
        direction="incoming",
        cheque_number="000123",
        bank_name="KCB",
        drawer_name="Acme Insurers",
        amount=Decimal("5000"),
        status="Cleared",
        clearance_date=datetime.utcnow(),
        received_by=1,
    )
    db.add(chq)
    db.commit()

    backfill_all(db)

    rows = _entries(db, "cheques.deposit.cleared")
    assert len(rows) == 1
    assert rows[0].source_id == chq.cheque_id


def test_uncleared_cheque_not_posted(db):
    chq = Cheque(
        direction="incoming",
        cheque_number="000124",
        bank_name="KCB",
        drawer_name="Acme Insurers",
        amount=Decimal("5000"),
        status="Received",
        received_by=1,
    )
    db.add(chq)
    db.commit()

    backfill_all(db)

    assert _entries(db, "cheques.deposit.cleared") == []


# ─── Client deposits ─────────────────────────────────────────────────────────

def test_client_deposit_received_posts(db):
    patient = _patient(db)
    dep = ClientDeposit(
        deposit_number="DEP-0001",
        patient_id=patient.patient_id,
        amount=Decimal("2000"),
        method="Cash",
        status="available",
        received_by=1,
    )
    db.add(dep)
    db.commit()

    backfill_all(db)

    rows = _entries(db, "billing.deposit.received")
    assert len(rows) == 1
    assert rows[0].source_id == dep.deposit_id


# ─── Insurance claims ────────────────────────────────────────────────────────

def test_settled_claim_posts_submitted_and_settled(db):
    provider = InsuranceProvider(name="NHIF")
    db.add(provider)
    db.flush()
    now = datetime.utcnow()
    sched = ClaimSchedule(
        schedule_number="CLM-0001",
        provider_id=provider.provider_id,
        period_from=date.today() - timedelta(days=30),
        period_to=date.today(),
        total_amount=Decimal("8000"),
        status="settled",
        submitted_at=now - timedelta(days=10),
        settled_at=now,
        settled_amount=Decimal("7500"),
        created_by=1,
    )
    db.add(sched)
    db.commit()

    backfill_all(db)

    submitted = _entries(db, "insurance.claim.submitted")
    settled = _entries(db, "insurance.claim.settled")
    assert len(submitted) == 1 and submitted[0].source_id == sched.schedule_id
    assert len(settled) == 1 and settled[0].source_id == sched.schedule_id


# ─── Orchestrator contract ───────────────────────────────────────────────────

def test_summary_shape_with_no_data(db):
    summary = backfill_all(db)
    assert set(summary) == {"sources", "totals"}
    assert set(summary["totals"]) == {"posted", "skipped", "errors"}
    # Every registered pass reports in, none errored on an empty DB.
    assert "billing_payments" in summary["sources"]
    assert summary["totals"]["errors"] == 0
