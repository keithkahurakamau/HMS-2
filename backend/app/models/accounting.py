"""
Managerial Accounting — double-entry ledger primitives.

Tenant-scoped (no master-DB tables). Built so the rest of HMS can post
to the ledger without knowing the implementation:

  * `Currency` + `FxRate` — multi-currency support; every journal entry
    carries an entry-currency + an fx_rate snapshot so historical
    revaluation doesn't break old reports.
  * `Account` — chart of accounts. Hierarchical via `parent_id`; only
    leaf accounts (`is_postable=True`) accept journal lines.
  * `FiscalPeriod` — months are locked once closed; the post service
    refuses to write into a closed period.
  * `JournalEntry` + `JournalLine` — header/lines split, balance is
    enforced at the service layer in base currency, not entry currency.
  * `AccountingSettings` — per-tenant config: base currency, go-live
    date (no auto-posting before this), fiscal year start month.

The invariants (balanced entries, no posting to closed periods, posted
entries immutable) live in `app.services.accounting`, not here.
"""
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, ForeignKey,
    Numeric, Text, UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


# ─── Currency ────────────────────────────────────────────────────────────────

class Currency(Base):
    """ISO-4217 currency codes a tenant has chosen to transact in."""
    __tablename__ = "acc_currencies"

    currency_id = Column(Integer, primary_key=True)
    code = Column(String(3), unique=True, nullable=False, index=True)
    name = Column(String(80), nullable=False)
    symbol = Column(String(8), nullable=True)
    decimals = Column(Integer, nullable=False, default=2)
    is_base = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Only one base currency per tenant. Postgres supports partial
        # unique indexes which we use here.
        Index(
            "uq_acc_currencies_one_base",
            "is_base",
            unique=True,
            postgresql_where=Column("is_base") == True,  # noqa: E712
        ),
    )


class FxRate(Base):
    """Exchange rate from→to on a given effective_date.

    Stored sparsely — record a rate when it changes; the service layer
    picks the most recent rate <= the entry's posting date.
    """
    __tablename__ = "acc_fx_rates"

    fx_rate_id = Column(Integer, primary_key=True)
    from_currency = Column(String(3), nullable=False, index=True)
    to_currency = Column(String(3), nullable=False, index=True)
    rate = Column(Numeric(20, 10), nullable=False)
    effective_date = Column(Date, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "from_currency", "to_currency", "effective_date",
            name="uq_acc_fx_rates_pair_date",
        ),
        CheckConstraint("rate > 0", name="ck_acc_fx_rates_positive"),
    )


# ─── Chart of Accounts ────────────────────────────────────────────────────────

# Account types map to the side of the ledger they normally sit on.
# Stored as text so we don't need an enum type that's painful to migrate.
ACCOUNT_TYPES = ("Asset", "Liability", "Equity", "Revenue", "Expense")


class Account(Base):
    """Chart of Accounts entry. Hierarchical via `parent_id`.

    Postable vs. non-postable: a roll-up account ('Current Assets')
    can't receive journal lines directly — only its leaf children can.
    The UI hides postable=False from the line-picker.
    """
    __tablename__ = "acc_accounts"

    account_id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(160), nullable=False, index=True)
    account_type = Column(String(20), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("acc_accounts.account_id", ondelete="RESTRICT"), nullable=True, index=True)
    currency_code = Column(String(3), nullable=True)  # Null = base currency
    is_postable = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    parent = relationship("Account", remote_side=[account_id], backref="children")

    __table_args__ = (
        CheckConstraint(
            "account_type IN ('Asset','Liability','Equity','Revenue','Expense')",
            name="ck_acc_accounts_valid_type",
        ),
    )


# ─── Fiscal Periods ───────────────────────────────────────────────────────────

PERIOD_STATUSES = ("open", "closed")


class FiscalPeriod(Base):
    """One row per (year, month). Closed periods reject new postings."""
    __tablename__ = "acc_fiscal_periods"

    period_id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=False)  # 1..12
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(10), nullable=False, default="open", index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_acc_fiscal_periods_year_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_acc_fiscal_periods_month"),
        CheckConstraint("status IN ('open','closed')", name="ck_acc_fiscal_periods_status"),
    )


