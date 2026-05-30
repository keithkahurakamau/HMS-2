# Audit 03 — Test Coverage Gap Analysis

**Auditor:** TEST-COVERAGE
**Branch:** `audit/world-class-codebase-20260530`
**Date:** 2026-05-30
**Phase:** Gap analysis only — no test code written in this phase.

---

## 1. Scope & Method

- Backend: 37 route files in `backend/app/routes/` mapped against 11 pytest suites in
  `backend/tests/` + a 9-file accounting suite (`backend/tests/accounting/`).
- HTTP endpoint census via `@router.*` / `@tenant_router.*` / `@admin_router.*` decorators.
  `websockets.py` exposes 3 `@router.websocket` endpoints (counted separately — not HTTP).
- Frontend: 4 test files vs. 56 page/component `.jsx` sources under
  `frontend/src/pages` + `frontend/src/components`.
- Convention confirmed: backend pytest hits a **live server** with real JWT cookies minted in
  `backend/tests/conftest.py` (bypassing the login rate-limit); the accounting suite is an
  in-process **service-layer** suite (`backend/tests/accounting/conftest.py`). Frontend uses
  **Vitest + React Testing Library** with a mocked `apiClient` (`renderWithProviders`).

### Headline numbers

| Metric | Value |
|---|---|
| Total HTTP endpoints (across 36 HTTP route files) | **312** |
| WebSocket endpoints | 3 |
| Route files with **zero** test coverage | **22 of 37 files** |
| Endpoints with **no** coverage (full or partial) | **~200 of 312** |
| Frontend source files (pages + components) | 56 |
| Frontend files with **no** test | **52 of 56** |
| Backend HTTP suites | 11 + accounting (9 files) |

> Endpoint counts per file: auth 2, users 6, admin 19, billing 4, payhero_payment 6,
> payhero_admin 7, payhero_superadmin 6, platform_payhero 8, clinical 6, queue 2, patients 9,
> appointments 7, pharmacy 6, laboratory 13, radiology 9, settings 5, cheques 12, triage 3,
> notifications 3, medical_history 7, accounting 24, accounting_debtors 10, accounting_bank 10,
> accounting_config 17, inventory 7, branding 2, referrals 3, public 10, analytics 1,
> messaging 12, wards 6, dashboard 1, patient_portal 6, privacy 6, support 11, websockets 3(ws).

---

## 2. Coverage Matrix — Backend Routes

Legend: **yes** = real assertions on behavior/edge cases · **partial** = happy-path / RBAC-status
only, no business-logic or negative assertions · **no** = zero tests.

