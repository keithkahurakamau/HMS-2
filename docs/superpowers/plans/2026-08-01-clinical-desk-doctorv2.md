# Clinical Desk → DoctorV2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Clinical Desk to the DoctorV2 information architecture (collapsible Patient-Details + consultation-queue header, Encounter Notes / Patient History tabs, one consolidated Actions menu) in HMS-2's design system, and add every missing DoctorV2 action.

**Architecture:** Presentational rebuild around the *existing* encounter state + submit + draft logic (preserved in a shell). New backend surface is tiny: one `clinical_files` table + one `assessment_plan` column. The `POST /clinical/submit` handler already persists any MedicalRecord attribute generically (`setattr`), so `assessment_plan` needs no route change. Most Actions reuse existing modals/endpoints; a few new modals/reports are added.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + Vite + Tailwind + Vitest/RTL (frontend). Branch `feat/clinical-desk-doctorv2` off `development`.

## Global Constraints

- Branch off `development`; promote development → beta → main, each its own PR. Migration-check must be green at every stage.
- New migration `down_revision = f3c73d2e5a91` (current development head). Register any new model file in `scripts/migrate_all_tenants.py`.
- Files under 500 lines; reuse `.input`/`.btn-*`/`.card`/`.section-eyebrow`/`badge-*`/`PageHeader`.
- Data loaders use `.then/.catch` (no synchronous setState in effects) — react-hooks rule.
- RBAC via existing permissions; hide Action items the user lacks.
- Files stored base64 in DB, ≤ 2 MB/file (branding pattern).
- Preserve: submit targets (Draft/Billed/Pharmacy/Completed), client+server draft safety-net, consent capture, guided-tour anchors.
- eslint 0 errors + `npm run build` + backend import + pytest green before each promotion.

---

## File Structure

**Backend**
- `backend/app/models/clinical_files.py` (new) — `ClinicalFile` table.
- `backend/app/models/clinical.py` (modify) — add `assessment_plan` column to `MedicalRecord`.
- `backend/alembic/versions/a1b2c3d4e5f6_doctorv2_files_and_assessment.py` (new) — table + column.
- `backend/app/routes/clinical_files.py` (new) — upload/list/download/delete.
- `backend/app/main.py` (modify) — register router.
- `backend/scripts/migrate_all_tenants.py` (modify) — import `clinical_files`.
- `backend/app/routes/clinical_history.py` (modify) — expose `assessment_plan` in visit detail.
- `backend/tests/test_clinical_files.py`, `backend/tests/test_assessment_plan.py` (new).

**Frontend**
- `frontend/src/pages/ClinicalDesk.jsx` (rewrite as shell — state, submit, draft, which-modal-open).
- `frontend/src/pages/clinical/PatientDetailsHeader.jsx` (new).
- `frontend/src/pages/clinical/EncounterNotesTab.jsx` (new).
- `frontend/src/pages/clinical/PatientHistoryTab.jsx` (new).
- `frontend/src/pages/clinical/ActionsMenu.jsx` (new).
- `frontend/src/pages/clinical/modals/` (new): `VitalsModal.jsx`, `PrescriptionModal.jsx`, `AssessPlanModal.jsx`, `FilesModal.jsx`, `MyAppointmentsModal.jsx`, `QueuePatientModal.jsx`, `PickAdmissionModal.jsx`.
- `frontend/src/utils/printReports.js` (modify) — `printLabReport`, `printTheatreReport`.
- `frontend/src/api/clinicalFiles.js` (new) — files API.
- Tests colocated `*.test.jsx`.

**Reused unchanged:** `ReferralModal`, lab/imaging modals, `ClinicalExtrasPanel`, `CarePathwaysPanel`, consent modal, `VitalsTrendsModal`, `PatientSearch`, `IcdDiagnosisPicker`, existing `printReports` (Visit Summary/Examination/All-Visits), `useDraftSafetyNet`.

---

## Task 1: Backend — `clinical_files` table + `assessment_plan` column + migration

**Files:**
- Create: `backend/app/models/clinical_files.py`
- Modify: `backend/app/models/clinical.py` (MedicalRecord: `assessment_plan = Column(Text, nullable=True)`)
- Create: `backend/alembic/versions/a1b2c3d4e5f6_doctorv2_files_and_assessment.py` (down_revision `f3c73d2e5a91`)
- Modify: `backend/scripts/migrate_all_tenants.py` (add `clinical_files` to model imports)

**Interfaces — Produces:**
- `ClinicalFile(file_id, patient_id, record_id, filename, mime, size_bytes, data, uploaded_by, created_at)`
- `MedicalRecord.assessment_plan: Text|None`

