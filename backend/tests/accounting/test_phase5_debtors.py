"""Phase 5 — debtor lifecycle (claim schedules + client deposits).

Service-layer tests don't exist for this phase (logic lives in the route
file). Tests exercise the model invariants + simulate the lifecycle steps
manually, then verify the ledger entries posted via accounting_posting
end up where they should.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.accounting import (
    ClaimSchedule,
    ClaimScheduleItem,
    ClientDeposit,
    DepositApplication,
    InsuranceProvider,
    JournalEntry,
)
from app.models.patient import Patient
from app.services.accounting_posting import post_from_event
from .conftest import account_id


# ─── Helpers ────────────────────────────────────────────────────────────────

def _patient(db, patient_id=1, surname="Test", other_names="One"):
    p = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if p:
        return p
    p = Patient(
        patient_id=patient_id,
        outpatient_no=f"OP-{patient_id:06d}",
        surname=surname,
        other_names=other_names,
        sex="Female",
        date_of_birth=date(1990, 1, 1),
    )
    db.add(p)
    db.commit()
    return p


def _provider(db, name="Test Insurance"):
    p = db.query(InsuranceProvider).filter(InsuranceProvider.name == name).first()
    if p:
        return p
    p = InsuranceProvider(name=name, is_active=True)
    db.add(p)
    db.commit()
    return p


# ─── Claim schedule lifecycle ───────────────────────────────────────────────

def test_claim_submit_posts_ar_to_insurance_ar(db):
    provider = _provider(db)
    sched = ClaimSchedule(
        schedule_number="CLM-TEST-0001",
        provider_id=provider.provider_id,
        period_from=date.today(),
        period_to=date.today(),
        total_amount=Decimal("5000"),
        status="draft",
        created_by=1,
    )
    db.add(sched)
    db.flush()
    db.add(ClaimScheduleItem(
        schedule_id=sched.schedule_id,
        amount_claimed=Decimal("5000"),
        patient_name="Patient A",
    ))
    db.commit()

    # Simulate the submit endpoint's posting call.
    entry = post_from_event(
        db,
        user_id=1,
        source_key="insurance.claim.submitted",
        source_id=sched.schedule_id,
        amount=sched.total_amount,
        reference=sched.schedule_number,
    )
    db.commit()

    assert entry is not None
    dr = next(l for l in entry.lines if l.debit > 0)
    cr = next(l for l in entry.lines if l.credit > 0)
    assert dr.account_id == account_id(db, "1150")  # Insurance Receivable
    assert cr.account_id == account_id(db, "1140")  # Accounts Receivable
    assert dr.debit == Decimal("5000.0000")


def test_claim_settled_posts_bank_against_insurance_ar(db):
    provider = _provider(db)
    sched = ClaimSchedule(
        schedule_number="CLM-TEST-0002",
        provider_id=provider.provider_id,
        period_from=date.today(),
        period_to=date.today(),
        total_amount=Decimal("3000"),
        status="submitted",
        created_by=1,
        submitted_at=datetime.utcnow(),
    )
    db.add(sched)
    db.commit()

    entry = post_from_event(
        db,
        user_id=1,
        source_key="insurance.claim.settled",
        source_id=sched.schedule_id,
        amount=Decimal("2800"),  # partial settlement
        reference="EFT-12345",
    )
    db.commit()

    assert entry is not None
    dr = next(l for l in entry.lines if l.debit > 0)
    cr = next(l for l in entry.lines if l.credit > 0)
    assert dr.account_id == account_id(db, "1120")  # Bank
    assert cr.account_id == account_id(db, "1150")  # Insurance Receivable
    assert dr.debit == Decimal("2800.0000")


# ─── Client deposits ────────────────────────────────────────────────────────

def test_deposit_received_posts_cash_to_patient_deposits(db):
    _patient(db)
    dep = ClientDeposit(
        deposit_number="DEP-TEST-0001",
        patient_id=1,
        deposit_date=date.today(),
        amount=Decimal("4000"),
        amount_applied=Decimal("0"),
        method="Cash",
        status="available",
        received_by=1,
    )
    db.add(dep)
    db.commit()

    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.deposit.received",
        source_id=dep.deposit_id,
        amount=dep.amount,
        reference=dep.deposit_number,
    )
    db.commit()

    assert entry is not None
    dr = next(l for l in entry.lines if l.debit > 0)
    cr = next(l for l in entry.lines if l.credit > 0)
    assert dr.account_id == account_id(db, "1110")  # Cash
    assert cr.account_id == account_id(db, "2170")  # Patient Deposits liability


def test_deposit_applied_clears_liability_against_ar(db):
    _patient(db)
    entry = post_from_event(
        db,
        user_id=1,
        source_key="billing.deposit.applied",
        source_id=999,
        amount=Decimal("1500"),
        reference="DEP-XYZ",
    )
    db.commit()

    assert entry is not None
    dr = next(l for l in entry.lines if l.debit > 0)
    cr = next(l for l in entry.lines if l.credit > 0)
    assert dr.account_id == account_id(db, "2170")  # Patient Deposits liability
    assert cr.account_id == account_id(db, "1140")  # AR


# ─── Model invariants ───────────────────────────────────────────────────────

def test_deposit_negative_amount_rejected(db):
    _patient(db)
    db.add(ClientDeposit(
        deposit_number="DEP-NEG-0001",
        patient_id=1,
        deposit_date=date.today(),
        amount=Decimal("-50"),
        amount_applied=Decimal("0"),
        method="Cash",
        status="available",
        received_by=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deposit_applied_exceeding_amount_rejected(db):
    _patient(db)
    db.add(ClientDeposit(
        deposit_number="DEP-OVER-0001",
        patient_id=1,
        deposit_date=date.today(),
        amount=Decimal("100"),
        amount_applied=Decimal("150"),
        method="Cash",
        status="fully_applied",
        received_by=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
