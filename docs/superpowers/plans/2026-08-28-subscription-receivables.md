# Subscription Receivables and Dunning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform able to answer "who owes me, how much, and for how long", then chase it automatically.

**Architecture:** Four tables in the master database record obligations and receipts. Balance and ageing are always derived from those rows, never stored, so they cannot drift. Two idempotent service functions (`ensure_invoices`, `run_dunning`) do all the work and are safe to run repeatedly; a daily Render cron calls them, and a console button calls the same code path. Reminders are written into each tenant's own database, since notifications live there.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Postgres, pytest. React 19, Vite 8, Tailwind 3.4, Vitest with Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-28-subscription-receivables-design.md`

**Branch:** `feat/subscription-receivables` off `development`.

## Global Constraints

- **No em dashes** anywhere, in code, comments, copy or commit messages. Colon, comma, parentheses or full stop.
- **Amounts are KES**, `Numeric(12,2)`. Never float.
- **Balance and ageing are derived**, never stored columns.
- **Notify only.** Nothing in this plan may restrict, downgrade or suspend a tenant automatically. Suspension stays a manual operator action.
- **Idempotency is the core property.** Every service function must be safe to run any number of times per day. This is what the tests exist to prove.
- **One tenant must never break the run.** Every per-tenant operation is wrapped; a failure is logged and skipped, and its `DunningEvent` is not written so the next run retries it.
- **Master-DB tables only.** These four tables live in `hms_master`, not in tenant databases.
- **Alembic head is `b2c3d4e5f6a7`.** The new revision's `down_revision` must be exactly that.
- Backend tests must land in a directory CI runs. CI currently runs only `pytest tests/accounting/ -q` and `pytest tests/email/ -q`, so Task 3 adds `tests/receivables/` to the workflow.

## Commands

```bash
# backend, from backend/
venv/bin/pytest tests/receivables/ -q
venv/bin/alembic upgrade head
REDIS_URL="" venv/bin/uvicorn app.main:app --reload   # local run

# frontend, from frontend/
npx vitest run --no-file-parallelism    # serial: the full suite OOMs on this machine in parallel
npm run lint
npm run build
```

## File Structure

**Backend, created:**
- `app/models/subscription_billing.py`: the four tables. Nothing else.
- `app/services/subscription_billing.py`: `ensure_invoices`, `run_dunning`, and the pure helpers. All the logic.
- `app/routes/receivables.py`: superadmin HTTP surface. Thin, delegates to the service.
- `app/schemas/receivables.py`: request and response models.
- `app/cli/run_billing.py`: the cron entry point. Calls the service and exits non-zero on failure.
- `alembic/versions/c3d4e5f6a7b8_subscription_receivables.py`: master-only, idempotent.
- `tests/receivables/conftest.py` and four test modules.

**Backend, modified:**
- `scripts/migrate_all_tenants.py`: model import block, plus `MASTER_DB_PATCHES`.
- `app/main.py`: include the new router.
- `render.yaml`: the daily cron service.
- `.github/workflows/ci.yml`: run the new test directory.

**Frontend, created:**
- `src/pages/superadmin/Receivables.jsx`: the page.
- `src/pages/superadmin/receivables/AgeingTable.jsx` and `TenantDrawer.jsx`: split from the start, since the page owns two distinct surfaces.
- `src/api/receivables.js`: the API wrapper.
- Test files alongside each.

**Frontend, modified:**
- `src/App.jsx`: the route.
- `src/components/layouts/SuperAdminLayout.jsx`: the nav entry.
- `src/pages/superadmin/SuperAdminDashboard.jsx`: the collected-this-month figure.

---

## Task 1: The four tables

**Files:**
- Create: `backend/app/models/subscription_billing.py`
- Do not modify: `backend/scripts/migrate_all_tenants.py` (see Step 2)

**Interfaces:**
- Produces: `Subscription`, `SubscriptionInvoice`, `InvoicePayment`, `DunningEvent` importable from `app.models.subscription_billing`.

- [ ] **Step 1: Write the model module**

