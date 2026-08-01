# Dialysis / Renal Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a nephrology-grade Dialysis module (HD) to HMS-2 — renal profile, per-session orders with prescription/anticoagulation, machine safety checklists, a session state machine, append-only intradialytic monitoring, complications, adequacy (URR + Kt/V), consumables, and unit management (machines + recurring roster).

**Architecture:** Follows the Maternity module pattern exactly — `models/dialysis.py` + `schemas/dialysis.py` + `routes/dialysis.py` (module-gated, `RequirePermission`), one alembic `add_dialysis_tables` revision registered in `migrate_all_tenants.py` with a `dialysis_seed.py` hook, and a thin `pages/Dialysis.jsx` wrapper over a `pages/dialysis/` subdir of tabs/forms with a local `api.js`. Full schema in [2026-07-22-dialysis-module-design.md](../specs/2026-07-22-dialysis-module-design.md).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic (backend); React + Vite + Tailwind + Vitest/RTL (frontend); pytest live-server (backend tests).

## Global Constraints

- Branch `feat/dialysis-module` off `development`; PR into `development` only (never beta/main directly).
- Migration gate: `add_dialysis_tables` revision **and** `dialysis` registered in `migrate_all_tenants.py` model-imports **and** `dialysis_seed.py` hooked into `migrate_one`. `migrate_all_tenants.py` must stay green on fresh Postgres.
- Every module route behind `RequirePermission("dialysis:*")` and the `dialysis` module gate; module-gated tests must enable `feature_flags.dialysis` in `mayoclinic_db` (and `REDIS_URL=""` for local uvicorn).
- Files under 500 lines; `models/dialysis.py`, `routes/dialysis.py`, `schemas/dialysis.py` each one responsibility. Split routes if >500 lines (`dialysis.py` + `dialysis_unit.py` for Phase 2).
- `npm run build` + `eslint` before every push (vite build misses no-undef).
- Keys/enums copied verbatim from the design doc. Kt/V = Daugirdas 2nd-gen: `−ln(R − 0.008·t) + (4 − 3.5·R)·UF/W`, `R = post_urea/pre_urea`, `t`=hours, `UF`=litres, `W`=post_weight_kg. URR = `(1 − post_urea/pre_urea)·100`.

---

## PHASE 1 — Clinical core (shippable)

### Task 1: Data model + migration + seed

**Files:**
- Create: `backend/app/models/dialysis.py`
- Create: `backend/alembic/versions/<rev>_add_dialysis_tables.py`
- Create: `backend/app/services/dialysis_seed.py`
- Modify: `backend/scripts/migrate_all_tenants.py` (imports block + seed hook)
- Test: `backend/tests/test_dialysis_migration.py`

**Interfaces:**
- Produces: SQLAlchemy models `DialysisChecklist, DialysisMachine, DialysisOrder, DialysisObservation, DialysisComplication, DialysisAdequacy, DialysisConsumable, DialysisChecklistRun, VascularAccess, DialysisSchedule` (all 10 tables land in this one migration; Phase-1 code uses the first 8). `seed_dialysis_checklists(conn) -> int`.

- [ ] **Step 1: Write `models/dialysis.py`** — all 10 tables per the design doc §Data model, mirroring `models/maternity.py` conventions (Integer PKs, `ForeignKey(..., ondelete=...)`, `recorded_by/created_by → users.user_id SET NULL`, `created_at = Column(DateTime(timezone=True), server_default=func.now())`, `Numeric` measurements, string status enums). `DialysisOrder.__table_args__` includes the partial unique index:
```python
Index("uq_dialysis_active_per_patient", "patient_id", unique=True,
      postgresql_where=text("status NOT IN ('Completed','Cancelled')"))
```
- [ ] **Step 2: Generate alembic revision** — `cd backend && alembic revision -m "add dialysis tables"`; set `down_revision` to current head (`alembic heads`); hand-write `upgrade()` creating all 10 tables + the partial index, `downgrade()` dropping them (reverse order).
- [ ] **Step 3: Register model + seed in `migrate_all_tenants.py`** — add `dialysis` to the `from app.models import (...)` block; add `_seed_dialysis(tenant_url)` mirroring `_seed_maternity_price_list`, calling `seed_dialysis_checklists`, and invoke it in `migrate_one` after migrate.
- [ ] **Step 4: Write `dialysis_seed.py`** — `seed_dialysis_checklists(conn)` inserts the 5 default checklists (idempotent: skip if `dialysis_checklists` non-empty) + 1 demo machine; returns rows inserted.
- [ ] **Step 5: Test migration on fresh DB** — `test_dialysis_migration.py`: run `migrate_all_tenants` against fresh Postgres; assert all 10 tables exist and `dialysis_checklists` has ≥5 rows.

