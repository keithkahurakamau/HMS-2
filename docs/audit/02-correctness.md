# 02 — Correctness Audit

Auditor: CORRECTNESS (4-agent codebase audit)
Branch: `audit/world-class-codebase-20260530`
Scope: routes/services, models, the new triage module, accounting money-math, frontend data flow / hooks.
Mode: read-only. No code changed.

Tenancy note: isolation is **database-per-tenant** (engine selected by `X-Tenant-ID` header in `get_db`, `backend/app/config/database.py:121`). Per-tenant queries therefore need no `tenant_id` filter — this removes a whole class of would-be "missing tenant filter" findings. They are intentionally **not** reported below.

---

## Severity counts

| Severity | Count |
|----------|-------|
| CRITICAL | 2 |
| HIGH     | 4 |
| MEDIUM   | 6 |
| LOW      | 4 |
| **Total**| **16** |

---

## CRITICAL

### C1 — Cash/Card payment posting raises `TypeError` (Decimal += float) — payments can fail outright
**File:** `backend/app/routes/billing.py:78` (and `:79`, `:129`)
**Schema:** `backend/app/schemas/billing.py:8` (`amount: float`)
**Model:** `backend/app/models/billing.py:14-15` (`total_amount`, `amount_paid` are `Numeric(10,2)`)

`PaymentRequest.amount` is declared `float`, so Pydantic always coerces the inbound value to a Python `float`. In `process_cash_card_payment` the invoice is loaded from Postgres via `with_for_update()`, so `invoice.amount_paid` comes back as a **`Decimal`** (psycopg2 adapts `NUMERIC` → `Decimal`). The line

```python
invoice.amount_paid += req.amount          # Decimal += float
```

executes `Decimal.__add__(Decimal, float)`, which **raises `TypeError: unsupported operand type(s) for +: 'decimal.Decimal' and 'float'`** (verified: `Decimal('0') + 1000.0` raises). The blanket `except Exception` at `:110` catches it, rolls back, and returns HTTP 400 with the raw error string. **Net effect: cash/card payment recording fails** whenever the invoice already has a persisted `amount_paid` value.

This is not theoretical — the pharmacy module hit the *exact same bug* and left a comment about it: `backend/app/routes/pharmacy.py:85-88` ("that mismatch broke `(total_amount - amount_paid)` … when one operand had been mutated to float"). Pharmacy was fixed to stay in `Decimal`; **billing was not**.

- **Trigger:** any cash/card payment against an invoice whose `amount_paid` is already a DB-loaded Decimal (i.e. essentially all real payments; a brand-new invoice with in-session default `0` int would by luck succeed).
- **Fix:** declare `amount: condecimal(gt=0, max_digits=10, decimal_places=2)` (or `Decimal`) in `PaymentRequest`, and/or coerce at use: `invoice.amount_paid = (invoice.amount_paid or Decimal(0)) + Decimal(str(req.amount))`. Apply the same in `charge_consultation_fee` (`:129`).

### C2 — `charge_consultation_fee` has no idempotency guard and no rollback — duplicate charges + poisoned transaction
**File:** `backend/app/routes/billing.py:114-154`

Unlike `process_cash_card_payment` (which uses `idempotent_guard`) and `pharmacy.dispense_drug`, the consultation-fee endpoint:
1. Has **no idempotency key** and no `with_for_update()` on the existing-invoice lookup (`:117`). A double-click (or doctor saving twice) creates **two `InvoiceItem` "Doctor Consultation Fee" rows and double-counts `total_amount`**, or two concurrent requests each miss the Pending invoice and create two invoices.
2. Has **no `try/except db.rollback()`** wrapper. It also suffers the C1 `Decimal += float` problem at `:129` for an *existing* Pending invoice. When that raises mid-handler, the session is left in `InFailedSqlTransaction`; the unguarded `db.commit()` at `:153` then fails and the connection is returned to the pool dirty.

- **Trigger:** double-submit of a consultation fee, or any fee charged against a patient who already has a Pending invoice.
- **Fix:** wrap in `idempotent_guard`, take `with_for_update()` on the invoice lookup, add `try/except: db.rollback()`, and use Decimal math (see C1).

---

## HIGH

### H1 — `/triage/submit` is not idempotent — double-submit creates duplicate triage rows and onward queue entries
**File:** `backend/app/routes/triage.py:79-163`, `backend/app/schemas/triage.py` (no `idempotency_key`)

The triage submit path writes a `TriageRecord` and routes the patient onward. There is no idempotency key (cf. billing/pharmacy which both use `idempotent_guard`). The onward-routing de-dup at `:126-133` only catches a duplicate **if the first request has already committed and is visible**. Two near-simultaneous submits (slow network + impatient nurse clicking "Save & send to doctor" twice — the button is disabled only by client `isSubmitting` state, `frontend/src/pages/Triage.jsx:254`) can both pass the `existing` check and **insert two Consultation queue rows** for the same patient, plus two immutable triage rows.

