# Performance Optimization — Query Efficiency + Frontend Bundle — Design

**Date:** 2026-06-25
**Branch:** `perf/query-and-bundle-optimization` (off `development`)
**Delivery:** one combined PR → `development` (then promote `development → beta → main`)

## Context

User asked to "make response times as minimal as possible." A **measurement-driven audit**
(local server, seeded `mayoclinic_db`) found **no current bottleneck** at local data volumes
(endpoints 14–39 ms), but several **N+1 query patterns and missing indexes** that degrade
linearly as data grows (production already carries much more data — e.g. 146 pending
prescriptions). User approved fixing **all** findings.

### Measured baseline (local, best-of-5, small dataset)

| Endpoint | ms | rows in play |
|----------|----|--------------|
| `/api/laboratory/queue` | 38.8 | 8 lab tests |
| `/api/radiology/` | 34.9 | 14 requests |
| `/api/patients/?search=` | 25.7 | 476 patients |
| `/api/clinical/queue` | 25.2 | 261 queue |
| `/api/queue/?department=Pharmacy` | 22.0 | 261 queue |
| `/api/clinical/prescriptions/pending` | 21.4 | 8 records |

These are floors; the N+1s below scale with row count.

## Decisions (confirmed with user)

- Scope: **all findings** (#1–#7 below).
- Behavior-preserving: every backend fix must return the **exact same response shape** —
  verified by tests asserting the response, not just status.
- Soft constraint: only #1 (radiology indexes) is a schema change; everything else is
  code-only.

## Global constraints

- One schema change: additive indexes on `radiology_requests` (`patient_id`, `status`).
  Needs an alembic revision chained from head; `migrate-all-tenants` must stay green; the
  model file is already imported by `migrate_all_tenants.py`. Everything else keeps the
  migration gate a no-op.
- N+1 rewrites must not change the JSON shape or ordering of any endpoint. Lean on existing
  suites (`test_laboratory.py`, `test_inventory_locations.py`) plus added response assertions.
- Frontend: keep `npm run build` green and the app functional; verify chunk split in `dist`.

---

## Findings & fixes

### #1 — Missing indexes on `RadiologyRequest` (schema change)
`models/radiology.py:34,50`: `patient_id` (FK) and `status` are unindexed; the radiology
worklist filters by `status` and joins `Patient`.
**Fix:** add `index=True` to both columns + an alembic revision creating
`ix_radiology_requests_patient_id` and `ix_radiology_requests_status`. Additive,
backward-compatible.

### #2 — Lab queue N+1 (`laboratory.py:137–140`)
Per test, 3 separate queries (Patient, User, LabTestCatalog) inside the loop.
**Fix:** fetch the tests with eager joins (`join`/`joinedload` for patient, ordered_by user,
catalog) or batch the three lookups with `IN (...)` maps, then build the same `result` dicts.
Identical output, 3 queries total instead of 3×N.

### #3 — Inventory stock summary N+1 (`inventory.py:247–248`)
Per active item, a separate `SUM(StockBatch.quantity)` query.
**Fix:** one grouped query — `SELECT item_id, SUM(quantity) ... GROUP BY item_id` — into a
dict, then read per item. Same output.

### #4 — Medical-history per-row user lookups (`medical_history.py:113,130`)
Doctor-per-recent-visit and nurse-per-triage-row, each ≤10 but two separate N+1s.
**Fix:** collect the distinct `doctor_id`/`nurse_id`, one `User.user_id.in_(...)` query into a
`{id: full_name}` map, read from it. Same output.

### #5 — Smaller N+1s
- `users.py:199` — `_serialize_user(db, u)` per user across `User.all()`. If it issues
  per-user queries (role/permission), batch them or eager-load.
- `patient_portal.py:251` — doctor lookup per appointment → batch with `IN`.
- `pharmacy.py:546` — `COUNT(Payment)` per row in the dispense report → single grouped count.
**Fix:** batch each; preserve output shape.

### #6 — Frontend vendor chunk split (`frontend/vite.config.js`)
Routes are already `lazy()`-loaded, but the main `index` chunk is **416 KB / 128 KB gzip**
(React, router, axios, shared context) and reloads with every app deploy.
**Fix:** add Rollup `manualChunks` to split stable vendor libs (`react`, `react-dom`,
`react-router-dom`, `axios`) into a long-cached `vendor` chunk so app-code changes don't
bust the vendor cache. Verify the split in `dist/assets` and that the app still boots.

### #7 — Accounting page chunk (145 KB)
`Accounting-*.js` is the largest page chunk.
**Fix:** identify the heaviest import in `pages/Accounting.jsx` (and its subcomponents) and
lazy-load it (e.g. a sub-tab or a heavy table/util) if it isn't needed on first paint. Only
defer what's genuinely deferrable; do not break the page. If nothing is cleanly deferrable,
document that and leave it (YAGNI) — note it in the PR.

---

## Testing

- **Backend:** for each N+1 fix, a test (or extension of the existing suite) that asserts the
  endpoint's JSON response is unchanged (key fields + ordering) after the refactor. Where a
  live-server query-count assertion isn't practical, response-shape equality is the gate.
  `test_laboratory.py`, `test_inventory_locations.py` already exist — extend them.
- **Radiology indexes:** `migrate-all-tenants` green; `alembic` at the new head; the index
  exists (a migration-applies check).
- **Frontend:** `npm run lint` 0 errors, `npm run build` succeeds, the `vendor` chunk appears
  in `dist/assets`, and the app renders (existing Vitest suites stay green).

## Migration / release notes

- One additive index migration on `radiology_requests` — must pass the gate at development,
  beta, main. No data change, no downtime risk (small table).
- All other changes are code-only; migration gate stays a no-op for them.

## Out of scope / YAGNI

- Render cold-start mitigation (ops-level: keep-warm ping / paid tier) — noted, not in this PR.
- Caching layers / query result caching — premature; revisit if measurement shows need.
- Rewriting endpoints that measured fine and have no N+1.
- `CREATE INDEX CONCURRENTLY` — `radiology_requests` is small; a normal indexed migration is
  fine and keeps the alembic transaction simple.
