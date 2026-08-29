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
import calendar
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors the canonical tier prices in app/routes/public.py and
# frontend/src/pages/superadmin/PlatformBilling.jsx. Used only to seed
# price_kes on backfilled subscriptions; the column itself is the source of
# truth from here on (see the comment on Subscription.price_kes).
TIER_PRICING = {"premium": 49500, "standard": 18500}

# The only database this revision is allowed to act on. Derived the same way
# migrate_all_tenants.py's `_master_db_url` derives it (it appends
# "/hms_master" to whatever host/port the tenant URLs share).
MASTER_DB_NAME = "hms_master"


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _next_billing_date(today: date, day: int) -> date:
    """The next occurrence of ``day`` (a day-of-month) on or after ``today``.

    Clamped to the last day of a short month (e.g. day 31 in February becomes
    the 28th/29th), and rolled to next month if this month's occurrence has
    already passed.
    """
    def _clamp(year: int, month: int) -> date:
        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(day, last))

    candidate = _clamp(today.year, today.month)
    if candidate < today:
        if today.month == 12:
            candidate = _clamp(today.year + 1, 1)
        else:
            candidate = _clamp(today.year, today.month + 1)
    return candidate


def upgrade() -> None:
    bind = op.get_bind()

    # Master-only migration. RULING (overrides the ab3c9e5d27f8 precedent
    # this revision otherwise follows): `_has_table(bind, "tenants")` alone
    # is NOT a reliable guard here. Every tenant database also has a
    # `tenants` table: it leaked in through the unfiltered
    # `Base.metadata.create_all()` that migrate_all_tenants.py runs for
    # legacy-bootstrapped tenants (the master-only Tenant model is imported
    # into the same shared metadata as every tenant model). So table
    # presence proves nothing about which database this is. The database
    # name is the trustworthy signal: only the master database is named
    # "hms_master" (see `_master_db_url` in migrate_all_tenants.py, which
    # derives it the same way). The `_has_table` checks stay on as a second,
    # belt-and-braces condition, so a differently-named master fails safe
    # (does nothing) rather than silently double-creating tables.
    if bind.engine.url.database != MASTER_DB_NAME:
        return
    if not _has_table(bind, "tenants"):
        return

    if not _has_table(bind, "subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.tenant_id"), nullable=False, unique=True, index=True),
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
    # anchored to its creation date.
    #
    # RULING (overrides the brief, which set next_invoice_on to the first of
    # next month): next_invoice_on is the NEXT OCCURRENCE of the tenant's own
    # billing day, derived from created_at, clamped to the target month's
    # length. The invoice generator (a later task) advances the cycle using
    # started_on.day, so anchoring the first invoice to the 1st would bill a
    # hospital on the 1st exactly once and then jump to its signup
    # anniversary day forever after, a visible, unexplainable billing-date
    # change for the customer.
    today = date.today()
    tenants = bind.execute(
        sa.text(
            """
            SELECT t.tenant_id, t.is_premium, t.is_active, t.created_at
            FROM tenants t
            WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.tenant_id)
            """
        )
    ).fetchall()

    insert_stmt = sa.text(
        """
        INSERT INTO subscriptions
            (tenant_id, plan, price_kes, cycle, status, started_on, next_invoice_on, reminders_paused)
        VALUES
            (:tenant_id, :plan, :price_kes, 'monthly', :status, :started_on, :next_invoice_on, FALSE)
        """
    )
    for row in tenants:
        started_on = row.created_at.date() if row.created_at is not None else today
        is_premium = bool(row.is_premium)
        plan = "premium" if is_premium else "standard"
        price = TIER_PRICING["premium"] if is_premium else TIER_PRICING["standard"]
        status = "active" if row.is_active else "paused"
        next_invoice_on = _next_billing_date(today, started_on.day)
        bind.execute(
            insert_stmt,
            {
                "tenant_id": row.tenant_id,
                "plan": plan,
                "price_kes": price,
                "status": status,
                "started_on": started_on,
                "next_invoice_on": next_invoice_on,
            },
        )


def downgrade() -> None:
    for table in ("dunning_events", "invoice_payments", "subscription_invoices", "subscriptions"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
