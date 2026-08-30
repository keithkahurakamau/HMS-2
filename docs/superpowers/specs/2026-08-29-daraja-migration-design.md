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

### Per-department tills

A hospital is not always one till. Departments run their own books: the pharmacy
settles separately from the laboratory, an outpatient desk from a maternity wing.
The operator requires that each department be able to collect on its own M-Pesa
shortcode.

**Shape.** `mpesa_configs` becomes a multi-row table with a nullable
`department_id` referencing `departments.department_id`. The row with a NULL
department is the hospital-wide default. A department with its own row overrides
the default; a department without one falls back to it. This matters because no
hospital onboards with twenty configured tills: they start with one and split it
out as they need to, and the fallback is what makes that possible without a
migration per department.

Two partial unique indexes hold the shape: at most one row per department, and at
most one default row. Postgres treats NULLs as distinct in a plain unique index,
so the default needs its own partial index rather than relying on the first.

**Resolution.** One function, `config_for(db, department_id=None)`: the
department's active config when present, otherwise the hospital default,
otherwise the same "not configured" error as today. Every caller goes through it.
That single seam is the whole reason the change is small.

**Routing back.** Each config already carries its own callback token pair, so each
till gets its own callback URL and an inbound callback identifies the exact till
that received the money, not merely the hospital. `mpesa_transactions` therefore
gains an `mpesa_config_id` FK. Without it a refund could not know which till to
pay back from, and reconciliation could not tell two tills apart.

**What this does not do.** Invoices carry no department today, so nothing infers a
department automatically. The caller passes one when it knows: the pharmacy screen
knows it is the pharmacy. Everything else uses the hospital default and behaves
exactly as it does now. Inferring a department from `InvoiceItem.item_type` was
considered and rejected: an invoice can carry items from several service lines,
so there is no single correct answer, and guessing would route real money to the
wrong department's till.

### Many terminals, one till

A department is not one computer. A pharmacy can have several machines taking
payments against the same shortcode at the same moment, and those machines are
served by different gunicorn workers, so nothing in a single process can
coordinate them. Two failures follow from that, and they are different problems
with different fixes.

**The same action submitted twice.** One cashier double-clicks, or the network
drops the response and the browser retries. This is idempotency, and the codebase
already has the mechanism: `IdempotencyKey` in `app/models/idempotency.py`, scoped
to (user_id, endpoint, key) with a SHA-256 fingerprint of the request body, and
the helper in `app/core/idempotency.py`. Reusing a key with a DIFFERENT body
returns 409 rather than the wrong cached answer, which is the property that makes
it safe. STK initiation is wrapped in it, so a repeated submit returns the first
response and pushes no second prompt.

Note the scope is per user, and that is correct: two different cashiers pressing
their own buttons are two genuine actions, not one action retried.

**Two terminals pushing the same invoice.** This is not idempotency. Two different
users, each acting deliberately, both send an STK prompt for one invoice, and the
patient receives two prompts and can pay twice. No per-user key catches this.

The guard is a partial unique index: at most one `Pending` transaction per invoice,
and likewise per dispense. Postgres enforces it across every worker and every
machine, which is exactly the scope the problem lives at. A second concurrent push
loses the race and is handed the existing pending transaction instead of creating
its own.

That must not become a permanent lock when a prompt goes unanswered. An STK prompt
expires on the handset in about a minute, so a `Pending` transaction older than a
short timeout is resolved by the reconciliation job (via STK Query, so the outcome
comes from Safaricom rather than from a guess) and the slot frees. A cashier
retrying a genuinely dead prompt is a normal path, not an error.

**Settlement is already safe under concurrency** and stays that way: `receipt_number`
carries a unique constraint, so two callbacks delivering the same receipt cannot
both create a payment, and `settle_invoice_match` is idempotent on
`Payment.transaction_reference`. Concurrent settlement of the SAME invoice from two
different receipts is legitimate (a split payment) and must keep working.

**The OAuth token cache** is keyed by consumer key and shared by every request in a
worker, so terminals in one department share one token. A concurrent miss can cause
two workers to fetch a token at once. That is harmless: Daraja issues a valid token
per request and both are usable. It is called out here only so nobody later adds a
lock and serialises the payment path to fix a non-problem.

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

### The event log, and pages to verify against

