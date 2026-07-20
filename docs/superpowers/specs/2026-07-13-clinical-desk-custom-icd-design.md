# Clinical Desk — Custom ICD-10 Diagnoses + Module Hardening

**Date:** 2026-07-13
**Status:** Approved
**Scope:** Phase 1 (this branch). Phases 2+ are logged here for follow-up PRs but are out of scope.

## Problem

The Clinical Desk diagnosis picker (`IcdDiagnosisPicker.jsx`) only accepts codes from the
CMS ICD-10-CM catalogue (~74k rows via `/clinical/icd10/search`). When a clinician's
diagnosis isn't in the catalogue — a local/working diagnosis, a provisional impression,
or simply wording they prefer — the picker dead-ends at "No codes found." The separate
free-text field below it is disconnected from the chip flow, so custom diagnoses don't
participate in the primary/secondary ordering or the referral summary.

A module audit also surfaced picker UX defects and an orphaned backend endpoint
(vitals history) that Phase 1 fixes while we're here.

## Phase 1 design (frontend-only; no schema change, migration gate stays a no-op)

### 1. Custom diagnosis chips

- When the search input has ≥ 2 characters, the dropdown always shows a final row:
  **Add "&lt;typed text&gt;" as custom diagnosis (note)** — offered whether or not
  catalogue matches exist, so the clinician can keep their exact wording.
- A custom pick becomes a chip `{ code: null, description: <text>, custom: true }`,
  rendered with a **Note** badge where catalogue chips show the mono code.
- Custom chips count toward the existing max of 10, participate in "first chip is
  primary", and satisfy the has-diagnosis validation in `validateForSubmit`.
- Dedupe: catalogue chips dedupe by code (unchanged); custom chips dedupe
  case-insensitively by text, and a custom entry that exactly matches an existing
  catalogue chip's code is also rejected.
- Chip identity moves from `c.code` (breaks once code can be null) to a per-chip uid
  generated at add time; removal and React keys use the uid.

### 2. Submit mapping (reuses existing columns)

- `icd10_code` ← catalogue codes only, comma-joined (**unchanged**). Custom text never
  enters this column — `clinical_history.py`'s legacy parser treats the column as a
  code list only when every part looks like a code, so free text there would mangle
  real codes in visit history.
- `diagnosis` ← "; "-join of custom chip texts followed by the free-text field.
  When both are empty, fall back to the catalogue descriptions join (preserves the
  current behavior that feeds the visit-history summary line).
- `ReferralModal`'s `initialSummary` includes custom chip texts using the same
  precedence as `diagnosis`.

### 3. Picker UX / accessibility hardening

- Dropdown closes on outside click and Escape.
- ArrowUp/ArrowDown move an active-descendant highlight; Enter selects it
  (falling back to "add as custom" when nothing is highlighted).
- Combobox ARIA: `role="combobox"`, `aria-expanded`, `aria-controls`,
  `aria-activedescendant` on the input; `role="listbox"`/`role="option"` on the results.

### 4. Wire the orphaned "View trends" button

`GET /clinical/patients/{id}/vitals-history` exists and is unused; the button currently
toasts "under development". Replace with a modal listing past readings (oldest → newest)
per vital, using the endpoint's shape as-is. No backend change.

### 5. Tests

- `IcdDiagnosisPicker.test.jsx`: add-as-custom row appears, custom chip renders with
  Note badge, dedupe rules, keyboard navigation, Escape/outside-click close, max-10
  applies across both kinds.
- `ClinicalDesk` submit payload: catalogue-only, custom-only, and mixed cases map to
  `icd10_code` / `diagnosis` per §2.

## Phase 2+ backlog (separate PRs, priority order)

1. **Draft resume / update-in-place** — every "Save draft" POST inserts a new
   `MedicalRecord`; drafts can't be reopened and duplicates pollute visit history.
2. **Returned-prescription worklist** — pharmacy "return to doctor" notifies with a
   link to the desk, but the desk has no view of `record_status = "Returned"` records.
3. **Lab-order ↔ record linkage** — desk lab orders send `record_id: null`, so visit
   detail (which joins on `record_id`) never shows them.
4. **Persist `follow_up_date`** — booking a follow-up never writes the record column.
5. Roadmap: paediatric growth charts, MOH regulatory reports, PACS viewer — each needs
   its own spec.

## Decisions taken with the user (2026-07-13)

- Storage: reuse `diagnosis` column for custom entries (no migration) — chosen over a
  new JSON `diagnoses` column.
- Scope: full module audit requested; Phase 1 approved as designed, deeper workflow
  defects deferred to follow-up PRs.