```python
"""Operator-side receivables: what each hospital owes MediFleet, and what
has been received against it.

These four tables live in the MASTER database only. Tenant databases never
see them: a hospital does not need to know how the platform bills it.

Balance and ageing are deliberately NOT columns. They are derived from the
payment rows, because a stored total is a second source of truth that
drifts the first time a payment is corrected.
"""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
    Text, UniqueConstraint, func,
)

from app.config.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), unique=True, nullable=False, index=True)
    plan = Column(String(20), nullable=False, default="standard")
    # The agreed price, copied onto each invoice at issue time. Stored rather
    # than read from TIER_PRICING so a negotiated rate survives a change to
    # the public price list, and so an invoice can always be explained.
    price_kes = Column(Numeric(12, 2), nullable=False, default=0)
    cycle = Column(String(10), nullable=False, default="monthly")
    status = Column(String(20), nullable=False, default="active")
    started_on = Column(Date, nullable=False)
    # The idempotency key for generation: an invoice is raised only when this
    # date has arrived, and the date advances as part of the same transaction.
    next_invoice_on = Column(Date, nullable=False)
    reminders_paused = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SubscriptionInvoice(Base):
    __tablename__ = "subscription_invoices"
    __table_args__ = (
        # The guard that makes generation safe to run repeatedly.
        UniqueConstraint("subscription_id", "period_start", name="uq_invoice_period"),
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False, index=True)
    number = Column(String(20), unique=True, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    amount_kes = Column(Numeric(12, 2), nullable=False)
    issued_on = Column(Date, nullable=False)
    due_on = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    void_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvoicePayment(Base):
    __tablename__ = "invoice_payments"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("subscription_invoices.id"), nullable=False, index=True)
    # Set when an M-Pesa receipt settled this. Null for manual entries.
    platform_transaction_id = Column(Integer, nullable=True)
    amount_kes = Column(Numeric(12, 2), nullable=False)
    paid_on = Column(Date, nullable=False)
    # A waiver is a payment, not a deletion: the invoice closes and the
    # write-off stays visible and attributable.
    method = Column(String(20), nullable=False, default="mpesa")
    recorded_by = Column(Integer, ForeignKey("superadmins.admin_id"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DunningEvent(Base):
    __tablename__ = "dunning_events"
    __table_args__ = (
        # Stops a hospital being reminded twice for the same milestone,
        # however often the job runs.
        UniqueConstraint("invoice_id", "day_offset", name="uq_dunning_milestone"),
    )

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("subscription_invoices.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    day_offset = Column(Integer, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    recipients = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 2: Do NOT add the module to the migrate script's import block**

This is the opposite of the rule for tenant models, and getting it backwards is
load-bearing. That import list feeds `Base.metadata`, and the script runs an
unfiltered `Base.metadata.create_all()` against every tenant engine, so anything
in the list is physically created in every hospital database. `platform_payhero`,
the existing master-only precedent, is deliberately absent from the list for
exactly this reason. Master-only tables are bootstrapped by `MASTER_DB_PATCHES`
in Task 2 instead. Leave `scripts/migrate_all_tenants.py` untouched in this task.

- [ ] **Step 3: Verify the models import and the metadata is complete**

Run:
```bash
cd backend && venv/bin/python -c "
import app.models.subscription_billing as m
from app.config.database import Base
names = {'subscriptions','subscription_invoices','invoice_payments','dunning_events'}
assert names <= set(Base.metadata.tables), sorted(names - set(Base.metadata.tables))
print('all four tables registered in metadata')
"
```
Expected: `all four tables registered in metadata`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/subscription_billing.py
git commit -m "feat(billing): subscription, invoice, payment and dunning tables"
```

---

## Task 2: Migration and backfill

