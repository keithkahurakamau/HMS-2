# Maternity Module — Design

**Date:** 2026-07-10
**Status:** Approved (brainstormed with operator; Option 1 of 3)
**Scope decision:** Full arc *including* partograph. Theatre module follows as a separate spec that reuses these patterns.

## Overview

A standalone, opt-in `maternity` module covering the full pregnancy arc: ANC
enrollment and visits → labor admission → intrapartum partograph → delivery and
newborn records → PNC visits — with per-service billing and GL posting wired
into the existing invoice/ledger machinery. Benchmarked against MediCentre v3's
Maternity Management module (competitive-gap audit, 2026-07-10).

## Goals

- Track a pregnancy as a first-class episode a patient can have at most one of
  at a time.
- Capture ANC and PNC visits with clinical observations, each raising a charge.
- Tie labor to a normal wards admission (bed board and daily ward billing stay
  in the wards module).
- Capture a WHO-style partograph as append-only timed entries with an SVG chart
  (alert line: 1 cm/hr from 4 cm; action line: +4 h parallel), flagging
  crossings via the existing notifications system.
- Record deliveries (mode, outcomes, complications) and per-baby newborn
  records, with one-click registration of a live newborn as a linked Patient.
- Bill delivery by mode and visits by type through `PriceListItem` service
  codes; post revenue to CoA 4700 (Maternity Revenue) via `post_from_event`.

## Non-goals (follow-ups)

- Theatre module (next spec; C-section op notes live there later).
- MOH maternity registers (MOH 333/405) — reporting layer comes with the wider
  MOH-reports effort.
- Immunization schedules for the newborn (future child-welfare work).
- SMS visit reminders (blocked on the SMS gateway).

## Data model — `backend/app/models/maternity.py`

Six tables. All FKs `ondelete` defaults; all timestamps timezone-aware
`server_default=func.now()` per existing convention.

### `pregnancy_episodes`
- `episode_id` PK
- `patient_id` FK `patients.patient_id`, indexed — the mother
- `gravida` int, `para` int
- `lmp` date nullable, `edd` date nullable (prefilled LMP+280d, overridable)
- `blood_group` varchar(8) nullable, `rhesus` varchar(4) nullable
- `risk_flags` text nullable (free text, comma-separated)
- `status` varchar(20) default `Active`, indexed — Active | Delivered | Closed | Transferred
- `created_by` FK users, `created_at`, `closed_at` nullable
- **Partial unique index:** `patient_id` WHERE `status = 'Active'` — one active
  pregnancy per patient.

### `anc_visits`
- `visit_id` PK, `episode_id` FK indexed
- `visit_number` int, `visit_date` date
- `gestation_weeks` int nullable (derived from LMP at entry, stored)
- `bp_systolic`/`bp_diastolic` int nullable, `weight_kg` numeric(5,1) nullable
- `fundal_height_cm` numeric(4,1) nullable, `fetal_heart_rate` int nullable
- `urine_dip` varchar(40) nullable, `notes` text nullable
- `recorded_by` FK users, `created_at`

### `labor_admissions`
- `labor_admission_id` PK
- `episode_id` FK indexed, `admission_id` FK `admission_records.admission_id`
  unique — one labor record per ward admission
- `active_labor_started_at` timestamptz nullable (partograph time zero; set
  when the first ≥4 cm entry lands or manually)
- `created_at`

### `partograph_entries` (append-only)
- `entry_id` PK, `labor_admission_id` FK indexed
- `recorded_at` timestamptz (observation time, client-supplied, defaults now)
- `cervical_dilation_cm` numeric(3,1) nullable, `descent_fifths` int nullable
- `contractions_per_10min` int nullable, `contraction_duration_sec` int nullable
- `fetal_heart_rate` int nullable, `liquor` varchar(4) nullable (I/C/M1–M3/B),
  `moulding` varchar(4) nullable (0/+/++/+++)
- `maternal_bp_systolic`/`_diastolic`/`pulse` int nullable,
  `temperature_c` numeric(3,1) nullable
