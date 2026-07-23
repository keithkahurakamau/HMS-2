# Theatre / Surgery Module — Design

**Date:** 2026-07-23
**Branch:** `feat/theatre-module` (off `feat/dialysis-module`, so the migration chains linearly after dialysis's `d1a15c0b7e42`)
**Parity source:** [medicentrev3-parity/README.md](medicentrev3-parity/README.md) Epic B (MedicentreV3 licenses Theatre separately — no pixel screenshots; this is a domain-informed design, like Reports).
**Pattern:** follows the Maternity / Dialysis modules (`models/*.py`, `routes/*.py`, `pages/*/`, `migrate_all_tenants` seed hook, alembic revision, DB-backed RBAC, feature-flag gate, charge-on-complete billing).

## Goal

Add a surgical-grade **Theatre / Surgery** module to HMS-2 — entirely missing today — covering the operating-theatre workflow: theatre rooms, surgical case booking, the **WHO Surgical Safety Checklist** (Sign-In → Time-Out → Sign-Out) as the safety spine, a case state machine, operative note, anaesthesia record, surgical team, consumables/implants, post-op recovery, and charge-on-complete billing.

## Design principles (from parity README)

Full depth, flexible configuration, usable, spacious (grouped cards, calm tables, clear stepper, dark-mode aware). Reuse HMS-2's patient / queue / billing / wards plumbing — no duplication. The WHO checklist is the signature safety feature and gates the state machine.

## Data model — `backend/app/models/theatre.py`

Conventions mirror maternity/dialysis: `Integer` PKs, FK `ondelete` cascades, `created_by`/`recorded_by` → `users.user_id SET NULL`, `created_at` server-default `now()`, `Numeric` measurements, string status enums documented inline, append-only recovery obs via `corrects_obs_id`.

### A · Config
- **`theatre_rooms`** — `room_id`, `name`, `is_active`, `created_at`.
- **`surgical_checklists`** — `checklist_id`, **`phase`** (SignIn/TimeOut/SignOut), `name`, `description`, `is_active`, `created_at`. *Seeded* with standard WHO Surgical Safety Checklist items per phase.

### B · The case
- **`surgical_cases`** — `case_id`, `patient_id`(FK CASCADE, index), `admission_id`(FK `admission_records` SET NULL, nullable — inpatient link), `theatre_room_id`(FK SET NULL), `primary_surgeon_id`(FK users SET NULL), `anaesthetist_id`(FK users SET NULL), `procedure_name`, `procedure_code`, `diagnosis`, **`priority`** (Elective/Emergency), `scheduled_at`(DateTime), **`status`** (Scheduled/InTheatre/Recovery/Completed/Cancelled, index), `started_at`, `ended_at`, `cancel_reason`, `created_by`, `created_at`.

### C · Safety checklist
- **`surgical_checklist_runs`** — `run_id`, `case_id`(FK CASCADE, index), `checklist_id`(FK SET NULL), **`phase`**, `checked`(Boolean), `note`, `checked_by`(FK users), `created_at`.

### D · Operative & anaesthesia (1:1 per case)
- **`operative_notes`** — `note_id`, `case_id`(FK CASCADE, unique), `findings`(Text), `procedure_performed`(Text), `technique`(Text), `closure`, `blood_loss_ml`(Int), `specimens`, `complications`(Text), `estimated_duration_min`(Int), `surgeon_id`(FK users SET NULL), `created_at`, `updated_at`.
- **`anaesthesia_records`** — `anaesthesia_id`, `case_id`(FK CASCADE, unique), **`type`** (GA/Spinal/Epidural/Local/Sedation), **`asa_grade`** (I–V), `agents`, `airway`, `notes`, `anaesthetist_id`(FK users SET NULL), `created_at`, `updated_at`.

### E · Team
- **`surgical_team_members`** — `member_id`, `case_id`(FK CASCADE, index), `user_id`(FK users SET NULL, nullable), `name`(fallback), **`role`** (Surgeon/Assistant/Anaesthetist/Scrub-Nurse/Circulating-Nurse/Perfusionist), `created_at`.

### F · Materials
- **`surgical_consumables`** — `consumable_id`, `case_id`(FK CASCADE, index), `item_id`(FK `inventory_items` SET NULL, nullable), `item_name`, `qty`(Numeric), **`is_implant`**(Boolean), `serial_no`(implant traceability), `created_at`.

### G · Recovery (append-only)
- **`recovery_observations`** — `obs_id`, `case_id`(FK CASCADE, index), `recorded_at`, `bp_systolic`, `bp_diastolic`, `pulse`, **`spo2`**, `temperature_c`(Numeric(3,1)), **`pain_score`**(Int 0–10), `consciousness`(AVPU), `notes`, `corrects_obs_id`(FK self SET NULL), `recorded_by`(FK users), `created_at`.

## API — `routes/theatre.py` (+ `theatre_unit.py` for Phase 2 if >500 lines)

All routes `Depends(RequirePermission("theatre:*"))` behind the `theatre` module gate.

- **Cases:** `GET/POST /theatre/cases` (filters status/patient/date) · `GET /theatre/cases/{id}` (deep: checklist_runs, operative_note, anaesthesia, team, consumables, recovery).
- **State machine:** `POST /theatre/cases/{id}/{start|to-recovery|complete|cancel}`. Guards: **`start` (→InTheatre) requires a checked Time-Out checklist run**; **`complete` requires a checked Sign-Out** and raises the theatre charge; illegal transition → 409; `cancel` requires a reason.
- **Records:** `POST .../checklist-runs` (phase-tagged) · `PUT .../operative-note` (upsert) · `PUT .../anaesthesia` (upsert) · `POST/DELETE .../team-members` · `POST .../consumables` · `POST .../recovery-observations` (append).
- **Config:** `GET/POST/PUT /theatre/rooms` · `GET/POST/PUT /theatre/checklists`.
- **Board:** `GET /theatre/board?date_str=` — the day's cases grouped by room (schedule/occupancy).

Pydantic request models inline in the route module (maternity convention).

## RBAC, module gate, wiring

- `core/modules.py`: add `theatre` to `MODULES` + `/api/theatre/` to `URL_PREFIX_MAP`. Permissions `theatre:read` / `theatre:manage` (DB-seeded in the migration, granted to Admin/Doctor/Nurse — surgeon & theatre nurse).
- Feature-flag gated (`feature_flags.theatre`); module-gated tests enable it in `mayoclinic_db`.
- `main.py`: import + include the router(s).
- **Migration:** alembic `add_theatre_tables` (all 9 tables + `theatre:read`/`theatre:manage` perms), **`down_revision = "d1a15c0b7e42"`**. Register `theatre` in `migrate_all_tenants.py` model-imports + a `_seed_theatre` hook.
- **Seed:** `app/services/theatre_seed.py` → WHO checklist items (per phase) + a demo theatre room + `THEATRE-MAJOR` / `THEATRE-MINOR` price codes (zero-priced).
- **Billing:** `app/services/theatre_billing.py` → `raise_theatre_charge` (mirrors dialysis_billing), called on case `complete`.

## Frontend — `pages/Theatre.jsx` + `pages/theatre/`

Thin `Theatre.jsx` wrapper → tabs:
- `CasesTab` (list + status/date filters, new case) · `CaseForm` (patient, procedure, surgeon/anaesthetist, room, priority, schedule) · **`CaseBoard`** (state stepper, **WHO 3-phase checklist**, operative note, anaesthesia, team, consumables/implants, recovery timeline) · `OperativeNoteForm` · `AnaesthesiaForm` · `RecoveryObsForm` · `ScheduleBoard` (Phase 2) · `RoomsTab` · `ChecklistsConfigTab`.
- `api.js`, `errors.js`. Reuse `ActivePatientBar`, queue, billing links, dark-mode styling. Route `/app/theatre` (ModuleGuard) + sidebar entry (Scissors icon).

## Testing (TDD)

- **Backend (pytest, live-server):** case create + lifecycle transitions + guards (Time-Out-before-start, Sign-Out-before-complete, illegal transition 409), operative-note/anaesthesia upsert, append-only recovery obs, RBAC (nurse vs receptionist), module-gate 402, billing item on complete. Enable `theatre` flag in `mayoclinic_db`.
- **Frontend (Vitest + RTL):** CasesTab, CaseForm, CaseBoard checklist-gating + transitions, RecoveryObs.
- `npm run build` + eslint (0 errors) before push.

## Build phasing (one branch, one migration)

- **Phase 1 — clinical core (immediate):** theatre_rooms, surgical_checklists (+ runs), surgical_cases + state machine + WHO Time-Out/Sign-Out gates, operative_notes, anaesthesia_records; billing-on-complete; frontend Cases/CaseForm/CaseBoard/OperativeNote/Anaesthesia/ChecklistsConfig/Rooms; full tests. **Shippable.**
- **Phase 2 — fast follow:** surgical_team_members, surgical_consumables (+implants), recovery_observations, ScheduleBoard. Schema for both lands in the one migration up front.

## Open decisions (resolved)

- WHO checklist modelled as configurable phase-tagged items (SignIn/TimeOut/SignOut) + per-case runs (mirrors dialysis checklist). One operative note + one anaesthesia record per case (upsert). No one-active-case-per-patient constraint (elective scheduling is many-per-patient). Charge on complete via `THEATRE-MAJOR` (zero-priced default).