| Module / route file | Endpoints | Tests? | Where | Risk if untested |
|---|---|---|---|---|
| `auth.py` (login/logout) | 2 | partial | `test_api.py` (wrong-pw, unknown-user → 401) | **HIGH** — logout, token rotation, rate-limit, tenant binding untested |
| `users.py` (me/permissions/modules/CRUD) | 6 | partial | `test_api.py` (identity, permissions) | MED — deactivate + create-user not asserted |
| `admin.py` (users/roles/RBAC/pricing/audit) | 19 | partial | `test_api.py` (metrics/staff/audit/pricing RBAC) | **HIGH** — role/permission **mutations** (PUT roles, user perms) untested; privilege-escalation surface |
| `patients.py` | 9 | partial | `test_api.py`, `test_patients.py` | MED — create/update/delete + access-grant logic |
| `queue.py` | 2 | yes | `test_api.py`, `test_queue.py` | LOW |
| `appointments.py` | 7 | yes | `test_appointments.py` | LOW |
| `clinical.py` (queue/submit/prescriptions) | 6 | partial | `test_api.py` | **HIGH** — `/submit` (record + Rx creation) not asserted; prescription return path untested |
| `laboratory.py` | 13 | yes | `test_laboratory.py`, `test_api.py` | LOW–MED — result-entry/reject edges |
| `pharmacy.py` (dispense/mpesa) | 6 | yes | `test_pharmacy.py` + accounting suite | LOW — well covered incl. STK init |
| `radiology.py` | 9 | yes | `test_radiology.py`, `test_api.py` | LOW |
| `settings.py` | 5 | yes | `test_settings.py` | LOW |
| `cheques.py` | 12 | yes | `test_cheques.py` | LOW — lifecycle transitions covered |
| `billing.py` (process-payment/mpesa-txns) | 4 | partial | `test_api.py` (RBAC + mpesa-txns list) | **HIGH** — `/process-payment` settlement logic not asserted |
| **`triage.py`** (queue/submit/latest) | 3 | **no** | — | **HIGH** — new module; routing/acuity/BMI/queue-close logic 100% untested |
| **`payhero_payment.py`** (stk/status/callback) | 6 | **no** (route-level) | service STK tested in accounting suite | **CRITICAL** — webhook signature verify + callback settlement untested |
| **`payhero_admin.py`** (per-tenant config) | 7 | **no** | — | **HIGH** — tenant secret storage, unmatched-txn assign untested |
| **`payhero_superadmin.py`** (provisioning) | 6 | **no** | — | **HIGH** — operator config-write + webhook-health untested |
| **`platform_payhero.py`** (subscription rail) | 8 | **no** | — | **CRITICAL** — operator's ONLY revenue rail; charge/config untested |
| **`accounting.py`** | 24 | partial | service-level posting tested | MED — 24 HTTP endpoints not hit at route level |
| `accounting_bank.py` | 10 | partial | `test_phase6_bank.py` (service) | MED |
| `accounting_config.py` | 17 | **no** | — | MED — chart-of-accounts/tax config |
| `accounting_debtors.py` | 10 | partial | `test_phase5_debtors.py` (service) | MED |
| `medical_history.py` | 7 | **no** | — | MED — clinical data read surface |
| `inventory.py` | 7 | partial | `test_api.py` (RBAC) | MED — stock mutation untested |
| `wards.py` | 6 | partial | `test_api.py` (board/inventory) | LOW–MED |
| `messaging.py` | 12 | **no** | — | MED — internal comms, no isolation test |
| `notifications.py` | 3 | **no** | — | LOW |
| `patient_portal.py` | 6 | **no** | — | **HIGH** — patient-facing auth + own-record scoping |
| `privacy.py` | 6 | **no** | — | **HIGH** — consent/data-access; compliance surface |
| `branding.py` | 2 | **no** | — | LOW |
| `referrals.py` | 3 | **no** | — | LOW |
| `support.py` (tenant + admin routers) | 11 | **no** | — | MED — cross-tenant ticket leakage risk |
| `public.py` | 10 | partial | `test_superadmin.py` (hospital list, superadmin login) | MED — public endpoints, abuse surface |
| `analytics.py` | 1 | **no** | — | LOW |
| `dashboard.py` | 1 | partial | `test_api.py` | LOW |
| `websockets.py` (3 ws) | 3 | **no** | — | MED — payment WS auth/tenant scoping untested |

**Superadmin tenant management** (`/api/public/superadmin/...`) is **yes/partial** —
`test_superadmin.py` covers token-required (401), cross-tenant patient listing, feature-flag /
plan-limit / notes PATCH. But **tenant PROVISIONING** (`provision_tenant` in
`services/tenant_provisioning.py:495` — DB creation + model migration) has **no** test.

---

## 3. Existing Test Quality Assessment

**Strengths:**
- `test_api.py` is genuinely strong on **RBAC negative cases**: e.g. `test_doctor_blocked_from_metrics`
  (403), `test_nurse_does_not_have_billing_manage`, `test_lab_tech_blocked_from_central_inventory`,
  and a sweep `test_all_protected_endpoints_reject_unauthenticated` asserting 401. Real assertions,
  not smoke.
- Accounting suite has excellent **edge-case** coverage: overpayment rejection, already-paid
  rejection, partial payment, walk-in 404, MPESA idempotency (`test_mpesa_idempotent_returns_existing_pending`),
  and ledger-posting verification.
- Frontend `Pharmacy/Appointments/Patients.test.jsx` are real RTL suites (48–74 `it/expect` each)
  with mocked `apiClient`, fixtures, and `userEvent` interaction — not smoke.

**Weaknesses / risks:**
- **Smoke-only:** `frontend/src/test/smoke.test.js` (2 assertions) is the only coverage for 52 files.
- **Partial = status-code-only:** much of `test_api.py` asserts only `status_code == 200` for
  mutation-capable modules (clinical `/submit`, billing `/process-payment`) — no assertion that the
  side effect (record created, invoice settled, queue advanced) actually happened.
- **No webhook/signature tests anywhere:** `core/payhero_webhook.py::_signature_valid` (HMAC-SHA256 +
  `compare_digest`, fail-closed) and `verify_payhero` have **zero** tests. This is the security
  boundary for money settlement.
- **No tenant-isolation tests:** no test asserts that tenant A cannot read tenant B's data via a
  forged/mismatched `X-Tenant-ID` or a cross-tenant callback `db_name`.
