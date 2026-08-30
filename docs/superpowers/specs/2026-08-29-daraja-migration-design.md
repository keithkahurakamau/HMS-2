# Daraja Migration: Design

**Status:** Draft for approval
**Date:** 2026-08-29
**Replaces:** the Pay Hero aggregator integration (`c5b4c68`, 2026-05-20)

## Problem

MediFleet collects money on two rails, and both currently run through Pay Hero
(payhero.co.ke), an aggregator sitting on SasaPay infrastructure:

- **Hospital rail** (tenant DBs): patients paying invoices and pharmacy dispenses.
  Custody-free: the money moves from the patient to the hospital's own till, and
  MediFleet never holds it.
- **Subscription rail** (master DB): hospitals paying MediFleet. This is the only
  money the operator actually receives.

The aggregator is a dependency we do not need. It sits between us and Safaricom,
takes a cut, owns the settlement schedule, and introduces a second party to every
support conversation about a missing payment. Talking to Safaricom's Daraja API
directly removes it.

Confirmed with the operator: **no hospital is live on Pay Hero and no payments
have been processed through it.** There is no production data to migrate and no
customer to coordinate with. This is a clean swap, not a dual-run.

## Goals

1. Speak Daraja directly on both rails, with each hospital using its own shortcode
   and its own Daraja credentials. The custody-free property is preserved: money
   still moves patient → hospital till, never through MediFleet.
2. Support the full set of flows, not just collection:
   - STK Push (Lipa na M-Pesa Online) and STK Query
   - C2B (customer pays the till directly) with validation and confirmation
   - **B2C for refunds**: money going back out to a patient
   - Transaction Status, for reconciliation and for verifying inbound payments
   - Account Balance, so an operator can see the B2C float before promising a refund
3. Remove Pay Hero entirely: services, routes, models, settings, frontend, banks
   catalogue. Migration history stays (it is immutable), the code does not.
4. Keep the subscription rail wired into the receivables ledger shipped on
   2026-08-29, so a subscription STK payment lands as an `InvoicePayment` row
   rather than an untracked receipt.

## Non-goals

- Migrating historical Pay Hero transactions. There are none.
- Supporting both providers at once. A feature flag that keeps a dead aggregator
  alive is a liability, not a safety net.
- Automating Safaricom's Go-Live process. A hospital must obtain its own
  production credentials from Safaricom; we consume them, we cannot issue them.
- Changing what money moves or who receives it. This is a transport change.

---

## The one thing that makes this harder than it looks

**Daraja does not sign its callbacks.**

Pay Hero signs every webhook with an HMAC that we verify in
`app/core/payhero_webhook.py`. Safaricom sends an unauthenticated HTTP POST to
whatever URL we registered. Anyone who learns a callback URL can POST a
fabricated "payment received" body at it.

The current callback URL is
`/api/payments/payhero/callback/{tenant_db}`, and `tenant_db` is a guessable
value (`mayoclinic_db`). Under Pay Hero that is fine, because the HMAC is the
real gate and the path is only for routing. Carry that design to Daraja unchanged
and it becomes a way to mint free payments against any hospital whose database
name you can guess.

So authentication has to be rebuilt from different parts:

1. **Unguessable per-tenant callback token in the path.** Not the database name:
   a high-entropy random token stored on the config row, rotatable from the admin
   UI, and mapped back to a tenant on receipt. Rotation exists because a token in
   a URL leaks through logs, proxies and screenshots in a way a header secret
   does not.
2. **Safaricom IP allow-list.** Keep the CIDR machinery already in
   `payhero_webhook.py` (including its `X-Forwarded-For` handling, which is
   already correct about only trusting the header behind a configured proxy).
   Fail closed in production when the list is empty.
3. **Never settle on the callback's word alone.** Every settlement path
   cross-checks against state we already hold:
   - **STK callbacks** must match a `Pending` transaction we ourselves created,
     by `CheckoutRequestID`. The amount in the callback must equal the amount we
     requested. A mismatch is quarantined, never settled.
   - **C2B confirmations** have no prior record by definition: the customer just
     paid the till. These are verified by calling Daraja's **Transaction Status**
     API for the receipt before any money is posted to the ledger. If Safaricom
     does not confirm it, the receipt is recorded as unverified and shown on the
     unmatched queue for a human, but nothing posts.
4. **Replay protection.** `receipt_number` keeps its unique constraint; a repeated
   callback for a receipt already settled is a no-op that returns 200. Safaricom
   retries, and a retry must never double-credit.

This is defence in depth in the real sense: no single one of these is sufficient,
and the settlement cross-check is the one that still holds if the other three fail.

---

## Architecture

### Credentials, per tenant

Daraja needs materially more per-shortcode configuration than Pay Hero did.

