# Full Visit History, Multiple ICD-10 Diagnoses & Printable Referral Letters

**Date:** 2026-07-06
**Status:** Approved
**Branch target:** feature branch off `development`

Client feedback drives three changes to the clinical workflow:

1. Doctors must see a patient's **complete visit history** — every visit ever, with everything done in each visit (today: last 10 visits, 5 summary fields each).
2. A consultation must support **multiple ICD-10 diagnoses** (today: one code).
3. Doctors must be able to **print a referral letter**, with a choice of a fully typed letter, a blank letter pre-filled with patient info, or a fully blank letter for handwriting.

---

## 1. Full visit history

### Current state
- `GET /api/medical-history/{patient_id}/chart` (`backend/app/routes/medical_history.py`) limits medical records to `.limit(10)` and serialises only `record_id`, `date`, `doctor`, `chief_complaint`, `diagnosis`, `record_status`.
- `frontend/src/pages/MedicalHistory.jsx` renders these rows read-only under "recent visits".

### Design — summary list + lazy detail (approved)
**Backend**
- Chart endpoint: drop the `limit(10)` on medical records so **all** visits return as summary rows (same fields as today). The existing doctor-name batch lookup already avoids N+1.
- New endpoint `GET /api/clinical/record/{record_id}` in `backend/app/routes/clinical.py`, permission `history:read`, returning the full encounter:
  - SOAP: `chief_complaint`, `history_of_present_illness`, `review_of_systems`, `physical_examination`
  - Vitals: BP, HR, RR, temp, SpO2, weight, height, BMI, blood glucose
  - Diagnosis & plan: `icd10_code` (may contain multiple comma-separated codes), `diagnosis`, `treatment_plan`, `prescription_notes`, parsed prescriptions (reuse `_parse_prescriptions`), `follow_up_date`
  - Linked orders: lab tests (`LabTest.record_id`) and radiology requests for this record — name, status, and result summary each
  - Meta: visit date, doctor name, `record_status`
  - `internal_notes` are included only for clinical roles (same sensitivity posture as the chart's `SENSITIVE_DATA_RESTRICTED_ROLES`).
- KDPA: the chart access is already logged via `_log_data_access`; the record-detail endpoint logs an equivalent access entry.

**Frontend (`MedicalHistory.jsx`)**
- "Recent visits" section becomes **"Visit history"** listing all visits (scrollable).
- Each visit row is an expandable accordion. First expansion fetches `/clinical/record/{record_id}` and caches it in component state; renders vitals grid, SOAP sections, diagnosis list (ICD chips), prescriptions table, lab/radiology orders.

### Non-goals
- No pagination for now — summary rows are light; revisit if a tenant accumulates thousands of visits per patient.
- No change to queue visibility or assignment rules.

---

## 2. Multiple ICD-10 diagnoses

### Current state
- `MedicalRecord.icd10_code` — `String(255)`, indexed, single code.
- Clinical Desk has a single ICD-10 type-ahead (`/clinical/icd10/search`) whose text becomes both `icd10_code` and fallback `diagnosis`.

### Design — comma-separated codes in the existing column (approved)
**Storage (schema-compatible, no migration):**
- `icd10_code` stores comma-separated codes: `"E11.9, I10, N39.0"`. First code = **primary diagnosis**.
- `diagnosis` stores the joined descriptions, `"; "`-separated, in the same order.
- UI caps at **10 codes** (≈120 chars, well inside 255). Backend `/api/clinical/submit` validates the joined string fits 255 chars.

**Clinical Desk UI:**
- Type-ahead stays; choosing a result **adds a chip** (code + description) below the field and clears the input. Chips are removable (×). First chip visually marked "Primary".
- Free-typed text that isn't picked from the dropdown continues to work as a diagnosis description (current behaviour), it just doesn't add a code chip.
- Submit payload: `icd10_code` = joined codes, `diagnosis` = joined descriptions (or the free-text diagnosis if no chips).

**Display:** everywhere `icd10_code`/`diagnosis` currently render (visit history, privacy exports), the comma/semicolon lists render as-is; the new visit-detail view renders codes as chips.

### Trade-off accepted
A JSON column or child table is more normalized but forces an alembic migration + `migrate_all_tenants` registration through development → beta → main. Comma-separated in the existing column keeps the migration gate a no-op and satisfies the requirement. If structured reporting on diagnoses is needed later, promote to a child table then.

---

## 3. Printable referral letters

### Current state
- Backend complete: `referrals` table (`backend/app/models/referral.py`), `POST/GET/PATCH /api/referrals` (`routes/referrals.py`), permissions `referrals:manage` / `clinical:read`.
- Clinical Desk "Refer patient" button → `handleNotImplemented('External Referrals')`. No letter printing anywhere.

### Design (approved)
**Referral modal (Clinical Desk):**
- "Refer patient" opens a modal in the active consultation: specialty (required), target facility, target clinician, urgency (Routine/Urgent/Emergency), reason (required), clinical summary (pre-seeded from the current consult's diagnosis if present).
- Save → `POST /api/referrals/` with the current `patient_id` and, when available, the consult's `record_id`.

**Printing — three modes, chosen in the modal:**
1. **Typed letter** — generated from the saved referral: clinic letterhead (hospital name/branding), date, patient name/age/sex/OPD no, referral fields, referring doctor name + signature line. Requires the referral to be saved first (keeps the referral log accurate).
2. **Blank + patient info** — letterhead, date, patient identity block, and referring doctor pre-filled; specialty/reason/summary printed as ruled blank sections for handwriting. Does **not** create a referral record.
3. **Fully blank** — letterhead + form structure only; every field including patient identity is a ruled blank. No record created.

**Print mechanism:** same pattern as `printPharmacyReceipt` in `Pharmacy.jsx` — `window.open` + inline A4 print CSS + `window.print()`, with `escapeHtml` on all interpolated values. Extracted as a shared helper so Pharmacy and referrals don't duplicate `escapeHtml`. Hospital name/branding sourced the same way the receipt gets it (tenant branding/settings already available to the frontend).

### Non-goals
- No referral worklist/management page in this iteration — creation + printing from Clinical Desk only. Status transitions remain available via the existing API for later UI.
- No PDF generation dependency; browser print only.

---

## Error handling
- Record-detail fetch failure → inline error in the expanded row with retry.
- Referral save failure → toast with backend detail; modal stays open preserving input.
- Pop-up blocked on print → toast (same as pharmacy receipt).
- ICD chips: duplicate code selection is ignored; >10 codes blocked with a hint.

## Testing
- **Backend (pytest, live-server pattern):** chart returns >10 visits when present; record-detail returns full fields incl. prescriptions and linked lab orders; permission checks (`history:read`); multi-code submit round-trips `icd10_code` string; referral create validates required fields.
- **Frontend (Vitest + RTL):** ICD chips add/remove/primary marking and submit payload; visit accordion fetch-on-expand renders SOAP/vitals/prescriptions; referral modal validation and that each print mode opens the print window with expected content (mock `window.open`).

## Rollout
- Single feature branch off `development`; no schema change, so `migration-check` stays a no-op. Standard promotion `development → beta → main`.