- **Flaky pattern:** backend suites depend on **seeded live data** in `mayoclinic_db` (hard-coded
  patient/user IDs, `test_get_by_id` on id=1). Re-seeding or data drift will break these
  non-deterministically. The accounting suite (self-contained fixtures) is the better model.
- **`scope="module"` cookie fixtures** share state across a module — acceptable for read tests, but
  risky if mutation tests are added to the same module without isolation.

---

## 4. Prioritized Highest-Value Missing Tests

Ordered by blast radius (money / tenant isolation / new code / privilege).

1. **Pay Hero webhook signature verification** (`core/payhero_webhook.py`) — the money boundary.
2. **Tenant callback isolation** (`payhero_payment.py::payhero_callback`) — wrong/forged
   `{tenant_db}` must not settle in another tenant's DB.
3. **Platform (subscription) charge + callback** (`platform_payhero.py`) — operator's only revenue.
4. **Triage module end-to-end** (`triage.py`) — brand-new, zero coverage, mutates two queues.
5. **RBAC mutation negative cases** (`admin.py` role/permission PUTs) — privilege-escalation guard.
6. **Billing `/process-payment` settlement** — assert invoice state transitions, not just 200.
7. **Clinical `/submit`** — assert MedicalRecord + prescription rows created.
8. **Per-tenant Pay Hero config write** (`payhero_admin.py`) — secret storage + retrieval.
9. **Patient portal own-record scoping** (`patient_portal.py`) — a patient must not read another's data.
10. **Tenant provisioning** (`services/tenant_provisioning.py::provision_tenant`).
11. **Privacy/consent endpoints** (`privacy.py`) — compliance surface.
12. **Support ticket cross-tenant isolation** (`support.py`).
13. **Payment WebSocket auth/tenant scoping** (`websockets.py /ws/payments/{tenant_db}`).
14. **Unmatched-transaction assignment** (`payhero_admin.py /unmatched/{txn_id}/assign`).
15. **Frontend payment/superadmin pages** (PaymentsManager, PlatformSubscriptions, MpesaSettings, Triage).

---

## 5. Concrete Proposed Test Cases — Top 15 Gaps (Phase 2 ready)

### Gap 1 — Pay Hero webhook signature (`tests/test_payhero_webhook.py`, service-style)
- `test_valid_hmac_signature_passes` — body signed with the tenant secret → `verify_payhero` returns raw bytes.
- `test_invalid_signature_returns_401` — tampered body / wrong secret → `HTTPException(401)`.
- `test_sha256_prefixed_form_accepted` — header `sha256=<hex>` validates identically to bare hex.
- `test_missing_signature_header_fails_closed` — no `x-payhero-signature` → 401, never 200.
- `test_compare_digest_is_constant_time` — assert `_signature_valid` uses `hmac.compare_digest` (no early-return on first byte mismatch).

### Gap 2 — Tenant callback isolation (`tests/test_payhero_callback.py`)
- `test_callback_resolves_tenant_from_path` — `/callback/mayoclinic_db` settles in mayoclinic only.
- `test_unknown_tenant_db_acks_200_but_does_not_settle` — bogus `{tenant_db}` → 200, no receipt written anywhere.
- `test_callback_cross_tenant_receipt_not_applied` — receipt for tenant A posted to tenant B's URL → rejected/ignored.
- `test_duplicate_receipt_is_idempotent` — same `receipt_number` twice → single transaction (UNIQUE guard).
- `test_non_json_body_after_valid_sig_returns_ignored` — verified but non-JSON → `{"status":"ignored"}`.

### Gap 3 — Platform subscription rail (`tests/test_platform_payhero.py`)
- `test_charge_requires_superadmin_token` — non-superadmin → 401/403.
- `test_charge_initiates_stk_against_platform_account` — uses master-DB secret, not a tenant's.
- `test_platform_callback_settles_in_master_db` — `PLAT-<tenant>-<nonce>` ref settles subscription, master DB only.
- `test_platform_callback_wrong_secret_rejected` — signed with a tenant secret → 401.
- `test_platform_callback_pushes_ws_update` — successful settle publishes `payment:platform` topic.

### Gap 4 — Triage module (`tests/test_triage.py`, live-server)
- `test_queue_requires_triage_read_permission` — nurse 200, role without `triage:read` → 403.
- `test_queue_ordered_by_acuity_then_arrival` — acuity 1 before acuity 4; ties by `joined_at`.
- `test_submit_creates_record_and_closes_triage_row` — Triage queue row → `Completed`; TriageRecord persisted.
- `test_submit_routes_patient_to_disposition_queue` — new Consultation queue row carries assessed acuity.
- `test_submit_does_not_double_queue` — already-active disposition row → acuity refreshed, no duplicate.
- `test_submit_derives_bmi_when_missing` — weight+height given, no `calculated_bmi` → server computes it.
- `test_acuity_clamped_to_1_5` — stray acuity 9 or 0 → clamped into [1,5]; null → 3.
- `test_submit_unknown_patient_returns_404`.
- `test_latest_returns_most_recent_or_null` — newest TriageRecord; null when never triaged.