Run: `cd backend && python scripts/migrate_all_tenants.py && pytest tests/test_dialysis_migration.py -v`
Expected: PASS; tables present; checklists seeded.

- [ ] **Step 6: Commit** — `git commit -m "feat(dialysis): data model + migration + checklist seed"`

### Task 2: Schemas + module registration + RBAC

**Files:**
- Create: `backend/app/schemas/dialysis.py`
- Modify: `backend/app/core/modules.py` (MODULES + PERMISSION_CATALOG + ROLE_GRANTS)
- Modify: `backend/app/main.py` (import + include_router — router added empty in Task 3)
- Test: `backend/tests/test_dialysis_rbac.py`

**Interfaces:**
- Produces: Pydantic `DialysisOrderCreate/Out, ObservationCreate/Out, ComplicationCreate/Out, AdequacyCreate/Out, ChecklistRun*, Checklist*` etc. Permissions `dialysis:read|write|manage`.

- [ ] **Step 1: Write failing RBAC test** — assert `"dialysis"` in `MODULES`, and `dialysis:read/write/manage` in `PERMISSION_CATALOG`, and granted to roles Nurse/ClinicalOfficer/MedicalOfficer (read+write) and Admin (manage).
- [ ] **Step 2: Run — FAIL** (`KeyError`/assert). `pytest tests/test_dialysis_rbac.py -v`
- [ ] **Step 3: Register** — add `dialysis` to `MODULES`; `dialysis:read/write/manage` to `PERMISSION_CATALOG`; grants to `ROLE_GRANTS` (Nurse+CO+MO → read,write; Admin/Nephrologist → manage). Follow the exact dict/list shape already used for `maternity`.
- [ ] **Step 4: Write `schemas/dialysis.py`** — request/response models matching the design doc fields; `AdequacyOut` includes computed `urr`, `kt_v`.
- [ ] **Step 5: Run — PASS.**
- [ ] **Step 6: Commit** — `feat(dialysis): schemas + module/RBAC registration`

### Task 3: Orders — create / list / detail

**Files:**
- Create: `backend/app/routes/dialysis.py`
- Modify: `backend/app/main.py` (wire the real router)
- Test: `backend/tests/test_dialysis_orders.py`

**Interfaces:**
- Consumes: models + schemas (Tasks 1-2), `RequirePermission`, `get_current_user`, tenant/db session deps (copy from `routes/maternity.py`).
- Produces: `GET /dialysis/orders`, `POST /dialysis/orders`, `GET /dialysis/orders/{id}`.

- [ ] **Step 1: Failing tests** — (a) POST creates an order for a patient → 201 + status `Ordered`; (b) GET list returns it, filterable by `status`/`patient`; (c) GET `{id}` embeds empty observations/complications/adequacy/checklist_runs/consumables; (d) module-gate 402 when `dialysis` flag off; (e) `dialysis:write` required for POST (nurse allowed, unauthorized role 403).
- [ ] **Step 2: Run — FAIL** (404 route). `pytest tests/test_dialysis_orders.py -v`
- [ ] **Step 3: Implement** — `APIRouter(prefix="/dialysis", tags=["dialysis"])`; `create_order`, `list_orders`, `get_order`; enforce one-live-session (catch IntegrityError on partial index → 409 "patient already has a live session"); `treatment_no` = count of patient's prior orders + 1. Wire router in `main.py`.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `feat(dialysis): order create/list/detail endpoints`

### Task 4: Session state machine + guards

**Files:**
- Modify: `backend/app/routes/dialysis.py`
- Test: `backend/tests/test_dialysis_state_machine.py`

**Interfaces:**
- Produces: `POST /dialysis/orders/{id}/{connect|disconnect|complete|cancel}`.

- [ ] **Step 1: Failing tests** — (a) Ordered→connect requires ≥1 passed checklist-run else 409 "checklist not passed"; with a passed run, connect → status `Connected` + `connected_at` set; (b) Connected→disconnect → `Disconnected`; (c) Disconnected→complete → `Completed` + `completed_at`; (d) illegal transition (e.g. Ordered→complete) → 409; (e) cancel without reason → 422; cancel with reason → `Cancelled` + `cancel_reason`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — a `_TRANSITIONS = {"Ordered": {"connect": "Connected", "cancel": "Cancelled"}, "Connected": {"disconnect": "Disconnected", "cancel": "Cancelled"}, "Disconnected": {"complete": "Completed"}}` guard table; the connect handler additionally checks a passed `DialysisChecklistRun` exists; set the matching `*_at` timestamp.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `feat(dialysis): session state machine + guards`

### Task 5: Observations (append-only) + complications

