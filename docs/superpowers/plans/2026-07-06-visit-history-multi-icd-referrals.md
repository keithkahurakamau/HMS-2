# Visit History, Multi ICD-10 & Referral Letters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Doctors see every past visit with full detail, record multiple ICD-10 diagnoses per consultation, and print referral letters (typed, blank-with-patient-info, or fully blank).

**Architecture:** Three independent slices on one branch. (1) The medical-history chart drops its 10-visit cap and a new `GET /api/clinical/record/{record_id}` endpoint serves full encounter detail, rendered by an expandable `VisitHistoryList` component. (2) ICD-10 codes store comma-separated in the existing `icd10_code` String(255) column (no migration), edited via a new `IcdDiagnosisPicker` chips component. (3) The existing referrals API gets a Clinical Desk modal plus a `printReferralLetter` template with three print modes.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + Vite + Tailwind (frontend), pytest + httpx live-server tests, Vitest + RTL.

**Spec:** `docs/superpowers/specs/2026-07-06-visit-history-multi-icd-referral-letters-design.md`

## Global Constraints

- Branch: `feat/visit-history-multi-icd-referrals` (already created off `development`); PR targets `development` only.
- **No schema changes.** `icd10_code` stays `String(255)`; radiology visit-linking is best-effort by patient + same calendar day (no new FK). The `migration-check` gate must stay a no-op.
- Keep files under 500 lines — new UI goes in new component files, not into the 1700-line `ClinicalDesk.jsx`.
- Max **10** ICD codes per record; joined code string must fit 255 chars (server rejects longer with HTTP 400).
- ICD codes join with `", "`; diagnosis descriptions join with `"; "` (same convention as `complaints.join('; ')` already in ClinicalDesk).
- All printed output goes through `printDocument()` / `printUtils` in `frontend/src/utils/printDocument.js` — never `window.print()` directly.
- All HTML interpolation in print templates uses `esc()`/`orDash()` — patient data is untrusted.
- Backend tests run against a live server: `cd backend && REDIS_URL="" uvicorn app.main:app --port 8000` (empty REDIS_URL or slowapi 500s locally), tenant `mayoclinic_db`, fixtures from `backend/tests/conftest.py` (`doctor_cookies`, `receptionist_cookies`, …). `backend/tests/test_api.py` has ~34 pre-existing failures — never run it to judge this work; run only the files named in each task.
- Frontend: run `npx eslint <changed files>` before every commit of JSX (vite build misses no-undef).
- Commit messages end with `Co-Authored-By: RuFlo <ruv@ruv.net>`.

---

### Task 1: Backend — chart returns ALL visits (with ICD codes)

**Files:**
- Modify: `backend/app/routes/medical_history.py:107-134` (drop `.limit(10)`, add `icd10_code` to summary rows)
- Test: `backend/tests/test_visit_history.py` (new)

