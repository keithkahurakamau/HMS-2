# Clinical Flow Fixes + "What's New" Announcements — Design

**Date:** 2026-06-24
**Branch:** `feat/clinical-flow-and-whats-new` (off `development`)
**Delivery:** one combined PR → `development` (then promote `development → beta → main`)

## Context

A batch of customer-reported issues plus a new in-app announcements feature.
Work groups into four streams. Only **Stream C** changes the database schema, so
the `migrate-all-tenants` gate stays a near no-op for the rest.

Key facts established from the codebase:

- Queue lives in `PatientQueue` (`backend/app/models/clinical.py`); active statuses
  are `["Waiting", "In Progress", "In Consultation"]`, terminal is `"Completed"`.
- `PATCH /api/queue/{id}/checkout` already soft-completes a single row; the doctor's
  "remove from queue" calls it (`ClinicalDesk.jsx:149`).
- `Triage.jsx` hardcodes `disposition: 'Consultation'` (line 124); the backend
  (`triage.py::submit_triage`) already routes to any `_canonical_department`.
- `TriageRecord` captures `blood_glucose` (RBS) and `calculated_bmi`, but
  `MedicalRecord` has **no `blood_glucose` column**, and `prefillFromTriage`
  (`ClinicalDesk.jsx:221`) copies BP/HR/RR/temp/SpO₂/weight/height — **not** RBS.
- The medical chart endpoint (`medical_history.py::get_patient_medical_chart`)
  returns `recent_visits` (MedicalRecords) but **no triage history**.
- Notifications: `Notification` model + `app/utils/notify.py` (`notify`,
  `notify_permission`, `notify_role`) back a bell inbox + WebSocket fan-out.
- Journey/tour system: `JourneyContext` exposes `forceStartJourney(moduleKey)`,
  `restartAll()`, `restart`-able via Settings ("Replay tours").
- App version is currently `frontend/package.json` `0.0.0`.

## Decisions (confirmed with user)

1. "Accounts notifications" actually means **in-app "What's New" announcements**:
   notify users when we ship app changes, version-tracked (v1, v2…), with an
   **optional "Take the tour" button**.
2. Announcement content lives in a **frontend changelog** (no DB table, no migration).
3. Dashboard/Home should show **only active/pending** patients (still to be seen) —
   hide both `Completed` and `Cancelled`.
4. "Clear previous visit" = **start-new-visit / clear current** action, as the first
   item on patient history.
5. Versioning = a maintained release change-history (v1, v2…).
6. All four streams ship in **one combined PR**.

---

## Stream A — "What's New" in-app announcements (frontend-driven)

**Goal:** when the app updates, the user sees what changed, versioned, with an
optional button to launch the product tour.

**Components:**

- `frontend/src/releases.js` — single source of truth. Ordered list, newest first:
  ```js
  export const APP_VERSION = "1.0.0";
  export const RELEASES = [
    {
      version: "1.0.0",
      date: "2026-06-24",
      title: "Clinical flow improvements",
      changes: [
        "Triage can now route patients to any module (lab, pharmacy, reception…).",
        "Doctors now see Random Blood Sugar (RBS) and BMI from triage.",
        "Patients can be cancelled when not seen; dashboards show only active patients.",
        "Full triage history now appears in the patient chart.",
      ],
      tourKey: null, // optional module key to offer a tour for
    },
  ];
  ```
- `package.json` version → `1.0.0` (kept in sync with `APP_VERSION`).
- Per-user "last seen version" persisted in `localStorage` (mirror the journey
  progress pattern: key by `user_id`). Helper `readLastSeenVersion(userId)` /
  `writeLastSeenVersion(userId, version)`.
- A small `WhatsNew` surface (modal or bell-anchored card) shown on app load when
  the stored last-seen version is behind `APP_VERSION`. It lists the changes for
  every release newer than what the user last saw, and renders an **optional
  "Take the tour" button** when a release declares a `tourKey` (or a generic
  "Replay tours" that calls `restartAll()` from `JourneyContext`).
- Dismissing the surface writes `APP_VERSION` as last-seen so it doesn't reappear.
- Also re-accessible from Settings (next to "Replay tours") via a "What's new" button.

**Data flow:** load → read last-seen → compare to `APP_VERSION` → if behind, show
surface with the diff of releases → dismiss writes last-seen.

**Out of scope (possible v2):** superadmin-authored DB-backed announcements.

---

## Stream B — Queue & triage workflow (no schema change)

### B1 — Reliable "remove from queue" across all modules
- Reproduce the customer failure for the per-row remove.
- Ensure `checkout` works for any department's queue rows, and that removed rows
  stop showing as waiting everywhere (consultation, lab, pharmacy, triage, etc.).
- Add an explicit per-row remove affordance to module queues that lack one, all
  routed through `PATCH /api/queue/{id}/checkout`.

### B2 — Triage disposition picker (route to any module)

**Architectural finding (confirmed during planning):** the generic `PatientQueue`
is only *consumed* by Triage and Consultation. Other modules run their own
order-based queues (`/laboratory/queue` = lab orders, `/billing/queue` = invoices,
Pharmacy = prescriptions, `/radiology/queue`). Reception has no waiting-patient
queue at all. So routing a triage patient to e.g. Pharmacy creates a `PatientQueue`
row that nobody sees. To make "route to all modules" real, each destination needs a
panel that reads the generic queue. **User chose: all modules.**

