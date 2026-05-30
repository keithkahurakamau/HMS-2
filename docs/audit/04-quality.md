# Audit 04 — Code Quality & Architecture

Branch: `audit/world-class-codebase-20260530`
Auditor: code-quality & architecture
Scope: `backend/app` (FastAPI, ~19.6k LOC) + `frontend/src` (React/Vite, ~26.8k LOC). Read-only.
Project rule under audit: **files must stay under 500 lines** (CLAUDE.md).

> Tooling note: `Bash` (wc/find/grep/git) was unavailable in this session, so
> line counts for the seven backend offenders come from the audit brief and were
> spot-verified by reading each file end-to-end. The frontend offenders below
> were discovered by reading the page tree from `App.jsx` and opening the
> largest files directly. A follow-up `wc -l frontend/src/**/*.jsx` pass is
> recommended to enumerate every frontend file over 500 lines — at least one
> (`Accounting.jsx`, 2,960 lines) is confirmed and is by far the worst offender
> in the entire codebase.

---

## HIGH

### H1. `frontend/src/pages/Accounting.jsx` — 2,960 lines (≈6× the 500-line limit)
Single file holds 8 tab components, 5 config sub-sections, ~10 CRUD modals, and
the shared shells (`ModalShell`, `ModalActions`, `Field`) all inline.
Evidence: `Accounting.jsx:44` (root), `:89 ChartOfAccountsTab`, `:260 JournalEntriesTab`,
`:554 CurrenciesTab`, `:726 SettingsTab`, `:821 ConfigurationTab` with sections at
`:853 SuppliersSection`, `:991 InsuranceSection`, `:1108 SchemesSection`, `:1233 PriceListSection`,
plus `BankTab`/`DebtorsTab`/`ReportsTab` and the shells at `:2921 ModalShell`, `:2937 ModalActions`, `:2952 Field`.
This is the single biggest quality liability in the repo. See Refactor plan RP-1.
**Remediation:** split into `pages/accounting/` directory — one file per tab, a
`components/accounting/` for the per-entity modals, and promote `ModalShell`/`ModalActions`/`Field`
to `components/ui/`.

### H2. Fat routes carrying business logic that belongs in a service layer
There is **no service layer for the transactional modules** — pharmacy, cheques,
laboratory, messaging, and admin all embed inventory math, invoice posting,
ledger posting, and state-machine transitions directly inside the HTTP handler.
- `pharmacy.py:59-176` `dispense_drug` — does idempotency, FEFO stock deduction,
  invoice creation/rollup, ledger posting, audit, and response shaping in one
  118-line handler wrapped in a broad `try/except Exception`.
- `pharmacy.py:451-570` `pharmacy_transactions` — builds a correlated subquery +
  multi-table outer-join report inline in the route.
- `cheques.py` — the entire incoming/outgoing state machine
  (`deposit`/`dispatch`/`clear`/`bounce`/`return`/`stop`/`cancel`) lives in the
  router; `clear_cheque` (`cheques.py:441-510`) posts Payments and GL entries inline.
- `laboratory.py:416-482` `complete_lab_test` — inventory deduction + reusable-item
  logic inside the handler.
**Remediation:** introduce `app/services/<module>.py` (a `cheque_service`,
`pharmacy_service`, `lab_service`) that takes a `Session` + DTO and returns
domain objects; routes become thin (validate → call service → serialize). This
also makes the >500-line route files shrink naturally.

### H3. Pervasive lookup-or-404 boilerplate (DRY violation across every route file)
The exact pattern
```python
x = db.query(Model).filter(Model.id == id).first()
if not x:
    raise HTTPException(status_code=404, detail="... not found.")
```
is repeated dozens of times. Confirmed instances:
`cheques.py:276,304,307,364,379,382` and again in every action endpoint (`:404,:426,:456,:521,:551,:581,:607`);
`admin.py:140,153,218,239,249,363,396,420,455,505`;
`laboratory.py:211,225,241,260,275,394,424,497`;
`messaging.py:217,318,496,527,589`;
`pharmacy.py:36,81,185,402,408`.
**Remediation:** add `app/core/crud.py` with `get_or_404(db, Model, pk, name=...)`
and a `RequireRecord` dependency. Replaces ~40 four-line blocks with one call each.

