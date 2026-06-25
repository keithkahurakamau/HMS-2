# Performance Optimization (Query + Bundle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the audited N+1 query patterns and missing indexes, and split the frontend vendor bundle — all behavior-preserving.

**Architecture:** Backend N+1 loops are rewritten to batch their per-row lookups into single `IN (...)`/`GROUP BY` queries (identical JSON output, fewer round-trips). One additive index migration on `radiology_requests`. Frontend adds a Rollup `manualChunks` vendor split. Each change is verified against the unchanged response shape / a working build.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Pytest (live-server httpx integration), React/Vite, Rollup, Vitest.

## Global Constraints

- Branch: `perf/query-and-bundle-optimization` (already created off `development`). One combined PR → `development`.
- **Behavior-preserving:** no endpoint may change its JSON shape, field names, or ordering. Tests assert the response, not just the status.
- One schema change: additive indexes on `radiology_requests` (`patient_id`, `status`). Alembic revision chains from head `b1c2d3e4f5a6`; `migrate-all-tenants` must stay green (the model file is already imported by `migrate_all_tenants.py`). All other tasks keep the migration gate a no-op.
- Backend tests are live-server integration tests: server on `http://localhost:8000`, tenant `mayoclinic_db`, CSRF double-submit, `*_cookies` fixtures, run with `REDIS_URL=""`. Server is NOT in --reload mode — restart it once after backend edits (`pkill -f "uvicorn app.main:app"` then relaunch `REDIS_URL="" nohup uvicorn app.main:app --port 8000 --host 127.0.0.1 > <scratch>/uvicorn.log 2>&1 & disown`; wait for `/docs` 200). Set cookies once on the client (`client.cookies.update(...)`), bare requests — pristine output (0 warnings).
- Frontend: `npm run lint` 0 errors, `npm run build` succeeds; existing Vitest suites stay green.
- Commit messages end with `Co-Authored-By: RuFlo <ruv@ruv.net>`.

---

## File Structure

**Backend**
- `backend/app/models/radiology.py` — add `index=True` to `RadiologyRequest.patient_id` + `status`.
- `backend/alembic/versions/<rev>_radiology_request_indexes.py` — create the two indexes.
- `backend/app/routes/laboratory.py` — batch the lab-queue lookups.
- `backend/app/routes/inventory.py` — group the stock-sum query.
- `backend/app/routes/medical_history.py` — batch the doctor/nurse name lookups.
- `backend/app/routes/patient_portal.py`, `pharmacy.py`, `users.py` — batch smaller N+1s.
- Tests: extend `backend/tests/test_laboratory.py`, `backend/tests/test_inventory_locations.py`; the medical-history change is covered by `backend/tests/test_medical_history_triage.py` (extend assertions).

**Frontend**
- `frontend/vite.config.js` — add `build.rollupOptions.output.manualChunks` vendor split.
- `frontend/src/pages/Accounting.jsx` (+ subcomponents) — lazy-load a heavy import if cleanly deferrable.

---

### Task 1: Radiology request indexes (model + migration)

**Files:**
- Modify: `backend/app/models/radiology.py` (`RadiologyRequest.patient_id` line 34, `.status` line 50)
- Create: `backend/alembic/versions/c2d3e4f5a6b7_radiology_request_indexes.py`

**Interfaces:**
- Produces: indexes `ix_radiology_requests_patient_id`, `ix_radiology_requests_status`.

- [ ] **Step 1: Add `index=True` to the two columns**

In `backend/app/models/radiology.py`:
- `patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=False)`
- `status = Column(String(50), default="Pending", index=True)`

- [ ] **Step 2: Create the alembic revision**

Create `backend/alembic/versions/c2d3e4f5a6b7_radiology_request_indexes.py`:

```python
"""radiology_request indexes (perf)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-25

Additive indexes on the radiology worklist's hot filter/join columns. No data change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_radiology_requests_patient_id", "radiology_requests", ["patient_id"])
    op.create_index("ix_radiology_requests_status", "radiology_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_radiology_requests_status", table_name="radiology_requests")
    op.drop_index("ix_radiology_requests_patient_id", table_name="radiology_requests")
```

