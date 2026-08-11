# Clinical Desk → DoctorV2 Redesign — Design Spec

**Date:** 2026-08-01
**Branch:** `feat/clinical-desk-parity` (continues the MedicentreV3 parity work)
**Status:** Approved design, pending spec review → implementation plan

## Goal

Rework the Clinical Desk so it matches the **information architecture** of MedicentreV3's
"Doctor New" (DoctorV2) screen, rendered in HMS-2's own modern design system (not the teal
MedicentreV3 look), and make every action on the DoctorV2 **Actions** menu available. Build
the layout **and** the currently-missing features in one pass.

Reference screenshots: `MEDICARE/Screenshot 2026-07-21 153923/153952` (Doctor classic, full
Actions menu) and `154026/154051` (DoctorV2 — tabbed Encounter Notes / Patient History).

## Non-goals (YAGNI)

- No pixel-copy of the teal MedicentreV3 chrome. HMS-2 design system only.
- No external object storage (S3/Cloudinary). Files reuse the existing base64-in-DB pattern.
- No change to the encounter submit contract (`POST /clinical/submit`), the draft safety-net,
  consent capture, billing/pharmacy routing, or the prescription→pharmacy pipeline.
- "Special Clinics", "Patient Chart", "Diary", "Guide" and other MedicentreV3 nav items are out
  of scope — this spec is the Doctor consultation screen only.

## Information architecture

Replaces today's single vertical scroll (vitals → documentation → diagnosis&orders → panels →
footer) with the DoctorV2 shape:

```
PageHeader — Consultation / Clinical Desk

┌ Patient Details (collapsible; "click to hide") ───────────────────────────┐
│ LEFT  demographics: OPD No · Name · Age/Sex · Residence · Occupation ·      │
│       No. of Visits · Scheme · Rem. Credit · Allergies (rose) · Note        │
│ RIGHT Consultation Queue table: Q.No · OPD No · Name · From · Mins          │
│       + patient search (name / ID / OP-No / phone) + "View all patients"    │
└────────────────────────────────────────────────────────────────────────────┘

┌ Tabs: [Encounter Notes] [Patient History]                    [Actions ▾] ───┐
│ ENCOUNTER NOTES                                                             │
│   Complaints (+ chips)  │  History of Presenting Illness (textarea)         │
│   Physical Examination (textarea)                                           │
│   Impressions (+ chips)  │  Diagnosis (ICD-10 picker + free text)           │
│   Clinical Summary (full-width textarea)                                    │
│ PATIENT HISTORY                                                             │
│   Medical │ Surgical │ Family                                               │
│   Social  │ Economic │ Allergies      (each: add + list of entries)         │
│   Immunizations (add + list)                                                │
│   Patient's Previous Visits table: Visit Id · Date · Note · Summary Report  │
└────────────────────────────────────────────────────────────────────────────┘

Footer (unchanged behavior): Save draft · Send to billing · Forward to pharmacy · Finalize & sign
```

**Queue in the header.** The consultation queue moves from today's collapsible card into the
Patient-Details header as a compact table driven by the existing `/clinical/queue` data.
Columns: Q.No (queue_id), OPD No (outpatient_no), Name, From (source/department), Mins
(now − created_at). Double-click / click-to-select loads the patient into the desk (same
`handlePatientSelect` path as today). The name/ID search bar (existing `PatientSearch`) sits
here too, plus "View all patients" (routes to Patient Registry).

## Component decomposition

`frontend/src/pages/ClinicalDesk.jsx` is ~2,000 lines today (over the 500-line guideline). The
rebuild decomposes it; each file has one responsibility and a clear prop interface. State,
submit, and the draft safety-net stay in the shell.

| File | Responsibility |
|------|----------------|
| `pages/ClinicalDesk.jsx` (shell) | Orchestration: active patient, encounter state, tab state, submit (Draft/Billed/Pharmacy/Completed), draft safety-net, which Action modal is open. |
| `pages/clinical/PatientDetailsHeader.jsx` | Collapsible demographics + consultation-queue table + search + "View all patients". Props: `patient`, `queue`, `onSelectPatient`, `onSearch`. |
| `pages/clinical/EncounterNotesTab.jsx` | Complaints, HPI, Physical Exam, Impressions, Diagnosis (ICD-10), Clinical Summary. Controlled via props from the shell. |
| `pages/clinical/PatientHistoryTab.jsx` | The 6 history categories + Immunizations (reuse existing history add/list + `PatientHistoryModal` inline logic) + Previous Visits table. |
| `pages/clinical/ActionsMenu.jsx` | The `Actions ▾` dropdown: grouped, permission-gated items; emits an action key to the shell which opens the matching modal. |
| New modals (below) | One file each, kept small. |

