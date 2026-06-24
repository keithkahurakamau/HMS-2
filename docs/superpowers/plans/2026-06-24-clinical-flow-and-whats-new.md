# Clinical Flow Fixes + "What's New" Announcements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix customer-reported queue/triage/clinical/history issues and add a versioned in-app "What's New" announcement, all in one PR to `development`.

**Architecture:** FastAPI + SQLAlchemy backend (multi-tenant, alembic migrations), React (Vite) frontend. Patient flow uses a generic `PatientQueue` table (consumed today only by Triage + Consultation); we add a reusable `DepartmentQueue` panel so every module can show patients routed to it. One additive schema change (`medical_records.blood_glucose`). Announcements are frontend-only (a versioned `releases.js`).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Pytest (live-server httpx integration tests), React 18, Vite, Vitest + React Testing Library, Tailwind, lucide-react, react-hot-toast.

## Global Constraints

- Branch: `feat/clinical-flow-and-whats-new` (already created off `development`). One combined PR → `development`.
- Migration gate: any change to `backend/alembic/**`, `backend/app/models/**`, or `migrate_all_tenants.py` must keep `migrate_all_tenants.py` green on fresh Postgres. New alembic revision must chain from head `a6f2d9c4e7b1` and be at head before promoting.
- Keep files under 500 lines; never save tests/working files to repo root.
- Backend tests are **live-server integration tests**: a server must be running on `http://localhost:8000` against seeded tenant `mayoclinic_db`. State-changing requests need the CSRF double-submit pattern (GET first, echo `csrf_token` cookie as `x-csrf-token` header). Auth via `*_cookies` fixtures in `backend/tests/conftest.py` (`admin_cookies`, `doctor_cookies`, `nurse_cookies`, `pharmacist_cookies`, `lab_cookies`, `radiologist_cookies`, `receptionist_cookies`).
- Local server env: `REDIS_URL=""` (slowapi 500s on dead Redis); `mayoclinic_db` feature_flags must enable billing/accounting/laboratory/wards.
- Canonical departments live in `backend/app/routes/patients.py`: `CANONICAL_DEPARTMENTS` frozenset + `_DEPARTMENT_ALIASES` dict + `_canonical_department()`.
- Active queue statuses: `["Waiting", "In Progress", "In Consultation"]`; terminal: `"Completed"`. We add `"Cancelled"` (string value only — no enum/migration).
- Run frontend lint before pushing (`cd frontend && npm run lint`) — vite build misses `no-undef`.
- Commit messages end with the `Co-Authored-By: RuFlo <ruv@ruv.net>` trailer.

---

## File Structure

**Backend**
- Create `backend/alembic/versions/<rev>_add_medical_record_blood_glucose.py` — adds `medical_records.blood_glucose`.
- Modify `backend/app/models/clinical.py` — `MedicalRecord.blood_glucose`.
- Modify `backend/app/routes/patients.py` — add `Reception` to department catalogue.
- Modify `backend/app/routes/queue.py` — exclude `Cancelled` from list; add `cancel` + `close-visit` endpoints.
- Modify `backend/app/routes/clinical.py` — persist `blood_glucose` on submit; exclude `Cancelled`.
- Modify `backend/app/routes/medical_history.py` — add `triage_history` to chart.
- Modify `backend/app/schemas/medical_history.py` — `triage_history` field + item schema.
- Tests: `backend/tests/test_queue.py` (cancel, close-visit, list excludes Cancelled), `backend/tests/test_triage.py` (route to non-Consultation), `backend/tests/test_clinical_blood_glucose.py` (new), `backend/tests/test_medical_history_triage.py` (new).

**Frontend**
- Create `frontend/src/releases.js` — versioned changelog + last-seen helpers.
- Create `frontend/src/components/WhatsNew.jsx` — announcement surface.
- Create `frontend/src/components/DepartmentQueue.jsx` — reusable routed-patients panel.
- Modify `frontend/package.json` — version `1.0.0`.
- Modify `frontend/src/pages/Triage.jsx` — disposition picker.
- Modify `frontend/src/pages/ClinicalDesk.jsx` — RBS prefill + field.
- Modify `frontend/src/pages/MedicalHistory.jsx` — triage section + clear-visit control.
- Modify `frontend/src/pages/Patients.jsx`, `Laboratory.jsx`, `Pharmacy.jsx`, `Radiology.jsx`, `Wards.jsx` — embed `DepartmentQueue`.
- Modify `frontend/src/App.jsx` (or `MainLayout.jsx`) — mount `WhatsNew`.
- Tests: `frontend/src/pages/Triage.test.jsx` (new), `frontend/src/components/DepartmentQueue.test.jsx` (new), `frontend/src/components/WhatsNew.test.jsx` (new).

---

## Task ordering

Backend schema/data first (Stream C, B3/B4, D1, B2-backend), then frontend. This lets backend tests pass against a migrated DB before UI work. Recommended order: Task 1 → 12.

---

### Task 1: Add `blood_glucose` to MedicalRecord (model + migration)

**Files:**
- Modify: `backend/app/models/clinical.py` (MedicalRecord vitals block, ~line 99-101)
- Create: `backend/alembic/versions/b1c2d3e4f5a6_add_medical_record_blood_glucose.py`

**Interfaces:**
- Produces: `MedicalRecord.blood_glucose` (Float, nullable) — consumed by Tasks 2, 9.

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/clinical.py`, in `MedicalRecord`, after the `calculated_bmi` line (currently `calculated_bmi = Column(Float, nullable=True)` ~line 101) add:

```python
    blood_glucose = Column(Float, nullable=True)  # mmol/L (RBS), carried from triage
```

- [ ] **Step 2: Create the alembic revision**

Create `backend/alembic/versions/b1c2d3e4f5a6_add_medical_record_blood_glucose.py`:

```python
"""add medical_record blood_glucose

Revision ID: b1c2d3e4f5a6
Revises: a6f2d9c4e7b1
Create Date: 2026-06-24

Additive, nullable column so the doctor's encounter can store the Random Blood
Sugar (RBS) captured at triage. Backward-compatible.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a6f2d9c4e7b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("medical_records") as batch:
        batch.add_column(sa.Column("blood_glucose", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("medical_records") as batch:
        batch.drop_column("blood_glucose")
```

- [ ] **Step 3: Verify the migration applies on a fresh DB**

Run (from `backend/`, with a Postgres available per project test env):

```bash
cd backend && REDIS_URL="" python scripts/migrate_all_tenants.py 2>&1 | tail -20
```

Expected: completes without error; no "Target database is not up to date". `MedicalRecord` model is already imported by `migrate_all_tenants.py` (via `app.models.clinical`), so no new import registration is needed — confirm by grep:

```bash
grep -n "models.clinical\|MedicalRecord\|import clinical" backend/scripts/migrate_all_tenants.py
```

Expected: clinical models are imported. If not, add `from app.models import clinical  # noqa` to the import block.

- [ ] **Step 4: Confirm alembic at head**

```bash
cd backend && REDIS_URL="" alembic heads && REDIS_URL="" alembic current 2>&1 | tail -5
```

Expected: head is `b1c2d3e4f5a6`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/clinical.py backend/alembic/versions/b1c2d3e4f5a6_add_medical_record_blood_glucose.py
git commit -m "feat(clinical): add blood_glucose (RBS) column to medical_records

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 2: Persist `blood_glucose` on clinical submit

**Files:**
- Modify: `backend/app/routes/clinical.py` (`submit_consultation`, ~line 90-120)
- Test: `backend/tests/test_clinical_blood_glucose.py` (create)

**Interfaces:**
- Consumes: `MedicalRecord.blood_glucose` (Task 1).
- Produces: clinical submit accepts and stores `blood_glucose`; `/clinical/queue` and any record read expose it.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_clinical_blood_glucose.py`:

```python
"""Doctor's encounter stores Random Blood Sugar (RBS) carried from triage.