- `drugs_note` varchar(255) nullable (oxytocin/analgesia free text)
- `corrects_entry_id` self-FK nullable — corrections are new rows pointing at
  the row they supersede; superseded rows are excluded from the chart but kept
  forever. **No UPDATE or DELETE endpoints exist for this table.**
- `recorded_by` FK users, `created_at`

### `delivery_records`
- `delivery_id` PK, `episode_id` FK indexed,
  `labor_admission_id` FK nullable (BBA/unbooked deliveries have none)
- `delivered_at` timestamptz
- `mode` varchar(20) — SVD | Assisted | CSection | Breech
- `placenta_complete` bool nullable, `blood_loss_ml` int nullable
- `perineum` varchar(40) nullable, `complications` text nullable
- `mother_status` varchar(20) default `Stable` — Stable | Referred | Deceased
- `conducted_by` FK users, `assistant_id` FK users nullable
- `created_at`
- Side-effect on create: episode `status → Delivered`; delivery charge raised
  by mode (see Billing).

### `newborn_records`
- `newborn_id` PK, `delivery_id` FK indexed
- `birth_order` int default 1 (twins+)
- `sex` varchar(10), `weight_g` int nullable
- `apgar_1`/`apgar_5`/`apgar_10` int nullable
- `outcome` varchar(10) — Live | FSB | MSB
- `resuscitated` bool default false, `notes` text nullable
- `registered_patient_id` FK `patients.patient_id` nullable — set by the
  register-as-patient action; surname = mother's, DOB = `delivered_at`,
  `guardian`/next-of-kin fields point at the mother. Action is idempotent
  (409 if already registered) and requires `patients:write`.

### `pnc_visits`
Mirror of `anc_visits` minus fundal height/FHR, plus:
- mother: `involution` varchar(40), `lochia` varchar(40)
- baby: `feeding` varchar(40), `cord_status` varchar(40), `baby_weight_g` int
- `newborn_id` FK nullable (visit may be mother-only)

## API — `backend/app/routes/maternity.py`

