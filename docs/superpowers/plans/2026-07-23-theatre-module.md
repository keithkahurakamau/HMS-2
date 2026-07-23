# Theatre / Surgery Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a surgical-grade Theatre module to HMS-2 — theatre rooms, WHO Surgical Safety Checklist (SignIn/TimeOut/SignOut) gating a case state machine, operative note, anaesthesia record, surgical team, consumables/implants, recovery observations, and charge-on-complete billing.

**Architecture:** Follows the Dialysis module exactly (`models/theatre.py` + `routes/theatre.py` [+`theatre_unit.py` P2] + `pages/theatre/`, one alembic revision registered in `migrate_all_tenants.py` with a `theatre_seed.py` hook, DB-backed RBAC, feature-flag gate, `theatre_billing.raise_theatre_charge` on complete). Full schema in [2026-07-23-theatre-module-design.md](../specs/2026-07-23-theatre-module-design.md).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Pydantic (backend); React + Vite + Tailwind + Vitest/RTL (frontend); pytest live-server (backend tests). Reference implementation: the dialysis module (`models/dialysis.py`, `routes/dialysis.py`, `services/dialysis_billing.py`, `pages/dialysis/`).

## Global Constraints

- Branch `feat/theatre-module` off `feat/dialysis-module`; PR into `development`. Migration `down_revision = "d1a15c0b7e42"` (dialysis head) to keep alembic linear.
- Migration gate: `add_theatre_tables` revision **and** `theatre` in `migrate_all_tenants.py` model-imports **and** `_seed_theatre` hooked into `migrate_one`.
- Every route behind `RequirePermission("theatre:*")` and the `theatre` module gate; module-gated tests enable `feature_flags.theatre` in `mayoclinic_db` (start uvicorn from `backend/` with `REDIS_URL=""`; venv at `backend/venv`).
- Files < 500 lines. `npm run build` + eslint (0 errors) before push. Frontend data-loaders use `.then/.catch` (not async/await) to avoid `react-hooks/set-state-in-effect`.
- WHO checklist phases: `SignIn`, `TimeOut`, `SignOut`. Case status: `Scheduled → InTheatre → Recovery → Completed / Cancelled`. `start` requires a checked `TimeOut` run; `complete` requires a checked `SignOut` run and raises `THEATRE-MAJOR` charge (zero-priced no-op until set).

---

## PHASE 1 — Clinical core (shippable)

