# Subscription Receivables and Dunning

**Date:** 2026-08-28
**Status:** Approved design, pending spec review
**Sequencing:** Built before the Daraja migration. The ledger is payment-provider
agnostic; only allocation touches the provider, and Daraja will settle against
the invoices this spec creates.

## Problem

The platform cannot answer "who owes me, how much, and for how long", because it
never records what anyone owes.

`Tenant` carries `is_premium`, `is_active` and a billing contact. There is no
subscription record, no billing cycle, no due date, no paid-through date and no
balance. The MRR shown on the Global Overview is computed as:

```python
mrr = premium_count * TIER_PRICING["premium"] + standard_count * TIER_PRICING["standard"]
```

That is a price-list multiplication over the tenant table. It would report the
same figure if no hospital had ever paid. `PlatformPayHeroTransaction` records
charges that occurred, but nothing links a charge to an obligation, so "paid"
and "unpaid" are not states the database can currently express.

## Goals

1. Record what each hospital owes, per billing period.
2. Record what has been received and which obligation it settled.
3. Derive balance and ageing from those two facts.
4. Remind hospital administrators automatically, in-app, when they are overdue.
5. Give the operator direct control: record manual payments, waive, void, pause
   reminders, run billing on demand, and suspend by hand.

## Non-goals

- No automatic restriction or suspension. The operator decides, always. The
  product is clinical software, and a hospital losing function mid-shift over an
  unpaid invoice is a worse outcome than a late payment.
- No email or SMS dunning in this version. In-app notification only.
- No multi-currency. Amounts are KES.
- No proration, plan changes mid-cycle, or usage-based billing.

## Decisions taken

| Decision | Choice |
|---|---|
| Sequencing | Receivables ledger first, Daraja second |
| Billing terms | Monthly in advance, due on issue |
| Overdue | Anything unpaid the day after issue begins ageing |
| Escalation | Notify only; suspension is a manual operator action |
| Trigger | Render cron job daily, plus a manual "Run billing now" control |
| Ledger location | Master database |

## Data model

Four new tables in the **master** database, in a new
`backend/app/models/subscription_billing.py`.

### Subscription

One row per tenant.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `tenant_id` | FK tenants.tenant_id, unique | one subscription per tenant |
| `plan` | String(20) | `standard` or `premium` |
| `price_kes` | Numeric(12,2) | the agreed monthly price, not the tier default |
| `cycle` | String(10) | `monthly`. Reserved for future terms |
| `status` | String(20) | `active`, `paused`, `cancelled` |
| `started_on` | Date | anchors the billing day of month |
| `next_invoice_on` | Date | advanced by the generator; the idempotency key |
| `reminders_paused` | Boolean | operator control, suppresses dunning only |
| `created_at` / `updated_at` | DateTime(tz) | |

`price_kes` is stored rather than read from `TIER_PRICING` so that a negotiated
price survives a change to the public price list, and so an invoice can always
be explained by the subscription that produced it.

### SubscriptionInvoice

One row per tenant per billing period.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `tenant_id` | FK, indexed | denormalised for query speed on the ageing view |
| `subscription_id` | FK | |
| `number` | String(20), unique | `MF-YYYY-NNNN`, human reference |
| `period_start` / `period_end` | Date | the month being paid for |
| `amount_kes` | Numeric(12,2) | copied from the subscription at issue time |
| `issued_on` | Date | |
| `due_on` | Date | equals `issued_on` under these terms |
| `status` | String(20) | `open`, `paid`, `void` |
| `void_reason` | Text, nullable | required when voiding |
| `created_at` | DateTime(tz) | |

Unique constraint on `(subscription_id, period_start)`. This is what makes
invoice generation safe to run repeatedly: a second run cannot create a
duplicate period.

`status` deliberately has no `part_paid` value. Partial payment is visible from
the balance and does not need a separate state that can drift out of sync with
the allocations.

### InvoicePayment

An allocation: money received, attached to the obligation it settles.

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `invoice_id` | FK, indexed | |
| `platform_transaction_id` | Integer, nullable | links to the M-Pesa receipt when one exists |
| `amount_kes` | Numeric(12,2) | |
| `paid_on` | Date | |
| `method` | String(20) | `mpesa`, `bank`, `cash`, `cheque`, `waiver` |
| `recorded_by` | FK superadmins.admin_id, nullable | null when automatic |
| `note` | Text, nullable | |
| `created_at` | DateTime(tz) | |

A waiver is recorded as a payment with `method='waiver'`, so the invoice closes
and the write-off remains visible and attributable rather than deleted.

### DunningEvent

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `invoice_id` | FK, indexed | |
| `tenant_id` | FK, indexed | |
| `day_offset` | Integer | 1, 7, 14 or 30 |
| `sent_at` | DateTime(tz) | |
| `recipients` | Integer | how many admins were notified |

Unique constraint on `(invoice_id, day_offset)`. This is what stops a hospital
being reminded twice for the same milestone, however often the job runs.

### Derived values, never stored

```
balance(invoice)  = amount_kes - sum(allocations)
age_days(invoice) = today - due_on          (only while balance > 0)
```

Storing either would let it drift from the rows that produce it.

## The engine

New `backend/app/services/subscription_billing.py`. Two idempotent entry points,
both safe to run any number of times per day.

### ensure_invoices(as_of: date) -> list[SubscriptionInvoice]