| Field | Used by | Notes |
|---|---|---|
| `shortcode` | all | The hospital's PayBill or Buy Goods till |
| `shortcode_type` | STK, C2B | `paybill` or `till`; decides `CustomerPayBillOnline` vs `CustomerBuyGoodsOnline` |
| `consumer_key` | all | OAuth |
| `consumer_secret` | all | OAuth |
| `passkey` | STK | Used to build the STK password |
| `initiator_name` | B2C | The API operator username Safaricom issues |
| `initiator_password` | B2C | Encrypted at rest; see below |
| `environment` | all | `sandbox` or `production`, per tenant |
| `callback_token` | callbacks | High-entropy, rotatable |

Everything except `shortcode`, `shortcode_type` and `environment` is encrypted at
rest with the existing Fernet key from `app/utils/encryption.py`.

`callback_token` is the one exception to a single encrypted column: it is held
as a Fernet-encrypted value plus a separate deterministic HMAC lookup hash,
because the encrypted form is needed to build outbound CallBackURLs and the
hash is needed since Fernet ciphertext cannot be looked up by equality.

**On `SecurityCredential`.** B2C does not take the initiator password directly; it
takes that password RSA-encrypted with Safaricom's public certificate, and the
sandbox and production certificates differ. Two options were considered:

- *Have the hospital paste a pre-generated `SecurityCredential`.* Fewer secrets
  stored, but it silently breaks whenever Safaricom rotates the certificate, and
  it breaks in a way that only shows up on a refund attempt.
- *Store the initiator password encrypted and generate the credential per call.*
  One more secret at rest, but certificate rotation becomes a redeploy rather than
  a support ticket to every hospital.

**Chosen: store the password, generate per call.** The certificates ship in the
repo under `backend/app/vendor/safaricom/` for both environments. The cost if
wrong is one more Fernet-encrypted secret in a database that already holds
consumer secrets and passkeys, so the marginal exposure is close to zero, and it
buys an operationally important property.

**Per-tenant environment.** Hospitals onboard on their own schedule, and a
hospital in sandbox while its Go-Live is pending is a normal state. The setting is
therefore per config row, not global. To stop that becoming a silent production
hazard, the superadmin health panel raises a warning whenever the deployment is in
production and any active tenant is still pointing at sandbox.

### Token handling

Daraja OAuth tokens are per-credential-pair and live about an hour. They are
cached in-process keyed by consumer key, with expiry held a minute short of the
stated lifetime, and refreshed on any 401. Deliberately not stored in the
database: under multiple gunicorn workers each process fetching its own token
costs a handful of extra calls per hour, which is cheaper than the invalidation
problem a shared cache creates.

### Schema

Tables move back to provider-neutral names, because M-Pesa is the rail no matter
who fronts it, and the next provider change should not rename tables again:

- `payhero_configs` → `mpesa_configs`
- `payhero_transactions` → `mpesa_transactions`
- `platform_payhero_configs` → `platform_mpesa_configs`
- `platform_payhero_transactions` → `platform_mpesa_transactions`

New in `mpesa_transactions`: `checkout_request_id`, `merchant_request_id`,
`conversation_id` and `originator_conversation_id` (B2C), `verified_at` and
`verification_source` (proof the receipt was confirmed with Safaricom rather than
merely asserted by a callback).

New table `mpesa_refunds` for the B2C flow, described below.

The migration must tolerate both starting shapes, because a legacy tenant database
may still carry `mpesa_*` names from before `aa2b7c3d8e91` renamed them to
`payhero_*`. It renames when it finds the Pay Hero name, creates when it finds
neither, and does nothing when the target already exists.

**Master-database tables follow the receivables precedent exactly.** The
`platform_mpesa_*` tables are master-only, so their model file stays OUT of the
import block in `scripts/migrate_all_tenants.py` (that list feeds an unfiltered
`create_all()` against every tenant engine) and their schema arrives through
`MASTER_DB_PATCHES` instead. Any master-only alembic revision is guarded on the
database name, never on `_has_table("tenants")`, because tenant databases also
contain a `tenants` table.

### Refunds (B2C)

This is the only part of the system that moves money *out*, and it is designed
accordingly.

**States:** `Requested → Approved → Processing → Completed | Failed | Reversed`

**Controls:**

- A dedicated permission, `mpesa:refund`, granted separately from
  `billing:manage`. Being able to take a payment must not imply being able to
  send one back.
- Two-person rule above a configurable threshold: the requester and the approver
  cannot be the same user.
- Every refund references the original inbound receipt. The refundable amount is
  the receipt amount minus refunds already completed or in flight against it,
  computed on read under a row lock. A refund that would exceed it is rejected.
- A per-transaction cap and a rolling 24-hour total cap, both configurable per
  tenant, both enforced server-side.
- `OriginatorConversationID` is minted once when the refund row is created and
  reused on every retry, so a retried request is recognised by Safaricom as the
  same instruction rather than a second one.
- The B2C result arrives on its own callback, with a separate queue-timeout URL. A
  timeout is explicitly **not** a failure: it moves to a `Processing` state that
  the reconciliation job resolves via Transaction Status. Treating a timeout as a
  failure is how a system refunds twice.

**`CommandID` is `BusinessPayment`**, not `PromotionPayment` or `SalaryPayment`.
It is the correct code for a refund and produces the right message on the
recipient's handset.

