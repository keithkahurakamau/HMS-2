# Clinical Desk Inline History + Cross-Module Draft Safety Net

**Date:** 2026-07-20
**Status:** Approved
**Scope:** Frontend-only. No schema change, migration gate stays a no-op.

## Problem

1. Clinical Desk's "History toolbar" (Medical Hx / Surgical Hx / Social Hx / Family Hx /
   Immunizations) navigates the doctor away to `/app/medical-history`, unmounting the
   in-progress encounter form. A doctor who just wants a quick look at prior history has
   to leave their current charting session to see it.
2. Free-text clinical notes typed across the app can be lost if something interrupts the
   doctor/nurse before they explicitly save — a shift change, an accidental navigation, a
   browser crash, or a closed tab. `feat/clinical-desk-custom-icd` (merged to `development`
   as PR #181, which folded in PR #183 "resume drafts & returned encounters") already
   solved this server-side for Clinical Desk *after* an explicit "Save draft" — that fix
   is out of scope here and already shipped. This spec covers the gap *before* that first
   explicit save, and extends equivalent protection to other clinically-relevant surfaces
   that don't have a server-side draft concept at all.

## Part A — Inline patient history popup

- New component `frontend/src/components/PatientHistoryModal.jsx`, read-only.
  - Fetches `GET /medical-history/{patientId}/chart` — the same endpoint
    `MedicalHistory.jsx` already uses (`PatientMedicalChartResponse`). No backend change.
  - Renders: patient header, KDPA badge, `VisitHistoryList` (reused as-is) for the full
    chart view, and collapsible sections per entry type (Surgical/Family/Social/
    Immunization/Allergy/Chronic Condition/Past Medical Event/Obstetric/Mental Health).
  - Props: `patientId`, `initialSection` (optional entry-type key to auto-expand),
    `onClose`.
  - Footer: "Open full record ↗" link to `/app/medical-history?patient_id=...` for
    doctors who need to add/edit/delete/print — this popup never writes.
- `ENTRY_TYPES` / `colorMap` currently defined inline in `MedicalHistory.jsx` move to
  `frontend/src/constants/medicalHistoryEntryTypes.js`, imported by both files, so the
  two views can't drift out of sync.
- `ClinicalDesk.jsx`: the five History toolbar buttons stop calling `navigate(...)` and
  instead open `PatientHistoryModal` with `initialSection` set to their `entry_type`. A
  new expand icon on the active-patient banner opens the same modal with no initial
  section (full chart). Closing the modal returns to the encounter form exactly as it
  was — nothing in the SOAP form state is touched by opening/closing it.

## Part B — Draft safety net

- New hook `frontend/src/hooks/useDraftSafetyNet.js`:
  - `useDraftSafetyNet({ storageKey, value, enabled })`.
  - Debounces (~1s) serializing `value` to `localStorage` under `hms:draft:${storageKey}`
    while `enabled` is true.
  - On mount, exposes `{ hasSavedDraft, savedAt, readDraft(), clearDraft() }` — it never
    auto-applies a saved draft over live state. The caller decides when to show/apply it.
  - `clearDraft()` is called by the host component after a successful save/submit so a
    stale draft can't resurface on a later, unrelated encounter for the same key.
- New shared `frontend/src/components/DraftRecoveryBanner.jsx` — "We found unsaved notes
  from `<time ago>` — Restore / Discard" — reused by every rollout site so recovery UX is
  consistent.
- **Storage-key isolation is a hard requirement, not a nice-to-have** — this is PHI. Every
  key includes the record identity it belongs to, e.g. `clinicalDesk:{queue_id}`,
  `medicalHistoryEntry:{patient_id}:{entry_id|'new'}`, `wardsLog:{admission_id}`,
  `triageNotes:{patient_id}`, `referral:{patient_id}`. One patient's draft can never
  surface on another patient's form.
- Restoring is always explicit and verbatim — the raw stored strings/objects are applied
  as-is via the banner's "Restore" action, never auto-merged or reformatted.

### Rollout targets (this pass)

Chosen because they're clinician-facing free-text entry with real shift/interruption
exposure — not back-office/admin config forms (Settings, role/department managers,
accounting config), which aren't subject to shift handovers and where lost text is an
inconvenience, not a safety concern:

1. `ClinicalDesk.jsx` — the whole encounter form (vitals, SOAP notes, complaints, exam
   findings, medications, ICD chips) as one blob keyed by `queue_id`. Sits underneath the
   already-shipped server-side draft/resume: this hook covers the interval *before* the
   first explicit "Save draft".
2. `MedicalHistory.jsx` — the add/edit-entry form (title/description).
3. `Triage.jsx` — the triage notes field.
4. `Wards.jsx` — the per-admission "Clinical log" observation textarea (the most literal
   match for "a shift happens and notes shouldn't be lost").
5. `ReferralModal.jsx` — reason + clinical summary fields.

## Testing

- `useDraftSafetyNet.test.js` — debounce timing, save/read/clear round-trip, and key
  isolation between two different `storageKey`s (proves no cross-patient bleed).
- `PatientHistoryModal.test.jsx` — renders chart sections, `initialSection` auto-expand,
  "Open full record" link builds the correct URL.
- `ClinicalDesk.test.jsx` (new) — history toolbar opens the modal instead of navigating;
  draft banner appears/restores/discards; draft clears after any successful submit.
- Lighter spot-check assertions (banner appears when `localStorage` is pre-seeded, clears
  after save) for the other four rollout sites rather than full duplicate suites.

## Branching

New branch off `development`, PR'd into `development` per the standard promotion path —
unrelated to the in-progress Maternity module work, so it does not ride on
`feat/maternity-module`. No `alembic/`, `models/`, or `migrate_all_tenants.py` changes, so
the migration-check gate stays a no-op.