### H4. `frontend` — repeated data-fetch + modal + error-toast pattern across all pages (DRY)
Every page reimplements the same trio of state hooks and handlers:
`const [items,setItems]=useState([]); const [loading,setLoading]=useState(true);`
+ a `load()` that does `try { const r = await apiClient.get(...) } catch { toast.error('Could not load …') } finally { setLoading(false) }`
+ a submit handler that does `toast.error(err?.response?.data?.detail || '…')`.
Confirmed in `Accounting.jsx` at `:94,:267,:560,:730,:859,:997,:1115,:1241` (8 copies in one file alone),
and the same shape in `Inventory.jsx`, `Pharmacy.jsx`, `MpesaSettings.jsx:31-40`.
The `err?.response?.data?.detail || '…'` idiom appears at `Accounting.jsx:212,293,305,439,643,690,752,765,941,1073,1203` and across other pages.
**Remediation:** ship a `useResource(url)` hook (returns `{data, loading, reload}`)
and a `useMutation` helper that centralizes the detail-extraction + toast. The
backend `api/client.js:87 normalizeFastApiDetail` already normalizes `detail`,
so a single `getErrorMessage(err)` util would DRY every callsite.

### H5. `Accounting.jsx`-local UI shells duplicate inline markup used everywhere else
`ModalShell` (`:2921`), `ModalActions` (`:2937`), `Field` (`:2952`),
`SectionHeader`, and `DataCard` are defined privately inside Accounting.jsx, yet
the *same* modal/overlay markup (`fixed inset-0 bg-ink-900/40 backdrop-blur-sm …`)
and label/input pattern are hand-rolled inline in Inventory, Pharmacy, Cheques,
etc. `PageHeader` (`components/PageHeader.jsx`) proves the team already has a
shared-component convention — these belong there too.
**Remediation:** move to `components/ui/{Modal,Field,FormActions,DataCard,SectionHeader}.jsx`
and import everywhere; delete the per-page copies.

---

## MEDIUM

### M1. Remaining backend files over 500 lines (the brief's list)
All verified by full read:
- `routes/admin.py` (603) — 7 unrelated concerns in one router (metrics, staff
  CRUD, audit log, pricing catalog, role perms, custom roles, per-user
  overrides). Inline Pydantic models at `:59` and `:284`. See RP-3.
- `routes/messaging.py` (594) — conversations + departments + serializers; the
  department-sync logic (`:402 _sync_department_conversation`) is service-grade. See RP-4.
- `services/tenant_provisioning.py` (575) — dominated by two large data
  constants (`DEFAULT_SETTINGS` `:77-109`, `PERMISSION_CATALOG` `:115-191`,
  `ROLE_GRANTS` `:204-237`). Logic is fine; just extract the seed data. See RP-5.
- `routes/pharmacy.py` (569) — see H2. See RP-2.
- `models/accounting.py` (560) — 12 ORM table classes; no logic, pure schema. See RP-6.
- `routes/laboratory.py` (509) — catalog/parameter CRUD + queue + complete/reject.
  Inline schemas at `:25-86` and a stray mid-file `class CollectRequest` at `:383`. See RP-7.

### M2. Inconsistent error handling — three different styles coexist
- Broad `except Exception as e: raise HTTPException(500, detail=str(e))` **leaks
  internal error text to clients**: `pharmacy.py:173-176`, `laboratory.py:152-154,168-170,311-313,479-482`.
  This contradicts `main.py:247` global handler which deliberately returns a
  generic "internal server error" message — these per-route catches defeat it.
- Most other routes (`cheques.py`, `admin.py`, `messaging.py`) correctly let
  exceptions bubble to the global handler.
**Remediation:** delete the per-route `except Exception` blocks; rely on the
global handler. Keep only specific catches (e.g. `ValueError` → 400 in
`laboratory.py:476`). Never `detail=str(e)` on a 500.

### M3. Inline Pydantic schemas scattered through route bodies
`admin.py` defines `StaffCreateRequest` (`:59`), `RoleCreateRequest` (`:284`),
`RoleUpdateRequest` (`:300`) inside the router file, plus a bare `import re` at
`:57` mid-module. `laboratory.py` defines all payloads at `:25-86` then a *second*
`class CollectRequest` buried at `:383`. `cheques.py` defines 11 request models
`:63-143`. Meanwhile `pharmacy.py` and `messaging.py` correctly import from
`app/schemas/`. Inconsistent — pick one (the `app/schemas/<module>.py` convention
already established) and move all inline models there.