Live-server integration test (server on :8000, tenant mayoclinic_db).
"""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _phone() -> str:
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies) -> dict:
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_RBS_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "RBS Patient", "sex": "Male",
        "date_of_birth": "1990-06-01", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_clinical_submit_persists_blood_glucose(client, doctor_cookies):
    patient = _new_patient(client, doctor_cookies)
    try:
        r = client.post("/api/clinical/submit", cookies=doctor_cookies, json={
            "patient_id": patient["patient_id"],
            "record_status": "Draft",
            "blood_glucose": 6.4,
            "chief_complaint": "RBS check",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("blood_glucose") == 6.4, body
    finally:
        client.delete(f"/api/patients/{patient['patient_id']}", cookies=doctor_cookies)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_clinical_blood_glucose.py -v
```

Expected: FAIL — response omits `blood_glucose` (field dropped) or assertion error.

- [ ] **Step 3: Read the current submit handler to find the whitelist**

```bash
sed -n '90,160p' backend/app/routes/clinical.py
```

Identify where `record_in` keys are filtered into `MedicalRecord(**...)`. The handler pops `queue_id` and builds a `MedicalRecord`. Ensure `blood_glucose` is among accepted fields and is returned in the response body.

- [ ] **Step 4: Implement — allow blood_glucose through and return it**

In `backend/app/routes/clinical.py::submit_consultation`, where the `MedicalRecord` fields are assembled from `record_in`, add `blood_glucose` to the accepted vitals (it mirrors the existing `weight_kg`, `spo2`, etc. handling). If the handler uses an explicit field list, add `"blood_glucose"`. Ensure the JSON response includes `blood_glucose` (add it to the serialized record dict if records are hand-serialized).

Example (adapt to the actual code shape):

```python
ALLOWED_VITALS = {
    "blood_pressure", "heart_rate", "respiratory_rate", "temperature",
    "spo2", "weight_kg", "height_cm", "calculated_bmi", "blood_glucose",
}
```

and in the response dict:

```python
"blood_glucose": record.blood_glucose,
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_clinical_blood_glucose.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/clinical.py backend/tests/test_clinical_blood_glucose.py
git commit -m "feat(clinical): persist and return blood_glucose (RBS) on submit

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 3: Queue list excludes `Cancelled`; add `cancel` endpoint

**Files:**
- Modify: `backend/app/routes/queue.py` (`get_active_queue` ~line 58-63; `ACTIVE_QUEUE_STATUSES` ~line 20; add cancel endpoint)
- Test: `backend/tests/test_queue.py` (append a `TestQueueCancel` class)

**Interfaces:**
- Produces: `PATCH /api/queue/{queue_id}/cancel` body `{"reason": str | null}` → `QueueResponse` with `status == "Cancelled"`. Consumed by Task 8 (DepartmentQueue) and Task 10 (ClinicalDesk).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_queue.py` (reuse existing `_new_patient`, `_enqueue`, `_cleanup_patient` helpers already in the file):

```python
# ─── 7. Cancel (patient left without being seen) ────────────────────────────

class TestQueueCancel:
    def test_cancel_requires_auth(self, client):
        r = client.patch("/api/queue/1/cancel", json={"reason": "left"})
        assert r.status_code == 401

    def test_cancel_unknown_returns_404(self, client, receptionist_cookies):
        r = client.patch("/api/queue/999999999/cancel",
                          cookies=receptionist_cookies, json={"reason": "x"})
        assert r.status_code == 404

    def test_cancel_sets_status_and_drops_from_active(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="CANCEL")
        try:
            qid = _enqueue(client, receptionist_cookies, patient["patient_id"], department="Wards")
            r = client.patch(f"/api/queue/{qid}/cancel",
                             cookies=receptionist_cookies, json={"reason": "Patient left"})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "Cancelled"

            rows = client.get("/api/queue/?department=Wards", cookies=receptionist_cookies).json()
            assert all(row["queue_id"] != qid for row in rows)
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_queue.py::TestQueueCancel -v
```

Expected: FAIL — 404/405 (endpoint missing) for the cancel calls.

- [ ] **Step 3: Add a Cancel schema**

In `backend/app/schemas/queue.py`, add:

```python
class QueueCancel(BaseModel):
    # Optional free-text reason the patient was cancelled (left, no-show…).
    reason: Optional[str] = None
```

- [ ] **Step 4: Exclude Cancelled from the active list and add the endpoint**

In `backend/app/routes/queue.py`:

Update the list query (`get_active_queue`) so it excludes both terminal states:

```python
TERMINAL_QUEUE_STATUSES = ["Completed", "Cancelled"]

@router.get("/", response_model=List[QueueResponse], dependencies=[Depends(RequirePermission("patients:read"))])
def get_active_queue(department: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(PatientQueue).filter(~PatientQueue.status.in_(TERMINAL_QUEUE_STATUSES))
    if department:
        query = query.filter(PatientQueue.department == department)
    return query.order_by(PatientQueue.acuity_level.asc(), PatientQueue.joined_at.asc()).all()
```

Add the import for the schema at the top (`QueueCancel`) and the endpoint after `checkout_from_queue`:

```python
@router.patch(
    "/{queue_id}/cancel",
    response_model=QueueResponse,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def cancel_from_queue(
    queue_id: int,
    payload: QueueCancel,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a patient who left without being seen.

    Distinct from checkout (Completed = seen & done): Cancelled means the
    patient never received the service. Soft-terminal so analytics can tell
    them apart and history retains the visit."""
    entry = db.query(PatientQueue).filter(PatientQueue.queue_id == queue_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    if entry.status not in TERMINAL_QUEUE_STATUSES:
        old = {"status": entry.status}
        entry.status = "Cancelled"
        entry.completed_at = datetime.now(timezone.utc)
        if payload.reason:
            entry.notes = ((entry.notes + " | ") if entry.notes else "") + f"Cancelled: {payload.reason}"
        log_audit(
            db, current_user["user_id"], "UPDATE", "Queue", entry.queue_id,
            old, {"status": "Cancelled", "reason": payload.reason},
            request.client.host if request.client else None,
        )
        db.commit()
        db.refresh(entry)
    return entry
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_queue.py::TestQueueCancel tests/test_queue.py::TestQueueList -v
```

Expected: PASS (including the existing list test still green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/queue.py backend/app/schemas/queue.py backend/tests/test_queue.py
git commit -m "feat(queue): add cancel action and exclude Cancelled from active list

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 4: Add `close-visit` endpoint (clear current visit)

**Files:**
- Modify: `backend/app/routes/queue.py` (add endpoint + schema import)
- Modify: `backend/app/schemas/queue.py` (response schema)
- Test: `backend/tests/test_queue.py` (append `TestCloseVisit`)

**Interfaces:**
- Produces: `POST /api/queue/patients/{patient_id}/close-visit` → `{"closed": int}`. Soft-completes the patient's active queue rows. Consumed by Task 11 (MedicalHistory clear-visit).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_queue.py`:

```python
# ─── 8. Close visit (start a fresh visit for a patient) ─────────────────────

class TestCloseVisit:
    def test_close_visit_requires_auth(self, client):
        r = client.post("/api/queue/patients/1/close-visit")
        assert r.status_code == 401

    def test_close_visit_completes_active_rows(self, client, receptionist_cookies):
        patient = _new_patient(client, receptionist_cookies, surname_tag="CLOSEV")
        try:
            q1 = _enqueue(client, receptionist_cookies, patient["patient_id"], department="Wards")
            q2 = _enqueue(client, receptionist_cookies, patient["patient_id"], department="Pharmacy")
            r = client.post(
                f"/api/queue/patients/{patient['patient_id']}/close-visit",
                cookies=receptionist_cookies,
            )
            assert r.status_code == 200, r.text
            assert r.json()["closed"] >= 2

            for dept in ("Wards", "Pharmacy"):
                rows = client.get(f"/api/queue/?department={dept}", cookies=receptionist_cookies).json()
                ids = {row["queue_id"] for row in rows}
                assert q1 not in ids and q2 not in ids
        finally:
            _cleanup_patient(client, receptionist_cookies, patient["patient_id"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_queue.py::TestCloseVisit -v
```

Expected: FAIL — endpoint missing (404).

- [ ] **Step 3: Add the response schema**

In `backend/app/schemas/queue.py`:

```python
class CloseVisitResult(BaseModel):
    closed: int
```

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routes/queue.py` (import `CloseVisitResult`), add:

```python
@router.post(
    "/patients/{patient_id}/close-visit",
    response_model=CloseVisitResult,
    dependencies=[Depends(RequirePermission("patients:write"))],
)
def close_visit(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Close a patient's current visit by soft-completing every active queue
    row they have, so the next registration/queue starts a clean visit.
    Backs the 'Clear previous visit / start new visit' control on the chart."""
    rows = db.query(PatientQueue).filter(
        PatientQueue.patient_id == patient_id,
        PatientQueue.status.in_(ACTIVE_QUEUE_STATUSES),
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = "Completed"
        row.completed_at = now
    log_audit(
        db, current_user["user_id"], "UPDATE", "Queue", f"close-visit:{patient_id}",
        {"active_count": len(rows)}, {"status": "Completed"},
        request.client.host if request.client else None,
    )
    db.commit()
    return CloseVisitResult(closed=len(rows))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_queue.py::TestCloseVisit -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/queue.py backend/app/schemas/queue.py backend/tests/test_queue.py
git commit -m "feat(queue): add close-visit endpoint to clear a patient's active queue rows

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 5: Add `Reception` to the department catalogue

**Files:**
- Modify: `backend/app/routes/patients.py` (`CANONICAL_DEPARTMENTS` ~line where frozenset defined; `_DEPARTMENT_ALIASES`)
- Test: `backend/tests/test_triage.py` (append `test_triage_routes_to_reception`)

**Interfaces:**
- Produces: `_canonical_department("reception")` → `"Reception"`; triage disposition + queue accept `Reception`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_triage.py` (reuse its existing `_new_patient`, `_queue_to_triage` helpers; add CSRF setup to the module `client` fixture if not present — check the top of the file and mirror test_queue.py's CSRF echo if state-changing calls 403):

```python
def test_triage_routes_to_reception(client, nurse_cookies):
    patient = _new_patient(client, nurse_cookies, surname_tag="RECEP")
    try:
        q = _queue_to_triage(client, nurse_cookies, patient["patient_id"])
        r = client.post("/api/triage/submit", cookies=nurse_cookies, json={
            "patient_id": patient["patient_id"],
            "queue_id": q["queue_id"],
            "chief_complaint": "Sent back to reception",
            "acuity_level": 3,
            "disposition": "Reception",
        })
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "Reception"

        rows = client.get("/api/queue/?department=Reception", cookies=nurse_cookies).json()
        assert any(row["patient_id"] == patient["patient_id"] for row in rows)
    finally:
        client.delete(f"/api/patients/{patient['patient_id']}", cookies=nurse_cookies)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_triage.py::test_triage_routes_to_reception -v
```

Expected: FAIL — 400 "Unknown department 'Reception'".

- [ ] **Step 3: Add Reception to the catalogue**

In `backend/app/routes/patients.py`:

```python
CANONICAL_DEPARTMENTS = frozenset({
    "Reception", "Triage", "Consultation", "Laboratory", "Radiology",
    "Pharmacy", "Billing", "Wards",
})
```

and in `_DEPARTMENT_ALIASES` add:

```python
    "reception":          "Reception",
    "front desk":         "Reception",
    "registration":       "Reception",
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_triage.py::test_triage_routes_to_reception -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/patients.py backend/tests/test_triage.py
git commit -m "feat(queue): add Reception as a routable department

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 6: Add `triage_history` to the patient chart

**Files:**
- Modify: `backend/app/schemas/medical_history.py` (add item schema + field on `PatientMedicalChartResponse`)
- Modify: `backend/app/routes/medical_history.py` (`get_patient_medical_chart` ~line 107-149)
- Test: `backend/tests/test_medical_history_triage.py` (create)

**Interfaces:**
- Consumes: `TriageRecord` (`app.models.clinical`).
- Produces: chart response field `triage_history: list[TriageHistoryItem]` (newest first, ≤10). Consumed by Task 11 (MedicalHistory UI).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_medical_history_triage.py`:

```python
"""Patient chart includes triage history.

Live-server integration test (server on :8000, tenant mayoclinic_db).
"""
from __future__ import annotations

import uuid
import pytest
import httpx

BASE = "http://localhost:8000"
HEADERS = {"X-Tenant-ID": "mayoclinic_db"}


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, headers=HEADERS, follow_redirects=True) as c:
        c.get("/api/queue/")
        token = c.cookies.get("csrf_token")
        if token:
            c.headers["x-csrf-token"] = token
        yield c


def _phone():
    return "9" + uuid.uuid4().int.__str__()[:11]


def _new_patient(client, cookies):
    r = client.post("/api/patients/", cookies=cookies, json={
        "surname": f"ZZ_MHTRI_{uuid.uuid4().hex[:6].upper()}",
        "other_names": "Hist Patient", "sex": "Female",
        "date_of_birth": "1991-02-02", "telephone_1": _phone(),
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_chart_includes_triage_history(client, nurse_cookies, doctor_cookies):
    patient = _new_patient(client, nurse_cookies)
    pid = patient["patient_id"]
    try:
        q = client.post("/api/queue/", cookies=nurse_cookies, json={
            "patient_id": pid, "department": "Triage", "acuity_level": 3})
        assert q.status_code == 200, q.text
        sub = client.post("/api/triage/submit", cookies=nurse_cookies, json={
            "patient_id": pid, "queue_id": q.json()["queue_id"],
            "blood_glucose": 7.1, "calculated_bmi": 24.2,
            "chief_complaint": "headache", "acuity_level": 2,
            "disposition": "Consultation"})
        assert sub.status_code == 200, sub.text

        chart = client.get(f"/api/medical-history/{pid}/chart", cookies=doctor_cookies)
        assert chart.status_code == 200, chart.text
        th = chart.json().get("triage_history")
        assert isinstance(th, list) and len(th) >= 1, chart.json()
        latest = th[0]
        assert latest["chief_complaint"] == "headache"
        assert latest["blood_glucose"] == 7.1
        assert latest["acuity_level"] == 2
    finally:
        client.delete(f"/api/patients/{pid}", cookies=nurse_cookies)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_medical_history_triage.py -v
```

Expected: FAIL — `triage_history` is None / missing.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/medical_history.py`, add an item model and a field on the chart response (match the file's existing pydantic style — `ConfigDict(from_attributes=True)` if used):

```python
class TriageHistoryItem(BaseModel):
    triage_id: int
    date: Optional[str] = None
    nurse: Optional[str] = None
    acuity_level: Optional[int] = None
    chief_complaint: Optional[str] = None
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    temperature: Optional[float] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    calculated_bmi: Optional[float] = None
    blood_glucose: Optional[float] = None
    triage_notes: Optional[str] = None
```

Add to `PatientMedicalChartResponse`:

```python
    triage_history: List[TriageHistoryItem] = []
```

(Ensure `List` and `Optional` are imported at the top of the file.)

- [ ] **Step 4: Populate it in the chart route**

In `backend/app/routes/medical_history.py`, import the model and build the list. Add near the `recent_records` block (~line 107):

```python
from app.models.clinical import MedicalRecord, TriageRecord  # extend existing import

# ... inside get_patient_medical_chart, after recent_visits is built:
triage_rows = db.query(TriageRecord).filter(
    TriageRecord.patient_id == patient_id
).order_by(desc(TriageRecord.created_at)).limit(10).all()

triage_history = []
for t in triage_rows:
    nurse = db.query(User).filter(User.user_id == t.nurse_id).first()
    triage_history.append({
        "triage_id": t.triage_id,
        "date": t.created_at.isoformat() if t.created_at else None,
        "nurse": nurse.full_name if nurse else "Unknown",
        "acuity_level": t.acuity_level,
        "chief_complaint": t.chief_complaint,
        "blood_pressure": t.blood_pressure,
        "heart_rate": t.heart_rate,
        "temperature": t.temperature,
        "spo2": t.spo2,
        "weight_kg": t.weight_kg,
        "height_cm": t.height_cm,
        "calculated_bmi": t.calculated_bmi,
        "blood_glucose": t.blood_glucose,
        "triage_notes": t.triage_notes,
    })
```

Then pass `triage_history=triage_history` into the `PatientMedicalChartResponse(...)` return.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_medical_history_triage.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/medical_history.py backend/app/routes/medical_history.py backend/tests/test_medical_history_triage.py
git commit -m "feat(history): include triage_history in patient chart

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 7: Run full backend suite for touched areas

**Files:** none (verification task).

- [ ] **Step 1: Start a local server if not running**

```bash
cd backend && REDIS_URL="" uvicorn app.main:app --port 8000 &  # background; ensure mayoclinic_db seeded + feature flags on
```

- [ ] **Step 2: Run the relevant suites**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_queue.py tests/test_triage.py tests/test_clinical_blood_glucose.py tests/test_medical_history_triage.py -v
```

Expected: all PASS. (Note: `tests/test_api.py` has ~34 known pre-existing failures unrelated to this work — do not run it as a gate.)

- [ ] **Step 3: Commit (no-op if nothing changed)** — skip if clean.

---

### Task 8: Reusable `DepartmentQueue` panel (frontend)

**Files:**
- Create: `frontend/src/components/DepartmentQueue.jsx`
- Create: `frontend/src/components/DepartmentQueue.test.jsx`

**Interfaces:**
- Consumes: `GET /api/queue/?department=<department>`, `PATCH /api/queue/{id}/checkout`, `PATCH /api/queue/{id}/cancel` (Tasks 3).
- Produces: `<DepartmentQueue department="Pharmacy" title="Patients sent to Pharmacy" />` default export. Props: `department: string` (required), `title?: string`, `onChange?: () => void`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/DepartmentQueue.test.jsx`:

```jsx
/* eslint-disable no-unused-vars */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), patch: vi.fn(), post: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => {
    const toast = vi.fn(); toast.success = vi.fn(); toast.error = vi.fn();
    return { default: toast };
});

import { apiClient } from '../api/client';
import DepartmentQueue from './DepartmentQueue';

describe('DepartmentQueue', () => {
    beforeEach(() => vi.clearAllMocks());

    it('lists patients routed to the department', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 11, patient_id: 5, department: 'Pharmacy', acuity_level: 3, status: 'Waiting', joined_at: '2026-06-24T08:00:00Z' },
        ]});
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith('/queue/?department=Pharmacy'));
        expect(await screen.findByText(/#11|Queue 11|5/)).toBeInTheDocument();
    });

    it('removes a patient via checkout', async () => {
        apiClient.get.mockResolvedValue({ data: [
            { queue_id: 12, patient_id: 6, department: 'Pharmacy', acuity_level: 3, status: 'Waiting', joined_at: '2026-06-24T08:00:00Z' },
        ]});
        apiClient.patch.mockResolvedValueOnce({ data: { queue_id: 12, status: 'Completed' } });
        renderWithProviders(<DepartmentQueue department="Pharmacy" />);
        const removeBtn = await screen.findByRole('button', { name: /remove/i });
        await userEvent.click(removeBtn);
        await waitFor(() => expect(apiClient.patch).toHaveBeenCalledWith('/queue/12/checkout'));
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/DepartmentQueue.test.jsx
```

Expected: FAIL — module `./DepartmentQueue` not found.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/DepartmentQueue.jsx`. Follow existing card/badge styling (mirror `Triage.jsx`'s queue card classes). Keep it under 200 lines:

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { Users, Clock, X, UserMinus } from 'lucide-react';

/**
 * DepartmentQueue — shows patients routed to a department via the generic
 * PatientQueue, with per-row remove (checkout) and cancel actions. Dropped
 * into module pages (Reception, Lab, Pharmacy, Radiology, Wards) so triage
 * dispositions actually surface where the patient was sent.
 */
export default function DepartmentQueue({ department, title, onChange }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchRows = useCallback(async () => {
        setLoading(true);
        try {
            const res = await apiClient.get(`/queue/?department=${department}`);
            setRows(res.data || []);
        } catch {
            // queue read is best-effort; leave empty on failure
        } finally {
            setLoading(false);
        }
    }, [department]);

    useEffect(() => { fetchRows(); }, [fetchRows]);

    const remove = async (queueId) => {
        try {
            await apiClient.patch(`/queue/${queueId}/checkout`);
            toast.success('Removed from queue.');
            fetchRows();
            onChange?.();
        } catch {
            toast.error('Could not remove from queue.');
        }
    };

    const cancel = async (queueId) => {
        const reason = window.prompt('Cancel reason (optional):') ?? null;
        try {
            await apiClient.patch(`/queue/${queueId}/cancel`, { reason });
            toast.success('Patient cancelled.');
            fetchRows();
            onChange?.();
        } catch {
            toast.error('Could not cancel.');
        }
    };

    return (
        <div className="card">
            <div className="p-4 flex items-center gap-3 border-b border-ink-100 dark:border-ink-800">
                <Users className="text-brand-600" size={18} />
                <h2 className="font-semibold text-ink-900 dark:text-white text-base">
                    {title || `Patients routed to ${department}`}
                </h2>
                <span className="badge-brand">{rows.length} Waiting</span>
            </div>
            <div className="p-4">
                {loading ? (
                    <p className="text-sm text-ink-400 text-center py-4">Loading&hellip;</p>
                ) : rows.length === 0 ? (
                    <p className="text-sm text-ink-400 text-center py-4">No patients routed here.</p>
                ) : (
                    <ul className="space-y-2">
                        {rows.map((r) => (
                            <li key={r.queue_id} className="flex items-center justify-between gap-3 p-3 rounded-xl border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900">
                                <div className="min-w-0">
                                    <p className="font-semibold text-sm text-ink-900 dark:text-white truncate">
                                        {r.patient_name || `Patient #${r.patient_id}`}
                                    </p>
                                    <p className="text-xs text-ink-500 flex items-center gap-1">
                                        <Clock size={10} /> Acuity {r.acuity_level} &middot; {r.status}
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <button type="button" onClick={() => remove(r.queue_id)}
                                        className="btn-secondary px-2 py-1 text-xs flex items-center gap-1">
                                        <UserMinus size={13} /> Remove
                                    </button>
                                    <button type="button" onClick={() => cancel(r.queue_id)}
                                        className="btn-secondary px-2 py-1 text-xs flex items-center gap-1 text-rose-600">
                                        <X size={13} /> Cancel
                                    </button>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}
```

> Note: `GET /api/queue/` returns `QueueResponse` which has no `patient_name`. The component falls back to `Patient #<id>`. If a name is desired, a follow-up can extend `QueueResponse`; YAGNI for now — fallback is acceptable.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/DepartmentQueue.test.jsx
```

Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd frontend && npx eslint src/components/DepartmentQueue.jsx
cd .. && git add frontend/src/components/DepartmentQueue.jsx frontend/src/components/DepartmentQueue.test.jsx
git commit -m "feat(queue): reusable DepartmentQueue panel with remove + cancel

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 9: Triage disposition picker + embed DepartmentQueue in modules

**Files:**
- Modify: `frontend/src/pages/Triage.jsx` (vitals/footer region; the `payload.disposition`)
- Modify: `frontend/src/pages/Patients.jsx`, `Laboratory.jsx`, `Pharmacy.jsx`, `Radiology.jsx`, `Wards.jsx` (embed panel)
- Test: `frontend/src/pages/Triage.test.jsx` (create)

**Interfaces:**
- Consumes: `DepartmentQueue` (Task 8); `POST /api/triage/submit` with chosen `disposition`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/Triage.test.jsx`:

```jsx
/* eslint-disable no-unused-vars */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));
vi.mock('react-hot-toast', () => {
    const toast = vi.fn(); toast.success = vi.fn(); toast.error = vi.fn();
    return { default: toast };
});

import { apiClient } from '../api/client';
import Triage from './Triage';

describe('Triage disposition', () => {
    beforeEach(() => vi.clearAllMocks());

    it('submits the chosen disposition (not hardcoded Consultation)', async () => {
        apiClient.get.mockResolvedValueOnce({ data: [
            { queue_id: 1, patient_id: 2, outpatient_no: 'OPD1', patient_name: 'Jane Doe', age: 30, gender: 'F', joined_time: '08:00 AM', status: 'Waiting', allergies: 'None' },
        ]});
        apiClient.post.mockResolvedValue({ data: { message: 'ok', disposition: 'Laboratory' } });

        renderWithProviders(<Triage />);
        await userEvent.click(await screen.findByText('Jane Doe'));
        // record a vital so submit is allowed
        await userEvent.type(screen.getByLabelText(/RBS/i), '5.5');
        // choose Laboratory in the disposition selector
        await userEvent.selectOptions(screen.getByLabelText(/route to|disposition|send to/i), 'Laboratory');
        await userEvent.click(screen.getByRole('button', { name: /save/i }));

        await waitFor(() => expect(apiClient.post).toHaveBeenCalled());
        const body = apiClient.post.mock.calls[0][1];
        expect(body.disposition).toBe('Laboratory');
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/pages/Triage.test.jsx
```

Expected: FAIL — no disposition selector (`getByLabelText` throws) or `disposition` still 'Consultation'.

- [ ] **Step 3: Add the disposition selector to Triage.jsx**

In `frontend/src/pages/Triage.jsx`:

Add a constant near `ACUITY_LEVELS`:

```jsx
const DISPOSITIONS = ['Consultation', 'Laboratory', 'Pharmacy', 'Radiology', 'Billing', 'Wards', 'Reception'];
```

Add state with the rest of the form state (near `const [acuity, setAcuity] = useState(3);`):

```jsx
const [disposition, setDisposition] = useState('Consultation');
```

Reset it in `handlePatientSelect` (alongside `setAcuity(...)`):

```jsx
setDisposition('Consultation');
```

Replace the hardcoded payload line `disposition: 'Consultation',` with:

```jsx
disposition,
```

Add the selector in the footer region (before the Save button) with an accessible label:

```jsx
<div className="flex items-center gap-2">
    <label htmlFor="triage-disposition" className="label mb-0">Route to</label>
    <select id="triage-disposition" value={disposition}
        onChange={(e) => setDisposition(e.target.value)} className="input w-auto">
        {DISPOSITIONS.map((d) => <option key={d} value={d}>{d}</option>)}
    </select>
</div>
```

Make the footer helper copy dynamic:

```jsx
<Stethoscope size={13} /> On save, the patient is routed to {disposition}.
```

- [ ] **Step 4: Run the Triage test to verify it passes**

```bash
cd frontend && npx vitest run src/pages/Triage.test.jsx
```

Expected: PASS.

- [ ] **Step 5: Embed DepartmentQueue in the module pages**

In each of `Patients.jsx` (Reception), `Laboratory.jsx`, `Pharmacy.jsx`, `Radiology.jsx`, `Wards.jsx`, import and render the panel near the top of the page body:

```jsx
import DepartmentQueue from '../components/DepartmentQueue';
// ...in the JSX, near the top of the main content:
<DepartmentQueue department="Laboratory" title="Patients sent to the Lab" />
```

Use the matching department per page: `Patients.jsx` → `"Reception"`, `Laboratory.jsx` → `"Laboratory"`, `Pharmacy.jsx` → `"Pharmacy"`, `Radiology.jsx` → `"Radiology"`, `Wards.jsx` → `"Wards"`. Place it where it reads as a "who's waiting for me" strip without disrupting each page's existing primary content (top of the page, full width, above existing cards).

- [ ] **Step 6: Lint + run the affected frontend tests**

```bash
cd frontend && npx eslint src/pages/Triage.jsx src/pages/Patients.jsx src/pages/Laboratory.jsx src/pages/Pharmacy.jsx src/pages/Radiology.jsx src/pages/Wards.jsx src/components/DepartmentQueue.jsx
npx vitest run src/pages/Triage.test.jsx src/components/DepartmentQueue.test.jsx
```

Expected: lint clean; tests PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Triage.jsx frontend/src/pages/Triage.test.jsx frontend/src/pages/Patients.jsx frontend/src/pages/Laboratory.jsx frontend/src/pages/Pharmacy.jsx frontend/src/pages/Radiology.jsx frontend/src/pages/Wards.jsx
git commit -m "feat(triage): disposition picker + routed-patient panels across modules

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 10: ClinicalDesk — RBS + BMI from triage

**Files:**
- Modify: `frontend/src/pages/ClinicalDesk.jsx` (`prefillFromTriage` ~line 221-244; vitals state/grid; submit payload ~line 320-360; BMI display ~line 586)

**Interfaces:**
- Consumes: `GET /triage/patients/{id}/latest` (returns `blood_glucose`, `calculated_bmi`); `POST /clinical/submit` now accepts `blood_glucose` (Task 2).

- [ ] **Step 1: Read the current vitals state shape**

```bash
grep -n "const \[vitals\|EMPTY_VITALS\|setVitals\|glucose\|blood_glucose\|calculateBMI" frontend/src/pages/ClinicalDesk.jsx | head
```

Identify the `vitals` state object keys (BP/HR/RR/temp/SpO₂/weight/height) and where the encounter payload is assembled.

- [ ] **Step 2: Add `glucose` to vitals + prefill it from triage**

In `ClinicalDesk.jsx`:

- Add `glucose: ''` to the vitals initial state object (wherever `EMPTY_VITALS`/`useState` for vitals is defined).
- In `prefillFromTriage`, extend the `setVitals({...})` call to include:

```jsx
                glucose: t.blood_glucose ?? '',
```

Update the success toast to mention RBS only if present (optional, keep simple — leave existing toast).

- [ ] **Step 3: Add an RBS input to the doctor's vitals grid**

Next to the existing vitals inputs (mirror the SpO₂/temp input markup), add:

```jsx
<div>
    <label htmlFor="clinical-rbs" className="label">RBS (mmol/L)</label>
    <input id="clinical-rbs" type="number" step="0.1" value={vitals.glucose}
        onChange={(e) => setVitals({ ...vitals, glucose: e.target.value })}
        placeholder="5.5" className="input" />
</div>
```

- [ ] **Step 4: Include blood_glucose in the submit payload**

Where the clinical submit payload is built (the object posted to `/clinical/submit`), add:

```jsx
            blood_glucose: vitals.glucose ? parseFloat(vitals.glucose) : null,
```

- [ ] **Step 5: Confirm BMI renders for prefilled patients**

The BMI display already calls `calculateBMI()` (~line 586) using `vitals.weight`/`vitals.height`, which are prefilled from triage. No change needed; verify visually in Step 6. (BMI is derived, so it shows once weight+height are present.)

- [ ] **Step 6: Lint + manual smoke**

```bash
cd frontend && npx eslint src/pages/ClinicalDesk.jsx
```

Expected: clean. (No new unit test required — covered by Task 2 backend test for persistence + Task 12 build. A manual smoke during verification confirms the field shows and prefills.)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ClinicalDesk.jsx
git commit -m "feat(clinical): doctor sees and stores RBS; BMI prefilled from triage

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 11: MedicalHistory — triage section + clear-visit control

**Files:**
- Modify: `frontend/src/pages/MedicalHistory.jsx` (chart render; the section list ~line 323-411)

**Interfaces:**
- Consumes: chart `triage_history` (Task 6); `POST /api/queue/patients/{id}/close-visit` (Task 4).

- [ ] **Step 1: Add the clear-visit handler**

In `MedicalHistory.jsx`, add a handler (near the other actions that call `apiClient`):

```jsx
const clearPreviousVisit = async () => {
    if (!chart?.patient_id) return;
    if (!window.confirm('Clear the current visit and start a fresh one? This closes any active queue entries for this patient.')) return;
    try {
        const res = await apiClient.post(`/queue/patients/${chart.patient_id}/close-visit`);
        toast.success(`Visit cleared (${res.data?.closed ?? 0} active entr${(res.data?.closed === 1) ? 'y' : 'ies'} closed).`);
        fetchChart(chart.patient_id);
    } catch {
        toast.error('Could not clear the visit.');
    }
};
```

- [ ] **Step 2: Render the clear-visit control as the FIRST item**

Immediately inside the chart body, before the history sections (before the `{ENTRY_TYPES.map(...)}` / consents block ~line 316-326), add:

```jsx
<div className="card p-4 flex items-center justify-between gap-3">
    <div>
        <h3 className="font-semibold text-ink-900 dark:text-white text-sm">Visit</h3>
        <p className="text-xs text-ink-500 dark:text-ink-400">Start a new visit — closes any active queue entries for this patient.</p>
    </div>
    <button type="button" onClick={clearPreviousVisit} className="btn-secondary">
        Clear previous visit
    </button>
</div>
```

- [ ] **Step 3: Render the triage history section**

After the "Recent Clinical Visits" block (~line 394-411), add a "Triage History" card that maps `chart.triage_history`:

```jsx
{/* Triage History */}
<div className="card p-4">
    <h3 className="font-bold text-slate-800 dark:text-ink-200 flex items-center gap-2 mb-3">
        <Activity size={16} /> Triage History
    </h3>
    {(chart.triage_history || []).length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-ink-400 italic text-center py-4">No triage records.</p>
    ) : (
        <div className="space-y-2">
            {chart.triage_history.map((t) => (
                <div key={t.triage_id} className="p-3 bg-slate-50 dark:bg-ink-800/40 rounded-xl border border-slate-100 dark:border-ink-800">
                    <div className="flex justify-between items-start">
                        <p className="font-semibold text-sm text-slate-800 dark:text-ink-200">{t.chief_complaint || 'No complaint recorded'}</p>
                        <span className="text-xs text-slate-400 dark:text-ink-400">{t.date ? new Date(t.date).toLocaleDateString() : '—'}</span>
                    </div>
                    <p className="text-xs text-slate-500 dark:text-ink-400 mt-1">
                        Acuity {t.acuity_level ?? '—'} &middot; BP {t.blood_pressure || '—'} &middot; HR {t.heart_rate ?? '—'} &middot; Temp {t.temperature ?? '—'}°C &middot; SpO₂ {t.spo2 ?? '—'}% &middot; BMI {t.calculated_bmi ?? '—'} &middot; RBS {t.blood_glucose ?? '—'} mmol/L
                    </p>
                    <p className="text-xs text-slate-400 dark:text-ink-400">Nurse: {t.nurse || '—'}</p>
                </div>
            ))}
        </div>
    )}
</div>
```

Ensure `Activity` is imported from `lucide-react` at the top (add to the existing import if missing).

- [ ] **Step 4: Lint**

```bash
cd frontend && npx eslint src/pages/MedicalHistory.jsx
```

Expected: clean (watch for `no-undef` on any newly used icon — add the import).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/MedicalHistory.jsx
git commit -m "feat(history): triage history section + clear-previous-visit control

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 12: "What's New" announcements (releases + surface)

**Files:**
- Create: `frontend/src/releases.js`
- Create: `frontend/src/components/WhatsNew.jsx`
- Create: `frontend/src/components/WhatsNew.test.jsx`
- Modify: `frontend/package.json` (version)
- Modify: `frontend/src/components/layouts/MainLayout.jsx` (mount `WhatsNew`)

**Interfaces:**
- Consumes: `JourneyContext` (`useJourney().restartAll`), `AuthContext` (`useAuth().user`).
- Produces: `APP_VERSION`, `RELEASES`, `readLastSeenVersion(userId)`, `writeLastSeenVersion(userId, version)` from `releases.js`; `<WhatsNew />` default export.

- [ ] **Step 1: Write `releases.js`**

Create `frontend/src/releases.js`:

```js
// Single source of truth for the in-app "What's New" feed. Newest first.
// Bump APP_VERSION and prepend a RELEASES entry whenever we ship user-facing
// changes; users behind this version get the announcement on next load.
export const APP_VERSION = '1.0.0';

export const RELEASES = [
    {
        version: '1.0.0',
        date: '2026-06-24',
        title: 'Clinical flow improvements',
        changes: [
            'Triage can now route patients to any module (lab, pharmacy, radiology, wards, reception).',
            'Doctors now see Random Blood Sugar (RBS) and BMI carried from triage.',
            'Patients can be cancelled when not seen; dashboards show only active patients.',
            'Full triage history now appears in the patient chart, with a “clear previous visit” action.',
        ],
        offerTour: true, // show a "Take the tour" button
    },
];

const KEY = (userId) => `hms_last_seen_version_${userId ?? 'anon'}`;

export function readLastSeenVersion(userId) {
    try { return localStorage.getItem(KEY(userId)); } catch { return null; }
}

export function writeLastSeenVersion(userId, version) {
    try { localStorage.setItem(KEY(userId), version); } catch { /* ignore */ }
}

// Simple semver-ish compare: returns true if `a` > `b`.
export function isNewer(a, b) {
    if (!b) return true;
    const pa = String(a).split('.').map(Number);
    const pb = String(b).split('.').map(Number);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
        const da = pa[i] || 0, db = pb[i] || 0;
        if (da !== db) return da > db;
    }
    return false;
}

// Releases the user hasn't seen yet (strictly newer than lastSeen).
export function unseenReleases(lastSeen) {
    return RELEASES.filter((r) => isNewer(r.version, lastSeen));
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/WhatsNew.test.jsx`:

```jsx
/* eslint-disable no-unused-vars */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/renderWithProviders';

const restartAll = vi.fn();
vi.mock('../context/JourneyContext', () => ({
    useJourney: () => ({ restartAll }),
}));
vi.mock('../context/AuthContext', async (orig) => {
    const actual = await orig();
    return { ...actual, useAuth: () => ({ user: { user_id: 42 } }) };
});

import { APP_VERSION } from '../releases';
import WhatsNew from './WhatsNew';

describe('WhatsNew', () => {
    beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });

    it('shows the announcement when the user has not seen the current version', async () => {
        renderWithProviders(<WhatsNew />);
        expect(await screen.findByText(/what's new/i)).toBeInTheDocument();
        expect(screen.getByText(/Clinical flow improvements/i)).toBeInTheDocument();
    });

    it('hides and persists last-seen after dismiss', async () => {
        renderWithProviders(<WhatsNew />);
        await userEvent.click(await screen.findByRole('button', { name: /got it|dismiss|close/i }));
        await waitFor(() => expect(localStorage.getItem('hms_last_seen_version_42')).toBe(APP_VERSION));
    });

    it('does not show when already on current version', async () => {
        localStorage.setItem('hms_last_seen_version_42', APP_VERSION);
        renderWithProviders(<WhatsNew />);
        await waitFor(() => expect(screen.queryByText(/what's new/i)).not.toBeInTheDocument());
    });
});
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/WhatsNew.test.jsx
```

Expected: FAIL — module `./WhatsNew` not found.

- [ ] **Step 4: Implement `WhatsNew.jsx`**

Create `frontend/src/components/WhatsNew.jsx`:

```jsx
import React, { useState, useEffect } from 'react';
import { Sparkles, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useJourney } from '../context/JourneyContext';
import { APP_VERSION, unseenReleases, writeLastSeenVersion, readLastSeenVersion } from '../releases';

/**
 * WhatsNew — shows a versioned "what changed" panel when the signed-in user is
 * behind the current APP_VERSION. Dismissing records APP_VERSION as last-seen
 * (per-user, localStorage) so it won't reappear. Optional "Take the tour"
 * button replays the product tours via JourneyContext.
 */
export default function WhatsNew() {
    const { user } = useAuth();
    const { restartAll } = useJourney();
    const userId = user?.user_id ?? null;
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);

    useEffect(() => {
        if (!userId) return;
        const unseen = unseenReleases(readLastSeenVersion(userId));
        if (unseen.length > 0) {
            setItems(unseen);
            setOpen(true);
        }
    }, [userId]);

    const dismiss = () => {
        writeLastSeenVersion(userId, APP_VERSION);
        setOpen(false);
    };

    const takeTour = () => {
        restartAll();
        dismiss();
    };

    if (!open || items.length === 0) return null;

    const offerTour = items.some((r) => r.offerTour);

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true" aria-label="What's new">
            <div className="card w-full max-w-md p-5">
                <div className="flex items-center justify-between mb-3">
                    <h2 className="font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                        <Sparkles size={18} className="text-brand-600" /> What's new
                    </h2>
                    <button type="button" onClick={dismiss} aria-label="Close" className="text-ink-400 hover:text-ink-700">
                        <X size={18} />
                    </button>
                </div>
                <div className="space-y-4 max-h-[60vh] overflow-y-auto">
                    {items.map((r) => (
                        <div key={r.version}>
                            <p className="text-sm font-semibold text-ink-800 dark:text-ink-200">
                                v{r.version} · {r.title}
                                <span className="text-xs font-normal text-ink-400 ml-2">{r.date}</span>
                            </p>
                            <ul className="mt-1 list-disc pl-5 space-y-1">
                                {r.changes.map((c) => (
                                    <li key={c} className="text-sm text-ink-600 dark:text-ink-400">{c}</li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                    {offerTour && (
                        <button type="button" onClick={takeTour} className="btn-secondary">Take the tour</button>
                    )}
                    <button type="button" onClick={dismiss} className="btn-primary">Got it</button>
                </div>
            </div>
        </div>
    );
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/WhatsNew.test.jsx
```

Expected: PASS.

- [ ] **Step 6: Mount `WhatsNew` and bump the version**

In `frontend/src/components/layouts/MainLayout.jsx`, import and render `<WhatsNew />` once inside the authenticated layout (near the top-level layout wrapper, alongside `JourneyOverlay` if present):

```jsx
import WhatsNew from '../WhatsNew';
// ...within the layout's returned JSX (top level):
<WhatsNew />
```

In `frontend/package.json`, set:

```json
  "version": "1.0.0",
```

- [ ] **Step 7: Lint + commit**

```bash
cd frontend && npx eslint src/releases.js src/components/WhatsNew.jsx src/components/layouts/MainLayout.jsx
cd .. && git add frontend/src/releases.js frontend/src/components/WhatsNew.jsx frontend/src/components/WhatsNew.test.jsx frontend/src/components/layouts/MainLayout.jsx frontend/package.json
git commit -m "feat(app): versioned What's New announcements with optional tour

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 13: Full verification before PR

**Files:** none (verification + gate).

- [ ] **Step 1: Frontend — full lint + build + tests**

```bash
cd frontend && npm run lint && npm run build && npx vitest run src/pages/Triage.test.jsx src/components/DepartmentQueue.test.jsx src/components/WhatsNew.test.jsx
```

Expected: lint clean, build succeeds, tests PASS.

- [ ] **Step 2: Backend — migration gate + touched suites**

```bash
cd backend && REDIS_URL="" python scripts/migrate_all_tenants.py 2>&1 | tail -5
REDIS_URL="" python -m pytest tests/test_queue.py tests/test_triage.py tests/test_clinical_blood_glucose.py tests/test_medical_history_triage.py -v
```

Expected: migration completes; all four suites PASS.

- [ ] **Step 3: Confirm alembic at head**

```bash
cd backend && REDIS_URL="" alembic heads
```

Expected: single head `b1c2d3e4f5a6`.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/clinical-flow-and-whats-new
gh pr create --base development --title "feat: clinical flow fixes + What's New announcements" --body "$(cat <<'EOF'
Implements the customer-reported batch: queue remove/cancel, triage routing to all modules, doctor RBS+BMI visibility, triage history, clear-previous-visit, and a versioned in-app "What's New" announcement.

Schema: one additive nullable column `medical_records.blood_glucose` (migration `b1c2d3e4f5a6`).

See `docs/superpowers/specs/2026-06-24-clinical-flow-and-whats-new-design.md`.

🤖 Generated with [RuFlo](https://github.com/ruvnet/ruflo)
EOF
)"
```

Expected: PR opened against `development`; CI (migrate-all-tenants, backend, frontend lint+build, react-doctor) runs.

---

## Self-Review

**Spec coverage:**
- Stream A (What's New, frontend changelog, versioned, optional tour) → Task 12. ✅
- Stream B1 (remove across modules) → Task 8 (DepartmentQueue remove) + existing checkout. ✅
- Stream B2 (triage routing to all modules + Reception + panels) → Tasks 5, 8, 9. ✅
- Stream B3 (cancel when not seen) → Task 3 (+ DepartmentQueue cancel in Task 8). ✅
- Stream B4 (dashboard/home only active/pending) → Task 3 (exclude Cancelled from active list; Completed already excluded). ✅
- Stream C (doctor RBS + BMI; schema) → Tasks 1, 2, 10. ✅
- Stream D1 (triage history visible) → Tasks 6, 11. ✅
- Stream D2 (clear previous visit, first item) → Tasks 4, 11. ✅

**Placeholder scan:** No TBD/TODO; every code step shows code; commands have expected output. The few "adapt to actual code shape" notes (Task 2 Step 4, Task 10) are paired with grep steps that reveal the exact shape first — acceptable because the surrounding handlers are hand-written dicts, not a fixed signature.

**Type consistency:**
- `MedicalRecord.blood_glucose` (Float) — defined Task 1, used Tasks 2, 6, 10. ✅
- `TERMINAL_QUEUE_STATUSES` / `ACTIVE_QUEUE_STATUSES` — Task 3 introduces TERMINAL; Task 4 reuses ACTIVE (existing). ✅
- `QueueCancel.reason`, `CloseVisitResult.closed` — defined Tasks 3/4, consumed Tasks 8/11. ✅
- `triage_history` item keys (`triage_id`, `blood_glucose`, `calculated_bmi`, `acuity_level`, `chief_complaint`, `nurse`, `date`) — defined Task 6, consumed Task 11. ✅
- `DepartmentQueue` props (`department`, `title`, `onChange`) — defined Task 8, used Task 9. ✅
- `releases.js` exports (`APP_VERSION`, `unseenReleases`, `readLastSeenVersion`, `writeLastSeenVersion`) — defined Task 12 Step 1, used Step 4/test. ✅

**Note for executor:** the "adapt to actual code shape" steps require reading the target handler first (grep steps included). If `ClinicalDesk.jsx`'s vitals object or `clinical.py`'s submit handler differ from the illustrative snippets, follow the established local pattern rather than the snippet verbatim.