### Gap 5 — RBAC mutation guards (`tests/test_admin_rbac.py`)
- `test_doctor_cannot_grant_self_permissions` — non-`roles:manage` PUT user perms → 403.
- `test_role_permission_update_persists_and_is_enforced` — grant then 200 on the gated route.
- `test_cannot_delete_in_use_role` — delete role with assigned users → 4xx, role intact.
- `test_pricing_mutation_blocked_for_non_admin` — doctor POST `/admin/pricing` → 403.

### Gap 6 — Billing settlement (`tests/test_billing_settlement.py`)
- `test_process_payment_full_marks_invoice_paid` — assert `status=Paid`, `amount_paid` exact.
- `test_process_payment_partial_keeps_partially_paid`.
- `test_process_payment_overpayment_rejected_400`.
- `test_process_payment_requires_billing_manage` — nurse → 403.

### Gap 7 — Clinical submit (`tests/test_clinical_submit.py`)
- `test_submit_creates_medical_record` — row count +1, fields persisted.
- `test_submit_with_prescription_creates_pending_rx` — appears in `/prescriptions/pending`.
- `test_submit_requires_clinical_write` — receptionist → 403.

### Gap 8 — Per-tenant Pay Hero config (`tests/test_payhero_admin.py`)
- `test_config_write_stores_webhook_secret` — POST then GET round-trips (secret masked in GET).
- `test_config_requires_admin_permission`.
- `test_unmatched_transaction_assign_links_to_invoice`.
- `test_test_stk_uses_tenant_account`.

### Gap 9 — Patient portal scoping (`tests/test_patient_portal.py`)
- `test_patient_can_read_own_records`.
- `test_patient_cannot_read_other_patient_records` — 403/404, no data leak.
- `test_portal_requires_patient_auth` — unauth → 401.

### Gap 10 — Tenant provisioning (`tests/test_provisioning.py`, service-level)
- `test_provision_creates_database_and_migrates_all_models` — every model table exists post-provision.
- `test_provision_seeds_default_roles_and_permissions`.
- `test_provision_is_idempotent_or_rejects_duplicate_domain`.

### Gap 11 — Privacy/consent (`tests/test_privacy.py`)
- `test_record_consent_persists`.
- `test_access_log_written_on_patient_view`.
- `test_consent_endpoints_require_auth`.

### Gap 12 — Support isolation (`tests/test_support.py`)
- `test_tenant_sees_only_own_tickets` — tenant A list excludes tenant B tickets.
- `test_reply_requires_support_manage`.
- `test_admin_inbox_requires_superadmin`.

### Gap 13 — Payment WebSocket (`tests/test_ws_payments.py`)
- `test_ws_payments_rejects_unauthenticated_connection`.
- `test_ws_payments_scoped_to_tenant` — tenant A socket never receives tenant B events.

### Gap 14 — Unmatched txn assignment (`tests/test_payhero_admin.py`)
- `test_assign_unmatched_settles_target_invoice`.
- `test_assign_unmatched_already_assigned_rejected`.

### Gap 15 — Frontend high-risk pages (Vitest + RTL)
- `MpesaSettings.test.jsx` — renders saved config, masks secret, save calls `apiClient.post`, error toast on 4xx.
- `PaymentsManager.test.jsx` — lists transactions, filters, handles empty state.
- `PlatformSubscriptions.test.jsx` — renders tenant billing rows, charge action calls charge endpoint.
- `Triage.test.jsx` — queue renders ordered, submit posts vitals, validates acuity, shows route-to message.
- `ClinicalDesk.test.jsx` — triage prefill loads latest vitals on patient select.

---

## 6. Recommended Phase-2 Sequencing

1. **Security/money first** (Gaps 1–3, 8, 14) — webhook signature, tenant isolation, platform rail.
2. **New code** (Gap 4 — triage backend + Gap 15 Triage frontend) before it accretes more callers.
3. **Privilege & settlement** (Gaps 5–7).
4. **Compliance & isolation** (Gaps 9–13).
5. Backfill **deterministic fixtures** for live-server suites to kill the seeded-data flakiness
   (adopt the accounting suite's self-contained-fixture model).