### M4. Untyped `payload: dict` request bodies bypass validation
Several mutating endpoints accept raw `dict` instead of a typed schema, losing
validation and OpenAPI docs:
`admin.py:136 toggle_user_status`, `:152 update_user_role`, `:202 create_service_pricing`,
`:217 update_service_pricing`, `:245 update_role_permissions`, `:392 update_role_permissions_by_id`,
`:482 set_user_permissions`. These then do manual `payload.get(...)` with float
coercion (`:206 float(payload.get("base_price", 0.0))`).
**Remediation:** replace with Pydantic models so bad input 422s at the boundary
(CLAUDE.md: "validate input at system boundaries").

### M5. N+1 query loops in list/queue endpoints
- `laboratory.py:136-150` `get_lab_queue` — for each test, three separate
  `db.query(...).first()` calls (Patient, User, Catalog) inside the loop.
- `laboratory.py:299-309` `get_lab_inventory` — per-batch `InventoryItem` lookup.
- `pharmacy.py:549-554` — per-row `payment_count` query inside the result loop.
- `admin.py:319-329` `list_roles` — per-role `user_count` count query in a loop.
(The untracked root `analyze.py` was clearly written to find exactly these; its
heuristics are valid even though the script itself should not be in the repo —
see R3.) Cross-reference with the performance audit; flagged here as an
architecture smell (queries belong in a service with eager-loading/joins).

### M6. Missing return-type hints on backend handlers
Almost no route handler declares a return type (`-> dict` / `-> list[...]`), and
several helpers omit param types. SQLAlchemy models also lack `Mapped[...]`
typing (pre-2.0 `Column` style throughout, e.g. `models/accounting.py`). Not
blocking, but inconsistent with the otherwise-typed service signatures
(`tenant_provisioning.provision_tenant` is fully typed). Recommend enabling
`mypy`/`ruff` type-checking in CI to enforce.

### M7. Frontend has zero prop validation and no TypeScript
`package.json` ships `@types/react` but the app is `.jsx`, not `.tsx`, and no
component declares `propTypes`. `PageHeader` takes 8 props (`PageHeader.jsx:30`),
modals take `initial/onClose/onSaved`, etc., all unchecked. For a 26.8k-LOC app
this is a real maintainability gap.
**Remediation:** either adopt `prop-types` on shared/reused components, or
incrementally migrate to TypeScript (deps are already present).

### M8. Dependency hygiene — frontend `lucide-react` pinned to an impossible/odd version
`frontend/package.json:17` pins `"lucide-react": "^1.8.0"`. lucide-react's real
versions are 0.x (e.g. 0.4xx). A `^1.8.0` range is suspicious — verify it
resolves, and align with the installed lockfile. Also `react@^19.2.4`,
`vite@^8.0.4`, `react-router-dom@^7.14.1` are very new majors; confirm they're
intentional and that the lockfile is committed.
**Remediation:** run `npm outdated` / `npm ls lucide-react`, correct the range,
and ensure `package-lock.json` is tracked.

---

## LOW

### L1. Backend requirements appear healthy but unpinned-by-purpose
`requirements.txt` is a flat fully-pinned freeze (52 lines, good). No obvious
duplicates. Minor: it mixes direct deps (fastapi, sqlalchemy) with transitive
ones (annotated-doc, wrapt, six, ecdsa) in one file — consider a
`requirements.in` + `pip-compile` split so intent is visible. `python-jose`
pulls `ecdsa`/`rsa`/`pyasn1` (a known historically-CVE-prone chain) — defer to
the security audit.

### L2. Stray mid-file imports
`admin.py:56 from pydantic import …` and `:57 import re` appear *after* the first
route definition; `pharmacy.py:391,401,407` and `:476-478` do function-local
imports (`from app.models.settings import HospitalSetting`, etc.);
`laboratory.py:22 from pydantic import …` sits between routers. Hoist to the top
import block.

### L3. `noqa`-suppressed unused import kept "for forward-compat"
`tenant_provisioning.py:30 from app.config.settings import settings  # noqa: F401`
— either use it or drop it; "kept for forward-compat" is dead weight.