**Files:**
- Modify: `backend/app/routes/dialysis.py`
- Test: `backend/tests/test_dialysis_observations.py`

**Interfaces:**
- Produces: `POST /dialysis/orders/{id}/observations`, `POST /dialysis/orders/{id}/complications`.

- [ ] **Step 1: Failing tests** — (a) append observation → 201, appears in order detail ordered by `recorded_at`; (b) correction: POST with `corrects_obs_id` creates a new row (no UPDATE/DELETE route exists); (c) complication append → 201 with `type` from the allowed enum, bad `type` → 422; (d) observation only allowed while status in `{Connected, Disconnected}` else 409.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement** — append-only handlers (no update/delete), enum-validate `complication.type`, status guard on observations.
- [ ] **Step 4: Run — PASS.**
- [ ] **Step 5: Commit** — `feat(dialysis): intradialytic observations + complications`

### Task 6: Adequacy — URR + Kt/V computation

**Files:**
- Create: `backend/app/services/dialysis_adequacy.py`
- Modify: `backend/app/routes/dialysis.py`
- Test: `backend/tests/test_dialysis_adequacy.py`

**Interfaces:**
- Produces: `compute_adequacy(pre_urea, post_urea, hours, uf_litres, post_weight) -> (urr, kt_v)`; `POST /dialysis/orders/{id}/adequacy`.

- [ ] **Step 1: Failing unit test** — `compute_adequacy(pre_urea=30, post_urea=9, hours=4, uf_litres=2.5, post_weight=70)` → URR ≈ `70.0`, Kt/V ≈ `1.45` (assert `round(urr,1)==70.0`, `1.3 < kt_v < 1.6`). Guard: `pre_urea<=0` → `ValueError`.
- [ ] **Step 2: Run — FAIL** (no module). `pytest tests/test_dialysis_adequacy.py -v`
- [ ] **Step 3: Implement `dialysis_adequacy.py`** —
```python
import math
def compute_adequacy(pre_urea, post_urea, hours, uf_litres, post_weight):
    if not pre_urea or pre_urea <= 0:
        raise ValueError("pre_urea must be > 0")
    R = post_urea / pre_urea
    urr = (1 - R) * 100
    kt_v = -math.log(R - 0.008 * hours) + (4 - 3.5 * R) * (uf_litres / post_weight)
    return round(urr, 1), round(kt_v, 2)
```
- [ ] **Step 4: Endpoint test + impl** — `POST /adequacy` persists pre/post labs, calls `compute_adequacy`, stores `urr`/`kt_v`, returns them; unique per order (second POST updates).
- [ ] **Step 5: Run — PASS.**
- [ ] **Step 6: Commit** — `feat(dialysis): adequacy (URR + Kt/V)`

### Task 7: Checklists config + checklist runs

**Files:**
- Modify: `backend/app/routes/dialysis.py`
- Test: `backend/tests/test_dialysis_checklists.py`

**Interfaces:**
- Produces: `GET/POST/PUT /dialysis/checklists` (manage), `POST /dialysis/orders/{id}/checklist-runs`.

- [ ] **Step 1: Failing tests** — (a) GET checklists returns the 5 seeded; (b) POST checklist requires `dialysis:manage` (nurse 403, admin 201); (c) POST checklist-run records `passed`; used by Task-4 connect guard.
- [ ] **Step 2: Run — FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** — `feat(dialysis): checklists config + runs`

### Task 8: Frontend — api client + wrapper + OrdersTab

**Files:**
- Create: `frontend/src/pages/Dialysis.jsx`, `frontend/src/pages/dialysis/api.js`, `frontend/src/pages/dialysis/errors.js`, `frontend/src/pages/dialysis/OrdersTab.jsx`
- Modify: `frontend/src/App.jsx` (route), sidebar nav component, `frontend/src/pages/dialysis/` index
- Test: `frontend/src/pages/dialysis/OrdersTab.test.jsx`

**Interfaces:**
- Consumes: `api/client.js` axios instance (copy maternity `api.js` shape).
- Produces: `listOrders/createOrder/getOrder/...` in `api.js`; `<Dialysis/>` page.

- [ ] **Step 1: Failing RTL test** — `OrdersTab` renders a list from a mocked `listOrders`, shows status chips, has a "New session" button and status/date filters.
- [ ] **Step 2: Run — FAIL. Step 3: Implement** `api.js` (all Phase-1 calls), `errors.js` (copy maternity), `Dialysis.jsx` wrapper (tabs), `OrdersTab`. Add `/dialysis` route in `App.jsx` behind `ModuleGuard`, and a sidebar entry.
- [ ] **Step 4: Run — PASS. Step 5: Commit** — `feat(dialysis): frontend api + OrdersTab`

### Task 9: Frontend — OrderForm (grouped param cards)

