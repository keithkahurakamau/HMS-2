# Dialysis / Renal Module — Design

**Date:** 2026-07-22
**Branch:** `feat/dialysis-module` (off `development`)
**Parity source:** [medicentrev3-parity/03-dialysis.md](medicentrev3-parity/03-dialysis.md)
**Pattern:** follows the Maternity module (`models/maternity.py`, `routes/maternity.py`,
`pages/maternity/`, `migrate_all_tenants` seed hook, alembic `add_maternity_tables`).

## Goal

Add a nephrology-grade **Dialysis** module to HMS-2 — entirely missing today — covering the full
haemodialysis workflow: patient renal profile, per-session orders with renal prescription, machine
safety checklists, a session state machine, append-only intradialytic monitoring, complications,
adequacy (Kt/V, URR), consumables, plus unit management (machines, recurring schedule roster).

## Design principles (from parity README)

Full depth, flexible configuration, usable (surface common actions, few clicks), and **spacious**
(grouped param cards, calm tables, clear stepper, dark-mode aware). Reuse HMS-2's existing
patient / queue / billing / lab / prescription plumbing — no duplication.

## Data model — `backend/app/models/dialysis.py`

Conventions mirror maternity: `Integer` PKs, FK `ondelete` cascades, `recorded_by/created_by →
users(user_id) SET NULL`, `created_at` server-default `now()`, `Numeric` for measurements, string
status enums documented inline, append-only observations via `corrects_*_id`.

### A · Unit setup
- **`dialysis_checklists`** — `checklist_id`, `name`, `description`, `is_active`, `created_at`.
  *Seeded:* Blood-leak test, Air-detect test, Machine-function test, Conductivity check, Dialysate-temp check.
- **`dialysis_machines`** — `machine_id`, `name`, `model`, `station`, `is_active`, `last_serviced`,
  `hours_run`, `created_at`.

### B · Patient renal profile (longitudinal)
- **`vascular_accesses`** — `access_id`, `patient_id`(FK CASCADE), `type` (AVF/AVG/Tunneled-cath/
  Non-tunneled-cath/Permcath), `site`, `created_date`, `status` (Active/Maturing/Failed/Infected/
  Removed), `last_assessed`, `complications`(Text), `notes`(Text), `created_at`.
- **`dialysis_schedules`** — `schedule_id`, `patient_id`(FK CASCADE), `pattern` (MWF/TTS/Daily/Custom),
  `shift` (Morning/Afternoon/Evening), `sessions_per_week`, `preferred_machine_id`(FK SET NULL),
  `target_dry_weight_kg`(Numeric(5,1)), `start_date`, `status` (Active/Paused/Ended), `created_at`.

### C · The session — `dialysis_orders`
- Identity/flow: `order_id`, `patient_id`(FK CASCADE, index), `treatment_no`, `schedule_id`(FK SET NULL),
  `vascular_access_id`(FK SET NULL), `machine_id`(FK SET NULL), `nephrologist_id`(FK users SET NULL),
  `ordered_by`(FK users SET NULL), `screening_date`(Date), `hiv_hbv_status`(String(20)),
  `blood_group`(String(8)).
- Prescription: `dialyzer`(String), `membrane_type`(String), `priming`(String), `k_bath`(String),
  `dialysate_calcium`(String), `dialysate_bicarbonate`(String), `dialysate_sodium`(String),
  `dialysate_temp_c`(Numeric(3,1)), `blood_flow_target`(Integer), `dialysate_flow_target`(Integer),
  `treatment_time_min`(Integer).
- Anticoagulation: `anticoag_type`(String: Heparin/Heparin-free/LMWH), `heparin_loading_dose`(String),
  `heparin_maintenance_dose`(String), `heparin_stop_time`(String).
- Fluid: `pre_weight_kg`,`dry_weight_kg`,`post_weight_kg`(Numeric(5,1)), `target_uf_ml`(Integer),
  `intake_ml`(Integer), `fluid_removal_goal_ml`(Integer).