For every `Subscription` with `status='active'` and `next_invoice_on <= as_of`:
raise an invoice for the period starting on `next_invoice_on`, then advance
`next_invoice_on` by one month. Loops until caught up, so a system that was down
for two months issues both invoices rather than losing one.

Under these terms `due_on = issued_on`.

Billing day of month comes from `started_on`. A subscription started on the 31st
bills on the last day of shorter months.

### run_dunning(as_of: date) -> list[DunningEvent]

For every invoice with `status='open'` and `balance > 0`, compute
`age = as_of - due_on`. For each milestone in `(1, 7, 14, 30)` where
`age >= milestone` and no `DunningEvent` exists for that pair, notify and record.

Skipped when the subscription has `reminders_paused`.

Only the highest milestone reached is sent in a catch-up run, so a system down
for a month does not deliver four notifications at once.

### Cross-database write

Notifications live in the **tenant** database, keyed to a tenant `user_id`. The
engine reads obligations from master, then opens a session per tenant using the
existing `_tenant_session` helper pattern and inserts one `Notification` per
user holding the Admin role.

Each tenant is handled in its own try block. A tenant whose database is
unreachable is logged and skipped; it must never abort the run for everyone
else. The `DunningEvent` is written only if the notification insert committed,
so a failed tenant is retried on the next run.

Notification content:

> **Title:** Subscription payment overdue
> **Body:** Invoice MF-2026-0007 for August 2026 is 14 days overdue. Balance KES 45,000.

### Trigger

A daily Render cron job runs `python -m app.cli.run_billing`, a thin command
that calls `ensure_invoices(today)` then `run_dunning(today)` and exits non-zero
on failure. The same two functions are exposed behind a superadmin endpoint so
the console's "Run billing now" control uses exactly the same code path.

Requires a new `cron` service in `render.yaml`.

## API

All under the existing superadmin router, superadmin auth required.

| Method | Path | Purpose |
|---|---|---|
| GET | `/public/superadmin/receivables/summary` | billed, received, outstanding, overdue totals |
| GET | `/public/superadmin/receivables/ageing` | per tenant: current, 1-30, 31-60, 61-90, 90+ |
| GET | `/public/superadmin/receivables/tenant/{tenant_id}` | invoices, payments, balance |
| POST | `/public/superadmin/receivables/invoice/{id}/payment` | record a manual payment or waiver |
| POST | `/public/superadmin/receivables/invoice/{id}/void` | void, reason required |
| POST | `/public/superadmin/receivables/tenant/{id}/reminders` | pause or resume reminders |
| POST | `/public/superadmin/receivables/run` | run billing now |
| PUT | `/public/superadmin/receivables/subscription/{tenant_id}` | set plan, price, status |

## Console UI

A new **Receivables** entry in the console navigation.

- Four summary tiles: billed to date, received, outstanding, overdue. Tabular
  numerals, and outstanding versus overdue must be visually distinct, since
  outstanding-but-current is not a problem and overdue is.
- Ageing table, one row per hospital, columns current / 1-30 / 31-60 / 61-90 /
  90+ and a total. Only genuinely overdue buckets carry warning colour.
- Row click opens a drawer: subscription terms, invoice history with status,
  payment history, and the action buttons.
- A tenant with reminders paused is labelled as such, so a quiet account is
  never mistaken for a healthy one.

Existing "Revenue & Tiers" keeps its tier and pricing role. The MRR figure on
Global Overview gains a companion "collected this month" figure from the ledger,
so the projection and the reality sit side by side.

## Error handling

- A tenant database that cannot be opened during dunning is logged and skipped,
  and its `DunningEvent` is not written, so the next run retries it.
- Recording a payment larger than the balance is rejected with a message naming
  the balance. Overpayment handling is out of scope.
- Voiding a paid invoice is rejected. The payment must be dealt with first.
- Invoice generation is wrapped per subscription: one bad subscription does not
  stop the rest.
- The manual run endpoint returns a per-tenant result summary, so the operator
  sees what happened rather than a bare success.

## Testing

**Unit, pure functions:** balance from allocations, ageing bucket boundaries at
0, 1, 30, 31, 90, 91 days, and the billing-day rollover for a subscription
started on the 31st.

**Idempotency, the property that matters most:** `ensure_invoices` run twice for
the same period creates one invoice. `run_dunning` run twice for the same
milestone sends one notification. A catch-up run after 45 days of downtime sends
one notification, not four.

**Cross-database isolation:** with two tenants where one database is
unreachable, the reachable tenant is still notified and the failing one is
retried next run.

**API:** each endpoint rejects unauthenticated calls; overpayment and
void-a-paid-invoice are rejected with useful messages.

**Frontend:** ageing table renders buckets correctly, actions call the right
endpoints, a paused tenant is labelled, and the four states of an invoice render
distinctly.

## Migrations

One Alembic revision creating the four master-database tables, plus:

- Register `app/models/subscription_billing.py` in the import block of
  `backend/scripts/migrate_all_tenants.py`, or legacy environments silently skip
  the tables.
- Add the tables to `MASTER_DB_PATCHES`, since these live in the master database
  rather than per-tenant schemas.
- A data step creating a `Subscription` row for every existing tenant, priced
  from its current tier, with `started_on` set to the tenant's `created_at` and
  `next_invoice_on` set to the next billing day. Without it, existing hospitals
  are never invoiced.

The `migration-check` workflow must be green at `development`, `beta` and `main`
before each promotion.

## Delivery

Its own branch off `development`, opened after the frontend redesign branch
merges, since both touch the console. Implementation follows in a separate plan.