**Files:** Create `frontend/src/pages/dialysis/OrderForm.jsx` + `.test.jsx`.
- [ ] **Step 1: Failing test** — renders grouped cards (Access/Machine, Renal Rx, Anticoagulation, Fluid targets); submit calls `createOrder` with the assembled payload; required-field validation blocks empty patient.
- [ ] **Step 2-4: FAIL → implement (spacious grouped cards, dark-mode aware) → PASS.**
- [ ] **Step 5: Commit** — `feat(dialysis): order form`

### Task 10: Frontend — SessionBoard + ObservationForm

**Files:** Create `SessionBoard.jsx`, `ObservationForm.jsx` + tests.
- [ ] **Step 1: Failing tests** — SessionBoard shows the state stepper; Connect disabled until a checklist run passes; clicking a transition calls the matching api; observation timeline renders newest-first; ObservationForm submit appends.
- [ ] **Step 2-4: FAIL → implement → PASS. Step 5: Commit** — `feat(dialysis): session board + observations`

### Task 11: Frontend — AdequacyPanel + FlowChart

**Files:** Create `AdequacyPanel.jsx`, `FlowChart.jsx` + tests.
- [ ] **Step 1: Failing tests** — AdequacyPanel posts pre/post labs and displays returned URR + Kt/V; FlowChart renders BP/pulse/UF series from observations (reuse existing chart util / `VitalsTrendsModal` approach).
- [ ] **Step 2-4: FAIL → implement → PASS. Step 5: Commit** — `feat(dialysis): adequacy panel + flow chart`

### Task 12: Frontend — ChecklistsConfigTab + Phase-1 integration

**Files:** Create `ChecklistsConfigTab.jsx` + test; wire all tabs into `Dialysis.jsx`.
- [ ] **Step 1-5:** manage checklists (list/add/toggle, manage-gated); assemble tabs; **Phase-1 verification:** `cd backend && pytest tests/test_dialysis*.py -v` all pass; `cd frontend && npx vitest run src/pages/dialysis && npm run build && npx eslint src/pages/dialysis`. Commit — `feat(dialysis): checklists config + phase-1 wiring`.

---

## PHASE 2 — Unit management

### Task 13: Vascular access registry
**Files:** `routes/dialysis.py` (or new `dialysis_unit.py` if >500 lines), `pages/dialysis/RenalProfileTab.jsx` + tests.
- [ ] TDD: `GET/POST/PUT /dialysis/vascular-accesses` (by patient), status enum; `GET /dialysis/patients/{id}/renal-profile` (accesses + schedule + adequacy trend + last N sessions); RenalProfileTab renders access history + adequacy trend chart. Commit.

### Task 14: Schedules + roster
**Files:** routes + `pages/dialysis/ScheduleRoster.jsx` + tests.
- [ ] TDD: `GET/POST/PUT /dialysis/schedules`; `GET /dialysis/roster?date=` returns the day's chair occupancy from schedules; ScheduleRoster weekly grid. Commit.

### Task 15: Machines + machine board
**Files:** routes + `pages/dialysis/MachineBoard.jsx` + tests.
- [ ] TDD: `GET/POST/PUT /dialysis/machines` (manage); `MachineBoard` station occupancy from active sessions. Commit.

### Task 16: Consumables → billing
**Files:** routes + SessionBoard consumables sub-panel + tests.
- [ ] TDD: `POST /dialysis/orders/{id}/consumables` (item_id→inventory or free name, qty, dialyzer_reuse_count); on `complete`, push consumables + a dialysis service charge to billing (reuse billing service, following Billables config pattern); test bill items created. Commit.

### Task 17: Full verification + PR
- [ ] `cd backend && pytest tests/test_dialysis*.py -v` (all green); `cd frontend && npx vitest run src/pages/dialysis && npm run build && npx eslint src/pages/dialysis`.
- [ ] Confirm `alembic` at head + `migrate_all_tenants.py` green on fresh Postgres.
- [ ] Push `feat/dialysis-module`; open PR **into `development`** with the migration-gate note; wait for `migration-check` green.

---

## Self-review

- **Spec coverage:** every design-doc section maps to a task — Data model→T1; RBAC/schemas→T2; orders→T3; state machine→T4; observations/complications→T5; adequacy→T6; checklists→T7; frontend core→T8-12; vascular access→T13; schedules/roster→T14; machines→T15; consumables/billing→T16; verify/PR→T17. ✓
- **Placeholders:** none — enums, formulas, transition table, and file paths are explicit; repetitive CRUD tasks carry exact endpoints + fields.
- **Type consistency:** `compute_adequacy` signature matches T6 usage; `_TRANSITIONS` keys match the status enum; model names match schema/route usage.