### Reconciliation

A scheduled job, reusing the advisory-lock pattern from the billing cron:

- Any transaction `Pending` for more than 5 minutes is queried via STK Query or
  Transaction Status and resolved.
- Any refund in `Processing` for more than 10 minutes is likewise resolved.
- Anything still unresolved after 24 hours is surfaced on the operator health
  panel rather than retried forever.

This is what makes the system self-healing when a callback is simply never
delivered, which on Daraja happens often enough to plan for.

---

## API surface

Routes move from `/api/payments/payhero/*` to `/api/payments/mpesa/*` and from
`/api/admin/payhero/*` to `/api/admin/mpesa/*`. The module key in
`core/modules.py` becomes `mpesa`, and the permission becomes `mpesa:manage`.
`RequirePermission` already accepts variadic any-of codenames, so the existing
`payhero:manage` and legacy `mpesa:manage` grants continue to authorise during
the transition without a data migration racing the deploy.

Callback endpoints, all token-addressed:

```
POST /api/payments/mpesa/stk/callback/{callback_token}
POST /api/payments/mpesa/c2b/validation/{callback_token}
POST /api/payments/mpesa/c2b/confirmation/{callback_token}
POST /api/payments/mpesa/b2c/result/{callback_token}
POST /api/payments/mpesa/b2c/timeout/{callback_token}
POST /api/payments/mpesa/platform/stk/callback/{callback_token}
```

Callbacks always return HTTP 200 with Safaricom's expected acknowledgement body,
including when we reject the content. Returning a 4xx makes Safaricom retry a
payload we have already decided is bad, and on C2B validation a non-200 can cause
the customer's payment to be declined at the till. Rejection is recorded on our
side and acknowledged on theirs.

## Frontend

- `pages/MpesaSettings.jsx` (which despite its name currently posts to Pay Hero)
  is rebuilt against the Daraja config: credentials, environment, callback token
  with a rotate action, B2C settings and caps.
- A refunds view under Billing: request, approve, and track state, gated on
  `mpesa:refund`.
- The superadmin console gains Daraja health beside the existing Pay Hero blocker
  checks in `PlatformHealth.jsx`: credentials present, callback URLs registered,
  sandbox-in-production warnings, unresolved-transaction count.
- The Pay Hero settlement-bank UI and its 35-bank catalogue are deleted. Under
  Daraja, settlement is Safaricom paying the hospital's own shortcode directly;
  there is no aggregator bank account to nominate.

## Testing

Every Daraja call goes through one client module, so the entire external surface
is mocked at one seam.

- Unit: password and `SecurityCredential` generation, MSISDN normalisation, token
  cache expiry, callback body parsing for each of the five shapes.
- Security: unsigned callback with a wrong token rejected; correct token from a
  disallowed IP rejected; STK callback whose amount differs from the requested
  amount quarantined rather than settled; replayed receipt is a no-op.
- Refunds: over-cap rejected, over-refund rejected, self-approval rejected,
  timeout resolves through reconciliation rather than failing, retry reuses the
  originator id.
- Cross-rail: a subscription STK payment produces an `InvoicePayment` row against
  the right invoice in the master database.

## Risks

| Risk | Mitigation |
|---|---|
| Forged callbacks (no signature) | Token in path, IP allow-list, cross-check against our own pending record, Transaction Status verification for C2B |
| Callback never delivered | Reconciliation job resolves by polling; timeouts are not failures |
| Double refund | Originator id reuse, row-locked refundable-amount computation, timeout goes to Processing not Failed |
| Certificate rotation breaks B2C | Store the initiator password, generate the credential per call |
| A hospital left on sandbox in production | Per-tenant environment plus an explicit health-panel warning |
| Big-bang cutover | No live Pay Hero data and no live hospital, so there is nothing to cut over from |

## Credentials: answered

**MediFleet holds no Daraja credentials of its own** (confirmed by the operator,
2026-08-29). No Safaricom Go-Live has been done for the MediFleet shortcode.

Consequences, all of which the design already accommodates:

- **The subscription rail ships pointed at sandbox.** It is built, tested and
  merged in full, and becomes live through a configuration change once the
  operator completes Go-Live. No redeploy, no code change, no migration.
- **Collecting subscriptions by M-Pesa is not available until then.** This is not
  a blocker: the receivables ledger shipped on 2026-08-29 already records payments
  received by any means, so the operator continues to record bank transfers and
  manual M-Pesa receipts against invoices exactly as now. The Daraja rail replaces
  the typing, not the ledger.
- **The hospital rail is unaffected.** Each hospital brings its own credentials
  when it onboards, and none is live today, so every hospital starts in sandbox
  and flips per tenant when its own Go-Live completes. The per-tenant
  `environment` field exists precisely for this.
- **Nothing in this work can be verified against production M-Pesa before merge.**
  Every flow is proven against Daraja sandbox and against mocked responses at the
  client seam. The first production transaction on either rail will be a live
  smoke test performed by a human with a real handset, not something CI can
  assert. The plan ends with a written smoke-test procedure for that reason.