- State machine: `status`(String(20): **Ordered → Connected → Disconnected → Completed** / Cancelled,
  index), `connected_at`,`disconnected_at`,`completed_at`(DateTime nullable), `cancel_reason`(Text),
  `created_at`.
- Partial unique index `uq_dialysis_active_per_patient` on `patient_id` where
  `status NOT IN ('Completed','Cancelled')` — one live session per patient (mirrors maternity).

### D · Intra- & post-session
- **`dialysis_observations`** (append-only) — `obs_id`, `order_id`(FK CASCADE, index), `recorded_at`
  (server-default), `bp_systolic`,`bp_diastolic`,`pulse`(Int), `venous_pressure`,`arterial_pressure`,
  `tmp`(Int), `conductivity`(Numeric(4,1)), `blood_flow_rate`,`dialysate_flow_rate`(Int),
  `uf_volume_ml`(Int, cumulative), `blood_volume_processed_l`(Numeric(5,1)), `temperature_c`
  (Numeric(3,1)), `heparin_note`(String(255)), `corrects_obs_id`(FK self SET NULL),
  `recorded_by`(FK users), `created_at`.
- **`dialysis_complications`** — `complication_id`, `order_id`(FK CASCADE, index), `occurred_at`,
  `type`(String: Hypotension/Cramps/Nausea/Vomiting/Clotting/Bleeding/Chest-pain/Fever/Disequilibrium),
  `intervention`(Text), `resolved`(Boolean), `recorded_by`, `created_at`.
- **`dialysis_adequacy`** — `adequacy_id`, `order_id`(FK CASCADE, unique), `pre_urea`,`post_urea`,
  `pre_creatinine`,`post_creatinine`,`pre_potassium`,`post_potassium`(Numeric), `pre_hb`(Numeric(4,1)),
  `ultrafiltration_actual_ml`(Int), `session_duration_min`(Int), `urr`(Numeric(4,1) — computed),
  `kt_v`(Numeric(4,2) — computed), `computed_at`, `recorded_by`.
  - **URR** = `(1 − post_urea/pre_urea) × 100`.
  - **Kt/V** (Daugirdas 2nd-gen) = `−ln(R − 0.008·t) + (4 − 3.5·R)·UF/W`, where `R=post/pre urea`,
    `t`=hours, `UF`=litres removed, `W`=post_weight. Computed server-side on POST.
- **`dialysis_consumables`** — `consumable_id`, `order_id`(FK CASCADE, index), `item_id`(FK inventory
  SET NULL, nullable), `item_name`(String, fallback), `qty`(Numeric(6,2)), `dialyzer_reuse_count`(Int),
  `created_at`.
- **`dialysis_checklist_runs`** — `run_id`, `order_id`(FK CASCADE, index), `checklist_id`(FK SET NULL),
  `passed`(Boolean), `note`(String(255)), `checked_by`(FK users), `created_at`.

## API — `backend/app/routes/dialysis.py`

All routes `Depends(RequirePermission("dialysis:*"))` and behind the `dialysis` module gate.

- **Orders:** `GET /dialysis/orders` (filters: status, from, to, patient) · `POST /dialysis/orders` ·
  `GET /dialysis/orders/{id}` (embeds observations, complications, adequacy, checklist-runs,
  consumables).
- **State machine:** `POST /dialysis/orders/{id}/connect|disconnect|complete|cancel`. Guards:
  *Connect* requires all active checklists run + passed; *Complete* requires disconnected; *Cancel*
  requires a reason; illegal transitions → 409.
- **Intra/post:** `POST /dialysis/orders/{id}/observations` (append) · `.../complications` ·
  `.../adequacy` (auto-computes URR + Kt/V) · `.../checklist-runs` · `.../consumables`.
- **Renal profile:** `GET/POST/PUT /dialysis/vascular-accesses` (by patient) ·
  `GET /dialysis/patients/{id}/renal-profile` (accesses + schedule + adequacy trend + last N sessions).
