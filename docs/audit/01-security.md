# 01 — Security Audit (HMS-2)

**Scope:** authn/authz, payment rails (Pay Hero two-rail), multi-tenant isolation,
secret handling, injection/SSRF, CORS/CSRF/headers, frontend token storage.
**Branch:** `audit/world-class-codebase-20260530`
**Mode:** read-only (no code changed).
**Date:** 2026-05-30

## Executive summary

The auth and platform layers are unusually mature for an HMS at this stage:
Argon2id+pepper, server-side refresh-token registry with reuse detection,
HMAC-verified webhooks with IP allow-list, HttpOnly cookies (no JWT in
localStorage), double-submit CSRF, strong CSP/HSTS, Fernet at-rest encryption
with a fail-closed key validator, parameterised SQL with an inline identifier
whitelist for the one place identifiers must be interpolated, and tenant-scoped
WebSocket feeds. Many classic findings are already closed.

The remaining risk is concentrated in **payment integrity** and a few
**tenant-isolation hardening gaps**. The single most serious issue is that the
Pay Hero callback trusts the `Amount` in the webhook body and settles an invoice
for whatever it says, never cross-checking the amount of the STK push it
initiated. Combined with the per-tenant webhook-secret model (where a tenant
controls its own signing secret), this is an amount-integrity weakness that
deserves a fix before this rail carries production money.

**Counts:** CRITICAL 2 · HIGH 5 · MEDIUM 6 · LOW 5

---

## CRITICAL

### C-1 — Webhook amount is trusted; no reconciliation against the initiated STK amount
**Files:**
- `backend/app/routes/payhero_payment.py:298,353-373` (tenant rail)
- `backend/app/services/payhero_service.py:236-266` (`settle_invoice_match`)
- `backend/app/services/platform_payhero_service.py:225,260-261` (platform rail)

**Evidence.** In `_apply_callback_async` the settled amount comes straight from
the callback body:

```python
amount = Decimal(str(resp.get("Amount") or resp.get("amount") or 0))   # line 298
...
txn.amount = amount or txn.amount                                       # line 354
if txn.status == "Success" and txn.invoice_id:
    ...
    if invoice and amount > 0:
        settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="external_reference")
```

`settle_invoice_match` then does `invoice.amount_paid += amount` and marks the
invoice `Paid` when `amount_paid >= total_amount`. The pending `PayHeroTransaction`
row created at STK-push time already stored the **authoritative** amount
(`payhero_service.initiate_stk_push:182`, `amount=Decimal(str(amount))`), but the
callback **overwrites** it with the body value and never compares the two.

**Why exploitable.** The webhook is authenticated by an HMAC secret that, on the
tenant rail, is owned and set by the tenant itself
(`payhero_payment.py:253-280`, `_tenant_webhook_secret`). A tenant who knows
their own secret (or any party who obtains it) can craft a perfectly-signed
callback whose `Amount` is larger than the customer actually paid — the invoice
is marked Paid and a ledger entry is posted via `post_from_event` for the inflated
sum. Even absent a malicious tenant, a buggy/replayed/aggregator-side amount
mismatch silently corrupts AR. Because settlement also writes the accounting
ledger, this is a financial-integrity defect, not just a display bug.

**Fix.** Treat the pending transaction's stored amount as the source of truth and
reject/quarantine mismatches:

```python
# In _apply_callback_async, after locating the pending txn:
initiated = Decimal(str(txn.amount or 0))
paid = amount
if initiated > 0 and paid != initiated:
    # Do NOT settle. Flag for manual reconciliation.
    txn.status = "AmountMismatch"
    txn.result_desc = f"callback amount {paid} != initiated {initiated}"[:255]
    db.commit()
    logger.error("Pay Hero amount mismatch on %s: initiated=%s callback=%s",
                 external_ref, initiated, paid)
    return
# settle using the *initiated* amount, never the body amount
settle_invoice_match(db, invoice=invoice, txn=txn, match_basis="external_reference")
```

For partial-payment flows that legitimately differ, settle for
`min(paid, initiated)` and never more than initiated. Apply the same guard in
`apply_platform_callback` (platform rail, line 260-261, currently
`if amount > 0: txn.amount = amount`).

---

### C-2 — `X-Tenant-ID` header flows unvalidated into a live DB connection string
**Files:** `backend/app/config/database.py:100-118,146-154`