- [ ] **Step 3: Apply + verify**

```bash
cd backend && REDIS_URL="" python scripts/migrate_all_tenants.py 2>&1 | tail -3
REDIS_URL="" alembic heads 2>&1 | tail -1
```

Expected: "All N tenants migrated successfully."; head `c2d3e4f5a6b7`.

- [ ] **Step 4: Confirm the indexes exist**

```bash
cd backend && source venv/bin/activate && python3 - <<'PY'
from dotenv import dotenv_values
import psycopg2
cfg=dotenv_values(".env"); base=cfg["DATABASE_URL"].rsplit("/",1)[0]
c=psycopg2.connect(f"{base}/mayoclinic_db"); cur=c.cursor()
cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='radiology_requests' ORDER BY 1;")
print([r[0] for r in cur.fetchall()]); c.close()
PY
```

Expected: list includes `ix_radiology_requests_patient_id` and `ix_radiology_requests_status`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/radiology.py backend/alembic/versions/c2d3e4f5a6b7_radiology_request_indexes.py
git commit -m "perf(radiology): index radiology_requests.patient_id and status

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 2: Lab queue N+1 → batched lookups

**Files:**
- Modify: `backend/app/routes/laboratory.py` (`get_lab_queue`, ~lines 128–160)
- Test: `backend/tests/test_laboratory.py` (extend)

**Interfaces:**
- Consumes: `LabTest`, `Patient`, `User`, `LabTestCatalog`.
- Produces: `GET /api/laboratory/queue` returns the SAME list of dicts, built with 3 batched queries instead of 3×N.

- [ ] **Step 1: Read the full loop to capture the exact output dict**

```bash
sed -n '126,160p' backend/app/routes/laboratory.py
```

Note every key in the appended `result` dict (test_id, test_name, catalog_id, requires_barcode, patient_*, doctor, …) — the rewrite MUST produce the identical keys/values.

- [ ] **Step 2: Add/confirm a test asserting the queue response shape**

In `backend/tests/test_laboratory.py`, ensure there's a test that creates (or relies on seeded) lab tests and asserts `GET /api/laboratory/queue` returns rows with the expected keys and that a known patient's name/doctor resolve correctly. If the file already has a queue test, extend it to assert the patient and doctor fields are populated (the N+1 fix must keep them). Use cookies-once pattern.

Run it to establish GREEN baseline before refactor:

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_laboratory.py -v
```

Expected: PASS (records the current contract).

- [ ] **Step 3: Rewrite the loop to batch the three lookups**

Replace the per-row queries with batched maps. Example (adapt to the real dict keys from Step 1):

```python
tests = db.query(LabTest).filter(
    LabTest.status.in_(["Pending", "Pending Collection", "In Progress"])
).order_by(desc(LabTest.requested_at)).all()

patient_ids = {t.patient_id for t in tests}
user_ids = {t.ordered_by for t in tests}
catalog_ids = {t.catalog_id for t in tests if t.catalog_id is not None}

patients = {p.patient_id: p for p in db.query(Patient).filter(Patient.patient_id.in_(patient_ids)).all()} if patient_ids else {}
doctors = {u.user_id: u for u in db.query(User).filter(User.user_id.in_(user_ids)).all()} if user_ids else {}
catalogs = {c.catalog_id: c for c in db.query(LabTestCatalog).filter(LabTestCatalog.catalog_id.in_(catalog_ids)).all()} if catalog_ids else {}

result = []
for t in tests:
    patient = patients.get(t.patient_id)
    doctor = doctors.get(t.ordered_by)
    catalog = catalogs.get(t.catalog_id)
    result.append({
        # ... EXACTLY the same keys/values as before, reading from patient/doctor/catalog ...
    })
```

Keep every dict key and the `getattr(catalog, "requires_barcode", False)` style guards identical.

- [ ] **Step 4: Restart server, run the test → still GREEN**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_laboratory.py -v
```