- **Unit mgmt:** `GET/POST/PUT /dialysis/machines` · `GET/POST/PUT /dialysis/schedules` ·
  `GET /dialysis/roster?date=` (chair occupancy for a day) · `GET/POST/PUT /dialysis/checklists`.
- **Queue/billing:** reuse existing `queue` + `billing` (session → bill items via consumables + a
  dialysis service charge, following Billables §config pattern).

Schemas in `backend/app/schemas/dialysis.py` (Pydantic request/response, mirroring maternity).

## RBAC, module gate, wiring

- `core/modules.py`: add `"dialysis"` to `MODULES`; permissions `dialysis:read`, `dialysis:write`,
  `dialysis:manage` in `PERMISSION_CATALOG`; grant read/write to **Nurse, Clinical Officer, Medical
  Officer**, manage to **Admin/Nephrologist**. (Nurses record obs/complications/adequacy/checklists;
  doctors create/cancel orders + prescription.)
- Feature-flag gated like billing/wards (tenant `feature_flags.dialysis`); module-gated tests must
  enable it (see local-test-env note).
- `main.py`: `import app.routes.dialysis as dialysis_module` + `app.include_router(...)`.
- **Migration:** alembic `add_dialysis_tables` (all 10 tables + partial unique index; `down_revision`
  = current head). Register `dialysis` in `migrate_all_tenants.py` model-imports block.
- **Seed:** `app/services/dialysis_seed.py` → `seed_dialysis_checklists(conn)` (+ 1-2 demo machines),
  hooked into `migrate_one` like `_seed_maternity_price_list`, and registered in `migrate_all_tenants`.

## Frontend — `frontend/src/pages/Dialysis.jsx` + `pages/dialysis/`

Thin `Dialysis.jsx` wrapper → tabbed workspace:
- `OrdersTab` (list + status/date filters, queue) · `OrderForm` (grouped cards: Access/Machine, Renal
  Rx, Anticoagulation, Fluid targets) · `SessionBoard` (state stepper Ordered→Completed, live
  observation timeline, complications log, checklist gate) · `ObservationForm` · `AdequacyPanel`
  (Kt/V + URR auto-calc, pre/post labs) · `RenalProfileTab` (vascular-access history, schedule,
  adequacy trend chart) · `MachineBoard` (station occupancy) · `ScheduleRoster` (weekly roster) ·
  `ChecklistRunForm` · `FlowChart` (BP/pulse/UF trend) · `ChecklistsConfigTab`.
- `api.js` (typed client), `errors.js`. Reuse `ActivePatientBar`, queue, `IcdDiagnosisPicker`,
  billing/prescription links, `ThemeToggle`-aware styling.

## Testing (TDD)

- **Backend (pytest, live-server):** order create + lifecycle transitions + guards (checklist-before-
  connect, illegal transition 409), append-only observations, adequacy computation (URR/Kt-V values),
  RBAC (nurse vs doctor), module-gate 402 when flag off. Enable `dialysis` flag in `mayoclinic_db`.
- **Frontend (Vitest + RTL):** `OrderForm` validation, `SessionBoard` transition buttons + gating,
  `AdequacyPanel` computed display, `FlowChart` render.
- `npm run build` + eslint before push (vite build misses no-undef).

## Build phasing (one branch, one migration)

- **Phase 1 — clinical core:** checklists, machines(min), orders (Rx/anticoag/fluid), observations,
  complications, adequacy, checklist-runs, state machine + guards; frontend Orders/OrderForm/
  SessionBoard/ObservationForm/AdequacyPanel/FlowChart/ChecklistsConfigTab; full backend + frontend
  tests. **Shippable.**
- **Phase 2 — unit management:** vascular-access registry, schedules/roster, machine board,
  consumables→billing; RenalProfileTab/MachineBoard/ScheduleRoster. Schema for both lands in the one
  migration up front.

## Open decisions (resolved)

- HD only for v2 (peritoneal dialysis = future). Kt/V via Daugirdas 2nd-gen. One live session per
  patient. Consumables link to inventory when available, else free-text name.