**Interfaces:**
- Consumes: existing `GET /api/medical-history/{patient_id}/chart` (permission `history:read`), `POST /api/clinical/submit`, `POST /api/medical-history/consent`.
- Produces: `chart.recent_visits` = **all** visits, newest first, each `{record_id, date, doctor, chief_complaint, diagnosis, icd10_code, record_status}`. Schema needs no change (`recent_visits: List[Dict[str, Any]]`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_visit_history.py`:

```python
"""
Visit history integration tests.

Covers:
  - /api/medical-history/{pid}/chart returns ALL visits (no 10-row cap) with icd10_code
  - /api/clinical/record/{record_id} full-detail endpoint (Task 2)
  - multi-code icd10 round-trip + oversize rejection (Task 3)
"""
from __future__ import annotations

import uuid

import pytest
import httpx

BASE = "http://localhost:8000"
TENANT = "mayoclinic_db"
HEADERS = {"X-Tenant-ID": TENANT}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True, timeout=30) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    client.cookies.update(cookies)
    r = client.post("/api/patients/", json={
        "surname": f"ZZ_VHIST_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Visit History", "sex": "Male",
        "date_of_birth": "1980-03-03", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def _consent(client, cookies, pid):
    client.cookies.update(cookies)
    r = client.post("/api/medical-history/consent", json={
        "patient_id": pid, "consent_type": "Treatment",
        "consent_given": True, "consent_method": "Verbal",
    })
    assert r.status_code == 200, r.text


def _submit_visit(client, cookies, pid, **overrides):
    client.cookies.update(cookies)
    payload = {
        "patient_id": pid, "record_status": "Completed",
        "chief_complaint": "cough", "diagnosis": "Acute bronchitis",
        "icd10_code": "J20.9",
    }
    payload.update(overrides)
    r = client.post("/api/clinical/submit", json=payload)
    assert r.status_code == 200, r.text


class TestChartAllVisits:
    def test_chart_returns_more_than_ten_visits(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            _consent(client, doctor_cookies, pid)
            for i in range(12):
                _submit_visit(client, doctor_cookies, pid,
                              chief_complaint=f"complaint {i}")

            chart = client.get(f"/api/medical-history/{pid}/chart")
            assert chart.status_code == 200, chart.text
            visits = chart.json()["recent_visits"]
            assert len(visits) == 12, f"expected all 12 visits, got {len(visits)}"
            assert visits[0]["icd10_code"] == "J20.9"
            # newest first
            assert visits[0]["chief_complaint"] == "complaint 11"
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_visit_history.py::TestChartAllVisits -v`
Expected: FAIL — `expected all 12 visits, got 10` (and/or KeyError on `icd10_code`).
(If the server isn't running: `REDIS_URL="" uvicorn app.main:app --port 8000 &` first.)

- [ ] **Step 3: Implement**

In `backend/app/routes/medical_history.py` change the records query (currently lines 107-110):

```python
    # Fetch all clinical visits (client requirement: doctors need the full
    # visit history, not a recent slice). Rows are summary-weight; full
    # detail loads lazily via GET /api/clinical/record/{record_id}.
    recent_records = db.query(MedicalRecord).filter(
        MedicalRecord.patient_id == patient_id
    ).order_by(desc(MedicalRecord.created_at)).all()
```

And add `icd10_code` to each summary dict (currently lines 127-134):

```python
        recent_visits.append({
            "record_id": rec.record_id,
            "date": rec.created_at.isoformat() if rec.created_at else None,
            "doctor": names.get(rec.doctor_id, "Unknown"),
            "chief_complaint": rec.chief_complaint,
            "diagnosis": rec.diagnosis,
            "icd10_code": rec.icd10_code,
            "record_status": rec.record_status
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_visit_history.py::TestChartAllVisits -v`
Expected: PASS

- [ ] **Step 5: Regression check + commit**

Run: `cd backend && python -m pytest tests/test_medical_history_triage.py -v` — Expected: PASS

```bash
git add backend/app/routes/medical_history.py backend/tests/test_visit_history.py
git commit -m "feat(history): chart returns full visit history with ICD codes

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 2: Backend — full visit-detail endpoint

**Files:**
- Modify: `backend/app/routes/clinical.py` (new endpoint after `get_patient_history`, ~line 168; new imports at top)
- Test: `backend/tests/test_visit_history.py` (extend)

**Interfaces:**
- Consumes: `_parse_prescriptions(treatment_plan)` (same file, line 220), `SENSITIVE_DATA_RESTRICTED_ROLES` + `_log_data_access` from `app.routes.medical_history`, `LabTest` (`app.models.laboratory`), `RadiologyRequest` (`app.models.radiology`).
- Produces: `GET /api/clinical/record/{record_id}` (permission `history:read`) →

```json
{
  "record_id": 51, "date": "2026-07-06T09:00:00+00:00", "doctor": "Dr Full Name",
  "record_status": "Completed",
  "vitals": {"blood_pressure": "120/80", "heart_rate": 72, "respiratory_rate": 16,
             "temperature": 36.8, "spo2": 98, "weight_kg": 70.0, "height_cm": 175.0,
             "calculated_bmi": 22.9, "blood_glucose": 5.4},
  "chief_complaint": "cough", "history_of_present_illness": "…",
  "review_of_systems": {}, "physical_examination": "…",
  "icd10_codes": ["J20.9", "E11.9"], "diagnosis": "Acute bronchitis; T2DM",
  "prescriptions": [{"drug": "…", "formulation": "…", "dosage": "…", "frequency": "…", "duration": "…"}],
  "prescription_notes": null, "follow_up_date": null,
  "internal_notes": "…only when caller's role is clinical…",
  "lab_tests": [{"test_id": 1, "test_name": "FBC", "status": "Completed", "result_summary": "…"}],
  "radiology": [{"request_id": 1, "exam_type": "Chest X-Ray", "status": "Pending", "conclusion": null}]
}
```
`prescriptions` is `[]` (not the "See Doctor Notes" placeholder) when `treatment_plan` is empty. `internal_notes` key is present only for non-restricted roles.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_visit_history.py`:

```python
class TestVisitDetail:
    def _make_visit(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        _consent(client, doctor_cookies, pid)
        _submit_visit(
            client, doctor_cookies, pid,
            icd10_code="J20.9, E11.9",
            diagnosis="Acute bronchitis; Type 2 diabetes",
            history_of_present_illness="Productive cough for 3 days",
            blood_pressure="120/80", heart_rate=72,
            treatment_plan='[{"drug":"Amoxicillin","formulation":"caps","dosage":"500mg","frequency":"8h","duration":"5d"}]',
            internal_notes="internal only",
        )
        client.cookies.update(doctor_cookies)
        chart = client.get(f"/api/medical-history/{pid}/chart")
        record_id = chart.json()["recent_visits"][0]["record_id"]
        return pid, record_id

    def test_requires_auth(self):
        # Fresh anonymous client — do NOT clear cookies on the shared module
        # client, that would drop its csrf_token and break later POSTs.
        with httpx.Client(base_url=BASE, headers=HEADERS) as anon:
            r = anon.get("/api/clinical/record/1")
            assert r.status_code == 401

    def test_full_detail(self, client, receptionist_cookies, doctor_cookies):
        pid, record_id = self._make_visit(client, receptionist_cookies, doctor_cookies)
        try:
            r = client.get(f"/api/clinical/record/{record_id}")
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["icd10_codes"] == ["J20.9", "E11.9"]
            assert d["vitals"]["blood_pressure"] == "120/80"
            assert d["vitals"]["heart_rate"] == 72
            assert d["history_of_present_illness"] == "Productive cough for 3 days"
            assert d["prescriptions"][0]["drug"] == "Amoxicillin"
            assert d["doctor"] and d["doctor"] != "Unknown"
            assert isinstance(d["lab_tests"], list)
            assert isinstance(d["radiology"], list)
            # doctor is a clinical role → sees internal notes
            assert d["internal_notes"] == "internal only"
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")

    def test_not_found(self, client, doctor_cookies):
        client.cookies.update(doctor_cookies)
        r = client.get("/api/clinical/record/99999999")
        assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_visit_history.py::TestVisitDetail -v`
Expected: FAIL — 404/405 on `/api/clinical/record/...` (route doesn't exist; FastAPI returns 404 "Not Found").

- [ ] **Step 3: Implement the endpoint**

In `backend/app/routes/clinical.py`, extend the model imports at the top:

```python
from app.models.laboratory import LabTest
from app.models.radiology import RadiologyRequest
```

Insert after `get_patient_history` (after line 167):

```python
@router.get("/record/{record_id}", dependencies=[Depends(RequirePermission("history:read"))])
def get_visit_detail(record_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Full detail for one clinical visit — everything the doctor did.

    Backs the expandable rows in the Medical History visit list. Access is
    KDPA-logged like the chart itself; internal notes are withheld from
    non-clinical roles.
    """
    from app.routes.medical_history import SENSITIVE_DATA_RESTRICTED_ROLES, _log_data_access

    rec = db.query(MedicalRecord).filter(MedicalRecord.record_id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Medical record not found.")

    _log_data_access(
        db, current_user["user_id"], rec.patient_id,
        str(request.client.host if request.client else "unknown"),
        f"Visit detail #{record_id} accessed by {current_user['role']} ({current_user['full_name']})",
    )

    doctor = db.query(User).filter(User.user_id == rec.doctor_id).first()

    labs = db.query(LabTest).filter(LabTest.record_id == record_id).all()

    # RadiologyRequest has no record FK — best-effort match: same patient,
    # same calendar day as the visit.
    rads = []
    if rec.created_at is not None:
        rads = db.query(RadiologyRequest).filter(
            RadiologyRequest.patient_id == rec.patient_id,
            func.date(RadiologyRequest.created_at) == rec.created_at.date(),
        ).all()

    codes = [c.strip() for c in (rec.icd10_code or "").split(",") if c.strip()]

    detail = {
        "record_id": rec.record_id,
        "date": rec.created_at.isoformat() if rec.created_at else None,
        "doctor": doctor.full_name if doctor else "Unknown",
        "record_status": rec.record_status,
        "vitals": {
            "blood_pressure": rec.blood_pressure,
            "heart_rate": rec.heart_rate,
            "respiratory_rate": rec.respiratory_rate,
            "temperature": rec.temperature,
            "spo2": rec.spo2,
            "weight_kg": rec.weight_kg,
            "height_cm": rec.height_cm,
            "calculated_bmi": rec.calculated_bmi,
            "blood_glucose": rec.blood_glucose,
        },
        "chief_complaint": rec.chief_complaint,
        "history_of_present_illness": rec.history_of_present_illness,
        "review_of_systems": rec.review_of_systems,
        "physical_examination": rec.physical_examination,
        "icd10_codes": codes,
        "diagnosis": rec.diagnosis,
        "prescriptions": _parse_prescriptions(rec.treatment_plan) if rec.treatment_plan else [],
        "prescription_notes": rec.prescription_notes,
        "follow_up_date": rec.follow_up_date.isoformat() if rec.follow_up_date else None,
        "lab_tests": [
            {"test_id": t.test_id, "test_name": t.test_name, "status": t.status,
             "result_summary": t.result_summary}
            for t in labs
        ],
        "radiology": [
            {"request_id": r.request_id, "exam_type": r.exam_type, "status": r.status,
             "conclusion": r.result.conclusion if r.result else None}
            for r in rads
        ],
    }
    if current_user["role"] not in SENSITIVE_DATA_RESTRICTED_ROLES:
        detail["internal_notes"] = rec.internal_notes

    db.commit()  # persist the data-access log row
    return detail
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_visit_history.py -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/clinical.py backend/tests/test_visit_history.py
git commit -m "feat(clinical): full visit-detail endpoint for history expansion

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 3: Backend — accept & guard multi-code ICD strings on submit

**Files:**
- Modify: `backend/app/routes/clinical.py:91-100` (guard at top of `submit_consultation`, **before** the `try:` block — HTTPExceptions raised inside it get swallowed into a generic 400)
- Test: `backend/tests/test_visit_history.py` (extend)

**Interfaces:**
- Consumes: `POST /api/clinical/submit` (existing).
- Produces: submits with `icd10_code` longer than 255 chars are rejected with HTTP 400 `detail="Too many ICD-10 diagnoses — the combined code list exceeds 255 characters (about 10 codes)."`. Valid comma-lists round-trip unchanged (already proven by Task 2's `test_full_detail`).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_visit_history.py`:

```python
class TestMultiIcdGuard:
    def test_oversize_icd_list_rejected(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            _consent(client, doctor_cookies, pid)
            client.cookies.update(doctor_cookies)
            too_long = ", ".join(f"Z{i:02d}.{i%10}XX" for i in range(40))  # > 255 chars
            r = client.post("/api/clinical/submit", json={
                "patient_id": pid, "record_status": "Draft",
                "icd10_code": too_long, "diagnosis": "x",
            })
            assert r.status_code == 400, r.text
            assert "ICD-10" in r.json()["detail"]
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")


class TestReferralApi:
    """Sanity checks on the existing referrals API the new modal depends on."""

    def test_create_requires_specialty_and_reason(self, client, doctor_cookies):
        client.cookies.update(doctor_cookies)
        r = client.post("/api/referrals/", json={"patient_id": 1, "specialty": "", "reason": ""})
        assert r.status_code == 422  # Pydantic min_length=1

    def test_create_and_serialize(self, client, receptionist_cookies, doctor_cookies):
        patient = _new_patient(client, receptionist_cookies)
        pid = patient["patient_id"]
        try:
            client.cookies.update(doctor_cookies)
            r = client.post("/api/referrals/", json={
                "patient_id": pid, "specialty": "Cardiology",
                "reason": "Suspected arrhythmia", "urgency": "Urgent",
                "target_facility": "KNH",
            })
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["specialty"] == "Cardiology"
            assert body["status"] == "Pending"
            assert body["doctor_name"], body
            assert body["patient_opd"], body
        finally:
            client.cookies.update(receptionist_cookies)
            client.delete(f"/api/patients/{pid}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_visit_history.py::TestMultiIcdGuard -v`
Expected: FAIL — status 400 arrives but with the generic `Failed to save clinical record: …` DataError text, so the `"ICD-10" in detail` assertion fails. (If Postgres silently truncates instead, the status is 200 — either way the test fails.)

- [ ] **Step 3: Implement the guard**

In `submit_consultation`, insert right after the docstring, before `try:`:

```python
    # Multiple diagnoses arrive comma-separated in one string (schema-compatible
    # multi-ICD). Guard the column limit with a readable error instead of a
    # DataError from the driver.
    icd = record_in.get("icd10_code")
    if icd and len(icd) > 255:
        raise HTTPException(
            status_code=400,
            detail="Too many ICD-10 diagnoses — the combined code list exceeds 255 characters (about 10 codes).",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_visit_history.py tests/test_clinical_blood_glucose.py -v`
Expected: PASS (including the blood-glucose regression file, which also exercises `/clinical/submit`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/clinical.py backend/tests/test_visit_history.py
git commit -m "feat(clinical): readable 400 for oversize multi-ICD code lists

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 4: Frontend — IcdDiagnosisPicker chips component + Clinical Desk integration

**Files:**
- Create: `frontend/src/components/IcdDiagnosisPicker.jsx`
- Create: `frontend/src/components/IcdDiagnosisPicker.test.jsx`
- Modify: `frontend/src/pages/ClinicalDesk.jsx` (state ~lines 51-113, `validateForSubmit` line 290, submit payload lines 349-350, JSX lines 653-668)

**Interfaces:**
- Consumes: `GET /clinical/icd10/search?q=` via `apiClient` → `[{code, description}]`.
- Produces: `<IcdDiagnosisPicker codes={codes} onChange={setCodes} />` where `codes` is `[{code: "E11.9", description: "Type 2 diabetes…"}]`, capped at 10, first entry is primary. ClinicalDesk submits `icd10_code: codes.map(c => c.code).join(', ')` and `diagnosis: clinicalNotes.diagnosis || codes.map(c => c.description).join('; ')`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/IcdDiagnosisPicker.test.jsx` (mock style copied from `frontend/src/pages/Pharmacy.test.jsx`):

```jsx
import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

import { apiClient } from '../api/client';
import IcdDiagnosisPicker from './IcdDiagnosisPicker';

const RESULTS = [
    { code: 'E11.9', description: 'Type 2 diabetes mellitus without complications' },
    { code: 'E11.2', description: 'Type 2 diabetes mellitus with kidney complications' },
];

function Harness({ initial = [] }) {
    const [codes, setCodes] = useState(initial);
    return <IcdDiagnosisPicker codes={codes} onChange={setCodes} />;
}

beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockResolvedValue({ data: RESULTS });
});

describe('IcdDiagnosisPicker', () => {
    it('adds a chip when a search result is picked, and clears the input', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(
            '/clinical/icd10/search', { params: { q: 'E11' } }));
        // Match the dropdown row by its description — /E11\.9/ alone would
        // also match a chip's "Remove diagnosis E11.9" button.
        await user.click(await screen.findByRole('button', { name: /without complications/i }));
        expect(screen.getByText('E11.9')).toBeInTheDocument();
        expect(screen.getByText(/primary/i)).toBeInTheDocument();
        expect(input).toHaveValue('');
    });

    it('marks only the first chip as primary and removes chips', async () => {
        const user = userEvent.setup();
        render(<Harness initial={[
            { code: 'E11.9', description: 'T2DM' },
            { code: 'I10', description: 'Hypertension' },
        ]} />);
        expect(screen.getAllByText(/primary/i)).toHaveLength(1);
        await user.click(screen.getByRole('button', { name: /remove diagnosis E11\.9/i }));
        expect(screen.queryByText('E11.9')).not.toBeInTheDocument();
        // I10 promoted to primary
        expect(screen.getByText(/primary/i)).toBeInTheDocument();
    });

    it('ignores duplicate codes', async () => {
        const user = userEvent.setup();
        render(<Harness initial={[{ code: 'E11.9', description: 'T2DM' }]} />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await user.click(await screen.findByRole('button', { name: /without complications/i }));
        expect(screen.getAllByText('E11.9')).toHaveLength(1);
    });

    it('blocks an 11th code with a hint', async () => {
        const user = userEvent.setup();
        const ten = Array.from({ length: 10 }, (_, i) => ({ code: `A0${i}`, description: `Dx ${i}` }));
        render(<Harness initial={ten} />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await user.click(await screen.findByRole('button', { name: /without complications/i }));
        expect(screen.queryByText('E11.9')).not.toBeInTheDocument();
        expect(screen.getByText(/maximum of 10/i)).toBeInTheDocument();
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/IcdDiagnosisPicker.test.jsx`
Expected: FAIL — cannot resolve `./IcdDiagnosisPicker`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/IcdDiagnosisPicker.jsx`:

```jsx
import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { apiClient } from '../api/client';

const MAX_CODES = 10;

/**
 * Multi-select ICD-10 picker. Type-ahead against /clinical/icd10/search;
 * each pick becomes a removable chip. The first chip is the primary
 * diagnosis. Parent owns the list via `codes` / `onChange`.
 */
export default function IcdDiagnosisPicker({ codes, onChange }) {
    const [search, setSearch] = useState('');
    const [results, setResults] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [limitHit, setLimitHit] = useState(false);

    useEffect(() => {
        if (!showDropdown || search.trim().length < 2) {
            setResults([]);
            return;
        }
        const timer = setTimeout(async () => {
            try {
                const res = await apiClient.get('/clinical/icd10/search', { params: { q: search } });
                setResults(res.data || []);
            } catch {
                setResults([]);
            }
        }, 250);
        return () => clearTimeout(timer);
    }, [search, showDropdown]);

    const addCode = (r) => {
        setShowDropdown(false);
        setSearch('');
        if (codes.some((c) => c.code === r.code)) return;
        if (codes.length >= MAX_CODES) {
            setLimitHit(true);
            return;
        }
        setLimitHit(false);
        onChange([...codes, { code: r.code, description: r.description }]);
    };

    const removeCode = (code) => {
        setLimitHit(false);
        onChange(codes.filter((c) => c.code !== code));
    };

    return (
        <div className="relative">
            <label htmlFor="clinic-diagnoses-icd-10" className="label">Diagnoses (ICD-10)</label>
            <input
                id="clinic-diagnoses-icd-10"
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setShowDropdown(true); }}
                onFocus={() => setShowDropdown(true)}
                className="input"
                placeholder="Type to search ICD-10 codes — add as many as apply…"
            />
            {showDropdown && search.trim().length >= 2 && (
                <div className="absolute z-30 w-full mt-1 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-xl shadow-elevated max-h-48 overflow-y-auto custom-scrollbar">
                    {results.length > 0 ? results.map((r) => (
                        <button
                            type="button"
                            key={r.code}
                            onClick={() => addCode(r)}
                            className="block w-full text-left px-4 py-2 hover:bg-brand-50 dark:hover:bg-brand-500/15 text-sm dark:text-ink-200"
                        >
                            <span className="font-mono font-semibold">{r.code}</span> — {r.description}
                        </button>
                    )) : <div className="px-4 py-3 text-sm text-ink-500 dark:text-ink-400">No codes found.</div>}
                </div>
            )}
            {limitHit && (
                <p className="text-xs text-rose-600 dark:text-rose-400 mt-1">Maximum of 10 diagnoses per visit.</p>
            )}
            {codes.length > 0 && (
                <ul className="flex flex-wrap gap-2 mt-2">
                    {codes.map((c, idx) => (
                        <li key={c.code} className="flex items-center gap-2 pl-2 pr-1 py-1 rounded-lg border border-brand-200 dark:border-brand-500/30 bg-brand-50 dark:bg-brand-500/10 text-xs text-brand-800 dark:text-brand-200 max-w-full">
                            <span className="font-mono font-semibold shrink-0">{c.code}</span>
                            <span className="truncate" title={c.description}>{c.description}</span>
                            {idx === 0 && (
                                <span className="shrink-0 px-1.5 py-0.5 rounded bg-brand-600 text-white text-2xs font-semibold uppercase tracking-wide">Primary</span>
                            )}
                            <button
                                type="button"
                                onClick={() => removeCode(c.code)}
                                aria-label={`Remove diagnosis ${c.code}`}
                                className="text-brand-400 hover:text-rose-600 shrink-0"
                            >
                                <X size={13} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/IcdDiagnosisPicker.test.jsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Integrate into ClinicalDesk**

In `frontend/src/pages/ClinicalDesk.jsx`:

1. Import: `import IcdDiagnosisPicker from '../components/IcdDiagnosisPicker';`
2. Replace the ICD state block (`icdSearch`, `icdResults`, `showIcdDropdown` at ~lines 51-56 and the debounce effect at ~lines 96-113) with a single `const [icdCodes, setIcdCodes] = useState([]);`. **Before deleting, run `grep -n "icdSearch\|setIcdSearch\|icdResults\|showIcdDropdown" src/pages/ClinicalDesk.jsx` and update every hit** — notably:
   - `validateForSubmit` line 290: `const hasDx = ((clinicalNotes.diagnosis || '').trim().length > 0) || icdCodes.length > 0;`
   - submit payload lines 349-350:
     ```js
     diagnosis: clinicalNotes.diagnosis || icdCodes.map((c) => c.description).join('; '),
     icd10_code: icdCodes.map((c) => c.code).join(', '),
     ```
   - any reset site (e.g. where the workspace clears after submit / patient switch): `setIcdCodes([])` wherever `setIcdSearch('')` appeared.
3. Replace the JSX block at lines 653-668 (`<div className="relative">…final diagnosis input + dropdown…</div>`) with:
   ```jsx
   <IcdDiagnosisPicker codes={icdCodes} onChange={setIcdCodes} />
   ```

- [ ] **Step 6: Verify + commit**

Run: `cd frontend && npx eslint src/components/IcdDiagnosisPicker.jsx src/components/IcdDiagnosisPicker.test.jsx src/pages/ClinicalDesk.jsx && npx vitest run && npm run build`
Expected: eslint clean, all Vitest suites pass, build succeeds.

```bash
git add frontend/src/components/IcdDiagnosisPicker.jsx frontend/src/components/IcdDiagnosisPicker.test.jsx frontend/src/pages/ClinicalDesk.jsx
git commit -m "feat(clinical): multiple ICD-10 diagnoses via chips picker

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 5: Frontend — expandable VisitHistoryList in Medical History

**Files:**
- Create: `frontend/src/components/VisitHistoryList.jsx`
- Create: `frontend/src/components/VisitHistoryList.test.jsx`
- Modify: `frontend/src/pages/MedicalHistory.jsx:417-439` (replace the "Recent Clinical Visits" card body)

**Interfaces:**
- Consumes: `GET /clinical/record/{record_id}` (Task 2 shape), visit summary rows from `chart.recent_visits` (Task 1 shape).
- Produces: `<VisitHistoryList visits={chart.recent_visits || []} />` — self-contained card section: header "Visit History (N)", accordion rows, lazy detail fetch with per-row cache, inline error + retry.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/VisitHistoryList.test.jsx`:

```jsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

import { apiClient } from '../api/client';
import VisitHistoryList from './VisitHistoryList';

const VISITS = [
    { record_id: 51, date: '2026-07-01T09:00:00Z', doctor: 'Dr. Otieno',
      chief_complaint: 'cough', diagnosis: 'Acute bronchitis', icd10_code: 'J20.9', record_status: 'Completed' },
    { record_id: 40, date: '2026-05-11T10:00:00Z', doctor: 'Dr. Wanjiru',
      chief_complaint: 'headache', diagnosis: 'Migraine', icd10_code: 'G43.9', record_status: 'Completed' },
];

const DETAIL = {
    record_id: 51, date: '2026-07-01T09:00:00Z', doctor: 'Dr. Otieno', record_status: 'Completed',
    vitals: { blood_pressure: '120/80', heart_rate: 72, respiratory_rate: null, temperature: 36.8,
              spo2: 98, weight_kg: 70, height_cm: 175, calculated_bmi: 22.9, blood_glucose: null },
    chief_complaint: 'cough', history_of_present_illness: 'Productive cough for 3 days',
    review_of_systems: null, physical_examination: 'Chest clear',
    icd10_codes: ['J20.9', 'E11.9'], diagnosis: 'Acute bronchitis; T2DM',
    prescriptions: [{ drug: 'Amoxicillin', formulation: 'caps', dosage: '500mg', frequency: '8h', duration: '5d' }],
    prescription_notes: null, follow_up_date: null, internal_notes: 'watch sugar',
    lab_tests: [{ test_id: 1, test_name: 'FBC', status: 'Completed', result_summary: 'Normal' }],
    radiology: [{ request_id: 3, exam_type: 'Chest X-Ray', status: 'Completed', conclusion: 'Clear' }],
};

beforeEach(() => vi.clearAllMocks());

describe('VisitHistoryList', () => {
    it('lists every visit summary', () => {
        render(<VisitHistoryList visits={VISITS} />);
        expect(screen.getByText(/visit history \(2\)/i)).toBeInTheDocument();
        expect(screen.getByText('Acute bronchitis')).toBeInTheDocument();
        expect(screen.getByText('Migraine')).toBeInTheDocument();
    });

    it('fetches and renders full detail on expand, once', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: DETAIL });
        render(<VisitHistoryList visits={VISITS} />);
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/clinical/record/51'));
        expect(await screen.findByText('120/80')).toBeInTheDocument();
        expect(screen.getByText('Productive cough for 3 days')).toBeInTheDocument();
        expect(screen.getByText('Amoxicillin')).toBeInTheDocument();
        expect(screen.getByText('FBC')).toBeInTheDocument();
        expect(screen.getByText('Chest X-Ray')).toBeInTheDocument();
        expect(screen.getByText('E11.9')).toBeInTheDocument();
        // collapse + re-expand must not refetch
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        expect(apiClient.get).toHaveBeenCalledTimes(1);
    });

    it('shows an inline error with retry when the fetch fails', async () => {
        const user = userEvent.setup();
        apiClient.get.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({ data: DETAIL });
        render(<VisitHistoryList visits={VISITS} />);
        await user.click(screen.getByRole('button', { name: /acute bronchitis/i }));
        expect(await screen.findByText(/could not load/i)).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: /retry/i }));
        expect(await screen.findByText('120/80')).toBeInTheDocument();
    });

    it('renders the empty state', () => {
        render(<VisitHistoryList visits={[]} />);
        expect(screen.getByText(/no clinical visits recorded/i)).toBeInTheDocument();
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/VisitHistoryList.test.jsx`
Expected: FAIL — cannot resolve `./VisitHistoryList`.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/VisitHistoryList.jsx`:

```jsx
import React, { useState } from 'react';
import { Clock, ChevronDown, ChevronRight, Pill, TestTube, Image as ImageIcon } from 'lucide-react';
import { apiClient } from '../api/client';

const VITAL_LABELS = [
    ['blood_pressure', 'BP'], ['heart_rate', 'HR'], ['respiratory_rate', 'RR'],
    ['temperature', 'Temp °C'], ['spo2', 'SpO2 %'], ['weight_kg', 'Weight kg'],
    ['height_cm', 'Height cm'], ['calculated_bmi', 'BMI'], ['blood_glucose', 'RBS mmol/L'],
];

function Section({ title, children }) {
    return (
        <div>
            <h5 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400 mb-1">{title}</h5>
            {children}
        </div>
    );
}

/**
 * Full clinic visit history. Summary rows come from the chart payload
 * (all visits); expanding a row lazy-loads /clinical/record/{id} once
 * and caches it for the life of the page.
 */
export default function VisitHistoryList({ visits }) {
    const [openId, setOpenId] = useState(null);
    const [details, setDetails] = useState({});   // record_id -> detail
    const [loadingId, setLoadingId] = useState(null);
    const [errorId, setErrorId] = useState(null);

    const fetchDetail = async (recordId) => {
        setLoadingId(recordId);
        setErrorId(null);
        try {
            const res = await apiClient.get(`/clinical/record/${recordId}`);
            setDetails((prev) => ({ ...prev, [recordId]: res.data }));
        } catch {
            setErrorId(recordId);
        } finally {
            setLoadingId(null);
        }
    };

    const toggle = (recordId) => {
        const next = openId === recordId ? null : recordId;
        setOpenId(next);
        if (next && !details[next]) fetchDetail(next);
    };

    return (
        <div className="bg-white dark:bg-ink-900 border border-slate-200 dark:border-ink-800 rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40">
                <h3 className="font-bold text-slate-800 dark:text-ink-200 flex items-center gap-2">
                    <Clock size={16} /> Visit History ({visits.length})
                </h3>
            </div>
            <div className="p-4 space-y-2 max-h-[32rem] overflow-y-auto custom-scrollbar">
                {visits.length === 0 ? (
                    <p className="text-sm text-slate-400 dark:text-ink-400 italic text-center py-4">No clinical visits recorded.</p>
                ) : visits.map((visit) => {
                    const isOpen = openId === visit.record_id;
                    const detail = details[visit.record_id];
                    return (
                        <div key={visit.record_id} className="rounded-xl border border-slate-100 dark:border-ink-800 overflow-hidden">
                            <button
                                type="button"
                                onClick={() => toggle(visit.record_id)}
                                aria-expanded={isOpen}
                                className="w-full flex gap-3 items-start p-3 bg-slate-50 dark:bg-ink-800/40 text-left hover:bg-slate-100 dark:hover:bg-ink-800/70"
                            >
                                {isOpen ? <ChevronDown size={15} className="mt-0.5 shrink-0" /> : <ChevronRight size={15} className="mt-0.5 shrink-0" />}
                                <span className="flex-1 min-w-0">
                                    <span className="flex justify-between items-start gap-2">
                                        <span className="font-bold text-sm text-slate-800 dark:text-ink-200 truncate">{visit.diagnosis || 'No diagnosis recorded'}</span>
                                        <span className="text-xs text-slate-400 dark:text-ink-400 shrink-0">{visit.date ? new Date(visit.date).toLocaleDateString() : '—'}</span>
                                    </span>
                                    <span className="block text-xs text-slate-500 dark:text-ink-400 mt-0.5">
                                        <span className="font-medium">Complaint:</span> {visit.chief_complaint || '—'} · <span className="font-medium">Dr:</span> {visit.doctor}
                                    </span>
                                </span>
                            </button>

                            {isOpen && (
                                <div className="p-4 space-y-4 border-t border-slate-100 dark:border-ink-800">
                                    {loadingId === visit.record_id && (
                                        <p className="text-sm text-slate-400 dark:text-ink-400 italic">Loading visit details…</p>
                                    )}
                                    {errorId === visit.record_id && (
                                        <p className="text-sm text-rose-600 dark:text-rose-400">
                                            Could not load this visit.{' '}
                                            <button type="button" className="underline font-medium" onClick={() => fetchDetail(visit.record_id)}>Retry</button>
                                        </p>
                                    )}
                                    {detail && (
                                        <>
                                            <Section title="Vitals">
                                                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                                                    {VITAL_LABELS.map(([key, label]) => (
                                                        <div key={key} className="rounded-lg bg-slate-50 dark:bg-ink-800/40 p-2">
                                                            <p className="text-2xs text-slate-400 dark:text-ink-400">{label}</p>
                                                            <p className="text-sm font-semibold text-slate-800 dark:text-ink-200">{detail.vitals?.[key] ?? '—'}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </Section>
                                            {detail.history_of_present_illness && (
                                                <Section title="History of present illness">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.history_of_present_illness}</p>
                                                </Section>
                                            )}
                                            {detail.physical_examination && (
                                                <Section title="Physical examination">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.physical_examination}</p>
                                                </Section>
                                            )}
                                            <Section title="Diagnoses">
                                                {detail.icd10_codes?.length ? (
                                                    <ul className="flex flex-wrap gap-1.5">
                                                        {detail.icd10_codes.map((code) => (
                                                            <li key={code} className="px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/30 font-mono text-xs font-semibold text-brand-800 dark:text-brand-200">{code}</li>
                                                        ))}
                                                    </ul>
                                                ) : null}
                                                <p className="text-sm text-slate-700 dark:text-ink-300 mt-1">{detail.diagnosis || '—'}</p>
                                            </Section>
                                            {detail.prescriptions?.length > 0 && (
                                                <Section title="Prescriptions">
                                                    <ul className="space-y-1">
                                                        {detail.prescriptions.map((p, i) => (
                                                            <li key={i} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <Pill size={13} className="text-accent-600 dark:text-accent-400 shrink-0" />
                                                                <span><span className="font-semibold">{p.drug}</span> {p.formulation} — {p.dosage}, {p.frequency}, {p.duration}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.lab_tests?.length > 0 && (
                                                <Section title="Lab tests">
                                                    <ul className="space-y-1">
                                                        {detail.lab_tests.map((t) => (
                                                            <li key={t.test_id} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <TestTube size={13} className="text-brand-600 dark:text-brand-400 shrink-0" />
                                                                <span><span className="font-semibold">{t.test_name}</span> · {t.status}{t.result_summary ? ` — ${t.result_summary}` : ''}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.radiology?.length > 0 && (
                                                <Section title="Imaging (same day)">
                                                    <ul className="space-y-1">
                                                        {detail.radiology.map((r) => (
                                                            <li key={r.request_id} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <ImageIcon size={13} className="text-brand-600 dark:text-brand-400 shrink-0" />
                                                                <span><span className="font-semibold">{r.exam_type}</span> · {r.status}{r.conclusion ? ` — ${r.conclusion}` : ''}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.internal_notes && (
                                                <Section title="Internal notes">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.internal_notes}</p>
                                                </Section>
                                            )}
                                            {detail.follow_up_date && (
                                                <p className="text-xs text-slate-500 dark:text-ink-400">Follow-up: {new Date(detail.follow_up_date).toLocaleDateString()}</p>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/VisitHistoryList.test.jsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Integrate into MedicalHistory.jsx**

Replace the whole "Recent Clinical Visits" block (`frontend/src/pages/MedicalHistory.jsx:417-439`, the `<div className="bg-white dark:bg-ink-900 …">…</div>` under the `{/* Recent Clinical Visits */}` comment) with:

```jsx
                        {/* Full visit history — every consultation, expandable to full detail */}
                        <VisitHistoryList visits={chart.recent_visits || []} />
```

Add the import: `import VisitHistoryList from '../components/VisitHistoryList';`

- [ ] **Step 6: Verify + commit**

Run: `cd frontend && npx eslint src/components/VisitHistoryList.jsx src/components/VisitHistoryList.test.jsx src/pages/MedicalHistory.jsx && npx vitest run && npm run build`
Expected: clean, pass, build OK.

```bash
git add frontend/src/components/VisitHistoryList.jsx frontend/src/components/VisitHistoryList.test.jsx frontend/src/pages/MedicalHistory.jsx
git commit -m "feat(history): full expandable visit history in Medical History

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 6: Frontend — referral letter print template (3 modes)

**Files:**
- Modify: `frontend/src/utils/printTemplates.js` (append `printReferralLetter` as section 8)
- Test: `frontend/src/utils/printTemplates.referral.test.js` (new)

**Interfaces:**
- Consumes: `printDocument(title, bodyHtml)` and `printUtils` (`esc`, `header`, `footer`) from `./printDocument`.
- Produces: `printReferralLetter({ mode, referral, patient, doctorName })` where `mode` ∈ `'typed' | 'blank-patient' | 'blank'`; `referral` = the serialized API referral (`specialty`, `target_facility`, `target_clinician`, `reason`, `clinical_summary`, `urgency`, `referral_id`); `patient` = `{ patient_name, age, gender, outpatient_no }` (Clinical Desk queue-row shape).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/utils/printTemplates.referral.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./printDocument', () => ({
    printDocument: vi.fn(),
    printUtils: {
        // Real escaping — the "escapes HTML" test depends on it.
        esc: (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'),
        hospital: () => 'Test Hospital',
        header: ({ docType, docNumber }) => `<div class="hdr">${docType} ${docNumber}</div>`,
        footer: (msg) => `<div class="ftr">${msg}</div>`,
    },
}));

import { printDocument } from './printDocument';
import { printReferralLetter } from './printTemplates';

const PATIENT = { patient_name: 'Asha Mwangi', age: 34, gender: 'F', outpatient_no: 'OP-2025-0001' };
const REFERRAL = {
    referral_id: 7, specialty: 'Cardiology', target_facility: 'KNH',
    target_clinician: 'Dr. Karanja', urgency: 'Urgent',
    reason: 'Suspected arrhythmia', clinical_summary: 'Palpitations for 2 weeks',
};

beforeEach(() => vi.clearAllMocks());

const lastBody = () => printDocument.mock.calls.at(-1)[1];

describe('printReferralLetter', () => {
    it('typed mode prints every referral field and the patient block', () => {
        printReferralLetter({ mode: 'typed', referral: REFERRAL, patient: PATIENT, doctorName: 'Dr. Otieno' });
        const body = lastBody();
        for (const text of ['Asha Mwangi', 'OP-2025-0001', 'Cardiology', 'KNH', 'Dr. Karanja',
                            'Urgent', 'Suspected arrhythmia', 'Palpitations for 2 weeks', 'Dr. Otieno']) {
            expect(body).toContain(text);
        }
    });

    it('blank-patient mode keeps patient identity but rules the clinical sections', () => {
        printReferralLetter({ mode: 'blank-patient', referral: {}, patient: PATIENT, doctorName: 'Dr. Otieno' });
        const body = lastBody();
        expect(body).toContain('Asha Mwangi');
        expect(body).not.toContain('Cardiology');
        expect(body).toContain('ruled-line');
    });

    it('fully blank mode has no patient data at all', () => {
        printReferralLetter({ mode: 'blank', referral: {}, patient: PATIENT, doctorName: '' });
        const body = lastBody();
        expect(body).not.toContain('Asha Mwangi');
        expect(body).not.toContain('OP-2025-0001');
        expect(body).toContain('ruled-line');
    });

    it('escapes HTML in referral fields', () => {
        printReferralLetter({
            mode: 'typed', patient: PATIENT, doctorName: 'Dr. O',
            referral: { ...REFERRAL, reason: '<script>alert(1)</script>' },
        });
        expect(lastBody()).not.toContain('<script>');
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/printTemplates.referral.test.js`
Expected: FAIL — `printReferralLetter` is not exported.

- [ ] **Step 3: Implement the template**

Append to `frontend/src/utils/printTemplates.js`:

```js
// =====================================================================
// 8. REFERRAL LETTER — typed | blank-patient | blank
// =====================================================================

// n ruled lines for handwriting on paper.
const ruledLines = (n) => Array.from({ length: n }, () =>
  '<div class="ruled-line" style="border-bottom:1px solid #94a3b8;height:24px;"></div>'
).join('');

export const printReferralLetter = ({ mode = 'typed', referral = {}, patient = {}, doctorName = '' }) => {
  const typed = mode === 'typed';
  const withPatient = mode !== 'blank';

  const field = (label, value, blankWidth = '60%') => `
    <div class="field">
      <div class="label">${esc(label)}</div>
      <div class="value">${
        value ? esc(value)
              : `<span class="ruled-line" style="display:inline-block;border-bottom:1px solid #94a3b8;width:${blankWidth};height:18px;"></span>`
      }</div>
    </div>`;

  const body = `
    ${header({ docType: 'Referral Letter', docNumber: typed && referral.referral_id ? `REF-${referral.referral_id}` : '—' })}

    <h1 class="doc-title">Referral Letter</h1>
    ${typed ? `<div class="doc-subtitle">Urgency: <span class="badge ${referral.urgency === 'Routine' ? 'paid' : 'pending'}">${esc(referral.urgency || 'Routine')}</span></div>`
            : `<div class="doc-subtitle">Urgency: &nbsp; ☐ Routine &nbsp; ☐ Urgent &nbsp; ☐ Emergency</div>`}

    <div class="panel">
      <h3>Patient</h3>
      <div class="grid-2">
        ${field('Name', withPatient ? patient.patient_name : null)}
        ${field('OP Number', withPatient ? patient.outpatient_no : null)}
        ${field('Age', withPatient ? patient.age : null, '40%')}
        ${field('Sex', withPatient ? patient.gender : null, '40%')}
      </div>
    </div>

    <div class="panel">
      <h3>Referred To</h3>
      <div class="grid-2">
        ${field('Specialty', typed ? referral.specialty : null)}
        ${field('Facility', typed ? referral.target_facility : null)}
        ${field('Clinician', typed ? referral.target_clinician : null)}
      </div>
    </div>

    <div class="panel">
      <h3>Reason for Referral</h3>
      ${typed && referral.reason ? `<p style="white-space:pre-wrap;">${esc(referral.reason)}</p>` : ruledLines(4)}
    </div>

    <div class="panel">
      <h3>Clinical Summary</h3>
      ${typed && referral.clinical_summary ? `<p style="white-space:pre-wrap;">${esc(referral.clinical_summary)}</p>` : ruledLines(6)}
    </div>

    <div class="signature-block">
      <div class="line">${doctorName ? `Referring Doctor: ${esc(doctorName)}` : 'Referring Doctor'}</div>
      <div class="line">Signature &amp; Date</div>
    </div>

    ${footer('Please attend to the referred patient at your earliest convenience.')}
  `;

  printDocument('Referral Letter', body);
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/printTemplates.referral.test.js`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd frontend && npx eslint src/utils/printTemplates.js src/utils/printTemplates.referral.test.js
git add frontend/src/utils/printTemplates.js frontend/src/utils/printTemplates.referral.test.js
git commit -m "feat(referrals): referral letter print template with typed and blank modes

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 7: Frontend — ReferralModal + wire "Refer patient"

**Files:**
- Create: `frontend/src/components/ReferralModal.jsx`
- Create: `frontend/src/components/ReferralModal.test.jsx`
- Modify: `frontend/src/pages/ClinicalDesk.jsx:799` (button) + modal render + state

**Interfaces:**
- Consumes: `POST /referrals/` (`{patient_id, record_id?, specialty, target_facility, target_clinician, reason, clinical_summary, urgency}` → serialized referral), `printReferralLetter` (Task 6), `useAuth()` from `../context/AuthContext` (`user.full_name`) — verify the hook's export name in `AuthContext.jsx` before importing; if only the context is exported, use `useContext(AuthContext)`.
- Produces: `<ReferralModal patient={activePatient} initialSummary={string} onClose={fn} />`. `patient` is the Clinical Desk queue row (`patient_id`, `patient_name`, `age`, `gender`, `outpatient_no`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ReferralModal.test.jsx`:

```jsx
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../utils/printTemplates', () => ({ printReferralLetter: vi.fn() }));
vi.mock('../context/AuthContext', () => ({
    useAuth: () => ({ user: { full_name: 'Dr. Otieno' } }),
}));

import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { printReferralLetter } from '../utils/printTemplates';
import ReferralModal from './ReferralModal';

const PATIENT = { patient_id: 11, patient_name: 'Asha Mwangi', age: 34, gender: 'F', outpatient_no: 'OP-2025-0001' };
const SAVED = { referral_id: 7, specialty: 'Cardiology', reason: 'Arrhythmia', urgency: 'Routine' };

beforeEach(() => {
    vi.clearAllMocks();
    apiClient.post.mockResolvedValue({ data: SAVED });
});

describe('ReferralModal', () => {
    it('requires specialty and reason before saving', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /save & print typed letter/i }));
        expect(apiClient.post).not.toHaveBeenCalled();
        expect(toast.error).toHaveBeenCalled();
    });

    it('saves then prints the typed letter', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="T2DM" onClose={() => {}} />);
        await user.type(screen.getByLabelText(/specialty/i), 'Cardiology');
        await user.type(screen.getByLabelText(/reason/i), 'Arrhythmia');
        await user.click(screen.getByRole('button', { name: /save & print typed letter/i }));
        await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith('/referrals/', expect.objectContaining({
            patient_id: 11, specialty: 'Cardiology', reason: 'Arrhythmia', clinical_summary: 'T2DM',
        })));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({
            mode: 'typed', referral: SAVED, doctorName: 'Dr. Otieno',
        }));
    });

    it('save-only does not print', async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={onClose} />);
        await user.type(screen.getByLabelText(/specialty/i), 'ENT');
        await user.type(screen.getByLabelText(/reason/i), 'Chronic sinusitis');
        await user.click(screen.getByRole('button', { name: /^save referral$/i }));
        await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
        expect(printReferralLetter).not.toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
    });

    it('blank prints never hit the API', async () => {
        const user = userEvent.setup();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={() => {}} />);
        await user.click(screen.getByRole('button', { name: /blank \(with patient info\)/i }));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({ mode: 'blank-patient', patient: PATIENT }));
        await user.click(screen.getByRole('button', { name: /fully blank/i }));
        expect(printReferralLetter).toHaveBeenCalledWith(expect.objectContaining({ mode: 'blank' }));
        expect(apiClient.post).not.toHaveBeenCalled();
    });

    it('keeps the modal open and shows the backend detail on save failure', async () => {
        const user = userEvent.setup();
        apiClient.post.mockRejectedValueOnce({ response: { data: { detail: 'Patient not found.' } } });
        const onClose = vi.fn();
        render(<ReferralModal patient={PATIENT} initialSummary="" onClose={onClose} />);
        await user.type(screen.getByLabelText(/specialty/i), 'ENT');
        await user.type(screen.getByLabelText(/reason/i), 'x');
        await user.click(screen.getByRole('button', { name: /^save referral$/i }));
        await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Patient not found.'));
        expect(onClose).not.toHaveBeenCalled();
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/ReferralModal.test.jsx`
Expected: FAIL — cannot resolve `./ReferralModal`.

- [ ] **Step 3: Implement the modal**

Create `frontend/src/components/ReferralModal.jsx`:

```jsx
import React, { useState } from 'react';
import { X, Printer, Save, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { printReferralLetter } from '../utils/printTemplates';

const URGENCIES = ['Routine', 'Urgent', 'Emergency'];

/**
 * External referral capture + letter printing. Typed letters require the
 * referral to be saved first (the referral log stays accurate); the two
 * blank modes only print — nothing is recorded.
 */
export default function ReferralModal({ patient, recordId = null, initialSummary = '', onClose }) {
    const { user } = useAuth();
    const doctorName = user?.full_name || '';
    const [form, setForm] = useState({
        specialty: '', target_facility: '', target_clinician: '',
        urgency: 'Routine', reason: '', clinical_summary: initialSummary,
    });
    const [isSaving, setIsSaving] = useState(false);

    const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

    const save = async () => {
        if (!form.specialty.trim() || !form.reason.trim()) {
            toast.error('Specialty and reason are required for a referral.');
            return null;
        }
        setIsSaving(true);
        try {
            const res = await apiClient.post('/referrals/', {
                patient_id: patient.patient_id,
                record_id: recordId,
                specialty: form.specialty.trim(),
                target_facility: form.target_facility.trim() || null,
                target_clinician: form.target_clinician.trim() || null,
                urgency: form.urgency,
                reason: form.reason.trim(),
                clinical_summary: form.clinical_summary.trim() || null,
            });
            toast.success('Referral recorded.');
            return res.data;
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not save the referral.');
            return null;
        } finally {
            setIsSaving(false);
        }
    };

    const handleSaveOnly = async () => {
        const saved = await save();
        if (saved) onClose();
    };

    const handleSaveAndPrint = async () => {
        const saved = await save();
        if (!saved) return;
        printReferralLetter({ mode: 'typed', referral: saved, patient, doctorName });
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="referral-modal-title">
            <div className="bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-lg max-h-[90vh] overflow-y-auto custom-scrollbar">
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <h3 id="referral-modal-title" className="font-bold text-ink-800 dark:text-ink-200 flex items-center gap-2">
                        <FileText size={16} /> Refer {patient.patient_name}
                    </h3>
                    <button type="button" onClick={onClose} aria-label="Close referral dialog" className="text-ink-400 hover:text-ink-600"><X size={18} /></button>
                </div>

                <div className="p-4 space-y-3">
                    <div>
                        <label htmlFor="referral-specialty" className="label">Specialty *</label>
                        <input id="referral-specialty" type="text" value={form.specialty} onChange={set('specialty')} className="input" placeholder="e.g. Cardiology" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="referral-facility" className="label">Target facility</label>
                            <input id="referral-facility" type="text" value={form.target_facility} onChange={set('target_facility')} className="input" placeholder="Receiving hospital / clinic" />
                        </div>
                        <div>
                            <label htmlFor="referral-clinician" className="label">Target clinician</label>
                            <input id="referral-clinician" type="text" value={form.target_clinician} onChange={set('target_clinician')} className="input" placeholder="If known" />
                        </div>
                    </div>
                    <div>
                        <label htmlFor="referral-urgency" className="label">Urgency</label>
                        <select id="referral-urgency" value={form.urgency} onChange={set('urgency')} className="input">
                            {URGENCIES.map((u) => <option key={u} value={u}>{u}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="referral-reason" className="label">Reason for referral *</label>
                        <textarea id="referral-reason" rows="3" value={form.reason} onChange={set('reason')} className="input resize-none" placeholder="Why this patient needs onward care…" />
                    </div>
                    <div>
                        <label htmlFor="referral-summary" className="label">Clinical summary</label>
                        <textarea id="referral-summary" rows="4" value={form.clinical_summary} onChange={set('clinical_summary')} className="input resize-none" placeholder="Relevant findings, treatment so far…" />
                    </div>
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 space-y-2">
                    <div className="flex gap-2">
                        <button type="button" onClick={handleSaveAndPrint} disabled={isSaving} className="btn-success flex-1">
                            <Printer size={14} /> Save &amp; print typed letter
                        </button>
                        <button type="button" onClick={handleSaveOnly} disabled={isSaving} className="btn-secondary flex-1">
                            <Save size={14} /> Save referral
                        </button>
                    </div>
                    <p className="text-2xs text-ink-500 dark:text-ink-400 pt-1">Print a letter to fill in by hand (nothing is saved):</p>
                    <div className="flex gap-2">
                        <button type="button" onClick={() => printReferralLetter({ mode: 'blank-patient', referral: {}, patient, doctorName })} className="btn-ghost flex-1 text-xs">
                            <Printer size={13} /> Blank (with patient info)
                        </button>
                        <button type="button" onClick={() => printReferralLetter({ mode: 'blank', referral: {}, patient, doctorName: '' })} className="btn-ghost flex-1 text-xs">
                            <Printer size={13} /> Fully blank
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/ReferralModal.test.jsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Wire into ClinicalDesk**

In `frontend/src/pages/ClinicalDesk.jsx`:

1. `import ReferralModal from '../components/ReferralModal';`
2. Add state near the other modal flags: `const [isReferModalOpen, setIsReferModalOpen] = useState(false);`
3. Replace line 799:
   ```jsx
   <button type="button" onClick={() => setIsReferModalOpen(true)} className="btn-ghost"><ArrowRightLeft size={15} /> Refer patient</button>
   ```
4. Render next to the lab/imaging modals (they render only when `activePatient` is set — same guard):
   ```jsx
   {isReferModalOpen && activePatient && (
       <ReferralModal
           patient={activePatient}
           initialSummary={clinicalNotes.diagnosis || icdCodes.map((c) => c.description).join('; ')}
           onClose={() => setIsReferModalOpen(false)}
       />
   )}
   ```
5. If `handleNotImplemented` now has no remaining callers, delete it (run `grep -n "handleNotImplemented" src/pages/ClinicalDesk.jsx` first).

- [ ] **Step 6: Verify + commit**

Run: `cd frontend && npx eslint src/components/ReferralModal.jsx src/components/ReferralModal.test.jsx src/pages/ClinicalDesk.jsx && npx vitest run && npm run build`
Expected: clean, all pass, build OK.

```bash
git add frontend/src/components/ReferralModal.jsx frontend/src/components/ReferralModal.test.jsx frontend/src/pages/ClinicalDesk.jsx
git commit -m "feat(referrals): refer-patient modal with typed and blank letter printing

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 8: Full verification + PR to development

**Files:** none new.

- [ ] **Step 1: Backend suite (targeted)**

Start the server if needed (`cd backend && REDIS_URL="" uvicorn app.main:app --port 8000 &`), then:

Run: `cd backend && python -m pytest tests/test_visit_history.py tests/test_medical_history_triage.py tests/test_clinical_icd10.py tests/test_clinical_blood_glucose.py -v`
Expected: all PASS.

- [ ] **Step 2: Frontend suite + lint + build**

Run: `cd frontend && npx vitest run && npx eslint src/components/IcdDiagnosisPicker.jsx src/components/VisitHistoryList.jsx src/components/ReferralModal.jsx src/utils/printTemplates.js src/pages/ClinicalDesk.jsx src/pages/MedicalHistory.jsx && npm run build`
Expected: all suites pass, eslint clean, build succeeds.

- [ ] **Step 3: Push and open PR against development**

```bash
git push -u origin feat/visit-history-multi-icd-referrals
gh pr create --base development --title "feat: full visit history, multiple ICD-10 diagnoses, printable referral letters" --body "$(cat <<'EOF'
## Summary
Client-requested clinical workflow upgrades:
- **Full visit history** — the Medical History chart now returns every visit (was capped at 10); each visit expands to full detail (SOAP, vitals, diagnoses, prescriptions, linked lab tests, same-day imaging) via a new `GET /api/clinical/record/{record_id}` endpoint (KDPA access-logged, internal notes withheld from non-clinical roles).
- **Multiple ICD-10 diagnoses** — chips picker in Clinical Desk; codes store comma-separated in the existing `icd10_code` column. **Schema-compatible: no migration needed**, the migration-check gate stays a no-op.
- **Printable referral letters** — "Refer patient" now opens a real modal (saves via the existing referrals API) with three print modes: typed letter, blank with patient info, fully blank for handwriting.

Spec: `docs/superpowers/specs/2026-07-06-visit-history-multi-icd-referral-letters-design.md`

## Test plan
- [ ] `backend/tests/test_visit_history.py` (new) — chart >10 visits, visit-detail fields & RBAC, multi-ICD round-trip + oversize 400
- [ ] Vitest: IcdDiagnosisPicker, VisitHistoryList, ReferralModal, printReferralLetter
- [ ] Manual: expand an old visit in Medical History; submit a consult with 3 ICD codes; print all three letter variants

🤖 Generated with [RuFlo](https://github.com/ruvnet/ruflo)
EOF
)"
```

Note: if the PR contains only frontend-touching files the required `migration-check` can't run — this PR touches `backend/app/routes/**` (not alembic/models), so the path filter for schema checks stays green/no-op. Do not merge to beta/main directly; standard promotion applies.