Expected: PASS — identical contract, now batched.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/laboratory.py backend/tests/test_laboratory.py
git commit -m "perf(laboratory): batch lab-queue patient/doctor/catalog lookups (N+1)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 3: Inventory stock summary N+1 → GROUP BY

**Files:**
- Modify: `backend/app/routes/inventory.py` (the low-stock block, ~lines 246–252)
- Test: `backend/tests/test_inventory_locations.py` (extend)

**Interfaces:**
- Produces: the inventory summary endpoint returns the SAME `low_stock_alerts` / `expiring_batches`, computed with one grouped stock query.

- [ ] **Step 1: Read the block + identify the endpoint**

```bash
sed -n '230,256p' backend/app/routes/inventory.py
grep -n "@router.get" backend/app/routes/inventory.py | head
```

Identify the route path (for the test) and confirm the returned dict shape.

- [ ] **Step 2: Add a test asserting the summary shape**

In `backend/tests/test_inventory_locations.py`, add/extend a test that GETs the summary endpoint and asserts it returns `low_stock_alerts` (list of `{item_name, current_stock, threshold}`) and `expiring_batches`. Run → GREEN baseline.

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_inventory_locations.py -v
```

- [ ] **Step 3: Replace the per-item SUM with one GROUP BY**

```python
from sqlalchemy import func  # already imported

items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()  # noqa: E712
stock_by_item = dict(
    db.query(StockBatch.item_id, func.sum(StockBatch.quantity))
      .group_by(StockBatch.item_id)
      .all()
)
low_stock_items = []
for item in items:
    total_stock = stock_by_item.get(item.item_id) or 0
    if total_stock <= item.reorder_threshold:
        low_stock_items.append({"item_name": item.name, "current_stock": total_stock, "threshold": item.reorder_threshold})
```

Keep `expiring_batches` and the return dict unchanged.

- [ ] **Step 4: Restart server, run the test → GREEN**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_inventory_locations.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/inventory.py backend/tests/test_inventory_locations.py
git commit -m "perf(inventory): single grouped stock-sum query for low-stock alerts (N+1)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 4: Medical-history user-name lookups → batched

**Files:**
- Modify: `backend/app/routes/medical_history.py` (recent_visits loop ~line 113; triage_history loop ~line 130)
- Test: `backend/tests/test_medical_history_triage.py` (extend)

**Interfaces:**
- Produces: chart `recent_visits[].doctor` and `triage_history[].nurse` resolve to the same names, via one `User` query.

- [ ] **Step 1: Read both loops**

```bash
sed -n '107,150p' backend/app/routes/medical_history.py
```

- [ ] **Step 2: Run the existing chart test (baseline GREEN)**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_medical_history_triage.py -v
```

- [ ] **Step 3: Batch the name lookups**

Before the two loops, build one name map covering both doctor and nurse ids:

```python
person_ids = {rec.doctor_id for rec in recent_records} | {t.nurse_id for t in triage_rows}
names = {
    u.user_id: u.full_name
    for u in db.query(User).filter(User.user_id.in_(person_ids)).all()
} if person_ids else {}
```

Then in the loops replace the per-row `db.query(User)...` with `names.get(rec.doctor_id, "Unknown")` and `names.get(t.nurse_id, "Unknown")` — keep the exact same output keys.

- [ ] **Step 4: Extend the test to assert the nurse name resolves**

In `test_medical_history_triage.py`, after fetching the chart, assert `triage_history[0]["nurse"]` is a non-empty string (and unchanged behavior). Run → GREEN.

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_medical_history_triage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/medical_history.py backend/tests/test_medical_history_triage.py
git commit -m "perf(history): batch doctor/nurse name lookups in patient chart (N+1)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 5: Smaller N+1s (patient-portal, pharmacy report, users list)

**Files:**
- Modify: `backend/app/routes/patient_portal.py` (~line 251), `backend/app/routes/pharmacy.py` (~line 546), `backend/app/routes/users.py` (~line 199)

**Interfaces:**
- Produces: same responses; per-row lookups batched where cheap.

- [ ] **Step 1: patient_portal appts — batch the doctor lookup**