**Evidence.** `get_db()` reads the raw header and hands it to `get_tenant_engine`,
which builds a connection URL by string concatenation with **no allow-list check
against the master registry**:

```python
tenant_db_name = request.headers.get("X-Tenant-ID")            # 146
...
engine = get_tenant_engine(tenant_db_name)                     # 153
# get_tenant_engine:
base_url = DATABASE_URL.rsplit('/', 1)[0]
db_url = f"{base_url}/{tenant_db_name}"                         # 112-113
engine = create_engine(db_url, ...)                            # 115
```

Contrast the webhook path, which *does* validate the tenant against the registry
before opening an engine (`payhero_payment.py:221-243`, `_resolve_tenant_db`), and
the superadmin cross-tenant paths, which look the tenant up first
(`public.py`, `payhero_superadmin.py`). The primary request path does not.

**Why exploitable.** This is the multi-tenant trust boundary. The value is
authorized only indirectly: `get_current_user` requires the JWT's `tenant_id` to
equal `X-Tenant-ID` (`dependencies.py:165-170`), so for *authenticated* routes a
caller cannot point at another tenant's DB. But:
- Routes that depend on `get_db` **without** `get_current_user` (or whose
  dependency ordering lets the DB session resolve first) accept an
  attacker-chosen db_name.
- The string is interpolated into a libpq connection URL. A crafted value
  (`?options=...`, alternate host via `dbname` tricks, or simply probing for
  other tenants' db_names which are *publicly enumerable* via
  `GET /api/public/hospitals` → `db_name` field, `public.py:42`) can be used to
  open engines against arbitrary databases on the same server, and the LRU cache
  (`TENANT_ENGINE_CACHE_SIZE`) will retain them.
- Predictable/enumerable tenant identifiers (the public hospital list leaks every
  `db_name`) remove any "secret db name" defence.

**Fix.** Validate `X-Tenant-ID` against the master `Tenant` registry (active,
exists) **and** apply the same `_DB_NAME_RE` whitelist used at provisioning
(`tenant_provisioning.py:270`) before constructing any engine, with a short cache
of valid names:

```python
# database.py, in get_db before get_tenant_engine:
if not _TENANT_NAME_RE.fullmatch(tenant_db_name):
    raise HTTPException(400, "Invalid tenant identifier")
if not _is_registered_active_tenant(tenant_db_name):   # cached master lookup
    raise HTTPException(410, "tenant_not_found")
```

Also stop returning `db_name` in `GET /api/public/hospitals`
(`public.py:_serialize_tenant`) — the picker needs `tenant_id`/`name`, not the
raw database name.

---

## HIGH

### H-1 — Superadmin login has no rate limit and no account lockout
**File:** `backend/app/routes/public.py:419-462`

`superadmin_login` has no `@limiter.limit(...)` decorator and no
failed-attempt lockout, unlike the tenant `/api/auth/login` (`auth.py:142`,
`5/minute` + 5-strike 15-min lockout). The only throttle is the global
`120/minute` IP default from `SlowAPIMiddleware`. The superadmin holds
platform-wide power (provision/suspend tenants, cross-tenant patient read,
configure the money-receiving subscription rail), so its login is the highest-value
credential in the system and is the least protected against credential stuffing.
**Fix:** add `@limiter.limit("5/minute")` keyed on IP+email and a lockout column on
`SuperAdmin` mirroring the tenant lockout logic.

### H-2 — Permission cache makes RBAC revocations lag up to a full access-token lifetime
**File:** `backend/app/core/dependencies.py:32-52,175-211`

Effective permissions are cached in Redis keyed on the JWT `jti` with TTL =
`ACCESS_TOKEN_EXPIRE_MINUTES` (15 min). When an admin revokes a permission or
deactivates a role grant, in-flight tokens keep their old permission set until the
cached envelope expires — there is no invalidation hook on permission/role change
(only tenant feature-flags get an explicit cache drop, `public.py:297-302`).
For a security system this means "revoke access now" does not mean now. The cache
also does not re-check `user.is_active` on a cache hit (line 179-180 returns the
cached envelope before the `is_active` check at 194). **Fix:** invalidate
`perm:{jti}` (or a per-user generation counter) on any role/permission/override
write and on user deactivation; or skip the cache for the `is_active` gate.

