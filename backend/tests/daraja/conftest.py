"""Shared fixtures for the tests/daraja package.

Two responsibilities:

1. Import-only model registration (Task 4). Instantiating any mapped ORM
   model is the first thing in the process to trigger SQLAlchemy's
   configure_mappers(), which resolves every relationship() string
   reference across the whole declarative registry, not just the class
   being touched. MpesaTransaction.invoice is a string reference to
   Invoice, and Invoice in turn references Patient and Appointment by
   string, so the whole graph has to be importable before any test builds
   a real row.

2. (Task 5) A real, isolated Postgres database for tests that need working
   Invoice/Payment/MpesaTransaction rows with their foreign keys and CHECK
   constraints enforced: the settlement cross-check and the ledger posting
   it triggers are exactly the kind of logic a mocked session would let
   slip past unnoticed. This mirrors tests/accounting/conftest.py's pattern
   (its own throwaway database, real Postgres, Base.metadata.create_all,
   truncate-and-reseed between tests) rather than SQLite, for the same
   reason that file gives: production is Postgres, and this package already
   has a Postgres-only test (the callback-token pair CHECK constraint in
   test_schema.py) that would not parse under SQLite anyway.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator, Optional

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Full model graph: Base.metadata.create_all needs every table that any FK
# points at (Invoice -> Appointment, JournalEntry -> User, ...), and
# configure_mappers() needs every relationship() target importable before
# the first real model instance is built anywhere in this package.
import app.models.master as _master                       # noqa: F401
import app.models.user as _user                            # noqa: F401
import app.models.patient as _patient                      # noqa: F401
import app.models.billing as _billing                      # noqa: F401
import app.models.clinical as _clinical                    # noqa: F401
import app.models.inventory as _inventory                  # noqa: F401
import app.models.wards as _wards                          # noqa: F401
import app.models.laboratory as _laboratory                # noqa: F401
import app.models.radiology as _radiology                  # noqa: F401
import app.models.medical_history as _med_history          # noqa: F401
import app.models.audit as _audit                          # noqa: F401
import app.models.auth_tokens as _auth_tokens              # noqa: F401
import app.models.idempotency as _idempotency              # noqa: F401
import app.models.notification as _notification            # noqa: F401
import app.models.messaging as _messaging                  # noqa: F401
import app.models.settings as _settings                    # noqa: F401
import app.models.referral as _referral                    # noqa: F401
import app.models.cheque as _cheque                        # noqa: F401
import app.models.support as _support                      # noqa: F401
import app.models.accounting as _accounting                # noqa: F401
# tests/daraja/test_master_schema.py imports app.models.platform_mpesa
# (a master-only model, per the design doc's precedent) in the same pytest
# session; its subscription_invoice_id FK needs subscription_invoices
# registered too, or Base.metadata.create_all below fails to resolve it
# regardless of whether this package's own tests ever touch that table.
import app.models.subscription_billing as _subscription_billing  # noqa: F401
from app.config.database import Base
from app.models.accounting import Account, AccountingSettings, LedgerMapping
from app.models.billing import Invoice
from app.models.mpesa import MpesaConfig, MpesaRefund, MpesaTransaction  # noqa: F401
from app.models.mpesa_events import MpesaEvent  # noqa: F401
from app.models.patient import Patient  # noqa: F401
from app.utils.encryption import encrypt_data
from app.services.daraja.tokens import mint_callback_token, store_callback_token


def _resolve_test_db_url() -> str:
    """Pick the test DB URL. Defaults to a dedicated DB on the local
    Postgres; overridable via DARAJA_TEST_DB_URL for CI."""
    if os.environ.get("DARAJA_TEST_DB_URL"):
        return os.environ["DARAJA_TEST_DB_URL"]
    base = os.environ.get(
        "DATABASE_URL", "postgresql://medifleet:medifleet@localhost:5432/hms_master"
    )
    prefix, _ = base.rsplit("/", 1)
    return f"{prefix}/hms_daraja_test"


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
    Base.metadata.create_all(bind=engine)

    # Stub Role + User so created_by/updated_by FKs (Invoice, JournalEntry,
    # MpesaConfig) resolve.
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO roles (role_id, name, description) "
            "SELECT 1, 'Admin', 'Test admin role' "
            "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE role_id = 1)"
        ))
        conn.execute(text(
            "INSERT INTO users (user_id, email, full_name, hashed_password, role_id) "
            "SELECT 1, 'daraja.test@hms.local', 'Daraja Test User', 'x', 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 1)"
        ))
        conn.commit()

    try:
        yield engine
    finally:
        engine.dispose()
        _drop_db(url)


@pytest.fixture
def db(_engine) -> Iterator[Session]:
    """Per-test session against the isolated Postgres test DB.

    Truncates the tables Task 5's tests touch between runs. Deliberately
    does NOT seed a `billing.payment.mpesa` LedgerMapping by default (see
    `seed_mpesa_ledger_mapping` below for the one test that wants a real
    ledger write): app/services/accounting_posting.py's post_from_event
    documents "Never raises", but when a mapping IS configured and no
    user_id is supplied (exactly the shape of a webhook-triggered
    settlement, since apply_stk_callback has no human actor to attribute
    the entry to), the failed NOT NULL insert on acc_journal_entries.created_by
    leaves the SQLAlchemy session in a PendingRollbackError state even after
    its own SAVEPOINT rollback, and the caller's next commit raises. That is
    a pre-existing gap in shared accounting code, not something introduced or
    fixed here; see the Task 5 report. Most tests below exercise the safe,
    common state instead
    (no mapping configured for this source_key), matching most tenants who
    have not wired billing.payment.mpesa into their Chart of Accounts yet.
    """
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    for tbl in [
        "acc_journal_lines", "acc_journal_entries", "acc_fiscal_periods",
        "acc_ledger_mappings", "acc_accounts", "acc_settings",
        "mpesa_events", "mpesa_refunds", "mpesa_transactions", "mpesa_configs",
        "payments", "invoice_items", "invoices",
        # Task 10 (platform Daraja / subscription rail): CASCADE handles the
        # FK ordering (invoice_payments/platform_mpesa_transactions ->
        # subscription_invoices -> subscriptions/tenants), so listing order
        # here doesn't matter, only that every table a test in this package
        # might touch gets reset between tests.
        "invoice_payments", "dunning_events", "subscription_invoices",
        "subscriptions", "platform_mpesa_transactions", "platform_mpesa_configs",
        "tenants",
    ]:
        try:
            session.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))
        except Exception:
            session.rollback()
    session.commit()

    try:
        yield session
    finally:
        session.close()


def seed_mpesa_ledger_mapping(session: Session) -> tuple[Account, Account]:
    """Add a real, active billing.payment.mpesa LedgerMapping (debit Mobile
    Money 1130, credit Accounts Receivable 1140) plus an AccountingSettings
    row. Only for tests that call settle_invoice_match WITH a real user_id
    (see the db fixture's docstring for why: without one, post_from_event's
    NOT NULL created_by insert fails and poisons the session)."""
    mobile_money = Account(
        code="1130", name="Mobile Money", account_type="Asset", is_postable=True
    )
    receivable = Account(
        code="1140", name="Accounts Receivable", account_type="Asset", is_postable=True
    )
    session.add_all([mobile_money, receivable])
    session.flush()
    session.add(LedgerMapping(
        source_key="billing.payment.mpesa",
        debit_account_id=mobile_money.account_id,
        credit_account_id=receivable.account_id,
        is_active=True,
    ))
    session.add(AccountingSettings(base_currency_code="KES", fiscal_year_start_month=1))
    session.commit()
    return mobile_money, receivable


# ─── Factories ──────────────────────────────────────────────────────────────
# Kept here, not in the test files, so test_stk.py and test_settlement.py
# both build fixtures the same way.


def make_invoice(
    session: Session, *, total_amount, created_by: int = 1, patient_id: Optional[int] = None
) -> Invoice:
    invoice = Invoice(
        total_amount=total_amount, amount_paid=0, status="Pending", created_by=created_by,
        patient_id=patient_id,
    )
    session.add(invoice)
    session.flush()
    return invoice


def make_pending_transaction(
    session: Session,
    *,
    amount,
    invoice_id: Optional[int] = None,
    checkout_request_id: str = "ws_CO_1",
    phone_number: str = "254712345678",
) -> MpesaTransaction:
    txn = MpesaTransaction(
        invoice_id=invoice_id,
        phone_number=phone_number,
        amount=amount,
        checkout_request_id=checkout_request_id,
        merchant_request_id="mr_1",
        status="Pending",
        transaction_type="STK",
    )
    session.add(txn)
    session.flush()
    return txn


def make_mpesa_config(session: Session, **overrides) -> MpesaConfig:
    """A usable MpesaConfig row: real (fake) encrypted creds, a minted
    callback token pair, active."""
    config = MpesaConfig(
        shortcode="174379",
        shortcode_type="paybill",
        environment="sandbox",
        consumer_key_encrypted=encrypt_data("test-consumer-key"),
        consumer_secret_encrypted=encrypt_data("test-consumer-secret"),
        passkey_encrypted=encrypt_data("test-passkey"),
        account_reference="HMS-BILLING",
        transaction_desc="Hospital Bill Payment",
        is_active=True,
    )
    store_callback_token(config, mint_callback_token())
    for key, value in overrides.items():
        setattr(config, key, value)
    session.add(config)
    session.flush()
    return config


def stk_callback_payload(
    *,
    checkout_request_id: str,
    result_code: int = 0,
    amount=None,
    receipt: Optional[str] = None,
    result_desc: str = "The service request is processed successfully.",
) -> dict:
    """Build a callback body shaped like Daraja's real STK callback."""
    stk_callback = {
        "MerchantRequestID": "mr_1",
        "CheckoutRequestID": checkout_request_id,
        "ResultCode": result_code,
        "ResultDesc": result_desc,
    }
    # Daraja sends ResultCode as an int from the STK callback but as a
    # string from STK Query; normalise the same way settlement.py does so
    # result_code="0" (string) still builds a CallbackMetadata block.
    if str(result_code) == "0":
        items = []
        if amount is not None:
            items.append({"Name": "Amount", "Value": float(amount)})
        if receipt is not None:
            items.append({"Name": "MpesaReceiptNumber", "Value": receipt})
        items.append({"Name": "PhoneNumber", "Value": 254712345678})
        stk_callback["CallbackMetadata"] = {"Item": items}
    return {"Body": {"stkCallback": stk_callback}}