Read `sed -n '240,260p' backend/app/routes/patient_portal.py`. Before the `for a in appts:` loop, build `doctors = {u.user_id: u for u in db.query(User).filter(User.user_id.in_({a.doctor_id for a in appts})).all()}` and read `doctors.get(a.doctor_id)` in the loop. Keep output identical.

- [ ] **Step 2: pharmacy report — single grouped payment count**

Read `sed -n '535,560p' backend/app/routes/pharmacy.py`. The loop counts `Payment` per row; replace with one grouped count keyed by the row's invoice/dispense id (a `func.count` `group_by` query into a dict), read per row. Keep output identical.

- [ ] **Step 3: users list — batch or document**

Read `_serialize_user` (`users.py:175`): it calls `resolve_effective_permissions(db, user)` per user, which issues its own queries → N+1 across `User.all()`. If `resolve_effective_permissions` can be fed a pre-loaded permission/role map cheaply, do so. If batching it requires refactoring `resolve_effective_permissions` itself (non-trivial), DO NOT refactor that shared function under this perf pass — instead eager-load the `role` relationship on the user query (`joinedload(User.role)`) to remove the per-user role query, and leave a code comment that permission resolution remains per-user (staff lists are small; YAGNI). Note this decision in the report.

- [ ] **Step 4: Verify affected suites still pass**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_superadmin.py tests/test_profile.py -q 2>&1 | tail -3
```

(Whichever existing suites cover users/portal/pharmacy — run them; if none cover a changed endpoint, manually GET it with a cookie and confirm the JSON shape is unchanged, and say so in the report.)

Expected: PASS / unchanged JSON.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/patient_portal.py backend/app/routes/pharmacy.py backend/app/routes/users.py
git commit -m "perf(api): batch smaller N+1 lookups (portal appts, pharmacy report, users role)

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 6: Backend perf checkpoint

**Files:** none (verification).

- [ ] **Step 1: Run all touched/related backend suites**

```bash
cd backend && REDIS_URL="" python -m pytest tests/test_laboratory.py tests/test_inventory_locations.py tests/test_medical_history_triage.py tests/test_radiology_cancel.py tests/test_superadmin.py tests/test_profile.py -q 2>&1 | tail -4
```

Expected: all PASS (no contract regressions). (Skip `tests/test_api.py` — known pre-existing failures.)

---

### Task 7: Frontend vendor chunk split

**Files:**
- Modify: `frontend/vite.config.js` (add `build.rollupOptions.output.manualChunks`)

**Interfaces:**
- Produces: a separate long-cached `vendor` chunk in `dist/assets`.

- [ ] **Step 1: Add the manualChunks config**

In `frontend/vite.config.js`, add a `build` key to the `defineConfig` object (alongside `plugins`, `server`, `test`):

```js
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom', 'axios'],
        },
      },
    },
  },
