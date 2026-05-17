"""Shared test fixtures for the accounting module.

These fixtures spin up an isolated Postgres DB per test session, apply the
schema with `Base.metadata.create_all`, seed the minimum reference data
the service layer expects (KES base currency + a default CoA + the
default ledger mappings the migrations seed), and yield a SQLAlchemy
session.

Why we don't use SQLite:
- accounting_phase1's `Index(..., postgresql_where=...)` partial unique
  index on the base-currency flag is Postgres-only;
- a couple of the CHECK constraints use Postgres `BETWEEN` semantics that
  SQLite's parser refuses;
- the production DB is Postgres, so test parity matters.

Why we don't use migrate_all_tenants.py:
- it's coupled to the master registry — overkill for an isolated test DB;
- `Base.metadata.create_all` + the seed snippets here give the same
  observable surface in 1/10th the wall clock.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Load backend/.env so DATABASE_URL is available before importing app.* —
# settings.py reads it at module-import time. Make backend/ importable too.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Import every model module so SQLAlchemy's Base.metadata catalogues
# every table — Base.metadata.create_all needs the full graph to resolve
# foreign-key references (invoices→appointments, etc.).
import app.models.master as _master                       # noqa: F401
import app.models.user as _user                            # noqa: F401
import app.models.patient as _patient                      # noqa: F401
import app.models.billing as _billing                      # noqa: F401
# Appointment is defined inside clinical.py (transitive FK from billing).
import app.models.clinical as _clinical                    # noqa: F401
import app.models.inventory as _inventory                  # noqa: F401
import app.models.wards as _wards                          # noqa: F401
import app.models.laboratory as _laboratory                # noqa: F401
import app.models.radiology as _radiology                  # noqa: F401
import app.models.medical_history as _med_history          # noqa: F401
import app.models.audit as _audit                          # noqa: F401
import app.models.auth_tokens as _auth_tokens              # noqa: F401
import app.models.idempotency as _idempotency              # noqa: F401
import app.models.mpesa as _mpesa                          # noqa: F401
import app.models.breach as _breach                        # noqa: F401
import app.models.notification as _notification            # noqa: F401
import app.models.messaging as _messaging                  # noqa: F401
import app.models.settings as _settings                    # noqa: F401
import app.models.referral as _referral                    # noqa: F401
import app.models.cheque as _cheque                        # noqa: F401
import app.models.support as _support                      # noqa: F401
import app.models.accounting as _acc                       # noqa: F401
from app.config.database import Base
from app.models.accounting import (
    Account,
    AccountingSettings,
    Currency,
    LedgerMapping,
)


# Default seed CoA mirrors the migration's DEFAULT_COA. Kept small here —
# tests don't need every account, just a representative slice that covers
# the ledger-mapping defaults.
SEED_ACCOUNTS = [
    # (code, name, type, parent_code, is_postable)
    ("1000", "Assets",                 "Asset",     None,   False),
    ("1100", "Current Assets",         "Asset",     "1000", False),
    ("1110", "Cash on Hand",           "Asset",     "1100", True),
    ("1120", "Bank Accounts",          "Asset",     "1100", True),
    ("1130", "Mobile Money",           "Asset",     "1100", True),
    ("1140", "Accounts Receivable",    "Asset",     "1100", True),
    ("1150", "Insurance Receivable",   "Asset",     "1100", True),
    ("1160", "Inventory Pharmacy",     "Asset",     "1100", True),
    ("2000", "Liabilities",            "Liability", None,   False),
    ("2110", "Accounts Payable",       "Liability", "2000", True),
    ("2170", "Patient Deposits",       "Liability", "2000", True),
    ("3000", "Equity",                 "Equity",    None,   False),
    ("3100", "Owners Capital",         "Equity",    "3000", True),
    ("4000", "Revenue",                "Revenue",   None,   False),
    ("4100", "OP Consultation",        "Revenue",   "4000", True),
    ("4500", "Pharmacy Revenue",       "Revenue",   "4000", True),
    ("4800", "Other Operating Revenue","Revenue",   "4000", True),
    ("5000", "Cost of Services",       "Expense",   None,   False),
    ("5100", "Cost of Drugs Sold",     "Expense",   "5000", True),
    ("6000", "Operating Expenses",     "Expense",   None,   False),
    ("6300", "Utilities",              "Expense",   "6000", True),
]


# Source-key → (debit_code, credit_code). Trimmed to the keys Phase 4
# auto-posting hits in the test suite.
SEED_MAPPINGS = [
    ("billing.invoice.created",    "1140", "4100"),
    ("billing.payment.cash",       "1110", "1140"),
    ("billing.payment.bank",       "1120", "1140"),
    ("billing.payment.mpesa",      "1130", "1140"),
    ("billing.deposit.received",   "1110", "2170"),
    ("billing.deposit.applied",    "2170", "1140"),
    ("pharmacy.dispense.revenue",  "1140", "4500"),
    ("pharmacy.dispense.cogs",     "5100", "1160"),
    ("cheques.deposit.cleared",    "1120", "1140"),
    ("mpesa.receipt.direct",       "1130", "4800"),
    ("insurance.claim.submitted",  "1150", "1140"),
    ("insurance.claim.settled",    "1120", "1150"),
]


def _resolve_test_db_url() -> str:
    """Pick the test DB URL. Defaults to a dedicated DB on the local
    Postgres; overridable via ACCOUNTING_TEST_DB_URL for CI."""
    if os.environ.get("ACCOUNTING_TEST_DB_URL"):
        return os.environ["ACCOUNTING_TEST_DB_URL"]
    base = os.environ.get("DATABASE_URL", "postgresql://medifleet:medifleet@localhost:5432/hms_master")
    # Swap the database name for an isolated test DB.
    prefix, _ = base.rsplit("/", 1)
    return f"{prefix}/hms_accounting_test"


def _create_db_if_missing(url: str) -> None:
    prefix, dbname = url.rsplit("/", 1)
    admin = create_engine(f"{prefix}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            ).fetchone()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        admin.dispose()


def _drop_db(url: str) -> None:
    prefix, dbname = url.rsplit("/", 1)
    admin = create_engine(f"{prefix}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n"
            ), {"n": dbname})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def _engine():
    url = _resolve_test_db_url()
    _create_db_if_missing(url)
    engine = create_engine(url)

    # Create permissions + role_permissions tables we touch indirectly,
    # plus a `users` row so journal entries have a valid created_by FK.
    Base.metadata.create_all(bind=engine)

    # Seed a stub Role + User so created_by FKs resolve.
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO roles (role_id, name, description) "
            "SELECT 1, 'Admin', 'Test admin role' "
            "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE role_id = 1)"
        ))
        conn.execute(text(
            "INSERT INTO users (user_id, email, full_name, hashed_password, role_id) "
            "SELECT 1, 'test.admin@hms.local', 'Test Admin', 'x', 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 1)"
        ))
        conn.commit()

    try:
        yield engine
    finally:
        engine.dispose()
        # Comment out the drop to inspect failures locally.
        _drop_db(url)


@pytest.fixture
def db(_engine) -> Iterator[Session]:
    """Per-test session. Truncates accounting tables between tests so each
    test starts from a known seed state without paying the create_all cost
    every time."""
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    # Clean accounting + billing tables between tests.
    for tbl in [
        "acc_bank_transactions", "acc_bank_accounts",
        "acc_deposit_applications", "acc_client_deposits",
        "acc_claim_schedule_items", "acc_claim_schedules",
        "acc_ledger_mappings", "acc_price_list", "acc_medical_schemes",
        "acc_insurance_providers", "acc_suppliers",
        "acc_journal_lines", "acc_journal_entries", "acc_fiscal_periods",
        "acc_fx_rates", "acc_accounts", "acc_settings", "acc_currencies",
        "payments", "invoice_items", "invoices",
    ]:
        try:
            session.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))
        except Exception:
            session.rollback()
    session.commit()

    # Re-seed the minimum: base currency, settings, CoA, ledger mappings.
    session.add(Currency(code="KES", name="Kenyan Shilling", symbol="KSh",
                         decimals=2, is_base=True, is_active=True))
    session.add(AccountingSettings(base_currency_code="KES",
                                   fiscal_year_start_month=1))
    session.flush()
    for code, name, acc_type, parent_code, is_postable in SEED_ACCOUNTS:
        parent_id = None
        if parent_code:
            parent = session.query(Account).filter(Account.code == parent_code).first()
            parent_id = parent.account_id if parent else None
        session.add(Account(code=code, name=name, account_type=acc_type,
                            parent_id=parent_id, is_postable=is_postable, is_active=True))
    session.flush()
    for source_key, dr_code, cr_code in SEED_MAPPINGS:
        dr = session.query(Account).filter(Account.code == dr_code).first()
        cr = session.query(Account).filter(Account.code == cr_code).first()
        session.add(LedgerMapping(
            source_key=source_key,
            debit_account_id=dr.account_id if dr else None,
            credit_account_id=cr.account_id if cr else None,
            is_active=True,
        ))
    session.commit()

    try:
        yield session
    finally:
        session.close()


# Helpers for tests — keep them out of the test files so each file stays
# focused on assertions.

def account_id(db: Session, code: str) -> int:
    a = db.query(Account).filter(Account.code == code).first()
    assert a is not None, f"Test seed missing account {code}"
    return a.account_id


def post_simple_entry(db: Session, dr_code: str, cr_code: str, amount,
                      on_date: date = None, *, user_id: int = 1,
                      reference: str = None, memo: str = None,
                      source_key: str = None, source_id: int = None):
    """Convenience: post a balanced 2-line entry directly via the service
    layer. Used everywhere except the dedicated lifecycle tests."""
    from app.services.accounting import create_draft_entry, post_entry

    class _Line:
        def __init__(self, account_id, debit=Decimal(0), credit=Decimal(0), description=None):
            self.account_id = account_id
            self.debit = debit
            self.credit = credit
            self.description = description

    dr = _Line(account_id(db, dr_code), debit=Decimal(str(amount)))
    cr = _Line(account_id(db, cr_code), credit=Decimal(str(amount)))
    entry = create_draft_entry(
        db,
        entry_date=on_date or date.today(),
        currency_code="KES",
        fx_rate=None,
        lines_in=[dr, cr],
        user_id=user_id,
        memo=memo,
        reference=reference,
        source_type=source_key,
        source_id=source_id,
    )
    post_entry(db, entry.entry_id, user_id)
    db.commit()
    db.refresh(entry)
    return entry