Every Daraja interaction is recorded, whatever its outcome: a successful STK push,
a customer who cancelled, a callback rejected for a mismatched amount, a refund
that timed out, a request Safaricom refused. Success, failure and error all land in
the same place, because the question a human actually asks is "what happened to
this payment", and that question cannot be answered by a log that only kept the
failures.

**Why this is not just logging.** Application logs are ephemeral, unstructured, and
invisible to the hospital staff who need them. When a patient says they paid and
the invoice says otherwise, a cashier needs to see the receipt number, the
timestamp, the amount Safaricom reported, and the reason it was not settled,
without an engineer reading a log aggregator. That is a product surface, not an
operational one.

**Shape.** An `mpesa_events` row per interaction, in the tenant database, carrying:
the flow (STK push, STK query, C2B validation, C2B confirmation, B2C request, B2C
result, B2C timeout, transaction status, balance, URL registration), the direction
(did we call Safaricom, or did Safaricom call us), the outcome, Safaricom's own
`ResultCode` and `ResultDesc` verbatim, the HTTP status, how long it took, and the
correlation handles that let a human join it up: the transaction or refund it
belongs to, the `CheckoutRequestID`, the `ConversationID`, the receipt number, and
which till took the money.

Both payloads are stored, redacted. Storing the actual request and response is what
makes the page worth having: "Safaricom rejected it" is not diagnosable, and
"Safaricom returned `Bad Request - Invalid Amount` for `Amount: 0`" is.

**Redaction is not optional and not best-effort.** The STK `Password`, the B2C
`SecurityCredential`, the consumer secret, the passkey, and the callback token must
never reach this table. It is read by hospital staff and rendered in a browser, so
a secret stored here is a secret disclosed. The redaction runs on the way IN, so a
secret is never written even if the page is later changed. A denylist of key names
is the wrong shape here: use an allowlist of fields known to be safe, because the
failure mode of a forgotten denylist entry is a leaked credential.

Phone numbers are personal data and belong to a patient, so the list view masks
them and the full value appears only in the detail view, behind the same permission
that already governs billing.

**Pages.** A hospital-facing view under the M-Pesa area: filter by outcome, flow,
till, date, and search by receipt or phone; a detail view showing everything above.
An operator-facing view in the superadmin console spanning tenants, for answering
"is this one hospital or all of them". The failure states get first-class treatment
rather than a generic error string: a quarantined callback shows the amount claimed
against the amount requested side by side, because that is the exact comparison a
human needs to make.

**Growth.** This table grows with transaction volume and is append-only. It carries
an index on time and on the correlation handles, the list view is paginated, and
old rows are prunable on a retention window the operator sets. An unbounded log
that nobody can query is a liability rather than a feature.

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

Callback endpoints carry a tenant routing hint alongside the token:

```
POST /api/payments/mpesa/stk/callback/{tenant_hint}/{token}
POST /api/payments/mpesa/c2b/validation/{tenant_hint}/{token}
POST /api/payments/mpesa/c2b/confirmation/{tenant_hint}/{token}
POST /api/payments/mpesa/b2c/result/{tenant_hint}/{token}
POST /api/payments/mpesa/b2c/timeout/{tenant_hint}/{token}
POST /api/payments/mpesa/platform/stk/callback/{tenant_hint}/{token}
```

**Why the hint exists, and why it does not reopen the hole this design closes.**
Resolving a callback from the token alone means searching for it, and with one
database per tenant that is a scan across every hospital. On an endpoint that is
public and unauthenticated by design, that turns one cheap forged request into a
database round trip per tenant, evicting connection-pool entries that other
hospitals are actively using. The hint removes the search: open the one named
database, do one indexed equality lookup on the token hash, done.

The token remains the sole gate. A wrong or spoofed hint grants nothing: it is
looked up like any other, and simply fails to find a token that lives elsewhere.
This is exactly what the retired Pay Hero design got wrong. There the guessable
tenant database name in the path WAS the gate once the HMAC was removed from the
picture; here the hint is never checked in place of a token, only alongside one.
Tenant database names are already publicly enumerable through
`GET /api/public/hospitals`, so the hint discloses nothing new.

The alternative considered and rejected was a lookup index in the master database
mapping token hash to tenant. It works, but it needs a dual write across two
databases with no shared transaction, so the two can drift, and a stale master row
becomes a cross-tenant routing bug: a callback settled against the wrong hospital.
That is a worse failure than the one it fixes.

The platform rail uses a reserved hint value that cannot collide with a tenant
database name, and resolves against master instead of opening a tenant engine.

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