```

(If any of those package names aren't dependencies, check `frontend/package.json` and include only the ones present — `react`, `react-dom` are certain; verify `react-router-dom` and `axios`.)

- [ ] **Step 2: Build and confirm the split**

```bash
cd frontend && npm run build 2>&1 | tail -15
ls -la dist/assets/*.js | grep -i vendor
```

Expected: build succeeds; a `vendor-*.js` chunk exists; the main `index-*.js` chunk is smaller than the prior 416 KB.

- [ ] **Step 3: Lint + existing tests still green**

```bash
cd frontend && npm run lint && npx vitest run src/components/DepartmentQueue.test.jsx src/pages/Triage.test.jsx
```

Expected: lint 0 errors; tests PASS (the split doesn't change runtime behavior).

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.js
git commit -m "perf(frontend): split react/router/axios into a cached vendor chunk

Co-Authored-By: RuFlo <ruv@ruv.net>"
```

---

### Task 8: Accounting chunk investigation + final verification + PR

**Files:**
- Modify (maybe): `frontend/src/pages/Accounting.jsx` (+ subcomponents) — lazy-load a heavy import if cleanly deferrable.

- [ ] **Step 1: Identify the heaviest import in the Accounting page**

```bash
cd frontend && grep -nE "^import " src/pages/Accounting.jsx | head -40
```

Look for a heavy, not-needed-on-first-paint import (e.g. a big table/export/util or a rarely-used sub-tab component). If one exists, convert it to `const X = lazy(() => import('...'))` wrapped in `<Suspense>`, mirroring how `App.jsx` lazy-loads pages. If nothing is cleanly deferrable (the size is just many small components), DO NOT force it — document in the report and the PR that the 145 KB is inherent and left as-is (YAGNI).

- [ ] **Step 2: Build + verify (whether or not a change was made)**

```bash
cd frontend && npm run build 2>&1 | tail -15
```

Expected: build succeeds; if a deferral was made, the Accounting chunk shrank and a new lazy chunk appears.

- [ ] **Step 3: Full final gate**

```bash
cd frontend && npm run lint && npm run build && npx vitest run
cd ../backend && REDIS_URL="" python scripts/migrate_all_tenants.py 2>&1 | tail -2 && REDIS_URL="" alembic heads 2>&1 | tail -1
```

Expected: frontend lint 0 errors, build ✓, Vitest suites pass; migration green; alembic head `c2d3e4f5a6b7`.

- [ ] **Step 4: Commit (if Accounting changed), push, open PR**

```bash
git add -A
git commit -m "perf(frontend): lazy-load heavy Accounting import" --allow-empty
git push -u origin perf/query-and-bundle-optimization
gh pr create --base development --title "perf: eliminate audited N+1s, add radiology indexes, split vendor bundle" --body "$(cat <<'EOF'
Measurement-driven performance pass. Eliminates the N+1 query patterns and missing indexes found in the audit, and splits the frontend vendor bundle. All backend changes are behavior-preserving (same JSON shape, verified by tests).

- Radiology: indexed `patient_id` + `status` (migration `c2d3e4f5a6b7`, additive).
- Batched N+1s: lab queue (3 queries/test → 3 total), inventory low-stock (per-item SUM → one GROUP BY), patient chart doctor/nurse names, patient-portal appts, pharmacy report counts, users-list role eager-load.
- Frontend: react/router/axios split into a cached `vendor` chunk; Accounting heavy import deferred where possible.

See docs/superpowers/specs/2026-06-25-perf-query-and-bundle-design.md.

🤖 Generated with [RuFlo](https://github.com/ruvnet/ruflo)
EOF
)"
```

Expected: PR opened against `development`; CI (incl. migrate-all-tenants) runs.

---

## Self-Review

**Spec coverage:**
- #1 radiology indexes → Task 1. ✅
- #2 lab queue N+1 → Task 2. ✅
- #3 inventory stock N+1 → Task 3. ✅
- #4 medical-history name lookups → Task 4. ✅
- #5 smaller N+1s (users/portal/pharmacy) → Task 5. ✅
- #6 vendor chunk split → Task 7. ✅
- #7 Accounting chunk → Task 8. ✅
- Behavior-preserving verification → each backend task asserts the unchanged response; Task 6 runs the suite set. ✅

**Placeholder scan:** No TBD/TODO. The "adapt to the real dict keys" notes (Tasks 2, 5) are paired with explicit `sed`/`grep` read steps that reveal the exact shape — required because these are hand-built response dicts that MUST be reproduced verbatim. Task 5 Step 3 and Task 8 Step 1 give explicit document-and-defer fallbacks (YAGNI) rather than vague "optimize."

**Type consistency:**
- Alembic: revision `c2d3e4f5a6b7`, down_revision `b1c2d3e4f5a6` (current head) — Task 1 + Task 8 reference the same new head. ✅
- Batched-map pattern (`{id: obj}` then `.get(id)`) consistent across Tasks 2/4/5. ✅
- `manualChunks.vendor` chunk name referenced consistently in Task 7. ✅

**Note for executor:** the backend N+1 rewrites are refactors — the single most important property is that the endpoint's JSON output is byte-for-byte the same. Always read the existing response-dict construction first and reproduce every key/guard exactly; the tests encode the contract.