**Files:**
- Create: `backend/alembic/versions/c3d4e5f6a7b8_subscription_receivables.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (`MASTER_DB_PATCHES`, line 84)

**Interfaces:**
- Consumes: the models from Task 1.
- Produces: the four tables in `hms_master`, plus a `Subscription` row for every existing tenant.

Follow `alembic/versions/ab3c9e5d27f8_platform_payhero.py`: master-only, guarded by `_has_table`, idempotent.

- [ ] **Step 1: Write the revision**

```python
"""Subscription receivables: subscriptions, invoices, payments, dunning.

Master-DB only. Tenant databases are untouched: a hospital does not need to
know how the platform bills it. Every statement is guarded so re-running on
an already-migrated master DB is a no-op.

Includes a backfill creating a Subscription for every existing tenant.
Without it, hospitals that predate this feature are never invoiced.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-28 21:00:00.000000
"""
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIER_PRICING = {"premium": 49500, "standard": 15000}


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    # Master-only: the tenants table is the marker for the master DB.
    if not _has_table(bind, "tenants"):
        return

    if not _has_table(bind, "subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.tenant_id"), nullable=False, unique=True),
            sa.Column("plan", sa.String(20), nullable=False, server_default="standard"),
            sa.Column("price_kes", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("cycle", sa.String(10), nullable=False, server_default="monthly"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("started_on", sa.Date(), nullable=False),
            sa.Column("next_invoice_on", sa.Date(), nullable=False),
            sa.Column("reminders_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_table(bind, "subscription_invoices"):
        op.create_table(
            "subscription_invoices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.tenant_id"), nullable=False, index=True),
            sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False, index=True),
            sa.Column("number", sa.String(20), nullable=False, unique=True),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("amount_kes", sa.Numeric(12, 2), nullable=False),
            sa.Column("issued_on", sa.Date(), nullable=False),
            sa.Column("due_on", sa.Date(), nullable=False, index=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="open", index=True),
            sa.Column("void_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("subscription_id", "period_start", name="uq_invoice_period"),
        )

    if not _has_table(bind, "invoice_payments"):
        op.create_table(
            "invoice_payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("subscription_invoices.id"), nullable=False, index=True),
            sa.Column("platform_transaction_id", sa.Integer(), nullable=True),
            sa.Column("amount_kes", sa.Numeric(12, 2), nullable=False),
            sa.Column("paid_on", sa.Date(), nullable=False),
            sa.Column("method", sa.String(20), nullable=False, server_default="mpesa"),
            sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("superadmins.admin_id"), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not _has_table(bind, "dunning_events"):
        op.create_table(
            "dunning_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("subscription_invoices.id"), nullable=False, index=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.tenant_id"), nullable=False, index=True),
            sa.Column("day_offset", sa.Integer(), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("recipients", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("invoice_id", "day_offset", name="uq_dunning_milestone"),
        )

    # Backfill: one subscription per existing tenant, priced from its tier,
    # anchored to its creation date, next invoice on the first of next month.
    today = date.today()
    nxt = date(today.year + (today.month // 12), (today.month % 12) + 1, 1)
    bind.execute(
        sa.text(
            """
            INSERT INTO subscriptions
                (tenant_id, plan, price_kes, cycle, status, started_on, next_invoice_on, reminders_paused)
            SELECT t.tenant_id,
                   CASE WHEN t.is_premium THEN 'premium' ELSE 'standard' END,
                   CASE WHEN t.is_premium THEN :premium ELSE :standard END,
                   'monthly',
                   CASE WHEN t.is_active THEN 'active' ELSE 'paused' END,
                   COALESCE(t.created_at::date, :today),
                   :nxt,
                   FALSE
            FROM tenants t
            WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.tenant_id)
            """
        ),
        {"premium": TIER_PRICING["premium"], "standard": TIER_PRICING["standard"],
         "today": today, "nxt": nxt},
    )


def downgrade() -> None:
    for table in ("dunning_events", "invoice_payments", "subscription_invoices", "subscriptions"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
```

- [ ] **Step 2: Mirror the schema into MASTER_DB_PATCHES**

`migrate_all_tenants.py` runs Alembic per tenant database only; master-DB schema is bootstrapped separately. Append to `MASTER_DB_PATCHES` (line 84), following the existing `platform_payhero_configs` entries: four `CREATE TABLE IF NOT EXISTS` statements matching the columns above exactly, then the indexes:

```python
    "CREATE INDEX IF NOT EXISTS ix_sub_invoice_tenant ON subscription_invoices (tenant_id);",
    "CREATE INDEX IF NOT EXISTS ix_sub_invoice_due    ON subscription_invoices (due_on);",
    "CREATE INDEX IF NOT EXISTS ix_invoice_payment_inv ON invoice_payments (invoice_id);",
    "CREATE INDEX IF NOT EXISTS ix_dunning_invoice    ON dunning_events (invoice_id);",
```

- [ ] **Step 3: Verify against a real database**

Run: `cd backend && venv/bin/alembic upgrade head`
Then:
```bash
venv/bin/python -c "
from app.config.database import get_master_db
from sqlalchemy import text
db = next(get_master_db())
n = db.execute(text('SELECT count(*) FROM subscriptions')).scalar()
t = db.execute(text('SELECT count(*) FROM tenants')).scalar()
print(f'subscriptions={n} tenants={t}')
assert n == t, 'every tenant must have exactly one subscription'
print('backfill correct')
"
```
Expected: subscriptions equals tenants, and `backfill correct`.

- [ ] **Step 4: Prove it is idempotent**

Run `venv/bin/alembic upgrade head` again, then re-run the check from Step 3. Expected: identical counts, no error.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/c3d4e5f6a7b8_subscription_receivables.py backend/scripts/migrate_all_tenants.py
git commit -m "feat(billing): master-DB migration and per-tenant subscription backfill"
```

---

## Task 3: Test harness

**Files:**
- Create: `backend/tests/receivables/__init__.py`, `backend/tests/receivables/conftest.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a `master_db` pytest fixture yielding a Session against an isolated Postgres with the four tables plus `tenants` and `superadmins`, and a `make_tenant` factory.

Model on `backend/tests/accounting/conftest.py`: real Postgres, `Base.metadata.create_all`, no reliance on the migrate script.

- [ ] **Step 1: Write the conftest**

```python
"""Fixtures for the receivables suite.

Real Postgres rather than SQLite, matching tests/accounting: the production
database is Postgres and Numeric semantics differ enough to matter when the
subject is money.
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

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.models.master as _master                       # noqa: F401,E402
import app.models.user as _user                           # noqa: F401,E402
import app.models.notification as _notification           # noqa: F401,E402
import app.models.subscription_billing as _sub            # noqa: F401,E402
from app.config.database import Base                      # noqa: E402
from app.models.master import Tenant                      # noqa: E402
from app.models.subscription_billing import Subscription   # noqa: E402

TEST_DB = os.getenv("RECEIVABLES_TEST_DB", "hms_receivables_test")


@pytest.fixture(scope="session")
def engine():
    admin_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{TEST_DB}"
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def master_db(engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine)()
    yield session
    session.rollback()
    # Order matters: children before parents.
    for table in ("dunning_events", "invoice_payments", "subscription_invoices",
                  "subscriptions", "tenants"):
        session.execute(text(f"DELETE FROM {table}"))
    session.commit()
    session.close()


@pytest.fixture()
def make_tenant(master_db):
    """Create a tenant with an active subscription. Returns (tenant, subscription)."""
    def _make(name="Test Hospital", price=Decimal("15000.00"),
              started=date(2026, 1, 1), next_on=date(2026, 8, 1), paused=False):
        t = Tenant(name=name, domain=f"{name.lower().replace(' ', '')}.test",
                   db_name=f"db_{name.lower().replace(' ', '_')}", is_active=True)
        master_db.add(t)
        master_db.flush()
        s = Subscription(tenant_id=t.tenant_id, plan="standard", price_kes=price,
                         cycle="monthly", status="active", started_on=started,
                         next_invoice_on=next_on, reminders_paused=paused)
        master_db.add(s)
        master_db.commit()
        return t, s
    return _make
```

- [ ] **Step 2: Add the suite to CI**

In `.github/workflows/ci.yml`, beside the existing accounting and email steps, add:

```yaml
      - name: Backend receivables tests
        working-directory: backend
        run: pytest tests/receivables/ -q
```

- [ ] **Step 3: Prove the harness works**

Create `backend/tests/receivables/test_harness.py`:

```python
from decimal import Decimal


def test_fixture_creates_tenant_and_subscription(make_tenant, master_db):
    tenant, sub = make_tenant(price=Decimal("49500.00"))
    assert tenant.tenant_id is not None
    assert sub.tenant_id == tenant.tenant_id
    assert sub.price_kes == Decimal("49500.00")
    assert sub.status == "active"
```

Run: `cd backend && venv/bin/pytest tests/receivables/ -q`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/receivables .github/workflows/ci.yml
git commit -m "test(billing): receivables test harness, gated in CI"
```

---

## Task 4: Balance and ageing

**Files:**
- Create: `backend/app/services/subscription_billing.py`
- Create: `backend/tests/receivables/test_derived.py`

**Interfaces:**
- Produces:
  - `outstanding_balance(db: Session, invoice: SubscriptionInvoice) -> Decimal`
  - `ageing_bucket(days_overdue: int) -> str` returning one of `current`, `1-30`, `31-60`, `61-90`, `90+`
  - `days_overdue(invoice: SubscriptionInvoice, as_of: date) -> int`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from decimal import Decimal

import pytest

from app.services.subscription_billing import ageing_bucket, days_overdue, outstanding_balance
from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice


@pytest.mark.parametrize("days,expected", [
    (0, "current"), (1, "1-30"), (30, "1-30"), (31, "31-60"), (60, "31-60"),
    (61, "61-90"), (90, "61-90"), (91, "90+"), (365, "90+"),
])
def test_ageing_bucket_boundaries(days, expected):
    assert ageing_bucket(days) == expected


def test_bucket_treats_not_yet_due_as_current():
    assert ageing_bucket(-5) == "current"


def _invoice(master_db, sub, tenant, amount="15000.00", due=date(2026, 8, 1)):
    inv = SubscriptionInvoice(
        tenant_id=tenant.tenant_id, subscription_id=sub.id, number="MF-2026-0001",
        period_start=due, period_end=date(2026, 8, 31), amount_kes=Decimal(amount),
        issued_on=due, due_on=due, status="open",
    )
    master_db.add(inv)
    master_db.commit()
    return inv


def test_balance_is_amount_when_nothing_paid(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    assert outstanding_balance(master_db, inv) == Decimal("15000.00")


def test_balance_subtracts_every_allocation(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    master_db.add_all([
        InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("5000.00"), paid_on=date(2026, 8, 2), method="mpesa"),
        InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("2500.00"), paid_on=date(2026, 8, 5), method="bank"),
    ])
    master_db.commit()
    assert outstanding_balance(master_db, inv) == Decimal("7500.00")


def test_a_waiver_closes_the_balance_like_any_payment(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant)
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=Decimal("15000.00"),
                                 paid_on=date(2026, 8, 9), method="waiver", note="goodwill"))
    master_db.commit()
    assert outstanding_balance(master_db, inv) == Decimal("0.00")


def test_days_overdue_counts_from_due_date(master_db, make_tenant):
    tenant, sub = make_tenant()
    inv = _invoice(master_db, sub, tenant, due=date(2026, 8, 1))
    assert days_overdue(inv, date(2026, 8, 1)) == 0
    assert days_overdue(inv, date(2026, 8, 15)) == 14
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && venv/bin/pytest tests/receivables/test_derived.py -q`
Expected: FAIL, `ModuleNotFoundError: app.services.subscription_billing`.

- [ ] **Step 3: Implement**

```python
"""Subscription receivables: invoice generation and dunning.

Everything here is idempotent. Both entry points may be called any number of
times a day, by the cron and by the operator's button, and must converge on
the same state. The tests exist mainly to prove that property.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.subscription_billing import (
    DunningEvent, InvoicePayment, Subscription, SubscriptionInvoice,
)

logger = logging.getLogger("subscription_billing")

MILESTONES = (1, 7, 14, 30)


def outstanding_balance(db: Session, invoice: SubscriptionInvoice) -> Decimal:
    """Amount still owed. Derived, never stored: a cached total is a second
    source of truth that drifts the first time a payment is corrected."""
    paid = db.query(func.coalesce(func.sum(InvoicePayment.amount_kes), 0)).filter(
        InvoicePayment.invoice_id == invoice.id
    ).scalar()
    return Decimal(invoice.amount_kes) - Decimal(paid)


def days_overdue(invoice: SubscriptionInvoice, as_of: date) -> int:
    return (as_of - invoice.due_on).days


def ageing_bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && venv/bin/pytest tests/receivables/test_derived.py -q`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_billing.py backend/tests/receivables/test_derived.py
git commit -m "feat(billing): derived balance and ageing buckets"
```

---

## Task 5: Invoice generation

**Files:**
- Modify: `backend/app/services/subscription_billing.py`
- Create: `backend/tests/receivables/test_generation.py`

**Interfaces:**
- Consumes: `outstanding_balance` from Task 4.
- Produces: `ensure_invoices(db: Session, as_of: date) -> list[SubscriptionInvoice]`, and `next_number(db: Session, on: date) -> str` returning `MF-YYYY-NNNN`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from decimal import Decimal

from app.models.subscription_billing import SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices


def test_raises_an_invoice_when_the_date_has_arrived(master_db, make_tenant):
    tenant, sub = make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    created = ensure_invoices(master_db, date(2026, 8, 1))
    assert len(created) == 1
    inv = created[0]
    assert inv.tenant_id == tenant.tenant_id
    assert inv.amount_kes == Decimal("15000.00")
    # Monthly in advance, due on issue.
    assert inv.issued_on == inv.due_on == date(2026, 8, 1)
    assert inv.period_start == date(2026, 8, 1)
    assert inv.status == "open"


def test_does_not_raise_before_the_date(master_db, make_tenant):
    make_tenant(next_on=date(2026, 9, 1))
    assert ensure_invoices(master_db, date(2026, 8, 20)) == []


def test_running_twice_creates_one_invoice(master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    assert master_db.query(SubscriptionInvoice).count() == 1


def test_catches_up_every_missed_period(master_db, make_tenant):
    # Down since June: June, July and August are all owed.
    make_tenant(next_on=date(2026, 6, 1))
    created = ensure_invoices(master_db, date(2026, 8, 15))
    assert len(created) == 3
    assert [i.period_start for i in created] == [date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 1)]


def test_skips_a_paused_subscription(master_db, make_tenant):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1))
    sub.status = "paused"
    master_db.commit()
    assert ensure_invoices(master_db, date(2026, 8, 1)) == []


def test_numbers_are_unique_and_sequential(master_db, make_tenant):
    make_tenant(name="A Hospital", next_on=date(2026, 8, 1))
    make_tenant(name="B Hospital", next_on=date(2026, 8, 1))
    created = ensure_invoices(master_db, date(2026, 8, 1))
    numbers = sorted(i.number for i in created)
    assert numbers == ["MF-2026-0001", "MF-2026-0002"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && venv/bin/pytest tests/receivables/test_generation.py -q`
Expected: FAIL, `ImportError: cannot import name 'ensure_invoices'`.

- [ ] **Step 3: Implement**

Append to `app/services/subscription_billing.py`:

```python
def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def _advance_one_month(d: date, billing_day: int) -> date:
    """Next occurrence of the billing day. A subscription anchored to the 31st
    bills on the last day of a shorter month rather than skipping it."""
    year = d.year + (d.month // 12)
    month = (d.month % 12) + 1
    last = _month_end(date(year, month, 1)).day
    return date(year, month, min(billing_day, last))


def next_number(db: Session, on: date) -> str:
    """Sequential within the year: MF-2026-0001."""
    prefix = f"MF-{on.year}-"
    latest = (
        db.query(SubscriptionInvoice.number)
        .filter(SubscriptionInvoice.number.like(f"{prefix}%"))
        .order_by(SubscriptionInvoice.number.desc())
        .first()
    )
    seq = int(latest[0].split("-")[-1]) + 1 if latest else 1
    return f"{prefix}{seq:04d}"


def ensure_invoices(db: Session, as_of: date) -> list[SubscriptionInvoice]:
    """Raise every invoice now due. Safe to run repeatedly: the unique
    constraint on (subscription_id, period_start) is the guard, and
    next_invoice_on advances in the same transaction."""
    created: list[SubscriptionInvoice] = []
    subs = db.query(Subscription).filter(
        Subscription.status == "active",
        Subscription.next_invoice_on <= as_of,
    ).all()

    for sub in subs:
        try:
            billing_day = sub.started_on.day
            while sub.next_invoice_on <= as_of:
                period_start = sub.next_invoice_on
                exists = db.query(SubscriptionInvoice).filter(
                    SubscriptionInvoice.subscription_id == sub.id,
                    SubscriptionInvoice.period_start == period_start,
                ).first()
                if not exists:
                    inv = SubscriptionInvoice(
                        tenant_id=sub.tenant_id,
                        subscription_id=sub.id,
                        number=next_number(db, period_start),
                        period_start=period_start,
                        period_end=_month_end(period_start),
                        amount_kes=sub.price_kes,
                        issued_on=period_start,
                        due_on=period_start,      # monthly in advance, due on issue
                        status="open",
                    )
                    db.add(inv)
                    db.flush()
                    created.append(inv)
                sub.next_invoice_on = _advance_one_month(period_start, billing_day)
            db.commit()
        except Exception:
            # One bad subscription must not stop the rest.
            db.rollback()
            logger.exception("Invoice generation failed for subscription %s", sub.id)
    return created
```

Add `from datetime import date, timedelta` to the imports.

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && venv/bin/pytest tests/receivables/test_generation.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_billing.py backend/tests/receivables/test_generation.py
git commit -m "feat(billing): idempotent invoice generation with catch-up"
```

---

## Task 6: Dunning

**Files:**
- Modify: `backend/app/services/subscription_billing.py`
- Create: `backend/tests/receivables/test_dunning.py`

**Interfaces:**
- Consumes: `outstanding_balance`, `days_overdue`, `MILESTONES`.
- Produces:
  - `run_dunning(db: Session, as_of: date, notifier=None) -> list[DunningEvent]`
  - `notify_tenant_admins(tenant_db_name: str, title: str, body: str) -> int` returning how many admins were notified.

`notifier` is injectable so tests do not need a second database. Default is the real cross-database writer.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from decimal import Decimal

from app.models.subscription_billing import DunningEvent, InvoicePayment, SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices, run_dunning


def _overdue(master_db, make_tenant, **kw):
    tenant, sub = make_tenant(next_on=date(2026, 8, 1), **kw)
    ensure_invoices(master_db, date(2026, 8, 1))
    return tenant, sub


def test_sends_at_the_first_milestone(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    sent = []
    events = run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: sent.append(a) or 2)
    assert len(events) == 1
    assert events[0].day_offset == 1
    assert events[0].recipients == 2


def test_nothing_before_the_first_milestone(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    assert run_dunning(master_db, date(2026, 8, 1), notifier=lambda *a, **k: 1) == []


def test_running_twice_sends_once(master_db, make_tenant):
    _overdue(master_db, make_tenant)
    run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 1)
    run_dunning(master_db, date(2026, 8, 2), notifier=lambda *a, **k: 1)
    assert master_db.query(DunningEvent).count() == 1


def test_a_catch_up_run_sends_only_the_highest_milestone(master_db, make_tenant):
    # 45 days late, so 1, 7, 14 and 30 have all passed.
    _overdue(master_db, make_tenant)
    events = run_dunning(master_db, date(2026, 9, 15), notifier=lambda *a, **k: 1)
    assert len(events) == 1, "a month of downtime must not deliver four notifications at once"
    assert events[0].day_offset == 30


def test_a_paid_invoice_is_never_chased(master_db, make_tenant):
    tenant, sub = _overdue(master_db, make_tenant)
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=inv.amount_kes,
                                 paid_on=date(2026, 8, 1), method="mpesa"))
    master_db.commit()
    assert run_dunning(master_db, date(2026, 8, 20), notifier=lambda *a, **k: 1) == []


def test_a_paused_tenant_is_not_chased(master_db, make_tenant):
    tenant, sub = _overdue(master_db, make_tenant)
    sub.reminders_paused = True
    master_db.commit()
    assert run_dunning(master_db, date(2026, 8, 20), notifier=lambda *a, **k: 1) == []


def test_one_failing_tenant_does_not_stop_the_others(master_db, make_tenant):
    make_tenant(name="Good Hospital", next_on=date(2026, 8, 1))
    make_tenant(name="Broken Hospital", next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))

    def flaky(tenant_db_name, *a, **k):
        if "broken" in tenant_db_name:
            raise RuntimeError("database unreachable")
        return 1

    events = run_dunning(master_db, date(2026, 8, 2), notifier=flaky)
    assert len(events) == 1, "the reachable tenant is still notified"
    # The failing tenant has no event, so the next run retries it.
    assert master_db.query(DunningEvent).count() == 1
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && venv/bin/pytest tests/receivables/test_dunning.py -q`
Expected: FAIL, `ImportError: cannot import name 'run_dunning'`.

- [ ] **Step 3: Implement**

```python
def notify_tenant_admins(tenant_db_name: str, title: str, body: str) -> int:
    """Write one notification per Admin user in a tenant's own database.

    Notifications live in the tenant DB, keyed to a tenant user_id, so the
    reminder has to cross databases. Caller wraps this: a tenant we cannot
    reach must not abort the run for everyone else.
    """
    from sqlalchemy.orm import sessionmaker

    from app.config.database import get_tenant_engine
    from app.models.notification import Notification
    from app.models.user import User

    session = sessionmaker(bind=get_tenant_engine(tenant_db_name))()
    try:
        admins = session.query(User).filter(User.role == "Admin", User.is_active == True).all()  # noqa: E712
        for admin in admins:
            session.add(Notification(user_id=admin.user_id, category="warning",
                                     title=title, body=body))
        session.commit()
        return len(admins)
    finally:
        session.close()


def run_dunning(db: Session, as_of: date, notifier=None) -> list[DunningEvent]:
    """Remind the admins of every hospital with an overdue balance.

    Only the highest milestone reached is sent, so a month of downtime does
    not deliver four notifications about one invoice at once.
    """
    from app.models.master import Tenant

    send = notifier or notify_tenant_admins
    events: list[DunningEvent] = []

    rows = (
        db.query(SubscriptionInvoice, Subscription, Tenant)
        .join(Subscription, SubscriptionInvoice.subscription_id == Subscription.id)
        .join(Tenant, SubscriptionInvoice.tenant_id == Tenant.tenant_id)
        .filter(SubscriptionInvoice.status == "open",
                SubscriptionInvoice.due_on < as_of)
        .all()
    )

    for invoice, sub, tenant in rows:
        if sub.reminders_paused:
            continue
        if outstanding_balance(db, invoice) <= 0:
            continue

        age = days_overdue(invoice, as_of)
        reached = [m for m in MILESTONES if age >= m]
        if not reached:
            continue
        milestone = max(reached)

        already = db.query(DunningEvent).filter(
            DunningEvent.invoice_id == invoice.id,
            DunningEvent.day_offset == milestone,
        ).first()
        if already:
            continue

        balance = outstanding_balance(db, invoice)
        title = "Subscription payment overdue"
        body = (
            f"Invoice {invoice.number} for {invoice.period_start:%B %Y} is "
            f"{age} days overdue. Balance KES {balance:,.0f}."
        )
        try:
            recipients = send(tenant.db_name, title, body)
        except Exception:
            # Log and skip. No DunningEvent is written, so the next run retries.
            logger.exception("Could not notify tenant %s", tenant.tenant_id)
            continue

        event = DunningEvent(invoice_id=invoice.id, tenant_id=tenant.tenant_id,
                             day_offset=milestone, recipients=recipients or 0)
        db.add(event)
        db.commit()
        events.append(event)

    return events
```

- [ ] **Step 4: Run them and watch them pass**

Run: `cd backend && venv/bin/pytest tests/receivables/ -q`
Expected: all passing, 26 tests total across the four modules.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_billing.py backend/tests/receivables/test_dunning.py
git commit -m "feat(billing): dunning with milestone suppression and per-tenant isolation"
```

---

## Task 7: Cron entry point

**Files:**
- Create: `backend/app/cli/__init__.py`, `backend/app/cli/run_billing.py`
- Modify: `render.yaml`

**Interfaces:**
- Consumes: `ensure_invoices`, `run_dunning`.
- Produces: `python -m app.cli.run_billing`, exit 0 on success and 1 on failure.

- [ ] **Step 1: Write the command**

```python
"""Daily billing run: raise what is due, then chase what is late.

Invoked by the Render cron service and by the console's 'Run billing now'
control. Both paths call the same two idempotent functions, so a manual run
can never produce a state the scheduled run would not.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from app.config.database import get_master_db
from app.services.subscription_billing import ensure_invoices, run_dunning

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("run_billing")


def main() -> int:
    today = date.today()
    db = next(get_master_db())
    try:
        invoices = ensure_invoices(db, today)
        log.info("Raised %d invoice(s)", len(invoices))
        events = run_dunning(db, today)
        log.info("Sent %d reminder(s)", len(events))
        return 0
    except Exception:
        log.exception("Billing run failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Add the cron service to render.yaml**

Append a `cron` service that runs daily at 03:00 UTC (06:00 EAT, before the working day), reusing the backend's build and environment:

```yaml
  - type: cron
    name: medifleet-billing
    runtime: python
    schedule: "0 3 * * *"
    buildCommand: pip install -r backend/requirements.txt
    startCommand: cd backend && python -m app.cli.run_billing
    envVars:
      - fromGroup: medifleet-backend
```

Confirm the env group name matches the existing backend service before committing; if the backend uses inline `envVars` rather than a group, mirror `DATABASE_URL` and `MASTER_DATABASE_URL` the same way it does.

- [ ] **Step 3: Run it locally against the dev database**

Run: `cd backend && venv/bin/python -m app.cli.run_billing`
Expected: exits 0, logs how many invoices and reminders it produced. Run it a second time: expect 0 invoices and 0 reminders, proving idempotency end to end.

- [ ] **Step 4: Commit**

```bash
git add backend/app/cli render.yaml
git commit -m "feat(billing): daily billing command and Render cron service"
```

---

## Task 8: API

**Files:**
- Create: `backend/app/routes/receivables.py`, `backend/app/schemas/receivables.py`
- Create: `backend/tests/receivables/test_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: everything from Tasks 4 to 6.
- Produces: the eight endpoints listed in the spec, all under `require_superadmin`.

- [ ] **Step 1: Write the router**

Follow `app/routes/payhero_superadmin.py`: a router with `dependencies=[Depends(require_superadmin)]`, mounted under the public superadmin prefix. Endpoints:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/receivables/summary` | totals: billed, received, outstanding, overdue |
| GET | `/receivables/ageing` | per tenant, the five buckets plus total |
| GET | `/receivables/tenant/{tenant_id}` | subscription, invoices, payments, balances |
| POST | `/receivables/invoice/{id}/payment` | record payment or waiver |
| POST | `/receivables/invoice/{id}/void` | void, `reason` required |
| POST | `/receivables/tenant/{id}/reminders` | `{paused: bool}` |
| POST | `/receivables/run` | run billing now, returns counts |
| PUT | `/receivables/subscription/{tenant_id}` | set plan, price, status |

Rules enforced in the route layer:
- A payment greater than the outstanding balance is rejected with 400 and a message naming the balance.
- Voiding an invoice that has any payments is rejected with 400.
- Recording a payment that closes the balance sets `status='paid'` in the same transaction.

- [ ] **Step 2: Write the tests**

```python
from datetime import date
from decimal import Decimal

from app.models.subscription_billing import InvoicePayment, SubscriptionInvoice
from app.services.subscription_billing import ensure_invoices, outstanding_balance


def test_overpayment_is_rejected(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"/api/public/superadmin/receivables/invoice/{inv.id}/payment",
                                 json={"amount_kes": "20000.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 400
    assert "15,000" in res.json()["detail"] or "15000" in res.json()["detail"]


def test_paying_the_balance_closes_the_invoice(client_superadmin, master_db, make_tenant):
    make_tenant(price=Decimal("15000.00"), next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    res = client_superadmin.post(f"/api/public/superadmin/receivables/invoice/{inv.id}/payment",
                                 json={"amount_kes": "15000.00", "paid_on": "2026-08-02", "method": "bank"})
    assert res.status_code == 200
    master_db.refresh(inv)
    assert inv.status == "paid"
    assert outstanding_balance(master_db, inv) == Decimal("0.00")


def test_voiding_a_paid_invoice_is_rejected(client_superadmin, master_db, make_tenant):
    make_tenant(next_on=date(2026, 8, 1))
    ensure_invoices(master_db, date(2026, 8, 1))
    inv = master_db.query(SubscriptionInvoice).first()
    master_db.add(InvoicePayment(invoice_id=inv.id, amount_kes=inv.amount_kes,
                                 paid_on=date(2026, 8, 2), method="bank"))
    master_db.commit()
    res = client_superadmin.post(f"/api/public/superadmin/receivables/invoice/{inv.id}/void",
                                 json={"reason": "mistake"})
    assert res.status_code == 400


def test_every_endpoint_requires_superadmin(client_anonymous):
    for path in ("/api/public/superadmin/receivables/summary",
                 "/api/public/superadmin/receivables/ageing"):
        assert client_anonymous.get(path).status_code in (401, 403)
```

Add `client_superadmin` and `client_anonymous` fixtures to the receivables conftest, using FastAPI's `TestClient` with `require_superadmin` overridden via `app.dependency_overrides` for the authenticated one.

- [ ] **Step 3: Run and iterate until green**

Run: `cd backend && venv/bin/pytest tests/receivables/ -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/receivables.py backend/app/schemas/receivables.py backend/app/main.py backend/tests/receivables/test_api.py backend/tests/receivables/conftest.py
git commit -m "feat(billing): superadmin receivables API"
```

---

## Task 9: The Receivables page

**Files:**
- Create: `frontend/src/api/receivables.js`
- Create: `frontend/src/pages/superadmin/Receivables.jsx`
- Create: `frontend/src/pages/superadmin/receivables/AgeingTable.jsx`, `TenantDrawer.jsx`
- Create: test files alongside each
- Modify: `frontend/src/App.jsx`, `frontend/src/components/layouts/SuperAdminLayout.jsx`

**Interfaces:**
- Consumes: the API from Task 8.
- Produces: the `/superadmin/receivables` route.

Use the design system that shipped in the redesign: `.card`, `.table-clean table-sticky`, `.tnum` on every figure, `StatTile` for the summary, `Skeleton` while loading, `ErrorState` on failure, `EmptyState` when nobody owes anything.

- [ ] **Step 1: Write the AgeingTable test**

```jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import AgeingTable from './AgeingTable';

const rows = [
    { tenant_id: 1, tenant_name: 'Mayo Clinic', current: '0.00', b1_30: '15000.00',
      b31_60: '0.00', b61_90: '0.00', b90_plus: '0.00', total: '15000.00', reminders_paused: false },
    { tenant_id: 2, tenant_name: 'MP Shah', current: '49500.00', b1_30: '0.00',
      b31_60: '0.00', b61_90: '0.00', b90_plus: '0.00', total: '49500.00', reminders_paused: true },
];

describe('AgeingTable', () => {
    it('shows one row per hospital with its total', () => {
        render(<AgeingTable rows={rows} onSelect={() => {}} />);
        expect(screen.getByText('Mayo Clinic')).toBeInTheDocument();
        expect(screen.getByText('MP Shah')).toBeInTheDocument();
    });

    it('labels a tenant whose reminders are paused, so a quiet account is not mistaken for a healthy one', () => {
        render(<AgeingTable rows={rows} onSelect={() => {}} />);
        expect(screen.getByText(/reminders paused/i)).toBeInTheDocument();
    });

    it('opens the drawer for the row that was clicked', async () => {
        const onSelect = vi.fn();
        render(<AgeingTable rows={rows} onSelect={onSelect} />);
        screen.getByText('Mayo Clinic').closest('tr').click();
        expect(onSelect).toHaveBeenCalledWith(1);
    });

    it('renders an empty state when nobody owes anything', () => {
        render(<AgeingTable rows={[]} onSelect={() => {}} />);
        expect(screen.getByText(/no outstanding balances/i)).toBeInTheDocument();
    });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npx vitest run src/pages/superadmin/receivables/AgeingTable.test.jsx`
Expected: FAIL, cannot resolve `./AgeingTable`.

- [ ] **Step 3: Implement the three components and the API wrapper**

`AgeingTable` renders `.table-clean table-sticky` with `.num tnum` money columns, a `Reminders paused` chip where applicable, and `EmptyState` for an empty list. `TenantDrawer` shows subscription terms, invoice history and payment history, with the action buttons. `Receivables.jsx` composes `PageHeader`, four `StatTile`s, `Toolbar` with the "Run billing now" button, and the two children, handling loading with `SkeletonTable` and failure with `ErrorState`.

- [ ] **Step 4: Run and watch it pass**

Run: `cd frontend && npx vitest run src/pages/superadmin/receivables/`
Expected: 4 passed.

- [ ] **Step 5: Wire the route and nav**

Add the lazy route in `App.jsx` beside the other superadmin pages, and a `Receivables` entry to `NAV` in `SuperAdminLayout.jsx` after "Revenue & Tiers", using the `Wallet` icon already imported there.

- [ ] **Step 6: Verify the whole suite and the build**

Run: `cd frontend && npx vitest run --no-file-parallelism && npm run lint && npm run build`
Expected: all green, 0 lint errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(billing): receivables page with ageing table and tenant drawer"
```

---

## Task 10: Collected versus projected

**Files:**
- Modify: `backend/app/routes/public.py` (the overview endpoint, around line 151)
- Modify: `frontend/src/pages/superadmin/SuperAdminDashboard.jsx`

The Global Overview currently reports MRR as `premium_count * price + standard_count * price`, a price-list projection that reads identically whether or not anyone has paid. Leave it, and put the truth beside it.

- [ ] **Step 1: Add `collected_this_month` to the overview payload**

Sum `InvoicePayment.amount_kes` where `paid_on` falls in the current calendar month. Return it alongside `mrr` and `arr`.

- [ ] **Step 2: Show both figures on the dashboard**

The MRR tile keeps its value and gains a hint line: `KES X collected this month`. Label the MRR tile explicitly as a projection so the two are never confused.

- [ ] **Step 3: Verify and commit**

Run: `cd frontend && npx vitest run --no-file-parallelism` and `cd backend && venv/bin/pytest tests/receivables/ -q`

```bash
git add backend/app/routes/public.py frontend/src/pages/superadmin/SuperAdminDashboard.jsx
git commit -m "feat(billing): show collected-this-month beside projected MRR"
```

---

## Task 11: Verification and PR

- [ ] **Step 1: Everything green**

```bash
cd backend && venv/bin/pytest tests/receivables/ -q && venv/bin/pytest tests/accounting/ -q
cd ../frontend && npx vitest run --no-file-parallelism && npm run lint && npm run build
```

- [ ] **Step 2: Migration gate**

```bash
cd backend && venv/bin/alembic upgrade head && venv/bin/alembic current
```
Expected: head is `c3d4e5f6a7b8`. Run `upgrade head` twice to confirm idempotency.

- [ ] **Step 3: Drive it in the browser**

Start the backend and frontend, sign in to the console, and confirm: the Receivables page lists every hospital, "Run billing now" raises invoices and reports counts, recording a payment closes an invoice and moves the balance, pausing reminders labels the tenant, and the dashboard shows collected beside projected.

- [ ] **Step 4: Confirm a reminder actually lands in a tenant**

Run the billing command with a back-dated overdue invoice, then sign in to that hospital as an Admin and confirm the notification appears in the bell with the invoice number, days overdue and balance.

- [ ] **Step 5: Open the PR**

```bash
git push -u origin feat/subscription-receivables
gh pr create --base development --title "feat(billing): subscription receivables and dunning" --body "..."
```

This one **does** touch `backend/app/models/**` and `backend/alembic/**`, so `migrate-all-tenants` will run and must be green. It is a required check, so no admin merge is needed here, unlike the frontend-only PRs.