### L4. Magic strings for status/state everywhere
Cheque statuses, lab statuses ("Pending", "In Progress", "Completed"), invoice
statuses ("Pending"/"Paid"/"Partially Paid"), and account types are bare string
literals duplicated across routes and the frontend. `cheques.py` at least
centralizes them (`:46-60`); `laboratory.py:131,353,397,469` and
`pharmacy.py:111,253` do not. Promote to `Enum`/constants shared module.

### L5. Naming inconsistency: PK column names
Mixed `cheque_id`/`user_id`/`patient_id` (snake-prefixed) vs `id`
(`PayHeroTransaction.id`, referenced `pharmacy.py:302,349`). Harmless but worth
a convention note.

---

## Repo hygiene

### R1. `ruvector.db` (1.5 MB binary) is committed despite being .gitignored — HIGH
`.gitignore:101` lists `ruvector.db` and `.gitignore:104` lists `*.db`, but the
file was committed **before** the ignore rule was added, so git keeps tracking
it (gitignore never untracks). A 1.5 MB AI-tooling vector DB has no business in
app history.
**Remediation:** `git rm --cached ruvector.db` (keep local), commit. Consider
`git filter-repo` to purge it from history if size matters.

### R2. `CLAUDE.md` is committed but also .gitignored — confusing
`.gitignore:100` lists `CLAUDE.md` (AI tooling), yet it's checked in and the
audit context treats it as the source of project rules. Decide: if it's the
canonical ruleset, remove the ignore entry; if it's local-only tooling, untrack
it. Right now the ignore line is dead.

### R3. Root-level `analyze.py` (93 lines, untracked) — stray script
Confirmed untracked (`?? analyze.py` in git status). It's a one-off AST/regex DB
query scanner whose paths are hardcoded to a non-existent `/Ubuntu/...` prefix
(`analyze.py:89-91`), so it doesn't even run as-is. It violates CLAUDE.md ("never
save working files to root — use /scripts").
**Remediation:** either move to `backend/scripts/` and fix the paths, or delete.
Do **not** commit it to root.

### R4. Local utility scripts ignored but pattern is fragile
`.gitignore:107-109` ignores three specific backend scripts by name
(`fix_permissions.py`, `check_users.py`, `reset_admin.py`). Per-file ignores rot;
prefer a `backend/scripts/local/` dir that's ignored wholesale.

### R5. `.gitignore` ordering bug makes `ruvector.db`/`CLAUDE.md` rules ineffective
Both are listed under "Claude Code & AI tooling" (`:95-101`) but are already
tracked — see R1/R2. Net effect: the ignore section gives false confidence that
these are excluded when they are not.

---

## Refactor plans (each >500-line file)

### RP-1 — `Accounting.jsx` (2,960 → ~8 files under 400 each)
```
pages/accounting/
  index.jsx                 # tab shell (the current root component, ~80 lines)
  ChartOfAccountsTab.jsx
  JournalEntriesTab.jsx
  ReportsTab.jsx
  DebtorsTab.jsx
  BankTab.jsx
  CurrenciesTab.jsx
  SettingsTab.jsx
  ConfigurationTab.jsx      # + config/ sub-sections as own files
components/ui/Modal.jsx      # ← promote ModalShell
components/ui/Field.jsx
components/ui/FormActions.jsx # ← promote ModalActions
components/ui/DataCard.jsx
components/ui/SectionHeader.jsx
```
Each entity modal (Supplier/Provider/Scheme/PriceList/Mapping/Account/Journal/
Currency/FxRate) becomes its own file. Shared `formatAmount`, `STATUS_BADGE`,
`TYPE_TONE` move to `accounting/constants.js`.

### RP-2 — `pharmacy.py` (569 → ~250)
Extract `app/services/pharmacy_service.py`: `dispense(db, dto, user)` (the
`dispense_drug` body), `collect_payment(...)`, `build_transaction_ledger(...)`
(the `pharmacy_transactions` query builder). Move `_resolve_dispense_invoice`
and the receipt-assembly dict into the service. Route file keeps only
HTTP wiring + `RequirePermission`. Drop the broad `except Exception` (M2).