### Task 1: Data model + migration + seed
**Files:** Create `backend/app/models/theatre.py`, `backend/alembic/versions/<rev>_add_theatre_tables.py`, `backend/app/services/theatre_seed.py`; Modify `backend/scripts/migrate_all_tenants.py`; Test `backend/tests/test_theatre_migration.py`.
**Interfaces:** Produces models `TheatreRoom, SurgicalChecklist, SurgicalCase, SurgicalChecklistRun, OperativeNote, AnaesthesiaRecord, SurgicalTeamMember, SurgicalConsumable, RecoveryObservation` (all 9 tables in this migration; P1 uses the first 6). `seed_theatre_reference(conn) -> int`, `seed_theatre_price_list(conn) -> int`.
- [ ] Write `models/theatre.py` — all 9 tables per design §Data model, mirroring `models/dialysis.py`. `SurgicalCase.status` default `"Scheduled"`; FKs to `patients`, `admission_records`, `users`, `inventory_items`, `theatre_rooms`, `surgical_cases`. `operative_notes.case_id` + `anaesthesia_records.case_id` are `unique=True`.
- [ ] Hand-write alembic `add_theatre_tables` (`revision = "e2b62c1d9f34"`, `down_revision = "d1a15c0b7e42"`): create 9 tables (referenced-before-referencing order: theatre_rooms, surgical_checklists, surgical_cases, surgical_checklist_runs, operative_notes, anaesthesia_records, surgical_team_members, surgical_consumables, recovery_observations) + indexes; seed `theatre:read`/`theatre:manage` permissions granted to Admin/Doctor/Nurse (copy the dialysis revision's permission block).
- [ ] `theatre_seed.py`: `seed_theatre_reference(conn)` inserts WHO checklist items (SignIn: "Patient identity/site/procedure/consent confirmed", "Site marked", "Anaesthesia safety check", "Pulse oximeter on & working", "Known allergy?", "Difficult airway/aspiration risk?", "Risk of >500ml blood loss?"; TimeOut: "Team introductions", "Confirm patient/site/procedure", "Antibiotic prophylaxis given", "Anticipated critical events reviewed", "Imaging displayed"; SignOut: "Procedure name recorded", "Instrument/sponge/needle counts correct", "Specimen labelled", "Equipment problems addressed", "Recovery concerns") — each `(phase, name)`, idempotent by (phase,name); + one demo `theatre_rooms` row. `seed_theatre_price_list(conn)` inserts `THEATRE-MAJOR`, `THEATRE-MINOR` (category "Theatre", zero-priced), idempotent (copy `dialysis_seed.seed_dialysis_price_list`).
- [ ] Register `theatre` in `migrate_all_tenants.py` imports; add `_seed_theatre(tenant_url)` (checklist/room via `seed_theatre_reference` if `surgical_checklists` exists; price via `seed_theatre_price_list` if `acc_price_list` exists) and call it in `migrate_one` after `_seed_dialysis`.
- [ ] Test `test_theatre_migration.py` (direct DB, copy `test_dialysis_migration.py`): assert 9 tables exist, `surgical_checklists` ≥ 15 rows, `theatre:read`/`theatre:manage` in `permissions`.
- [ ] Apply: `DATABASE_URL=<...>/mayoclinic_db venv/bin/alembic upgrade head`; run `seed_theatre_reference` + `seed_theatre_price_list` on mayoclinic_db; `venv/bin/pytest tests/test_theatre_migration.py -q` → PASS. Commit `feat(theatre): data model + migration + seed`.

### Task 2: Module registration + RBAC + flag
**Files:** Modify `backend/app/core/modules.py`, `backend/app/main.py` (import + include empty router in Task 3); Test `backend/tests/test_theatre_rbac.py`.
- [ ] Add `ModuleDef("theatre", "Theatre & Surgery", "Operating theatre scheduling, WHO safety checklist, operative notes, billing.", False)` to `MODULES` and `("/api/theatre/", "theatre")` to `URL_PREFIX_MAP`.
- [ ] Enable `theatre` flag in `mayoclinic_db` master `tenants.feature_flags` (Python: load flags JSON, set `theatre=True`, commit — copy the dialysis flag-enable snippet).
- [ ] Test `test_theatre_rbac.py`: `"theatre"` in `MODULES` keys; permissions seeded (queried DB). Commit `feat(theatre): register module + gate`.

### Task 3: Cases — create / list / detail
**Files:** Create `backend/app/routes/theatre.py`; Modify `backend/app/main.py`; Test `backend/tests/test_theatre_cases.py`.
**Interfaces:** `GET/POST /theatre/cases`, `GET /theatre/cases/{id}` (deep: checklist_runs, operative_note, anaesthesia, team[], consumables[], recovery[]). Inline Pydantic `CaseCreate` (patient_id, procedure_name, priority, scheduled_at, surgeon/anaesthetist/room/admission ids, diagnosis, procedure_code).
- [ ] Failing tests (copy `test_dialysis_orders.py::TestAccess` + lifecycle shape): unauth 401; nurse lists 200; receptionist 403; POST creates case status `Scheduled`; GET detail embeds empty children; unknown patient 404; module-gate 402 when flag off.
- [ ] Implement `routes/theatre.py` — `APIRouter(prefix="/api/theatre", tags=["Theatre"])`, `_case_dict(case, patient, deep)`, `_get_case_or_404`, create/list/detail (RequirePermission read/manage, audit-logged). Wire router in `main.py`.
- [ ] PASS. Commit `feat(theatre): case create/list/detail`.

### Task 4: State machine + WHO checklist gates + billing
**Files:** Create `backend/app/services/theatre_billing.py`; Modify `backend/app/routes/theatre.py`; Test `backend/tests/test_theatre_state_machine.py`.
**Interfaces:** `POST /theatre/cases/{id}/{start|to-recovery|complete|cancel}`; `raise_theatre_charge(db, *, patient_id, service_code, clinician_name, user_id)`.
- [ ] `theatre_billing.py` = copy `dialysis_billing.py`, `item_type="Theatre"`.
- [ ] Failing tests: `start` with no TimeOut run → 409; after a checked TimeOut run → status `InTheatre` + `started_at`; `to-recovery` → `Recovery`; `complete` with no SignOut run → 409; after checked SignOut → `Completed` + `ended_at`; illegal transition (Scheduled→complete) → 409; cancel without reason → 422, with reason → `Cancelled`; completing a priced `THEATRE-MAJOR` creates a `Theatre` invoice item (DB-assert, copy the dialysis billing test).
- [ ] Implement `_TRANSITIONS = {"Scheduled": {"start": "InTheatre", "cancel": "Cancelled"}, "InTheatre": {"to-recovery": "Recovery", "cancel": "Cancelled"}, "Recovery": {"complete": "Completed"}}`; `start` guard = a checked `SurgicalChecklistRun` with `phase="TimeOut"`; `complete` guard = checked `phase="SignOut"` run, then `raise_theatre_charge(..., service_code="THEATRE-MAJOR")`; set `started_at`/`ended_at`.
- [ ] PASS. Commit `feat(theatre): state machine + WHO gates + billing`.

### Task 5: Checklists config + runs
**Files:** Modify `backend/app/routes/theatre.py`; Test `backend/tests/test_theatre_checklists.py`.
- [ ] Failing tests: `GET /theatre/checklists` returns seeded (≥15, phase-tagged, filter `?phase=TimeOut`); `POST /theatre/checklists` manage-gated (nurse 200, receptionist 403); `POST /theatre/cases/{id}/checklist-runs` records `{checklist_id, phase, checked}`.
- [ ] Implement + PASS. Commit `feat(theatre): checklists config + runs`.

### Task 6: Operative note + anaesthesia (upsert)
**Files:** Modify `backend/app/routes/theatre.py`; Test `backend/tests/test_theatre_records.py`.
- [ ] Failing tests: `PUT /theatre/cases/{id}/operative-note` creates then updates the single note (blood_loss_ml, findings, procedure_performed…); `PUT /theatre/cases/{id}/anaesthesia` creates then updates (type in {GA,Spinal,Epidural,Local,Sedation}, asa_grade in {I,II,III,IV,V}); bad `type`/`asa_grade` → 422; both appear in case detail.
- [ ] Implement upsert (one row per case) + enum validation + PASS. Commit `feat(theatre): operative note + anaesthesia`.

### Task 7: Frontend — api + wrapper + CasesTab + route/nav
**Files:** Create `frontend/src/pages/Theatre.jsx`, `frontend/src/pages/theatre/{api.js,errors.js,CasesTab.jsx,CasesTab.test.jsx}`; Modify `frontend/src/App.jsx`, `frontend/src/components/layouts/MainLayout.jsx`.
- [ ] Copy `pages/dialysis/errors.js`. `api.js` — `listCases/createCase/getCase/startCase/toRecovery/completeCase/cancelCase/addChecklistRun/listChecklists/createChecklist/putOperativeNote/putAnaesthesia/listRooms/createRoom` (all `.then(r=>r.data)`, `/theatre/...`).
- [ ] `CasesTab.test.jsx` (copy `OrdersTab.test.jsx` shape): lists cases w/ status chip + "New case" button; row click → getCase → CaseBoard region; status filter reload.
- [ ] `CasesTab.jsx` (`.then/.catch` loader), `Theatre.jsx` wrapper (tabs Cases/Rooms/Checklists), `/app/theatre` route (ModuleGuard) + `Scissors` sidebar nav (add to lucide import, ROUTE_TO_JOURNEY, NAVIGATION with `requiredPermission: 'theatre:read'`). PASS. Commit `feat(theatre): frontend api + CasesTab`.

### Task 8: Frontend — CaseForm
**Files:** Create `frontend/src/pages/theatre/{CaseForm.jsx,CaseForm.test.jsx}`.
- [ ] Failing test: renders fields (patient id, procedure, priority select, scheduled datetime); submit calls `createCase` w/ assembled payload; required patient+procedure validation.
- [ ] Implement modal (copy `OrderForm.jsx` grouped-card style) + PASS. Commit `feat(theatre): case form`.

### Task 9: Frontend — CaseBoard (WHO checklist + records)
**Files:** Create `frontend/src/pages/theatre/{CaseBoard.jsx,OperativeNoteForm.jsx,AnaesthesiaForm.jsx,CaseBoard.test.jsx}`.
- [ ] Failing tests: state stepper; **Start disabled until a TimeOut checklist item is checked**; transitions call api + refresh; WHO checklist rendered in 3 phase groups; operative-note/anaesthesia panels submit via PUT.
- [ ] Implement (copy `SessionBoard.jsx` structure; checklist grouped by phase; gate `start` on a checked TimeOut run) + PASS. Commit `feat(theatre): case board + records`.

### Task 10: Frontend — ChecklistsConfigTab + RoomsTab + Phase-1 verify
**Files:** Create `frontend/src/pages/theatre/{ChecklistsConfigTab.jsx,RoomsTab.jsx}` (+ optional tests); wire tabs into `Theatre.jsx`.
- [ ] Checklist config (list by phase, add manage-gated) + rooms config (copy `dialysis/MachinesTab.jsx`). **Phase-1 verify:** `venv/bin/pytest tests/test_theatre*.py -q` all pass; `npx vitest run src/pages/theatre --no-file-parallelism --testTimeout=30000` + `npm run build` + `npx eslint src/pages/theatre` (0 errors). Commit `feat(theatre): checklists + rooms config + phase-1 wiring`.

---

## PHASE 2 — Fast follow

### Task 11: Team members
**Files:** `routes/theatre_unit.py` (new, if `theatre.py` >500 lines) + `pages/theatre/TeamPanel.jsx` (in CaseBoard) + tests.
- [ ] TDD: `POST/DELETE /theatre/cases/{id}/team-members` (role enum); CaseBoard team sub-panel add/remove. Commit.

### Task 12: Consumables / implants
**Files:** `routes/theatre_unit.py` + CaseBoard consumables sub-panel + tests.
- [ ] TDD: `POST /theatre/cases/{id}/consumables` (item_id→inventory or name, qty, `is_implant`, `serial_no`); surfaced in case detail. Commit.

### Task 13: Recovery observations
**Files:** `routes/theatre_unit.py` + `pages/theatre/RecoveryObsForm.jsx` + tests.
- [ ] TDD: `POST /theatre/cases/{id}/recovery-observations` (append-only; bp/pulse/spo2/temp/pain_score/AVPU; status-gated to Recovery); CaseBoard recovery timeline. Commit.

### Task 14: Schedule board
**Files:** `routes/theatre_unit.py` + `pages/theatre/ScheduleBoard.jsx` + tests.
- [ ] TDD: `GET /theatre/board?date_str=` groups the day's cases by room; ScheduleBoard grid. Commit.

### Task 15: Full verification + PR
- [ ] `venv/bin/pytest tests/test_theatre*.py -q` (green); `npx vitest run src/pages/theatre` + build + eslint; confirm alembic head + `migrate_all_tenants` green.
- [ ] Push `feat/theatre-module`; open PR into `development` (note the migration chains after dialysis #205; stacked until #205 merges).

---

## Self-review
- **Spec coverage:** rooms/checklists→T1/T5/T10; cases→T3; state machine + WHO gates + billing→T4; operative note/anaesthesia→T6; frontend core→T7-10; team→T11; consumables→T12; recovery→T13; board→T14; verify/PR→T15. ✓
- **Placeholders:** none — enums, phases, transition table, WHO items, file paths explicit.
- **Type consistency:** `_TRANSITIONS` keys match the status enum; `raise_theatre_charge` signature matches dialysis; model names match route/schema usage; checklist `phase` values consistent (SignIn/TimeOut/SignOut) across seed, gates, and UI.