- **Trigger:** double-click / retry on submit before the first commit lands.
- **Fix:** add `idempotency_key` to `TriageCreate` + `idempotent_guard`, or take a `with_for_update()` lock on the patient's disposition queue rows, or a partial unique index on `(patient_id, department, status='Waiting')`.

### H2 — Auto-post idempotency check excludes reversed entries → re-post after a reversal double-counts
**File:** `backend/app/services/accounting_posting.py:106-121`

The idempotency lookup filters `JournalEntry.status == "posted"`. When an entry is reversed, the original flips to `status="reversed"` (`backend/app/services/accounting.py:378`). If the **same source event** then fires `post_from_event` again (a retried webhook, a re-run of a settlement worker, a manual re-post), the lookup no longer finds the original (it's `reversed`, not `posted`), so a **brand-new posted entry is created** — silently double-counting revenue/cash for that source row.

- **Trigger:** re-delivery / re-processing of a source event after its journal entry was reversed.
- **Fix:** make the idempotency check key on `(source_type, source_id)` regardless of status (treat an existing `posted` *or* `reversed` entry as "already handled"), or post against a dedicated source-event ledger keyed uniquely.

### H3 — STK-pushed amount is integer-truncated and diverges from the stored Decimal amount
**File:** `backend/app/services/payhero_service.py:138` and `backend/app/services/platform_payhero_service.py:137`

Both rails build the Pay Hero payload with `"amount": int(Decimal(str(amount)))` — **truncation, not rounding** (`int(Decimal("18500.75"))` → `18500`). The transaction row, however, is persisted with the full `Decimal` amount (`payhero_service.py:182`, `platform_payhero_service.py:178`). So the amount we **charge** can be less than the amount we **record** as owed/charged, and reconciliation against the receipt will mismatch. (Mitigant: M-Pesa requires whole-shilling amounts, so fractional inputs are unusual — but nothing upstream enforces integer KES, and the divergence is silent.)

- **Trigger:** any charge/STK with a non-integer KES amount.
- **Fix:** validate amounts to whole shillings at the boundary, or quantize consistently (`amount.quantize(Decimal('1'), ROUND_HALF_UP)`) and store the **same** value you charge.

### H4 — Payment amount has no positivity / overpayment validation
**File:** `backend/app/schemas/billing.py:8`, `backend/app/routes/billing.py:78-82`

`amount: float` accepts negative and zero values. A negative payment **decreases** `amount_paid` and can flip an invoice back out of "Paid"; a huge value silently over-pays with no cap against `total_amount - amount_paid`. The status logic (`:79`) only checks `>= total_amount`, so overpayment is accepted and recorded as fully paid with no credit/change tracking.

- **Trigger:** crafted or fat-fingered `amount` (negative, zero, or > outstanding).
- **Fix:** `condecimal(gt=0)`, and clamp/validate against the outstanding balance before applying. (Pharmacy already validates `amount <= 0` at `payhero_service.py:237`; billing does not.)

---

## MEDIUM

### M1 — Triage `gender` collapses every non-"Male" value to "F"
**File:** `backend/app/routes/triage.py:68` — `"gender": "M" if q.sex == "Male" else "F"`
Any `sex` that isn't exactly the string `"Male"` (e.g. `None`, `"Unknown"`, `"Other"`, `"female"` lowercased, `"M"`) is displayed as **Female**. For a clinical triage worklist this is a real data-correctness defect, not cosmetic.
**Fix:** map explicitly (`Male→M`, `Female→F`, else `"?"`/`"-"`), and don't infer from a single equality.

### M2 — Triage age uses `.days // 365` (no leap-year handling)
**File:** `backend/app/routes/triage.py:61`
`(today - dob).days // 365` drifts: every ~4 years it can report an age one year too high near a birthday, and it uses naive `datetime.now().date()` (server local, not UTC). For paediatric triage (where age bands drive dosing/acuity), an off-by-one is clinically relevant.
**Fix:** compute calendar age: `today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))`.

### M3 — Live-feed merge triggers a side-effecting `loadTxns()` from inside a state updater
**File:** `frontend/src/pages/superadmin/PlatformSubscriptions.jsx:87-94`
The `setTxns(prev => { … if (idx === -1) { loadTxns(); return prev; } … })` calls `loadTxns()` **inside the reducer**. React may invoke updaters twice (StrictMode/concurrent), firing duplicate network requests, and performing a side effect inside a pure updater is a correctness smell. Combined with the unconditional refetch on an unmatched frame, a burst of webhook frames for not-yet-loaded txns can stampede the API.
**Fix:** compute the "miss" outside the updater (e.g. set a flag / use a ref) and call `loadTxns()` from an effect; debounce refetches.

### M4 — Triage onward-route reuses a queue row in `"In Consultation"` but never reactivates it
**File:** `backend/app/routes/triage.py:126-133`
The `existing` lookup includes status `"In Consultation"`. If the patient is *currently being seen* and is re-triaged, the code only bumps `acuity_level` and returns that in-progress `queue_id` — the patient is **not** re-queued as "Waiting", so a genuine re-triage (deterioration) won't re-surface them on the doctor's waiting list. Whether this is intended is ambiguous; at minimum it's a silent behavioural edge.
**Fix:** clarify policy; likely only `("Waiting","In Progress")` should be treated as "already queued", and an active consult should mint a fresh waiting row.

### M5 — `payment_method_to_key` silently mis-buckets cheques/cards as a bank *payment* and unknowns as cash
**File:** `backend/app/services/accounting_posting.py:255-260`
`"cheque"`/`"check"`/`"card"` all map to `billing.payment.bank`, and any unrecognised method falls through to `billing.payment.cash`. A stray/misspelled method posts to the **cash** ledger account, corrupting the cash position and daily-collections report (`accounting_reports.py:336`) with money that never hit the till.
**Fix:** make unknown methods raise or post to a `billing.payment.unmapped` suspense account rather than defaulting to cash.

### M6 — Cash-flow classification mis-files multi-leg and mixed entries
**File:** `backend/app/services/accounting_reports.py:293-302, 321-331`
`_classify_cash_entry` returns the **first** matching type bucket (`Revenue/Expense → operating` wins over `Asset → investing`), so a compound entry that moves cash against both a revenue and an asset leg is wholly classified Operating. The whole-entry `net` is then dumped into one bucket. The docstring admits this is "best-effort", but it can materially misstate Investing/Financing sections.
**Fix:** classify per-cash-leg against its paired counter-leg, or require explicit cash-flow tagging (the noted "v2").

---

## LOW

### L1 — Triage queue `joined_time` formats with no timezone/locale guarantee
**File:** `backend/app/routes/triage.py:42` — `func.to_char(joined_at, 'HH12:MI AM')` renders in the **DB session timezone**, which may not be the hospital's local time. Minor display drift.

### L2 — `usePlatformPaymentSocket` never reconnects and ignores `onEvent` identity
**File:** `frontend/src/hooks/usePlatformPaymentSocket.js:20-47`
The effect depends only on `[enabled]`; if the socket drops (server restart, network blip) it is never re-opened, silently degrading to polling forever for that session. `onerror`/`onclose` are no-ops. Low because polling is the documented fallback.
**Fix:** add an `onclose` backoff-reconnect while `enabled`.

### L3 — Triage BMI rounds server-side to 1 dp but client computes independently
**File:** `backend/app/routes/triage.py:106-109` vs `frontend/src/pages/Triage.jsx:53-60`
Both compute BMI; the client sends its value and the server only recomputes when `calculated_bmi is None`. Two code paths for the same number invite drift if one formula changes. Cosmetic today (formulas match).

### L4 — `process_cash_card_payment` returns raw exception text to the client
**File:** `backend/app/routes/billing.py:110-112` — `raise HTTPException(400, detail=str(e))` leaks internal error strings (e.g. the Decimal TypeError, SQL fragments) to the caller. Information-disclosure smell; also makes the C1 failure look like a "bad request" to the UI.

---

## Top 10 fix-now

1. **C1** — Billing `Decimal += float` `TypeError`: make `PaymentRequest.amount` a `Decimal`/`condecimal(gt=0)` and coerce before adding (`billing.py:78,129`). Payments are likely failing in production.
2. **C2** — Add idempotency + `with_for_update` + `try/except rollback` to `charge_consultation_fee` (`billing.py:114-154`).
3. **H1** — Add idempotency / unique-queue guard to `/triage/submit` (`triage.py:79`).
4. **H2** — Fix auto-post idempotency to treat `posted` **or** `reversed` source entries as already-handled (`accounting_posting.py:106`).
5. **H4** — Validate payment amount `> 0` and against outstanding balance (`schemas/billing.py:8`).
6. **H3** — Stop integer-truncating STK amounts; quantize and store-what-you-charge on both rails (`payhero_service.py:138`, `platform_payhero_service.py:137`).
7. **M1** — Fix triage gender mapping (`triage.py:68`).
8. **M5** — Don't default unknown/cheque/card payment methods to the **cash** ledger account (`accounting_posting.py:255`).
9. **M2** — Use calendar-correct age in triage (`triage.py:61`).
10. **M3** — Move `loadTxns()` out of the `setTxns` updater in the live feed (`PlatformSubscriptions.jsx:87`).