### RP-3 — `admin.py` (603 → 4 routers under 250)
Split by concern into a package:
```
routes/admin/__init__.py     # aggregates the sub-routers
routes/admin/metrics.py      # /metrics
routes/admin/staff.py        # /users CRUD + status/role
routes/admin/audit.py        # /audit-logs
routes/admin/pricing.py      # /pricing
routes/admin/rbac.py         # /roles, /permissions, per-user overrides
```
Move `StaffCreateRequest`/`RoleCreateRequest`/`RoleUpdateRequest` to
`app/schemas/admin.py`. Extract the effective-permission resolver
(`set_user_permissions` body, `:482-604`) to `app/services/rbac.py`.

### RP-4 — `messaging.py` (594 → ~300)
Move serializers (`_serialize_message`, `_serialize_conversation`,
`_serialize_department`) to `app/schemas/messaging_serializers.py` (or response
models). Extract conversation/department domain logic — especially
`_sync_department_conversation` (`:402`) and the direct-DM-dedup query
(`:224-255`) — into `app/services/messaging_service.py`. Routes keep WebSocket
broadcast wiring only.

### RP-5 — `tenant_provisioning.py` (575 → ~300)
Pure data extraction (no logic change):
```
app/seed_data/default_settings.py   # DEFAULT_SETTINGS, DEFAULT_LOCATIONS
app/core/permissions_catalog.py     # PERMISSION_CATALOG, ROLE_GRANTS, derived lists
```
`tenant_provisioning.py` imports them and keeps only the provisioning flow
(`provision_tenant`, `_seed_baseline`, `backfill_admin_permissions`, db helpers).
Note: the model-import block (`:40-59`) is load-bearing — keep it (see
project memory "migrate_all_tenants model imports").

### RP-6 — `models/accounting.py` (560 → 4 files under 200)
Split the 12 tables by sub-domain into a package:
```
models/accounting/__init__.py   # re-exports all for back-comat imports
models/accounting/ledger.py     # Currency, FxRate, Account, FiscalPeriod, JournalEntry, JournalLine, AccountingSettings
models/accounting/config.py     # Supplier, InsuranceProvider, MedicalScheme, PriceListItem, LedgerMapping
models/accounting/debtors.py    # ClaimSchedule, ClaimScheduleItem, ClientDeposit, DepositApplication
models/accounting/bank.py       # BankAccount, BankTransaction
```
Keep `__init__.py` re-exporting everything so `tenant_provisioning.py:59` and
other `from app.models.accounting import ...` callsites don't break.

### RP-7 — `laboratory.py` (509 → ~300)
Move all payloads to `app/schemas/laboratory.py` (including the orphaned
`CollectRequest` at `:383`). Extract `complete_lab_test`'s inventory-deduction
loop and `create_lab_orders`'s catalog-validation into
`app/services/lab_service.py`. Fix the N+1 queue loop (M5) while there with a
single joined query. Drop the broad `except Exception` blocks (M2).

---

## Top 10 fix-now (cheap, high-impact)

1. **`git rm --cached ruvector.db`** — stop tracking a 1.5 MB binary that's
   already gitignored (R1). One command.
2. **Delete or relocate root `analyze.py`** — untracked, broken paths, violates
   CLAUDE.md root rule (R3).
3. **Delete the 5 broad `except Exception: detail=str(e)` blocks** in
   `pharmacy.py:173`, `laboratory.py:152,168,311,479` — they leak internals and
   defeat the global handler (M2).
4. **Add `app/core/crud.py::get_or_404`** and replace the ~40 lookup-or-404
   blocks (H3). Mechanical, big readability win.
5. **Add `frontend getErrorMessage(err)` util** and replace the ~15
   `err?.response?.data?.detail || '…'` callsites (H4).
6. **Promote `ModalShell`/`ModalActions`/`Field` out of Accounting.jsx** into
   `components/ui/` (H5) — unblocks the Accounting split and de-dupes other pages.
7. **Fix `lucide-react` version range** in `package.json:17` (`^1.8.0` looks
   wrong) and confirm the lockfile is committed (M8).
8. **Hoist mid-file imports** in `admin.py:56-57`, `laboratory.py:22`,
   `pharmacy.py:391,401,407` to module top (L2).
9. **Replace `payload: dict` with Pydantic models** on the 7 `admin.py`
   endpoints (M4) — restores boundary validation per CLAUDE.md.
10. **Move inline route schemas to `app/schemas/`** for `admin.py`,
    `laboratory.py`, `cheques.py` (M3) — the convention already exists in
    `pharmacy.py`/`messaging.py`.
```