Existing components reused unchanged as Actions: `ReferralModal`, lab modal, imaging modal,
`ClinicalExtrasPanel` (Sick Note / Optical / External Request / Order Sets), `CarePathwaysPanel`
(Theatre Request / Admit), consent modal, `VitalsTrendsModal`, `printReports`
(Visit Summary / Examination / All Visits).

## Actions menu — inventory

Grouped in the dropdown; each gated on the viewer's permissions.

**Clinical:** Vitals* · Prescription* · Assess & Plan (new) · Refer Patient
**Orders:** Lab Request · Radiology Request · Theatre Request · External Request · Order Sets
**Flow:** Appointment (follow-up) · My Appointments (new) · Queue Patient (new) · Admit Patient · Pick Patient in Admission (new) · Billing (consultation fee)
**Documents:** Sick Note · Consent Form · Files (new)
**Reports:** Visit Summary · Lab Report (new) · Theatre Report (new) · Examination Report · All Visits · Blood Pressure Trend (new, BP subset of vitals-history)

\* **Vitals** and **Prescription** move behind the Actions menu as modals to keep the Encounter
Notes tab clean (matching DoctorV2). Their data still flows into the same encounter submit.
A small read-only "vitals recorded / N meds" summary chip shows on Encounter Notes when present.

### New features — how each is built