### H-3 — Platform callback does not bind the receipt to the tenant named in the reference
**File:** `backend/app/services/platform_payhero_service.py:215-273`

`apply_platform_callback` matches a `PLAT-<tenant_id>-<nonce>` callback solely by
`external_reference` and trusts the body's amount/receipt. It never re-derives
`tenant_id` from the reference and confirms it matches the pending row's
`tenant_id`, so a signed callback that reuses another tenant's reference shape
(or a manipulated reference) is applied without a tenant-consistency check. On the
operator's only money-receiving rail, settlement should assert
`txn.tenant_id == parse_tenant(external_ref)` and reject otherwise. Couple with
the amount guard from C-1.

### H-4 — Forwarded-for spoofing weakens the webhook IP allow-list
**File:** `backend/app/core/payhero_webhook.py:45-58,89-93`

`_client_ip` trusts the first hop of `X-Forwarded-For` unconditionally. Any client
that can reach the app directly (or through a proxy that doesn't strip the header)
can set `X-Forwarded-For: <allow-listed-IP>` and pass the IP check. The IP
allow-list is described as "defence-in-depth" behind the HMAC, which limits the
blast radius, but the control is effectively bypassable as written. **Fix:** only
honor `X-Forwarded-For` from a configured set of trusted proxy IPs (Render/your LB
egress), else use `request.client.host`.

### H-5 — Superadmin patient detail returns every column incl. national ID, with no per-access audit
**File:** `backend/app/routes/public.py:379-411`

`get_patient_detail` reflects **all** `Patient` columns
(`for col in p.__table__.columns.keys(): out[col] = ...`), including `id_number`,
phone numbers, NOK, insurance — full PHI/PII — across any tenant. Unlike the
tenant-side KDPA export (`privacy.py:103-109`) which writes a `DataAccessLog`, this
cross-tenant superadmin read records **no audit entry** in the tenant DB. The code
comment claims "logged separately by the caller" but no caller-side logging exists
in this router. For KDPA accountability and breach-investigation this cross-tenant
PHI read must be logged. **Fix:** write a `DataAccessLog`/audit row (in the tenant
DB and/or a master audit table) for every superadmin patient read, and consider
field minimisation (don't blanket-reflect `id_number`).

---

## MEDIUM

### M-1 — `forgot-password` returns the reset token in the response in non-production
**File:** `backend/app/auth/auth.py:438-439`

`if not settings.is_production: response["dev_token"] = raw_token`. Correctly gated
on `APP_ENV`, but it is a single env-var flip away from leaking live reset tokens,
and any staging environment that forgets to set `APP_ENV=production` exposes them.
Prefer logging the token server-side (debug) over returning it in the HTTP body even
in dev, and add a CI check that `APP_ENV=production` is set in prod manifests.

### M-2 — STK-push trigger does not enforce that `amount` matches the invoice balance
**File:** `backend/app/routes/payhero_payment.py:48-66`

`trigger_stk_push` accepts a client `amount` and only checks the invoice exists and
isn't already Paid; it pushes whatever amount the caller sends. A
`billing:manage` user can under/over-charge relative to the invoice. Combined with
C-1 (callback trusts body amount), the only amount the system ever validates against
the invoice is none. **Fix:** default/clamp `amount` to the invoice outstanding
balance server-side; reject amounts exceeding the balance.

### M-3 — `Decimal` parsing of attacker-influenced amounts can raise / floor unexpectedly
**Files:** `payhero_service.py:139` (`int(Decimal(str(amount)))`),
`payhero_payment.py:298`

`int(Decimal(str(amount)))` truncates fractional KES silently and
`Decimal(str(...))` on a non-numeric body field raises `InvalidOperation` inside the
background task (caught broadly, but the callback is then dropped with only a log).
Validate numeric ranges explicitly and reject non-numeric amounts before settlement
rather than relying on the blanket `except Exception`.

### M-4 — Webhook has no timestamp/nonce replay window beyond receipt-uniqueness
**Files:** `payhero_webhook.py:74-110`, `payhero_payment.py:283-351`

Replay is blocked *after the fact* by `UNIQUE(receipt_number)` and the advisory
lock — good for idempotency. But a captured, validly-signed callback with **no**
receipt number yet (a "pending/processing" frame) or with a reused
`external_reference` can still drive state transitions, and there is no signed
timestamp freshness check, so an old signed body replays indefinitely until a
receipt lands. Add a signed-timestamp tolerance (reject bodies older than N
minutes) if Pay Hero provides one, and ignore callbacks whose status regresses.

### M-5 — CORS `allow_credentials=True` with env-driven origin list — preview domains risk
**Files:** `backend/app/main.py:122-140`, `settings.py:65`

Config is correct (explicit method/header allow-list, no wildcard), but the dev
default `CORS_ORIGINS` includes localhost origins and the model only *documents*
that production must override. There is no runtime assertion that, when
`is_production`, the origin list excludes localhost and is non-empty/closed. With
`allow_credentials=True` a stray preview/localhost origin = credentialed
cross-origin access. **Fix:** in `is_production`, validate `cors_origin_list` is
non-empty and contains no `localhost`/`127.0.0.1`/wildcard entries (fail boot
otherwise, consistent with the SEC-001 fail-fast pattern).

### M-6 — Tenant DB names are publicly enumerable
**File:** `backend/app/routes/public.py:42,183-198`

`GET /api/public/hospitals` is unauthenticated and returns `db_name` for every
active tenant. That hands an attacker the exact identifiers needed to exploit C-2
and is itself information disclosure of internal infrastructure naming. Remove
`db_name` from the public serialization (keep it in superadmin views only).

---

## LOW

### L-1 — `python-jose` carries an unpatched advisory (PYSEC-2025-185), ignored in CI
**Files:** `.github/workflows/security.yml:52-55`, `core/security.py:18-26`
The pin to HS256 and the documented mitigation are reasonable, but the suppression
means any *new* jose CVE on the HS256 path is also masked by the broad
`--ignore-vuln`. Track a migration to PyJWT (removes the `ecdsa` transitive dep)
and scope the ignore narrowly.

### L-2 — `.env.example` ships a weak default superadmin password
**File:** `.env.example` (`SEED_SUPERADMIN_PASSWORD=SuperAdmin@2026`)
A copied-then-unedited `.env` boots a platform superadmin with a guessable
credential. Document a mandatory rotation, or have the seed script refuse this exact
string in production.

### L-3 — `npm audit` is `--audit-level=high` warn-context only; backend lacks SAST
**File:** `.github/workflows/security.yml:64-71`
Frontend audit won't fail on high transitive CVEs in some configs, and there is no
CodeQL/semgrep job despite the code referencing "CodeQL alerts" in comments. Add a
SAST job (CodeQL) to the security workflow.

### L-4 — Process-time header leaks backend timing
**File:** `backend/app/main.py:143-149`
`X-Process-Time` is exposed via CORS (`expose_headers`) and returned on every
response, giving an attacker a precise timing oracle for the (otherwise
time-equalized) auth endpoints. Strip it in production or stop exposing it.

### L-5 — Refresh-token registry stores client IP/UA but reuse-revoke is global, not device-scoped
**File:** `backend/app/auth/auth.py:62-75,262-271`
On reuse detection every session for the user is burned (correct, conservative),
but there is no signal to the user/admin that this happened beyond a 401. Consider
an audit/security-event emission so the abuse is visible, not silent.

---

## Top 10 fix-now

1. **C-1** — Reconcile webhook `Amount` against the initiated STK amount before
   settling; quarantine mismatches. Both tenant and platform rails.
2. **C-2** — Validate `X-Tenant-ID` against the master registry + identifier
   whitelist before opening any tenant engine in `get_db`.
3. **M-6 / C-2 enabler** — Stop returning `db_name` from
   `GET /api/public/hospitals`.
4. **H-1** — Rate-limit + lockout the superadmin login (`5/minute`, strike
   counter).
5. **H-3** — Bind platform callbacks to the `tenant_id` parsed from the
   `PLAT-<id>-` reference.
6. **H-4** — Only trust `X-Forwarded-For` from configured trusted-proxy IPs in the
   webhook IP check.
7. **H-2** — Invalidate the per-jti permission cache (and re-check `is_active`) on
   role/permission/override change and user deactivation.
8. **H-5** — Audit-log every superadmin cross-tenant patient read; minimise PHI
   fields returned.
9. **M-2** — Clamp STK-push `amount` to the invoice outstanding balance
   server-side.
10. **M-5** — Fail boot if production CORS origins are empty or include
    localhost/wildcard.