**Model** (`clinical_files.py`):
```python
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.config.database import Base

class ClinicalFile(Base):
    __tablename__ = "clinical_files"
    file_id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    record_id = Column(Integer, ForeignKey("medical_records.record_id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    mime = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    data = Column(Text, nullable=False)  # base64 data URL
    uploaded_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

**Migration** creates `clinical_files` (mirror columns, index on patient_id) and `op.add_column("medical_records", sa.Column("assessment_plan", sa.Text(), nullable=True))`; downgrade drops both.

- [ ] Write migration; apply to a scratch DB (`DATABASE_URL=.../mayoclinic_db alembic upgrade head`).
- [ ] Register `clinical_files` in `migrate_all_tenants.py` imports.
- [ ] Verify `python -c "import app.main"` OK and `alembic heads` = new revision.
- [ ] Commit: `feat(clinical-desk): clinical_files table + assessment_plan column (DoctorV2 backend)`

## Task 2: Backend — `clinical_files` routes + tests

**Files:** Create `backend/app/routes/clinical_files.py`; modify `backend/app/main.py`; create `backend/tests/test_clinical_files.py`.

**Interfaces — Produces (all `/api/clinical-files`):**
- `POST /` body `{patient_id, filename, mime, data, record_id?}` → 201 `{file_id,...}` (`clinical:write`); reject `data` > ~2.8 MB base64 (≈2 MB binary) with 413.
- `GET /?patient_id=` → list metadata (no `data`) (`clinical:read`).
- `GET /{file_id}` → one incl. `data` (`clinical:read`).
- `DELETE /{file_id}` → 200 (`clinical:write`), audit-logged.

Follow `routes/clinical_extras.py` conventions (inline Pydantic, `RequirePermission`, `log_audit`, add→flush→audit→commit).

- [ ] Write `test_clinical_files.py` (live-server, mirror `test_clinical_extras.py`): unauth 401; nurse read ok / write 403 (nurse lacks clinical:write); doctor upload→list(meta only)→download(data present)→delete; oversized 413; unknown patient 404.
- [ ] Run against live server; all green.
- [ ] Commit: `feat(clinical-desk): clinical_files upload/list/download/delete + tests`

## Task 3: Backend — expose `assessment_plan` in visit detail + submit round-trip test

**Files:** Modify `backend/app/routes/clinical_history.py` (add `"assessment_plan": rec.assessment_plan` to the visit-detail dict); create `backend/tests/test_assessment_plan.py`.

- [ ] Test: POST `/clinical/submit` with `assessment_plan:"A/P text"` (Draft) → fetch `/clinical_history/record/{id}` → detail `assessment_plan == "A/P text"`. (No route change to submit — generic setattr persists it.)
- [ ] Run; green.
- [ ] Commit: `feat(clinical-desk): persist + surface assessment_plan on the encounter`

## Task 4: Frontend — files API + `FilesModal`

**Files:** Create `frontend/src/api/clinicalFiles.js`, `frontend/src/pages/clinical/modals/FilesModal.jsx` (+ test).

**Interfaces — Produces:** `listFiles(patientId)`, `uploadFile({patient_id, filename, mime, data, record_id})`, `downloadFile(id)`, `deleteFile(id)` (thin `apiClient` wrappers). `FilesModal({ patient, recordId, onClose })`.

`FilesModal`: file `<input>` → read as base64 data URL (`FileReader`), guard ≤ 2 MB, POST; list with size + download (anchor to `data`) + delete. Loaders use `.then/.catch`.

- [ ] Vitest: renders list; upload calls `uploadFile` with `patient_id`; delete calls `deleteFile`.
- [ ] Commit: `feat(clinical-desk): Files attachments modal`

## Task 5: Frontend — new action modals (Vitals, Prescription, Assess & Plan, Queue Patient, My Appointments, Pick-in-Admission)

**Files:** Create each under `frontend/src/pages/clinical/modals/` (+ tests). All are controlled: parent (shell) owns the encounter state; modals edit shell state or POST to existing endpoints.

- `VitalsModal({ vitals, onChange, onClose })` — the BP/HR/RR/Temp/SpO2/RBS/Wt/Ht grid + computed BMI (moved out of today's inline card). Writes shell `vitals` state.
- `PrescriptionModal({ medications, onChange, onClose })` — the numbered medication rows (drug/formulation/dosage/frequency/duration) moved out of today's inline block. Writes shell `medications`.
- `AssessPlanModal({ value, onChange, onClose })` — `{ assessment, plan }` textareas; shell serializes into `assessment_plan` on submit (`"Assessment:\n…\n\nPlan:\n…"`).
- `QueuePatientModal({ patient, onClose })` — department/room select → `POST /queue/` (reuse). `clinical:write`.
- `MyAppointmentsModal({ onClose })` — `GET /appointments/?doctor_id=<me>` read-only list.
- `PickAdmissionModal({ onPick, onClose })` — `GET /wards/board`, list Occupied beds → `onPick({patient_id, patient_name})` loads into desk.

- [ ] One Vitest per modal (happy path with mocked `apiClient`/props).
- [ ] Commit per 2–3 modals: `feat(clinical-desk): <modals> action modals`

## Task 6: Frontend — report templates (Lab, Theatre) + BP Trend wiring

**Files:** Modify `frontend/src/utils/printReports.js` — add `printLabReport({patient, tests})` and `printTheatreReport({patient, cases})` (same `printDocument` infra as existing report fns). BP Trend reuses `VitalsTrendsModal`.

- [ ] Extend `printReports.test.js`: both render patient + rows; empty-state line.
- [ ] Commit: `feat(clinical-desk): Lab & Theatre printable reports from the desk`

## Task 7: Frontend — `PatientDetailsHeader` (collapsible demographics + consultation queue table + search)

**Files:** Create `frontend/src/pages/clinical/PatientDetailsHeader.jsx` (+ test).

**Interfaces — Consumes:** `patient`, `queue` (from `/clinical/queue`), `onSelectPatient(item)`, `onSearchSelect(p)`. **Produces:** collapsible header; left demographics (OPD, Name, Age/Sex, Residence, Occupation, No. of Visits, Scheme, Rem. Credit, Allergies rose, Note); right queue table columns Q.No·OPD·Name·From·Mins (Mins = now−created_at), row click → `onSelectPatient`; `PatientSearch` + "View all patients" → `/app/patients`.

- [ ] Vitest: renders demographics + a queue row; row click fires `onSelectPatient`; collapse toggles.
- [ ] Commit: `feat(clinical-desk): DoctorV2 patient-details + queue header`

## Task 8: Frontend — `EncounterNotesTab` + `PatientHistoryTab`

**Files:** Create both under `frontend/src/pages/clinical/` (+ tests).

- `EncounterNotesTab` (controlled): Complaints (+chips), HPI (textarea), Physical Examination (textarea), Impressions (+chips), Diagnosis (`IcdDiagnosisPicker` + free text), Clinical Summary (textarea). Small read-only "vitals recorded / N meds" chips when present.
- `PatientHistoryTab`: the 6 history categories + Immunizations (reuse existing history add/list logic from today's `PatientHistoryModal`/toolbar), then Previous Visits table (`GET /clinical/records/{patient_id}` → Visit Id·Date·Note·Summary, row → Visit Summary print).

- [ ] Vitest per tab (fields controlled; add-complaint appends; previous-visits renders rows).
- [ ] Commit: `feat(clinical-desk): Encounter Notes + Patient History tabs`

## Task 9: Frontend — `ActionsMenu` + shell rewrite wiring it all together

**Files:** Create `frontend/src/pages/clinical/ActionsMenu.jsx` (+ test); rewrite `frontend/src/pages/ClinicalDesk.jsx` as the shell.

**ActionsMenu** `({ perms, onAction })`: grouped items (Clinical / Orders / Flow / Documents / Reports per spec), each gated on perms, emits an action key. Renders as a dropdown (portal, like ClinicalExtrasPanel modals).

**Shell** keeps ALL existing state + handlers (encounter state incl. new `assessPlan`; `handleClinicalSubmit` adding `assessment_plan`; draft safety-net incl. `assessPlan`; consent; queue fetch). Renders: `PageHeader` → `PatientDetailsHeader` → tabs (`EncounterNotesTab`/`PatientHistoryTab`) + `ActionsMenu` → footer submit buttons. Action keys open the matching modal (new ones from Tasks 4–5, existing ones reused: refer/lab/imaging/theatre/sick-note/consent/order-sets/external/admit/reports).

- [ ] Vitest: shell renders header+tabs+actions for an active patient; empty state without one; ActionsMenu hides ungranted items.
- [ ] Manual/driver screenshot both tabs + open Actions menu.
- [ ] Commit: `feat(clinical-desk): DoctorV2 shell — header + tabs + Actions menu`

## Task 10: Verify + promote

- [ ] `cd frontend && npx eslint src && npm run build && npx vitest run` (targeted) — 0 errors, green.
- [ ] Backend: live-server `pytest tests/test_clinical_files.py tests/test_assessment_plan.py` green; `python -c "import app.main"`; `alembic upgrade head` clean.
- [ ] react-doctor `--scope changed` — no new errors.
- [ ] Push branch; open PR → development; migration-check + audits green; merge.
- [ ] Promote development → beta (PR), then beta → main (PR); migration-check green at each; alembic at head before each promotion.

---

## Self-Review

**Spec coverage:** Layout/header/tabs (T7,T8,T9) ✓ · Actions inventory: existing reused in T9, new modals T4/T5, reports T6, BP trend T6 ✓ · clinical_files T1/T2/T4 ✓ · assessment_plan T1/T3/T5 ✓ · RBAC gating T9 ✓ · draft/consent/submit preserved T9 ✓ · promotion T10 ✓. No spec gaps.

**Placeholder scan:** No TBD/TODO; each task names files, interfaces, and test intent with representative code. (Per-modal bodies follow the cited existing patterns — `clinical_extras.py`, `ClinicalExtrasPanel.jsx`, `printReports.js` — rather than being re-transcribed in full.)

**Type consistency:** `assessment_plan` (Text, snake_case) consistent across model/migration/history/submit/AssessPlanModal serialization. `ClinicalFile` fields consistent across model/migration/routes/api. `PatientDetailsHeader` prop names consistent with shell usage.
