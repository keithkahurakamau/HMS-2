"""Phase 7 — budgeting, debit/credit notes, and bulk deposit allocation.

Budgets + notes are exercised through their service layers; bulk allocation
lives in the route file, so we call the route function directly (bypassing
FastAPI's permission dependencies, which are declared on the decorator).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.accounting import (
    AdjustmentNote,
    Budget,
    BudgetLine,
    ClaimSchedule,
    ClaimScheduleItem,
    ClientDeposit,
    DepositApplication,
    JournalEntry,
)
from app.models.patient import Patient
from app.services import accounting_budget as budget_svc
from app.services import accounting_notes as notes_svc
from app.services.accounting import seed_fiscal_year
from .conftest import account_id, post_simple_entry


# ─── Helpers ────────────────────────────────────────────────────────────────

def _patient(db, patient_id=1):
    p = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if p:
        return p
    p = Patient(patient_id=patient_id, outpatient_no=f"OP-{patient_id:06d}",
                surname="Test", other_names="One", sex="Female",
                date_of_birth=date(1990, 1, 1))
    db.add(p)
    db.commit()
    return p


def _period(db, year, month):
    periods = seed_fiscal_year(db, year)
    db.commit()
    return next(p for p in periods if p.month == month)


# ─── Budgeting ──────────────────────────────────────────────────────────────

def test_create_budget_and_lines(db):
    budget = budget_svc.create_budget(db, name="Ops 2030", fiscal_year=2030, user_id=1)
    db.commit()
    period = _period(db, 2030, 1)
    util = account_id(db, "6300")

    line = budget_svc.add_or_update_line(db, budget_id=budget.budget_id,
                                         account_id=util, period_id=period.period_id,
                                         amount=Decimal("1000"))
    db.commit()
    assert line.amount == Decimal("1000.0000")

    # Upsert: same account/period updates rather than duplicates.
    budget_svc.add_or_update_line(db, budget_id=budget.budget_id, account_id=util,
                                  period_id=period.period_id, amount=Decimal("1200"))
    db.commit()
    rows = db.query(BudgetLine).filter(BudgetLine.budget_id == budget.budget_id).all()
    assert len(rows) == 1
    assert rows[0].amount == Decimal("1200.0000")


def test_budget_line_rejects_nonpostable_account(db):
    budget = budget_svc.create_budget(db, name="Bad 2030", fiscal_year=2030, user_id=1)
    db.commit()
    period = _period(db, 2030, 1)
    rollup = account_id(db, "6000")  # Operating Expenses roll-up (is_postable=False)
    with pytest.raises(HTTPException):
        budget_svc.add_or_update_line(db, budget_id=budget.budget_id, account_id=rollup,
                                      period_id=period.period_id, amount=Decimal("500"))


def test_budget_line_rejects_period_outside_fiscal_year(db):
    budget = budget_svc.create_budget(db, name="Span 2030", fiscal_year=2030, user_id=1)
    db.commit()
    period = _period(db, 2031, 1)  # wrong year
    util = account_id(db, "6300")
    with pytest.raises(HTTPException):
        budget_svc.add_or_update_line(db, budget_id=budget.budget_id, account_id=util,
                                      period_id=period.period_id, amount=Decimal("500"))


def test_budget_vs_actual_variance(db):
    budget = budget_svc.create_budget(db, name="VsActual 2030", fiscal_year=2030, user_id=1)
    db.commit()
    period = _period(db, 2030, 3)
    util = account_id(db, "6300")  # Expense — debit-natural
    budget_svc.add_or_update_line(db, budget_id=budget.budget_id, account_id=util,
                                  period_id=period.period_id, amount=Decimal("1000"))
    db.commit()

    # Post an actual expense of 800 in that period (Dr 6300 / Cr 1110).
    post_simple_entry(db, "6300", "1110", Decimal("800"), on_date=date(2030, 3, 15))

    result = budget_svc.budget_vs_actual(db, budget_id=budget.budget_id)
    row = next(r for r in result["rows"] if r["account_id"] == util)
    assert row["budget"] == Decimal("1000.0000")
    assert row["actual"] == Decimal("800.0000")
    assert row["variance"] == Decimal("200.0000")
    assert result["totals"]["variance"] == Decimal("200.0000")


# ─── Debit / credit notes ───────────────────────────────────────────────────

def test_post_credit_note_builds_balanced_posted_entry(db):
    note = notes_svc.create_note(
        db, note_type="credit", note_date=date.today(), amount=Decimal("500"),
        debit_account_id=account_id(db, "4100"),   # Dr Revenue
        credit_account_id=account_id(db, "1140"),  # Cr AR
        user_id=1, reason="Goodwill discount",
    )
    db.commit()
    assert note.status == "draft"

    posted = notes_svc.post_note(db, note_id=note.note_id, user_id=1)
    db.commit()
    assert posted.status == "posted"
    assert posted.journal_entry_id is not None

    entry = db.query(JournalEntry).filter(JournalEntry.entry_id == posted.journal_entry_id).first()
    assert entry.status == "posted"
    assert entry.source_type == "accounting.credit_note"
    dr = next(l for l in entry.lines if l.debit > 0)
    cr = next(l for l in entry.lines if l.credit > 0)
    assert dr.account_id == account_id(db, "4100")
    assert cr.account_id == account_id(db, "1140")
    assert dr.debit_base == cr.credit_base == Decimal("500.0000")


def test_void_note_reverses_entry(db):
    note = notes_svc.create_note(
        db, note_type="debit", note_date=date.today(), amount=Decimal("250"),
        debit_account_id=account_id(db, "1140"),
        credit_account_id=account_id(db, "4100"),
        user_id=1,
    )
    db.commit()
    posted = notes_svc.post_note(db, note_id=note.note_id, user_id=1)
    db.commit()
    original_entry_id = posted.journal_entry_id

    voided = notes_svc.void_note(db, note_id=note.note_id, user_id=1, reason="keyed in error")
    db.commit()
    assert voided.status == "void"

    original = db.query(JournalEntry).filter(JournalEntry.entry_id == original_entry_id).first()
    assert original.status == "reversed"
    mirror = db.query(JournalEntry).filter(
        JournalEntry.reverses_entry_id == original_entry_id).first()
    assert mirror is not None and mirror.status == "posted"


def test_note_distinct_accounts_enforced(db):
    same = account_id(db, "1140")
    with pytest.raises(HTTPException):
        notes_svc.create_note(db, note_type="credit", note_date=date.today(),
                              amount=Decimal("10"), debit_account_id=same,
                              credit_account_id=same, user_id=1)


# ─── Bulk deposit allocation ────────────────────────────────────────────────

def _deposit_with_claim(db, deposit_amount="5000", items=((3000,), (2000,))):
    _patient(db)
    dep = ClientDeposit(
        deposit_number="DEP-BULK-0001", patient_id=1, deposit_date=date.today(),
        amount=Decimal(str(deposit_amount)), amount_applied=Decimal("0"),
        method="Cash", status="available", received_by=1,
    )
    db.add(dep)
    sched = ClaimSchedule(
        schedule_number="CLM-BULK-0001", provider_id=None,  # nullable not enforced here
        period_from=date.today(), period_to=date.today(),
        total_amount=Decimal("0"), status="draft", created_by=1,
    )
    # provider_id is NOT NULL — create a provider.
    from app.models.accounting import InsuranceProvider
    prov = InsuranceProvider(name="BulkIns", is_active=True)
    db.add(prov)
    db.flush()
    sched.provider_id = prov.provider_id
    db.add(sched)
    db.flush()
    created = []
    for (amt,) in items:
        it = ClaimScheduleItem(schedule_id=sched.schedule_id,
                               amount_claimed=Decimal(str(amt)),
                               amount_allocated=Decimal("0"),
                               patient_name="P")
        db.add(it)
        created.append(it)
    db.commit()
    for it in created:
        db.refresh(it)
    db.refresh(dep)
    return dep, created


def test_bulk_allocate_happy_path(db):
    from app.routes.accounting_debtors import (
        allocate_deposit_bulk, BulkAllocateRequest, BulkAllocationItem,
    )
    dep, items = _deposit_with_claim(db)
    payload = BulkAllocateRequest(allocations=[
        BulkAllocationItem(item_id=items[0].item_id, amount=Decimal("2000")),
        BulkAllocationItem(item_id=items[1].item_id, amount=Decimal("1500")),
    ])
    result = allocate_deposit_bulk(deposit_id=dep.deposit_id, payload=payload,
                                   db=db, current_user={"user_id": 1})

    assert result.amount_applied == Decimal("3500.00")
    assert result.status == "partially_applied"

    db.refresh(items[0]); db.refresh(items[1])
    assert items[0].amount_allocated == Decimal("2000.00")
    assert items[1].amount_allocated == Decimal("1500.00")

    apps = db.query(DepositApplication).filter(
        DepositApplication.deposit_id == dep.deposit_id).all()
    assert len(apps) == 2
    assert all(a.invoice_id is None and a.claim_item_id is not None for a in apps)

    # Each allocation auto-posted a balanced entry Dr 2170 / Cr 1140.
    entries = db.query(JournalEntry).filter(
        JournalEntry.source_type == "billing.deposit.bulk_allocated").all()
    assert len(entries) == 2
    for e in entries:
        dr = next(l for l in e.lines if l.debit > 0)
        cr = next(l for l in e.lines if l.credit > 0)
        assert dr.account_id == account_id(db, "2170")
        assert cr.account_id == account_id(db, "1140")


def test_bulk_allocate_over_deposit_rejected(db):
    from app.routes.accounting_debtors import (
        allocate_deposit_bulk, BulkAllocateRequest, BulkAllocationItem,
    )
    dep, items = _deposit_with_claim(db, deposit_amount="1000")
    payload = BulkAllocateRequest(allocations=[
        BulkAllocationItem(item_id=items[0].item_id, amount=Decimal("900")),
        BulkAllocationItem(item_id=items[1].item_id, amount=Decimal("900")),
    ])
    with pytest.raises(HTTPException) as exc:
        allocate_deposit_bulk(deposit_id=dep.deposit_id, payload=payload,
                              db=db, current_user={"user_id": 1})
    assert exc.value.status_code == 400
    db.rollback()
    db.refresh(items[0])
    assert items[0].amount_allocated == Decimal("0.00")  # nothing applied


def test_bulk_allocate_over_item_remainder_rejected(db):
    from app.routes.accounting_debtors import (
        allocate_deposit_bulk, BulkAllocateRequest, BulkAllocationItem,
    )
    dep, items = _deposit_with_claim(db)
    payload = BulkAllocateRequest(allocations=[
        BulkAllocationItem(item_id=items[0].item_id, amount=Decimal("4000")),  # item only 3000
    ])
    with pytest.raises(HTTPException) as exc:
        allocate_deposit_bulk(deposit_id=dep.deposit_id, payload=payload,
                              db=db, current_user={"user_id": 1})
    assert exc.value.status_code == 400


def test_bulk_allocate_duplicate_item_rejected(db):
    from app.routes.accounting_debtors import (
        allocate_deposit_bulk, BulkAllocateRequest, BulkAllocationItem,
    )
    dep, items = _deposit_with_claim(db)
    payload = BulkAllocateRequest(allocations=[
        BulkAllocationItem(item_id=items[0].item_id, amount=Decimal("100")),
        BulkAllocationItem(item_id=items[0].item_id, amount=Decimal("100")),
    ])
    with pytest.raises(HTTPException) as exc:
        allocate_deposit_bulk(deposit_id=dep.deposit_id, payload=payload,
                              db=db, current_user={"user_id": 1})
    assert exc.value.status_code == 400