| Feature | Backend | Frontend |
|---------|---------|----------|
| **Files** | NEW `clinical_files` table + routes (upload/list/download/delete). base64 in DB, ≤ 2 MB/file, `clinical:write`/`read`. | `FilesModal.jsx` — drag/drop or picker, list with download/delete, client-side compress like branding. |
| **Assess & Plan** | NEW nullable `assessment_plan` column on `medical_records` (same migration). Written by `POST /clinical/submit`. *(Refinement over the initial "fold into treatment_plan JSON" idea — a dedicated column avoids touching the prescription parser that reads `treatment_plan`.)* | `AssessPlanModal.jsx` — assessment + plan textareas; value held in shell state, sent on submit. |
| **My Appointments** | Reuse existing appointments API filtered to current doctor. | `MyAppointmentsModal.jsx` — read-only list of the doctor's upcoming appointments. |
| **Queue Patient** | Reuse `POST /queue/` (create queue entry → department/room). | `QueuePatientModal.jsx` — pick department/room, submit. |
| **Pick Patient in Admission** | Reuse wards board / admissions list. | `PickAdmissionModal.jsx` — list admitted patients, select → load into desk. |
| **Lab Report** | Reuse `GET /clinical/records`/lab results by patient. | Print template in `printReports.js` (patient's lab results). |
| **Theatre Report** | Reuse theatre cases by patient. | Print template (patient's theatre cases + operative notes). |
| **BP Trend** | Reuse `GET /clinical/patients/{id}/vitals-history`. | Reuse/extend `VitalsTrendsModal` focused on BP. |

Everything not marked "NEW" reuses an endpoint that already exists.

## Backend changes (minimal)

1. **`clinical_files` table** (`models/clinical_extras.py` or a new `models/clinical_files.py`):
   `file_id` PK, `patient_id` FK→patients (CASCADE, indexed), `record_id` FK→medical_records
   (SET NULL, nullable), `filename` String(255), `mime` String(120), `size_bytes` Integer,
   `data` Text (base64), `uploaded_by` FK→users (SET NULL), `created_at` tz-aware default now.
2. **`medical_records.assessment_plan`** — new `Text` nullable column.
3. Alembic migration (one revision, `down_revision` = current head `f3c73d2e5a91`) creating the
   table + the column; register in `scripts/migrate_all_tenants.py` model imports (clinical_files
   if a new module) — `clinical_extras`/`clinical` already registered; no data seed needed.
4. Routes `routes/clinical_files.py`: `POST /clinical-files` (patient_id, filename, mime, data,
   optional record_id; enforce size), `GET /clinical-files?patient_id=`, `GET
   /clinical-files/{id}` (download), `DELETE /clinical-files/{id}`. `clinical:read`/`clinical:write`,
   audit-logged. Register in `main.py`.
5. `POST /clinical/submit` accepts `assessment_plan` (Optional[str]); persist to the new column.

Migration surface is deliberately tiny: **one new table + one nullable column**. This keeps the
`migration-check` gate green through development → beta → main.

## Data flow

- Encounter state stays in the shell: `vitals`, `complaints[]`, `hpi`, `physicalExam`,
  `icdCodes[]` + free-text diagnosis, `clinicalSummary`, `medications[]`, `assessPlan`,
  `pendingFollowUp`, consent flag.
- Patient History entries save individually via the existing medical-history endpoints (as today).
- Files upload/list/delete independently via the new endpoints (not part of the encounter submit).
- Submit → `POST /clinical/submit` with the encounter fields **plus** `assessment_plan`;
  status targets Draft/Billed/Pharmacy/Completed unchanged.
- Client draft safety-net (`useDraftSafetyNet`) and server draft/resume preserved; the draft
  value object gains `assessPlan`.

## RBAC

Reuse existing permissions. Action items gate on: `clinical:read/write` (notes, vitals, rx,
assess&plan, files, sick note, consent, order sets, external request, reports), `laboratory:*`,
`radiology:*`, `theatre:manage`, `wards:read/manage`, `billing:*`, `appointments:*`,
`referrals:*`. Menu items the user lacks permission for are hidden.

## Testing

- **Backend:** `test_clinical_files.py` (upload → list → download → delete; RBAC 401/403;
  size-limit 413/422; unknown patient 404). `assessment_plan` round-trips through submit +
  a record fetch.
- **Frontend (Vitest/RTL):** `PatientDetailsHeader` (renders demographics + queue rows, select
  fires), `ActionsMenu` (renders grouped items, hides ungranted, emits keys), `EncounterNotesTab`
  and `PatientHistoryTab` (fields controlled), each new modal (happy-path POST/GET with mocked
  api client, using `.then/.catch` loaders). Keep/adjust existing Clinical Desk tests.
- **Verify gate:** eslint 0 errors, `npm run build`, backend import + `migrate` head, react-doctor
  diff no new errors.

## Risks & mitigations

- **Regression risk** — the desk carries a lot of wired behavior (draft resume, consent, fee,
  submit targets, tour anchors). *Mitigation:* preserve the submit/draft/consent logic verbatim in
  the shell; the rework is presentational (header/tabs/actions) around the same state and handlers.
  Keep `data-tour` anchors (`clinical-queue`, `clinical-vitals`, `clinical-consent`,
  `clinical-submit`, …) on their nearest equivalents.
- **File bloat in tenant DB** — cap file size (~2 MB) and count; store base64 like branding; this
  is acceptable for the current scale (see the scale/perf memory) and avoids new infra.
- **`treatment_plan` parser** — untouched; Assess & Plan uses its own column.
- **Big single change** — decomposition into small files keeps each unit reviewable; land behind
  the existing feature branch and screenshot-verify before promoting.

## Deliverable order (single pass, but reviewable units)

1. Backend: `clinical_files` + `assessment_plan` migration, routes, submit field, tests.
2. Shell + `PatientDetailsHeader` (with queue table) + tab scaffold (behavior parity with today).
3. `EncounterNotesTab` + `PatientHistoryTab` (move existing fields; Previous Visits table).
4. `ActionsMenu` + wire existing modals as actions.
5. New modals: Vitals, Prescription, Assess & Plan, Files, My Appointments, Queue Patient,
   Pick-in-Admission; new report templates (Lab, Theatre, BP Trend).
6. Verify (eslint/build/vitest/pytest/migration) + screenshot both tabs + the Actions menu.

## Delivery, branching & migration

- **Own branch**, promoted **development → beta → main**, each stage its own PR (per project
  branching flow). Never PR straight into beta/main.
- **Perfect migration is the gate.** The `migration-check` workflow runs
  `migrate_all_tenants.py` against a fresh Postgres on push/PR into development, beta, and main —
  it must be green before promoting to the next stage. This work touches
  `backend/alembic/**` + `backend/app/models/**` + `migrate_all_tenants.py`, so it IS a schema
  change: add the alembic revision AND register the model file. Confirm `alembic` at head and
  migration-check green on the source branch before each promotion.
- **Dependency to resolve before branching (needs your call):** DoctorV2 **reuses** components
  that currently live only on the unmerged `feat/clinical-desk-parity` branch
  (`ClinicalExtrasPanel`, `CarePathwaysPanel`, `printReports`, the A–E parity features) — which
  itself is stacked on the unmerged Dialysis (#205) and Theatre (#206) PRs. A DoctorV2 branch cut
  from `development` would **not** have those. Options:
  - **(A) Land the stack first (recommended):** promote Dialysis → Theatre → clinical-desk-parity
    into development (they're built & verified), then cut the DoctorV2 branch from `development`.
    Clean history, no duplication.
  - **(B) Stack DoctorV2 on `feat/clinical-desk-parity`:** start immediately; the whole stack then
    promotes together. Faster to start, but development gets one large combined change.
  - **(C) DoctorV2 off `development` standalone:** only viable if the reused parity components are
    also brought along — effectively re-doing/merging A–E first. Most churn; not recommended.