- Replace the hardcoded `disposition: 'Consultation'` in `Triage.jsx` with a
  **department selector** (canonical departments). Default stays `Consultation`
  (preserves today's behaviour); footer copy becomes dynamic.
- Add **`Reception`** to `CANONICAL_DEPARTMENTS` and `_DEPARTMENT_ALIASES`
  (`backend/app/routes/patients.py`) so it's an accepted disposition.
- Build **one reusable `DepartmentQueue` panel** (`frontend/src/components/
  DepartmentQueue.jsx`) that reads `GET /api/queue/?department=<X>`, shows the
  patients routed there, and offers per-row remove (checkout) + cancel.
- Drop the panel into the **Reception (Patients), Laboratory, Pharmacy, Radiology,
  and Wards** pages. Consultation keeps its existing `/clinical/queue` worklist.
- Backend already routes via `_canonical_department`; the only backend change is
  adding `Reception` to the catalogue.

### B3 — Cancel-when-not-seen
- Introduce a new queue status string **`"Cancelled"`** (no migration — `status`
  is already a free `String`).
- New endpoint `PATCH /api/queue/{id}/cancel` (perm `patients:write`), optional
  `reason`, sets `status="Cancelled"`, stamps `completed_at`, writes an audit row.
- "Cancelled" is excluded from all active-queue queries (B4).
- Distinguish "Cancelled" (never seen) from "Completed" (seen & done) for history
  and any analytics.

### B4 — Dashboard/Home show only active/pending
- Update active-queue filters to exclude **both** `Completed` and `Cancelled`:
  - `GET /api/queue/` currently filters `status != "Completed"` → also exclude
    `"Cancelled"`.
  - `clinical.py::get_clinical_queue`, `triage.py::get_triage_queue` already use an
    allowlist of active statuses — confirm they exclude `Cancelled` implicitly.
- Verify Home (`Home.jsx`) and the dashboard surfaces only show active patients.

---

## Stream C — Doctor sees RBS + BMI  (the one schema change)

### Backend
- Add `blood_glucose = Column(Float, nullable=True)` to `MedicalRecord`
  (`backend/app/models/clinical.py`).
- Alembic revision adding the column.
- Register the change so legacy-tenant bootstrap and the migration gate stay green
  (model file already imported in `migrate_all_tenants.py`; confirm).
- Accept `blood_glucose` on the clinical submit path (`clinical.py::submit_consultation`).

### Frontend (`ClinicalDesk.jsx`)
- `prefillFromTriage` also copies `blood_glucose` (RBS); BMI is already recomputed
  from weight/height — keep, and also show the triage-derived value.
- Add an **RBS (mmol/L)** field to the doctor's vitals grid.
- Ensure **BMI** is visibly rendered (it already computes at line 586 — confirm it
  displays for prefilled patients).

---

## Stream D — Patient history (no schema change)

### D1 — Triage history visible
- Extend `get_patient_medical_chart` to include a `triage_history` list (last 10
  triage rows, newest first): date, nurse, acuity, chief complaint, key vitals
  incl. RBS + BMI.
- Add `triage_history` to `PatientMedicalChartResponse` schema.
- `MedicalHistory.jsx`: render a **"Triage History"** section alongside
  "Recent Clinical Visits".

### D2 — "Start new visit / clear current" (first item on history)
- A control at the top of the patient history page that:
  - Closes the patient's current open visit: any active `PatientQueue` rows for the
    patient (`Waiting`/`In Progress`/`In Consultation`) are soft-completed.
  - Clears the active-patient context in the UI so a fresh visit begins clean.
- Backend: `POST /api/queue/patients/{patient_id}/close-visit` (perm `patients:write`)
  — soft-completes the patient's active queue rows, returns count; audited.
- Placed as the **first item** in the history view, with a confirm dialog.

---

## Testing

- **Backend (pytest, live-server):** queue cancel + close-visit endpoints; triage
  disposition routing to non-Consultation departments; chart includes triage_history;
  MedicalRecord.blood_glucose round-trips; active-queue filters exclude Cancelled.
- **Frontend (Vitest + RTL):** Triage disposition picker; ClinicalDesk RBS prefill +
  field; WhatsNew surface shows on version bump and hides after dismiss; MedicalHistory
  triage section + clear-visit action.
- **Migration gate:** `migrate_all_tenants.py` against fresh Postgres must be green
  (new alembic revision at head; model registered).

## Migration / release notes

- One schema change: `medical_records.blood_glucose` (nullable Float) — additive,
  backward-compatible. Must pass the gate at `development`, `beta`, and `main`.
- Everything else is schema-compatible (new status string, frontend changelog, new
  endpoints reusing existing tables).

## Out of scope / YAGNI

- DB-backed, superadmin-authored announcements (possible v2).
- Reworking analytics dashboards beyond the active/pending filter change.
- Per-visit "encounter" entity refactor (we reuse `PatientQueue` rows as the visit
  unit for D2).