Prefix `/api/maternity`, tag `maternity`. All endpoints audit-logged via
`log_audit`. Reads require `maternity:read`, writes `maternity:manage`
(via `RequirePermission`), except newborn registration which additionally
requires `patients:write`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/episodes` | Enroll pregnancy (409 if an Active episode exists) |
| GET | `/episodes` | List/filter (status, patient_id, search) |
| GET | `/episodes/{id}` | Full episode: visits, labor, delivery, newborns |
| PATCH | `/episodes/{id}/close` | Close/Transfer with reason |
| POST | `/episodes/{id}/anc-visits` | Record ANC visit (+charge) |
| POST | `/episodes/{id}/pnc-visits` | Record PNC visit (+charge) |
| POST | `/episodes/{id}/labor` | Link a wards admission as labor (validates admission Active + same patient) |
| POST | `/labor/{id}/partograph` | Append partograph entry (optional `corrects_entry_id`) |
| GET | `/labor/{id}/partograph` | Entries, chronological, superseded rows marked |
| POST | `/episodes/{id}/delivery` | Record delivery + inline newborn rows (+mode charge, episode→Delivered) |
| POST | `/newborns/{id}/register-patient` | One-click linked Patient creation |
| GET | `/board` | Labor board: active labor admissions with latest partograph vitals |

If the route file approaches the 500-line limit, partograph + labor endpoints
split into `maternity_labor.py` (same convention as the `clinical.py` split).

**Alert-line check:** on each partograph append, if dilation plots right of the
alert (or action) line relative to `active_labor_started_at`, create a
notification (`notifications.py`) to ward staff: "Partograph alert-line
crossing — {patient}".

## Billing & GL

Consultation-fee pattern verbatim (`billing.py:charge_consultation_fee`):
lock-or-create the mother's Pending `Invoice` (`with_for_update`), append
`InvoiceItem` (`item_type="Maternity"`, description names the service and
clinician), bump `total_amount`, then
`post_from_event(source_key="billing.invoice.created", source_id=item.id, …)`.

Service codes seeded per tenant into `PriceListItem` (zero-priced until the
hospital sets prices in Admin → Pricing; zero-priced services raise no charge):

| Code | Service |
|---|---|
| `MAT-ANC-VISIT` | Antenatal clinic visit |
| `MAT-PNC-VISIT` | Postnatal clinic visit |
| `MAT-DEL-SVD` | Normal (spontaneous vaginal) delivery |
| `MAT-DEL-ASSISTED` | Assisted delivery |
| `MAT-DEL-CS` | Caesarean section |
| `MAT-DEL-BREECH` | Breech delivery |

Seeding ships as `app/services/maternity_seed.py` hooked into
`migrate_one` (mirrors the alembic DATA seed so legacy tenants get the codes —
per the migrate-all-tenants convention). The seed also adds a ledger mapping to
CoA `4700 Maternity Revenue` (account already exists in
`accounting_defaults_seed.py`). Ward bed-day billing remains untouched in the
wards module.

## Module gating, RBAC, queue

- `core/modules.py`: `ModuleDef("maternity", "Maternity", "ANC/PNC clinics, labor partograph, deliveries, newborns.", False)` — opt-in, default off.
- `URL_PREFIX_MAP`: `("/api/maternity/", "maternity")`.
- `tenant_provisioning.py` PERMISSIONS: `maternity:read` ("View maternity episodes and partographs"), `maternity:manage` ("Record ANC/PNC visits, partograph entries, deliveries"). Base grants: Nurse and Doctor get both; Admin read. A dedicated Midwife role is a hospital-side custom role granting these.
- Queue: add "Maternity" as a routable department (same registration as the Reception addition in `de4496c`).

## Frontend — `Maternity.jsx` + `frontend/src/pages/maternity/`

Route `/app/maternity` behind `ModuleGuard moduleKey="maternity"`; nav entry in
`MainLayout.jsx` with `moduleKey: "maternity"`. Three tabs:

1. **ANC Clinic** — routed-patient worklist (unified queue pattern), episode
   search/enroll, ANC visit form, episode timeline.
2. **Labor Board** — active labors (from `/board`), partograph entry form and
   **custom SVG chart** (no chart library): X = hours since
   `active_labor_started_at`, dilation curve vs alert/action lines, FHR strip
   above, contractions histogram below; correction flow renders superseded
   points hollow. Print view reuses the referral-letter print pattern.
3. **Deliveries & PNC** — delivery form (inline newborn rows), delivery
   register, register-newborn-as-patient action, PNC visit form.

Dark-mode classes per the established sweep map. Subcomponents live in
`pages/maternity/` to keep every file under 500 lines.

## Migration

One alembic revision: six tables + the partial unique index. Schema-additive
only — no existing tables change. Register `app/models/maternity.py` in the
`migrate_all_tenants.py` import block. Seed mirrored per Billing section.
Migration-check must be green on development before promotion (standard gate).

## Testing

**Backend (pytest, live-server convention):**
- Episode lifecycle + one-Active-per-patient 409.
- ANC/PNC visit creates invoice item + GL journal rows (assert both).
- Zero-priced service raises no charge.
- Labor link validates admission ownership/status.
- Partograph: append, correction chain excludes superseded from chart data,
  no update/delete routes exist, alert-line crossing creates a notification.
- Delivery flips episode status, raises mode-priced charge, rejects a second
  delivery for the same episode.
- Newborn registration: creates linked patient, idempotent 409 on repeat,
  requires `patients:write`.
- Module gate 402 when `maternity` flag off; 403 without permission.

**Frontend (Vitest + RTL):** ANC visit form validation, partograph SVG math
(line positions for known inputs), newborn-registration flow, module-guard
render gate.

## Rollout

Feature branch `feat/maternity-module` → PR to `development` → beta → main per
the staged flow. Enable the `maternity` flag for a pilot tenant
(mayoclinic_db) first. Update the roadmap memory and module catalogue docs
after ship.