# ─── Journal Entries ──────────────────────────────────────────────────────────

ENTRY_STATUSES = ("draft", "posted", "reversed")


class JournalEntry(Base):
    """Header for a balanced journal entry.

    Lifecycle: draft → posted → (optionally) reversed.
    Posted entries are immutable. To 'edit', reverse + repost.

    `currency_code` is the entry's reporting currency; `fx_rate` is the
    snapshot of (entry_currency → base_currency) at posting time. Lines
    carry both their original-currency amount and the base-currency
    amount derived from this rate.
    """
    __tablename__ = "acc_journal_entries"

    entry_id = Column(Integer, primary_key=True)
    entry_number = Column(String(40), unique=True, nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    fiscal_period_id = Column(Integer, ForeignKey("acc_fiscal_periods.period_id"), nullable=False, index=True)

    currency_code = Column(String(3), nullable=False)
    fx_rate = Column(Numeric(20, 10), nullable=False, default=1)

    status = Column(String(10), nullable=False, default="draft", index=True)
    memo = Column(Text, nullable=True)
    reference = Column(String(120), nullable=True, index=True)

    # Where this entry came from. NULL for manually-keyed entries; later
    # phases set ('Billing', invoice_id), ('Payment', payment_id), etc.
    source_type = Column(String(40), nullable=True, index=True)
    source_id = Column(Integer, nullable=True, index=True)

    created_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    posted_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    posted_at = Column(DateTime(timezone=True), nullable=True)
    reversed_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reverses_entry_id = Column(Integer, ForeignKey("acc_journal_entries.entry_id"), nullable=True)

    lines = relationship(
        "JournalLine",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalLine.line_number",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','posted','reversed')",
            name="ck_acc_journal_entries_status",
        ),
        CheckConstraint("fx_rate > 0", name="ck_acc_journal_entries_fx_positive"),
    )


class JournalLine(Base):
    """Single debit-or-credit line within a journal entry.

    Per-line invariant: exactly one of (debit, credit) is non-zero.
    Per-entry invariant: sum(debit_base) == sum(credit_base) — enforced
    at the service layer on post, not via a CHECK constraint.
    """
    __tablename__ = "acc_journal_lines"

    line_id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("acc_journal_entries.entry_id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    account_id = Column(Integer, ForeignKey("acc_accounts.account_id"), nullable=False, index=True)

    # Amounts in entry currency.
    debit = Column(Numeric(20, 4), nullable=False, default=0)
    credit = Column(Numeric(20, 4), nullable=False, default=0)
    # Amounts in base currency (entry-currency * fx_rate). Persisted so
    # historical reports stay stable even if rates are restated later.
    debit_base = Column(Numeric(20, 4), nullable=False, default=0)
    credit_base = Column(Numeric(20, 4), nullable=False, default=0)

    description = Column(Text, nullable=True)

    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")

    __table_args__ = (
        CheckConstraint(
            "(debit = 0 AND credit > 0) OR (debit > 0 AND credit = 0) "
            "OR (debit = 0 AND credit = 0)",
            name="ck_acc_journal_lines_dr_xor_cr",
        ),
        UniqueConstraint("entry_id", "line_number", name="uq_acc_journal_lines_entry_line"),
    )


# ─── Settings ────────────────────────────────────────────────────────────────

class AccountingSettings(Base):
    """Per-tenant accounting configuration. Single row enforced by app code."""
    __tablename__ = "acc_settings"

    settings_id = Column(Integer, primary_key=True)
    base_currency_code = Column(String(3), nullable=False, default="KES")
    # Go-live date: auto-posting from other modules ignores anything
    # dated before this. Manual entries are still allowed (admin can
    # key opening balances dated earlier).
    go_live_date = Column(Date, nullable=True)
    fiscal_year_start_month = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "fiscal_year_start_month BETWEEN 1 AND 12",
            name="ck_acc_settings_fy_month",
        ),
    )
