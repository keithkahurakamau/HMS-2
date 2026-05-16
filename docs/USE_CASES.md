# MediFleet — Complete Use Case Catalog

**System**: MediFleet Hospital Management System (HMS-2)  
**Version**: 1.0 | **Date**: 2026-05-16 | **Review**: 2027-05-16

---

## How to Read This Document

Each use case follows the Cockburn structured format:

```
### MODULE-UC-NNN: Use Case Name
Goal Level: Summary (S) | User-goal (U) | Sub-function (SF)
Primary Actor: Role
Supporting Actors: Other roles / external systems
Module Required: module_key (or "always-on")
Permission Required: codename

Preconditions: numbered list
Main Success Scenario: numbered steps
Alternative Flows: A1 (trigger): response
Postconditions (Success): DB state, audit entries
Postconditions (Failure): what was rolled back
Business Rules: BR-MODULE-NN: rule text
Data Validation Rules: field → constraint
```

**Permission codenames** follow the pattern `resource:action`.  
**Effective permissions** = (role_perms ∪ explicit_grants) − explicit_revokes.

---

## Part 1: System Context

### 1.1 System Boundary

MediFleet comprises:
- **FastAPI backend** (Python) — REST API + WebSocket server, port 8000
- **React 19 frontend** — SPA served by nginx, port 80/443
- **PostgreSQL databases** — one master (`hms_master`) + one per hospital tenant
- **Redis** — WebSocket pub/sub, entitlement cache (60s TTL), dashboard cache (30s TTL)
- **Safaricom Daraja API** — external M-Pesa payment processing (STK push, callbacks)
- **SMTP server** — external (for password reset emails in production)
- **ODPC** — Office of the Data Protection Commissioner (external recipient of breach notifications)

### 1.2 Actor Catalog

| Actor | System Access | Entry Point | Auth Type |
|---|---|---|---|
| SUPERADMIN | Master DB + all tenants | /superadmin | Bearer token (localStorage) |
| ADMIN | Tenant DB, all modules (users:manage) | /app/admin | JWT HttpOnly cookie |
| DOCTOR | Tenant DB, clinical modules | /app/clinical | JWT HttpOnly cookie |
| NURSE | Tenant DB, wards | /app/wards | JWT HttpOnly cookie |
| PHARMACIST | Tenant DB, pharmacy | /app/pharmacy | JWT HttpOnly cookie |
| LABORATORY_TECH | Tenant DB, laboratory | /app/laboratory | JWT HttpOnly cookie |
| RADIOLOGIST | Tenant DB, radiology | /app/radiology | JWT HttpOnly cookie |
| BILLING_OFFICER | Tenant DB, billing | /app/billing | JWT HttpOnly cookie |
| RECEPTIONIST | Tenant DB, patients | /app/patients | JWT HttpOnly cookie |
| PATIENT | Tenant DB (read-only) | /patient | HttpOnly cookie (portal_token) |

### 1.3 Summary-Level Use Cases

| ID | Summary Use Case | Primary Actor |
|---|---|---|
| UC-SUM-01 | Manage Hospital Tenant | SUPERADMIN |
| UC-SUM-02 | Manage Staff and Permissions | ADMIN |
| UC-SUM-03 | Process a Patient Visit (Outpatient) | RECEPTIONIST, DOCTOR, multiple |
| UC-SUM-04 | Manage Inpatient Stay | NURSE, DOCTOR, BILLING_OFFICER |
| UC-SUM-05 | Process Laboratory Workflow | DOCTOR, LABORATORY_TECH |
| UC-SUM-06 | Process Radiology Workflow | DOCTOR, RADIOLOGIST |
| UC-SUM-07 | Fulfil Pharmacy Order | PHARMACIST |
| UC-SUM-08 | Process Billing and Payment | BILLING_OFFICER |
| UC-SUM-09 | Manage Inventory | ADMIN, PHARMACIST |
| UC-SUM-10 | Communicate and Notify | All Staff |
| UC-SUM-11 | Maintain KDPA Compliance | ADMIN, DPO, DOCTOR |

---

## Part 2: Authentication Use Cases

### AUTH-UC-001: Log In to the System
**Goal Level**: User-goal | **Primary Actor**: Any Staff User  
**Module Required**: auth (always-on) | **Permission Required**: none

**Preconditions**:
1. User account exists with `is_active = True` in the tenant DB.
2. The tenant is active in `hms_master.tenants`.
3. The HTTP request includes `X-Tenant-ID` header matching a valid `db_name`.

**Main Success Scenario**:
1. User navigates to `/portal`, selects their hospital (sets `X-Tenant-ID`).
2. User navigates to `/login` and enters email and password.
3. System verifies the `X-Tenant-ID` header is present.
4. System routes to the tenant's PostgreSQL database.
5. System queries `users` table by email.
6. System checks `is_active = True`.
7. System checks `locked_until IS NULL OR locked_until < NOW()`.
8. System verifies bcrypt hash of the provided password.
9. System resets `failed_login_attempts = 0`, `locked_until = NULL`.
10. System checks `must_change_password` flag.
11. System generates JWT `access_token` (15-min TTL) and `refresh_token` (7-day TTL).
12. System inserts a `RefreshToken` record with `token_hash` (SHA-256), `jti`, `user_agent`, `ip_address`.
13. System sets HttpOnly cookies: `access_token`, `refresh_token`, `csrf_token`.
14. System returns user profile, role, and effective permissions.
15. Frontend routes to the role-based landing page.

**Alternative Flows**:
- A1 (Missing X-Tenant-ID header): HTTP 400 "X-Tenant-ID header is required. Pick a hospital before signing in."
- A2 (Tenant not found / inactive): HTTP 404 / 403.
- A3 (User not found): HTTP 401 "Invalid credentials." (no email enumeration).
- A4 (Account deactivated): HTTP 403 "Account is deactivated."
- A5 (Account locked): HTTP 403 "Account locked. Try again in N minutes."
- A6 (Wrong password, attempts < 5): Increment `failed_login_attempts`; HTTP 401 "Invalid credentials."
- A7 (Wrong password, attempts ≥ 5): Set `locked_until = NOW() + 15 minutes`; HTTP 403 "Account locked."
- A8 (`must_change_password = True`): HTTP 403 with code "PASSWORD_CHANGE_REQUIRED" and `X-User-ID` header; frontend routes to `/app/change-password`.

**Postconditions (Success)**:
- `RefreshToken` record in DB (`revoked = False`).
- `failed_login_attempts = 0`, `locked_until = NULL`.
- Three HttpOnly cookies set on the browser.

**Business Rules**:
- BR-AUTH-01: Rate limit: 5 login attempts per minute per IP (SlowAPI).
- BR-AUTH-02: Lockout duration: 15 minutes after 5 consecutive failures.
- BR-AUTH-03: Access token TTL: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15).
- BR-AUTH-04: Refresh token TTL: `REFRESH_TOKEN_EXPIRE_DAYS` (default 7).
- BR-AUTH-05: Generic error message on bad credentials prevents user enumeration.
- BR-AUTH-06: `X-Tenant-ID` must match a valid `db_name` in `hms_master.tenants`.

---

### AUTH-UC-002: Refresh Session Token
**Goal Level**: Sub-function | **Primary Actor**: System (automatic)

**Main Success Scenario**:
1. Frontend receives HTTP 401 on any API call.
2. Frontend automatically calls `POST /api/auth/refresh` with the `refresh_token` cookie.
3. System reads `refresh_token` cookie, hashes it (SHA-256), looks up the `RefreshToken` record by hash.
4. System verifies: record exists, `revoked = False`, `expires_at > NOW()`, `tenant_id` in token matches `X-Tenant-ID` header.
5. System generates a new `access_token` and new `refresh_token`.
6. System marks the old `RefreshToken.revoked = True`, sets `replaced_by_id`.
7. System inserts a new `RefreshToken` record.
8. System sets new HttpOnly cookies.
9. Frontend retries the original request.

**Alternative Flows**:
- A1 (Token reuse detected — same token presented again after already replaced): System revokes ALL active refresh tokens for that user. HTTP 401 "Refresh token reuse detected — all sessions revoked." This is a security event.
- A2 (Token expired): HTTP 401; user must log in again.
- A3 (Cross-tenant mismatch): HTTP 403 "Cross-tenant refresh forbidden."

**Business Rules**:
- BR-AUTH-07: Token rotation on every refresh — old token revoked, new token issued.
- BR-AUTH-08: Reuse detection triggers global session revocation for the affected user.
- BR-AUTH-09: Rate limit: 30 refresh attempts per minute per IP.

---

### AUTH-UC-003: Log Out
**Postconditions**: `RefreshToken.revoked = True`; cookies cleared.

### AUTH-UC-004: Forced Password Change
**Trigger**: `must_change_password = True` on login (A8 above).  
**Postconditions**: `must_change_password = False`; all existing sessions revoked; new session issued.

**Business Rules**:
- BR-AUTH-10: Password must meet policy — 8+ chars, uppercase, lowercase, digit, special character.

### AUTH-UC-005: Request Password Reset
**Business Rules**:
- BR-AUTH-11: The response is identical whether or not the email is registered (prevents enumeration).
- BR-AUTH-12: Rate limit: 3 forgot-password requests per minute per IP.
- BR-AUTH-13: Token valid for 60 minutes, single-use.
- BR-AUTH-14: In non-production environments, `dev_token` is returned in the response body.

### AUTH-UC-006: Complete Password Reset
**Postconditions**: All active sessions for the user are revoked (all `RefreshToken` records set `revoked = True`).

---

## Part 3: Patient Registry Use Cases

### PAT-UC-001: Register a New Patient
**Goal Level**: User-goal | **Primary Actor**: RECEPTIONIST  
**Module Required**: patients (always-on) | **Permission Required**: `patients:write`

**Preconditions**:
1. User is authenticated with `patients:write` permission.

**Main Success Scenario**:
1. Receptionist navigates to `/app/patients` → clicks **Register New Patient**.
2. Enters required fields: `surname`, `other_names`, `sex`, `date_of_birth`.
3. Enters optional fields: contact, identity, address, employment, NOK, insurance, clinical baselines.
4. Submits the registration form.
5. System auto-generates `outpatient_no` in format `OP-{YEAR}-{SEQUENCE:04d}`.
6. System creates a `Patient` record with `registered_by = current_user_id`, `registered_on = NOW()`, `is_active = True`.
7. System creates an `AuditLog` entry: `action=CREATE`, `entity_type=Patient`.
8. System invalidates the analytics dashboard cache.
9. System returns the created patient with `patient_id` and `outpatient_no`.

**Alternative Flows**:
- A1 (Missing required field): HTTP 422 with field-level validation errors.
- A2 (Duplicate `id_number`): If the id_number is already registered and is not null, the system may warn or block depending on configuration.

**Postconditions (Success)**:
- `Patient` record exists with `is_active = True`.
- `AuditLog` entry created.

**Business Rules**:
- BR-PAT-01: `outpatient_no` is auto-generated and unique — cannot be manually set.
- BR-PAT-02: `date_of_birth` must not be in the future.
- BR-PAT-03: `sex` must be one of the accepted values in the schema.
- BR-PAT-04: `telephone_1`, `id_number`, `email`, and `outpatient_no` are all indexed for fast search.

**Data Validation Rules**:
- `surname`: required, string, max 100 chars.
- `date_of_birth`: required, date, not in future.
- `sex`: required, enum.
- `telephone_1`: optional, string, max 20 chars.

---

### PAT-UC-002: Search for a Patient
**Main Success Scenario**: User enters search term → system queries `surname`, `other_names` (ILIKE), `outpatient_no` (exact), `id_number` (exact), `telephone_1` (prefix) → returns up to 50 active patients.

**Business Rules**:
- BR-PAT-05: Only `is_active = True` patients are returned by default.
- BR-PAT-06: Search is case-insensitive (ILIKE).

### PAT-UC-003: Edit Patient Demographics
**Permission Required**: `patients:write`  
**Postconditions**: `AuditLog` entry with `action=UPDATE`, `old_value`, `new_value`.

### PAT-UC-004: Add Patient to Queue
**Permission Required**: `patients:write`  
**Main Success Scenario**: Select patient → select department → select acuity (1/2/3) → system creates `PatientQueue` record with `status=Waiting`, `joined_at=NOW()`.

**Business Rules**:
- BR-PAT-07: Acuity 1 (Emergency) is displayed first in the clinical queue, regardless of join time.

---

## Part 4: Appointment Use Cases

### APT-UC-001: Book an Appointment
**Permission Required**: `patients:write`  
**Main Success Scenario**: Select patient → select doctor → select date/time → enter notes → system creates `Appointment` with `status=Scheduled`.

### APT-UC-002: Confirm an Appointment
**Transition**: Scheduled → Confirmed

### APT-UC-003: Cancel an Appointment
**Transition**: Scheduled | Confirmed → Cancelled

### APT-UC-004: Mark No-Show
**Transition**: Scheduled | Confirmed → No-Show

### APT-UC-005: Complete an Appointment
**Transition**: Confirmed → Completed (usually triggered at end of clinical encounter)

**Business Rules**:
- BR-APT-01: Valid statuses: Scheduled, Confirmed, Completed, Cancelled, No-Show.
- BR-APT-02: Only the assigned doctor or Admin can mark an appointment Completed.

---

## Part 5: Clinical Desk Use Cases

### CLIN-UC-001: Start a Clinical Encounter (Create Medical Record)
**Goal Level**: User-goal | **Primary Actor**: DOCTOR  
**Module Required**: clinical | **Permission Required**: `clinical:write`

**Preconditions**:
1. Patient exists and `is_active = True`.
2. Patient has an active `ConsentRecord` for Treatment (or emergency bypass is documented).
3. User has `clinical:write` permission.

**Main Success Scenario**:
1. Doctor views the clinical queue at `/app/clinical`.
2. Selects a patient with `status=Waiting` in the queue.
3. System creates `MedicalRecord`: `patient_id`, `doctor_id = current_user_id`, `record_status = Draft`.
4. System auto-creates a consultation fee `Invoice` (default KES 1,000) if no pending invoice exists.
5. Doctor enters vitals: `blood_pressure` ("120/80" format), `heart_rate`, `respiratory_rate`, `temperature`, `spo2`, `weight_kg`, `height_cm`.
6. System calculates `calculated_bmi = weight_kg / (height_cm / 100)²`.
7. Doctor completes SOAP fields: Chief Complaint, HPI, Review of Systems, Physical Examination.
8. Doctor enters diagnosis and ICD-10 code.
9. Doctor enters treatment plan and prescription notes.
10. Doctor sets `follow_up_date` if needed.
11. Doctor saves (record remains `Draft`).
12. System creates a `DataAccessLog` entry for the patient record view.
13. System creates an `AuditLog` entry: `action=CREATE, entity_type=MedicalRecord`.

**Alternative Flows**:
- A1 (No active consent): System warns; doctor may bypass by documenting `access_reason` in the DataAccessLog.

**Postconditions (Success)**:
- `MedicalRecord` with `record_status=Draft`.
- Consultation fee `Invoice` with `status=Pending`.
- `DataAccessLog` entry created.

**Business Rules**:
- BR-CLIN-01: `calculated_bmi` is always system-calculated; not editable.
- BR-CLIN-02: `blood_pressure` is stored as a string (e.g., "120/80").
- BR-CLIN-03: Record status transitions: Draft → Billed → Pharmacy → Completed.
- BR-CLIN-04: ICD-10 code is free-text (max 255 chars).

---

### CLIN-UC-002: Order Laboratory Tests
**Permission Required**: `clinical:write`  
**Main Success Scenario**: Doctor selects tests from catalog → sets priority (STAT/Urgent/Routine) → adds clinical notes → submits `LabOrderRequest` → system creates one `LabTest` record per test with `status=Pending`.

**Business Rules**:
- BR-CLIN-05: Batch ordering: one request can contain multiple tests.
- BR-CLIN-06: Priority: STAT > Urgent > Routine (affects queue sort order in laboratory).

### CLIN-UC-003: Order Radiology Exam
**Permission Required**: `clinical:write`  
**Postconditions**: `RadiologyRequest` created with `status=Pending`, `billed_price` from catalog.

### CLIN-UC-004: Write Prescription Notes
Prescription text stored in `MedicalRecord.prescription_notes`. No separate prescription entity — Pharmacy reads the notes field.

### CLIN-UC-005: Create a Referral
**Module Required**: referrals | **Permission Required**: `referrals:manage`  
**Main Success Scenario**: Doctor enters specialty (required), target facility, target clinician, reason, clinical summary, urgency → system creates `Referral` with `status=Pending`, linked to `record_id`.

**Business Rules**:
- BR-CLIN-07: Valid urgency values: Routine, Urgent, Emergency.
- BR-CLIN-08: `record_id` link is optional.

### CLIN-UC-006: Close an Encounter
**Transition**: Draft → Billed (when billing invoice is generated) → Pharmacy (when prescription sent to pharmacy) → Completed.  
Transitions are triggered by downstream systems (billing, pharmacy), not directly by the doctor.

---

## Part 6: Laboratory Use Cases

### LAB-UC-001: Process a Lab Order (End-to-End Summary)
**Goal Level**: Summary  
Spans LAB-UC-002 through LAB-UC-005: Receive order → collect specimen → enter results → complete.

### LAB-UC-002: Receive and Acknowledge a Lab Order
**Goal Level**: User-goal | **Primary Actor**: LABORATORY_TECH  
**Module Required**: laboratory | **Permission Required**: `laboratory:read`

**Main Success Scenario**:
1. Lab technician opens `/app/laboratory`.
2. System displays pending `LabTest` records, sorted by: STAT → Urgent → Routine, then by `requested_at` (oldest first).
3. Technician reviews the test: patient name, OP#, test name, specimen type, priority, clinical notes.
4. Technician clicks to claim the test.

### LAB-UC-003: Collect Specimen
**Main Success Scenario**:
1. Technician calls `POST /api/laboratory/tests/{test_id}/collect`.
2. If `catalog.requires_barcode = True`: system prompts for or auto-generates `specimen_id`.
3. Technician confirms `specimen_type`.
4. System updates `LabTest`: `specimen_id`, `specimen_type`, `sample_collected_at = NOW()`, `status = In Progress`.

### LAB-UC-004: Enter Lab Results
**Permission Required**: (none — any authenticated lab user)

**Main Success Scenario**:
1. Technician opens the result entry form for the test.
2. Form auto-populates from `LabTestCatalog` parameters (key, name, unit, value_type, ref_low, ref_high).
3. Technician enters result values per parameter.
4. System flags values outside [ref_low, ref_high] in red (visual only; no server-side blocking).
5. Technician enters `result_summary` (narrative) and `lab_technician_notes`.
6. Technician logs consumed reagents: selects batch from `StockBatch`, enters `quantity_used`.
7. System acquires a row-level lock on each `StockBatch` and deducts `quantity_used` (unless `is_reusable = True`).
8. System creates `InventoryUsageLog` entries for each consumed item.
9. System updates `LabTest`: `result_data = {JSON}`, `status = Completed`, `completed_at = NOW()`, `performed_by_id = current_user`.
10. System sends a WebSocket notification to the ordering doctor.

**Alternative Flows**:
- A1 (Insufficient batch quantity): HTTP 400 with remaining quantity in error detail.

**Postconditions (Success)**:
- `LabTest.status = Completed`.
- `StockBatch.quantity` reduced (for non-reusable items).
- `InventoryUsageLog` entries created.

**Business Rules**:
- BR-LAB-01: `result_data` is a JSONB object; keys must match the catalog's `LabCatalogParameter.key` values.
- BR-LAB-02: Reusable items (`is_reusable = True`): `InventoryUsageLog` created with `is_reusable_use = True` but quantity NOT deducted from `StockBatch`.
- BR-LAB-03: Row-level lock prevents race conditions on concurrent reagent consumption.
- BR-LAB-04: Out-of-range values are flagged in the UI but do not block result submission.

### LAB-UC-005: Manage Lab Test Catalog
**Permission Required**: `laboratory:manage`  
**Create test**: `test_name`, `category`, `default_specimen_type`, `base_price`, `turnaround_hours`, `requires_barcode`.  
**Add parameter**: `key` (machine), `name` (human), `unit`, `value_type` (number/text/choice), `choices` (comma-separated, required if value_type=choice), `ref_low`, `ref_high`, `sort_order`.

**Business Rules**:
- BR-LAB-05: `value_type=choice` requires non-empty `choices` field.
- BR-LAB-06: Deactivating a test (`is_active=False`) hides it from new orders but preserves historical test records.

### LAB-UC-006: Manage Lab Consumable Bill of Materials (BOM)
**Permission Required**: `laboratory:manage`  
Associates `InventoryItem` records with `LabTestCatalog` entries, specifying `quantity_required` per test run.

---

## Part 7: Radiology Use Cases

### RAD-UC-001: Request a Radiology Exam
**Permission Required**: `clinical:write`  
**Postconditions**: `RadiologyRequest` created with `status=Pending`.

### RAD-UC-002: Complete a Radiology Exam
**Primary Actor**: RADIOLOGIST | **Permission Required**: `radiology:manage`

**Main Success Scenario**:
1. Radiologist opens `/app/radiology`, selects a pending request.
2. Views: patient, exam type, modality, prep/contrast requirements, clinical notes.
3. Enters `findings` (pre-populated from `catalog.default_findings_template`).
4. Enters `conclusion` (pre-populated from `catalog.default_impression_template`).
5. Enters `image_url` (link to PACS or storage).
6. Records `contrast_used` (boolean).
7. Submits results.
8. System creates `RadiologyResult` linked to `request_id` (unique constraint — one result per request).
9. System updates `RadiologyRequest.status = Completed`.

**Business Rules**:
- BR-RAD-01: `findings` and `conclusion` are required on `RadiologyResult`.
- BR-RAD-02: `RadiologyResult.request_id` has a unique constraint — each request has at most one result.
- BR-RAD-03: `image_url` is optional.

### RAD-UC-003: Manage Radiology Catalog
**Permission Required**: `radiology:manage`  
Fields: `exam_name`, `modality` (X-Ray/CT/MRI/Ultrasound/Mammography), `body_part`, `base_price`, `requires_prep`, `requires_contrast`, `default_findings_template`, `default_impression_template`.

---

## Part 8: Pharmacy Use Cases

### PHARM-UC-001: Fulfil a Prescription
**Goal Level**: User-goal | **Primary Actor**: PHARMACIST  
**Module Required**: pharmacy | **Permission Required**: `pharmacy:manage`

**Preconditions**:
1. Patient has a clinical encounter with `prescription_notes`.
2. Pharmacy location (`StockBatch` at Pharmacy) has sufficient stock.

**Main Success Scenario**:
1. Pharmacist opens `/app/pharmacy`.
2. System displays inventory sorted by `expiry_date` ASC (FEFO).
3. Pharmacist locates the prescribed item and selects the earliest-expiry batch.
4. Pharmacist enters `quantity` and a unique `idempotency_key`.
5. System checks `IdempotencyKey` table — if key exists, returns the cached response (prevents double-dispense).
6. System acquires row-level lock on `StockBatch` (`SELECT FOR UPDATE`).
7. System verifies `batch.quantity >= requested_quantity`.
8. System deducts quantity from `StockBatch`.
9. System creates `DispenseLog`: `patient_id`, `record_id`, `item_id`, `batch_id`, `quantity_dispensed`, `total_cost`, `dispensed_by`, `dispensed_at`.
10. System finds or creates a Pending `Invoice` for the patient.
11. System adds an `InvoiceItem` to the invoice: `item_type=Pharmacy`, `amount = unit_price × quantity`.
12. System updates `invoice.total_amount`.
13. System stores the idempotency key with the response body.
14. System commits the transaction.

**Alternative Flows**:
- A1 (Duplicate `idempotency_key`): Returns original response without re-dispensing.
- A2 (Insufficient stock): HTTP 400 "Insufficient stock. Available: N units."

**Business Rules**:
- BR-PHARM-01: FEFO — earliest-expiry batch must be dispensed first.
- BR-PHARM-02: Idempotency key prevents double-charge on UI retry or network retry.
- BR-PHARM-03: Row-level lock prevents concurrent over-dispensing.
- BR-PHARM-04: `total_cost = item.unit_price × quantity`.

### PHARM-UC-002: OTC Sale
`patient_id = NULL`, `record_id = NULL`. No prescription required. Creates `DispenseLog` entry.

### PHARM-UC-003: View Pharmacy Stock
Returns `StockBatch` records for the Pharmacy location, sorted by `expiry_date` ASC.

---

## Part 9: Inventory Use Cases

### INV-UC-001: Add Inventory Item to Catalog
**Permission Required**: `pharmacy:manage`  
Fields: `item_code` (auto-generated if blank), `name`, `category` (Drug/Consumable/Reagent/Equipment), `unit_cost`, `unit_price`, `reorder_threshold`, `generic_name`, `dosage_form`, `strength`, `requires_prescription`, `is_reusable`.

### INV-UC-002: Receive Stock (Add Batch)
**Main Success Scenario**: Select item and location → enter `batch_number`, `quantity`, `expiry_date`, `supplier_name` → system creates `StockBatch` record.

### INV-UC-003: Transfer Stock Between Locations
**Main Success Scenario**: Select item, source location (from), destination location (to), batch, quantity → system creates `StockTransfer` record → stock availability updated at both locations.

**Business Rules**:
- BR-INV-01: Only items with `is_active = True` appear in order/transfer UI.
- BR-INV-02: Transfer quantity cannot exceed available batch quantity.

### INV-UC-004: Log Internal Consumption
System auto-creates `InventoryUsageLog` on laboratory result completion and ward consumable logging.

### INV-UC-005: Monitor Reorder Alerts
**Condition**: `StockBatch.quantity <= InventoryItem.reorder_threshold` for a given item.  
Reorder alerts are surfaced in the Admin Dashboard KPI tile (low stock count) and in `/api/inventory/alerts`.

---

## Part 10: Wards and Admissions Use Cases

### WARD-UC-001: Admit a Patient
**Goal Level**: User-goal | **Primary Actor**: NURSE  
**Module Required**: wards | **Permission Required**: `wards:write` (or authenticated user)

**Preconditions**:
1. At least one `Bed` with `status = Available` exists.
2. Patient has no other active `AdmissionRecord`.

**Main Success Scenario**:
1. Nurse opens `/app/wards` → views the bed board.
2. Selects an Available bed.
3. Clicks **Admit Patient** → selects patient, enters admitting doctor, primary diagnosis.
4. System creates `AdmissionRecord`: `patient_id`, `bed_id`, `admitting_doctor_id`, `primary_diagnosis`, `status=Active`, `admitted_at=NOW()`.
5. System updates `Bed.status = Occupied`.

**Business Rules**:
- BR-WARD-01: Only `Bed.status = Available` beds can be selected for admission.
- BR-WARD-02: `primary_diagnosis` is required.
- BR-WARD-03: A patient cannot have more than one `Active` admission simultaneously.

### WARD-UC-002: Discharge a Patient
**Main Success Scenario**: Select admission → enter discharge notes → system sets `AdmissionRecord.status=Discharged`, `discharged_at=NOW()` → system sets `Bed.status=Available` (or `Cleaning`).

**Business Rules**:
- BR-WARD-04: `discharge_notes` are recommended but not required.
- BR-WARD-05: After discharge, the bed must be explicitly marked Available or Cleaning.

### WARD-UC-003: Log Ward Consumables
System selects earliest-expiry batch (FEFO). Creates `InventoryUsageLog` with `reference_type=WardProcedure`.

### WARD-UC-004: View Bed Board
Real-time view of all wards, beds, and statuses. Color coding: Available=green, Occupied=orange, Maintenance=red, Cleaning=yellow. KPIs: total beds, occupied, available, occupancy rate.

---

## Part 11: Billing and Finance Use Cases

### BILL-UC-001: Process Cash or Card Payment
**Goal Level**: User-goal | **Primary Actor**: BILLING_OFFICER  
**Module Required**: billing | **Permission Required**: `billing:manage`

**Main Success Scenario**:
1. Billing Officer views the invoice queue at `/app/billing`.
2. Selects an invoice with outstanding balance.
3. Enters `amount` and `payment_method` (Cash/Card), generates `idempotency_key`.
4. System checks `IdempotencyKey` — if exists, returns cached response.
5. System acquires row-level lock on `Invoice`.
6. System adds `amount` to `invoice.amount_paid`.
7. If `amount_paid >= total_amount`: `invoice.status = Paid`.
8. Else: `invoice.status = Partially Paid`.
9. System creates `Payment` record: `invoice_id`, `amount`, `payment_method`, `payment_date=NOW()`.
10. System stores idempotency key with response.
11. System creates `AuditLog` entry.

**Alternative Flows**:
- A1 (Duplicate idempotency key): Returns original response.
- A2 (Invoice already Paid): HTTP 400.

**Business Rules**:
- BR-BILL-01: Idempotency prevents double-charge on network retry.
- BR-BILL-02: Partial payment allowed (no minimum).
- BR-BILL-03: `amount_paid` accumulates across multiple partial payments.
- BR-BILL-04: Payment method recorded per `Payment` record.

---

### BILL-UC-002: Initiate M-Pesa STK Push
**Module Required**: mpesa | **Permission Required**: `billing:manage`

**Main Success Scenario**:
1. Billing Officer enters customer phone number (07XXXXXXXX).
2. System normalises phone to `2547XXXXXXXX` format.
3. System retrieves `MpesaConfig` and decrypts credentials.
4. System fetches Daraja OAuth access token.
5. System sends STK push request to Safaricom Daraja API.
6. System creates `MpesaTransaction`: `status=Pending`, `merchant_request_id`, `checkout_request_id`.
7. System updates `Invoice.status = Pending M-Pesa`.
8. On callback from Safaricom: system looks up `MpesaTransaction` by `checkout_request_id`.
9. On success: `MpesaTransaction.status=Success`, `receipt_number` set; invoice auto-updated to Paid/Partially Paid.
10. On failure: `MpesaTransaction.status=Failed`, `result_desc` recorded; invoice returned to Pending.

**Business Rules**:
- BR-BILL-05: Phone normalised to `2547XXXXXXXX` before Daraja call.
- BR-BILL-06: Invoice status → `Pending M-Pesa` while awaiting callback.
- BR-BILL-07: `receipt_number` has a unique constraint — duplicate callbacks are idempotent.
- BR-BILL-08: Timeout (no callback): status → `Timeout`; invoice remains Pending.

---

### BILL-UC-003: Cheque Lifecycle
**Receive**: Create `Cheque` with `status=Received`. Fields: `cheque_number`, `drawer_name`, `drawer_type` (Insurance/Employer/Patient/Government/Other), `bank_name`, `bank_branch`, `amount`, `date_on_cheque`, `date_received`.

**Deposit**: `status=Received → Deposited`. Records `deposit_date`.

**Clear**: `status=Deposited → Cleared`. Records `clearance_date`. System auto-creates a `Payment` record against the linked invoice.

**Bounce**: `status=Deposited → Bounced`. Records `bounce_reason`. Invoice returns to `Pending`.

**Cancel**: Any non-terminal status → `Cancelled`. Records `cancel_reason`.

**Business Rules**:
- BR-BILL-09: Clearing auto-posts a `Payment` record.
- BR-BILL-10: Bouncing a cheque does NOT post a payment; invoice returns to Pending.
- BR-BILL-11: `bounce_reason` is required when marking a cheque as Bounced.

---

## Part 12: M-Pesa Integration Use Cases

### MPESA-UC-001: Configure M-Pesa
**Permission Required**: `settings:manage`

**Business Rules**:
- BR-MPESA-01: `consumer_key`, `consumer_secret`, and `passkey` are AES-encrypted before DB insert.
- BR-MPESA-02: The GET /config endpoint never returns decrypted credential values.
- BR-MPESA-03: Only one `MpesaConfig` row per tenant (singleton, upsert pattern).

### MPESA-UC-002: M-Pesa STK Push Flow
(See BILL-UC-002 for full flow)

**Business Rules**:
- BR-MPESA-04: Daraja OAuth access token is fetched fresh per STK push (not cached).
- BR-MPESA-05: `MPESA_ENV` controls sandbox vs. production Daraja endpoint.
- BR-MPESA-06: In sandbox, callback URL is auto-resolved from Ngrok (`http://127.0.0.1:4040/api/tunnels`).

### MPESA-UC-003: Handle M-Pesa Callback
Public endpoint `POST /api/payments/mpesa/callback`. No authentication required (Safaricom calls this).  
Receives: `MerchantRequestID`, `CheckoutRequestID`, `ResultCode`, `ResultDesc`, `MpesaReceiptNumber`, `Amount`, `PhoneNumber`, `TransactionDate`.  
Idempotent: duplicate callbacks with same `receipt_number` are safely ignored due to unique constraint.

---

## Part 13: Messaging Use Cases

### MSG-UC-001: Send a Direct Message
**Permission Required**: `messaging:write`  
**Main Success Scenario**: User creates direct conversation (exactly 2 participants) → sends message → system broadcasts via WebSocket to recipient's channel (`hms:user:{id}`).

**Business Rules**:
- BR-MSG-01: Direct conversations require exactly 2 participants.
- BR-MSG-02: Unread count = messages with `created_at > participant.last_read_at`.

### MSG-UC-002: Create a Group Conversation
**Business Rules**:
- BR-MSG-03: Groups can have 3+ participants.
- BR-MSG-04: Title is required for group conversations.

### MSG-UC-003: Communicate via Department Channel
**Business Rules**:
- BR-MSG-05: Department channels are linked to `department_id` (unique constraint — one channel per department).
- BR-MSG-06: Membership managed by Admin via `DepartmentsManager`; changes propagate immediately.
- BR-MSG-07: Real-time delivery via Redis pub/sub in multi-worker deployments.

---

## Part 14: Notification Use Cases

### NOTIF-UC-001: Receive a Real-Time Notification
**Main Scenario**: System sends notification → broadcasts to `hms:user:{id}` and `hms:role:{name}` Redis channels → WebSocket server pushes to connected clients → `Notification` record persisted with `is_read=False`.

**Business Rules**:
- BR-NOTIF-01: Role channel (`hms:role:{name}`) enables broadcasting to all users with a given role (e.g., all LABORATORY_TECH users notified of a STAT order).
- BR-NOTIF-02: Notifications are persistent in the `notifications` table; they survive page refresh.

### NOTIF-UC-002: Mark Notification as Read
Updates `Notification.is_read=True`, `read_at=NOW()`. Bulk mark-all-read also supported.

---

## Part 15: Medical History Use Cases

### HIST-UC-001: Record a Medical History Entry
**Module Required**: medical_history | **Permission Required**: `clinical:write`

**Business Rules**:
- BR-HIST-01: Valid `entry_type` values: SURGICAL_HISTORY, FAMILY_HISTORY, SOCIAL_HISTORY, IMMUNIZATION, ALLERGY, CHRONIC_CONDITION, PAST_MEDICAL_EVENT, OBSTETRIC_HISTORY, MENTAL_HEALTH.
- BR-HIST-02: `event_date` is stored as a string for flexibility (e.g., "2019" or "March 2020").
- BR-HIST-03: `is_sensitive=True` entries require explicit permission to view.

### HIST-UC-002: Access Sensitive Medical History
**Preconditions**: Patient has active `ConsentRecord` OR emergency access is documented.

**Postconditions**: `DataAccessLog` entry created for every sensitive record view (KDPA S.26).

**Business Rules**:
- BR-HIST-04: Every view of the full patient medical history chart creates a `DataAccessLog` entry.
- BR-HIST-05: Sensitive records (mental health, obstetric, HIV) are hidden from the patient portal.

### HIST-UC-003: Record Informed Consent
**Permission Required**: `clinical:write`

**Business Rules**:
- BR-HIST-06: Research consent (`consent_type=Research`) requires `consent_expires_at` to be set.
- BR-HIST-07: `require_active_consent()` utility is called before accessing the medical history chart.
- BR-HIST-08: Valid `consent_method` values: Written, Verbal, Guardian.

---

## Part 16: Referral Use Cases

### REF-UC-001: Create an Outbound Referral
**Module Required**: referrals | **Permission Required**: `referrals:manage`

**Business Rules**:
- BR-REF-01: `specialty` is required; `target_facility` and `target_clinician` are optional.
- BR-REF-02: Valid `urgency`: Routine, Urgent, Emergency.
- BR-REF-03: Initial `status = Pending`.

### REF-UC-002: Update Referral Status
**Lifecycle**: Pending → Sent → Accepted → Completed | Cancelled.

**Business Rules**:
- BR-REF-04: Status transitions are not strictly enforced server-side (any valid status can be set).

---

## Part 17: Settings and Branding Use Cases

### SET-UC-001: Configure Hospital Settings
**Permission Required**: `settings:manage`  
KV store in `HospitalSetting` table. `data_type` values: string, number, boolean, json, secret.

### SET-UC-002: Update Hospital Branding
**Module Required**: branding | **Permission Required**: `settings:read`

**Business Rules**:
- BR-BRAND-01: Logo and background data URLs capped at 1.2 MB server-side.
- BR-BRAND-02: Branding stored in `hms_master.tenants`, not the tenant DB.
- BR-BRAND-03: Public branding endpoint (`GET /api/public/branding`) returns data without authentication (needed for login page rendering before the user logs in).

---

## Part 18: Patient Portal Use Cases

### PORTAL-UC-001: Patient Self-Service Login
**Goal Level**: User-goal | **Primary Actor**: PATIENT  
**Module Required**: patient_portal

**Main Success Scenario**:
1. Patient navigates to `/patient`.
2. Enters OP number, date of birth, and last 4 digits of registered `telephone_1`.
3. System verifies all three against the `patients` table.
4. System issues a portal JWT (`type=patient_portal`) in an HttpOnly cookie.
5. Patient is logged in with read-only access.

**Business Rules**:
- BR-PORTAL-01: Three-factor verification: OP number + DOB + last 4 digits of `telephone_1`.
- BR-PORTAL-02: Portal token type = `patient_portal` (distinct from staff `access_token`).
- BR-PORTAL-03: Portal session TTL: 60 minutes.
- BR-PORTAL-04: Portal is entirely read-only — no clinical data mutations allowed.
- BR-PORTAL-05: Sensitive records (`is_sensitive=True`) are not returned by the portal API.

### PORTAL-UC-002: View Appointments
Returns `Appointment` records for the authenticated patient. All statuses visible.

### PORTAL-UC-003: View Invoices
Returns `Invoice` records with `InvoiceItem` details. All statuses visible.

### PORTAL-UC-004: View Medical History (Non-Sensitive)
Returns `MedicalHistoryEntry` records where `is_sensitive=False`.

---

## Part 19: Superadmin Console Use Cases

### SA-UC-001: Provision a New Hospital Tenant
**Goal Level**: User-goal | **Primary Actor**: SUPERADMIN

**Main Success Scenario**:
1. Superadmin enters: `name`, `domain` (unique), `db_name` (unique), `admin_email`, `admin_full_name`.
2. System validates uniqueness of `domain` and `db_name` in `hms_master`.
3. System inserts `Tenant` row in `hms_master.tenants`.
4. System executes `CREATE DATABASE {db_name}`.
5. System initialises the tenant engine and calls `Base.metadata.create_all` (builds schema).
6. System seeds built-in roles: Admin, Doctor, Nurse, Pharmacist, Laboratory Technician, Radiologist, Receptionist, Billing Officer, Patient.
7. System seeds permissions for each role.
8. System creates inventory locations: Main Store, Pharmacy, Laboratory, Wards.
9. System seeds default `HospitalSetting` records.
10. System generates a 16-character random temporary password.
11. System creates an `Admin` user account: `must_change_password=True`.
12. System returns the temporary password **once** in the response body.

**Alternative Flows**:
- A1 (DB creation fails after master row was inserted): System deletes the `Tenant` master row (best-effort rollback). Retry is safe.

**Business Rules**:
- BR-SA-01: `db_name` must be globally unique across the platform.
- BR-SA-02: Temporary password is generated with `secrets.token_urlsafe` — never stored in plaintext.
- BR-SA-03: `CREATE DATABASE` cannot be run inside a transaction (PostgreSQL limitation); failure after this point is cleaned up by deleting the master row.

### SA-UC-002: Manage Feature Flags
**Main Scenario**: Superadmin toggles module on/off in the tenant `feature_flags` JSON → system updates `tenants` row → entitlement cache expires after 60 seconds → all subsequent API calls see the new entitlement.

**Business Rules**:
- BR-SA-04: Always-on modules cannot be disabled: patients, appointments, dashboard, settings, support, messaging, notifications, users, auth.
- BR-SA-05: Entitlement cache TTL = 60 seconds (Redis-backed).

### SA-UC-003: Deactivate a Tenant
Sets `is_active=False`. Tenant no longer appears in the hospital picker. Existing sessions expire normally.

### SA-UC-004: Manage Support Inbox
Superadmin views all tenant support tickets → replies → updates status. Reply is tagged as "Platform Team".

---

## Part 20: Privacy and KDPA Use Cases

### PRIV-UC-001: Process a Data Subject Access Request (DSAR)
**Permission Required**: `history:read`  
**Main Scenario**: Admin exports patient data as CSV via `GET /api/privacy/patients/{patient_id}/export`. Export includes: demographics, appointments, lab tests, radiology, invoices, history entries, consents, admissions.

### PRIV-UC-002: Execute Right to Erasure (Pseudonymisation)
**Main Scenario**: Replace identifying fields with deterministic placeholders → set `is_active=False` → patient cannot log in to portal.

**Business Rules**:
- BR-PRIV-01: Pseudonymised fields: `surname`, `other_names`, `telephone_1`, `telephone_2`, `email`, `id_number`, all address fields.
- BR-PRIV-02: Clinical and billing records are retained (Health Act 2017, 7-year requirement).
- BR-PRIV-03: Hard deletion is legally prohibited.
- BR-PRIV-04: Erasure creates an `AuditLog` entry.

### PRIV-UC-003: Record a Data Breach Incident
**Permission Required**: `users:manage`  
System creates `BreachIncident` record. Fields: `detected_at`, `reported_by`, `severity` (Low/Medium/High/Critical), `nature`, `description`, `affected_categories` (JSONB), `estimated_records_affected`, `likely_consequences`, `mitigation_steps`.

### PRIV-UC-004: Notify ODPC of a Breach
**Business Rules**:
- BR-PRIV-05: KDPA Section 43 requires ODPC notification within **72 hours** of discovery.
- BR-PRIV-06: `odpc_notified_at` must be set; `odpc_reference` documents the confirmation number received from ODPC.
- BR-PRIV-07: Status progression: Open → Investigating → Contained → Closed.

---

## Part 21: Administration Use Cases

### ADMIN-UC-001: Create Staff Account
**Permission Required**: `users:manage`

**Business Rules**:
- BR-ADMIN-01: `email` must be unique within the tenant DB.
- BR-ADMIN-02: `license_number`: empty string is stored as `NULL` (unique constraint allows multiple NULLs; empty strings would collide).
- BR-ADMIN-03: Password must meet the 5-criteria policy (8+ chars, upper, lower, digit, special).
- BR-ADMIN-04: `must_change_password = True` by default for Admin-created accounts.

### ADMIN-UC-002: Deactivate Staff Account
Sets `is_active=False`. User cannot log in. Existing sessions expire normally (up to 15 min for access token, 7 days for refresh token).

### ADMIN-UC-003: Assign/Revoke Permission Override
Adds `UserPermissionOverride` record: `user_id`, `permission_id`, `granted` (True=grant, False=revoke).

**Business Rules**:
- BR-ADMIN-05: Effective permissions = (role_perms ∪ explicit_grants) − explicit_revokes.
- BR-ADMIN-06: An explicit revoke overrides even a role-level grant.

### ADMIN-UC-004: Create Custom Role
Creates a `Role` with a custom `name` and assigns `Permission` records via `RolePermission`.

### ADMIN-UC-005: Manage Department Membership
**Permission Required**: `departments:manage`  
Syncs `DepartmentMember` records. Removing a member removes them from the department messaging channel.

### ADMIN-UC-006: View Audit Logs
**Permission Required**: `users:manage`  
Returns `AuditLog` records filterable by `user_id`, `action`, `entity_type`, `entity_id`, date range, `ip_address`.

---

## Appendix A: Business Rule Index

| Rule ID | Module | Rule Summary | Source File |
|---|---|---|---|
| BR-AUTH-01 | Auth | Login rate limit: 5/min per IP | `backend/app/auth/auth.py` |
| BR-AUTH-02 | Auth | Lockout after 5 failures, 15 min | `backend/app/auth/auth.py` |
| BR-AUTH-03 | Auth | Access token TTL 15 min | `backend/app/config/settings.py` |
| BR-AUTH-04 | Auth | Refresh token TTL 7 days | `backend/app/config/settings.py` |
| BR-AUTH-07 | Auth | Token rotation on refresh | `backend/app/auth/auth.py` |
| BR-AUTH-08 | Auth | Reuse detection → revoke all sessions | `backend/app/auth/auth.py` |
| BR-AUTH-10 | Auth | Password policy (8+/U/L/D/S) | `backend/app/core/security.py` |
| BR-PAT-01 | Patients | OP# auto-generated, format OP-YYYY-NNNN | `backend/app/routes/patients.py` |
| BR-CLIN-01 | Clinical | BMI is system-calculated | `backend/app/routes/clinical.py` |
| BR-CLIN-03 | Clinical | Record status: Draft→Billed→Pharmacy→Completed | `backend/app/models/clinical.py` |
| BR-LAB-01 | Laboratory | result_data JSONB keys match catalog | `backend/app/routes/laboratory.py` |
| BR-LAB-02 | Laboratory | Reusable items: log but don't deduct | `backend/app/routes/laboratory.py` |
| BR-PHARM-01 | Pharmacy | FEFO: earliest-expiry batch first | `backend/app/routes/pharmacy.py` |
| BR-PHARM-02 | Pharmacy | Idempotency key prevents double-dispense | `backend/app/routes/pharmacy.py` |
| BR-RAD-02 | Radiology | One result per request (unique constraint) | `backend/app/models/radiology.py` |
| BR-WARD-01 | Wards | Only Available beds selectable for admission | `backend/app/routes/wards.py` |
| BR-BILL-01 | Billing | Idempotency prevents double-charge | `backend/app/routes/billing.py` |
| BR-BILL-07 | Billing | M-Pesa receipt_number unique constraint | `backend/app/models/mpesa.py` |
| BR-MPESA-01 | M-Pesa | Credentials AES-encrypted at rest | `backend/app/routes/admin_mpesa.py` |
| BR-MSG-01 | Messaging | DM requires exactly 2 participants | `backend/app/routes/messaging.py` |
| BR-BRAND-03 | Branding | Public branding endpoint unauthenticated | `backend/app/routes/branding.py` |
| BR-PORTAL-04 | Portal | Portal is entirely read-only | `backend/app/routes/portal.py` |
| BR-SA-01 | Superadmin | db_name globally unique | `backend/app/routes/public.py` |
| BR-SA-04 | Superadmin | Always-on modules cannot be disabled | `backend/app/core/modules.py` |
| BR-SA-05 | Superadmin | Entitlement cache TTL 60s | `backend/app/core/modules.py` |
| BR-PRIV-02 | Privacy | Clinical records retained 7 years | `backend/app/routes/privacy.py` |
| BR-PRIV-05 | Privacy | KDPA S.43: 72h ODPC notification | `backend/app/models/medical_history.py` |
| BR-ADMIN-05 | Admin | Effective permissions formula | `backend/app/routes/users.py` |

---

## Appendix B: State Machine Diagrams

### JWT Access Token
```
[Issued] --15 min TTL--> [Expired]
[Issued] --logout--> [Invalidated (cookie cleared)]
```

### Refresh Token
```
[Active] --used for refresh--> [Revoked] + [New Active token issued]
[Active] --used twice (reuse)--> [ALL user tokens revoked]
[Active] --7-day TTL--> [Expired]
[Active] --logout--> [Revoked]
[Active] --password reset--> [Revoked]
```

### Patient Record
```
[Active (is_active=True)] --deactivate--> [Inactive (is_active=False)]
[Active] --pseudonymisation--> [Pseudonymised (is_active=False)]
```

### Appointment Status
```
[Scheduled] --> [Confirmed] --> [Completed]
[Scheduled] --> [Cancelled]
[Confirmed] --> [Cancelled]
[Scheduled] --> [No-Show]
[Confirmed] --> [No-Show]
```

### Medical Record (Encounter) Status
```
[Draft] --> [Billed] --> [Pharmacy] --> [Completed]
```

### Lab Test Status
```
[Pending] --specimen collected (optional)--> [In Progress] --> [Completed]
[Pending] --> [Rejected]
[In Progress] --> [Rejected]
```

### Radiology Request Status
```
[Pending] --> [Completed]
```

### Invoice Status
```
[Pending] --partial payment--> [Partially Paid] --full payment--> [Paid]
[Pending] --full payment--> [Paid]
[Pending] --M-Pesa initiated--> [Pending M-Pesa] --callback success--> [Paid/Partially Paid]
[Pending M-Pesa] --callback fail/timeout--> [Pending]
[Pending] --> [Cancelled]
[Partially Paid] --> [Cancelled]
```

### M-Pesa Transaction Status
```
[Pending] --success callback--> [Success]
[Pending] --failure callback--> [Failed]
[Pending] --no callback (60s)--> [Timeout]
```

### Cheque Status
```
[Received] --> [Deposited] --> [Cleared]
[Deposited] --> [Bounced]
[Received/Deposited] --> [Cancelled]
```

### Referral Status
```
[Pending] --> [Sent] --> [Accepted] --> [Completed]
[Pending/Sent/Accepted] --> [Cancelled]
```

### Admission Record Status
```
[Active] --> [Discharged]
```

### Bed Status
```
[Available] --admit patient--> [Occupied]
[Occupied] --discharge--> [Available]
[Occupied] --discharge--> [Cleaning] --> [Available]
[Available/Cleaning] --> [Maintenance] --> [Available]
```

### Support Ticket Status
```
[Open] --> [In Progress] --> [Waiting on Customer] --> [In Progress]
[In Progress] --> [Resolved] --> [Closed]
[Open/In Progress] --> [Closed]
```

### Breach Incident Status
```
[Open] --> [Investigating] --> [Contained] --> [Closed]
```

---

## Appendix C: Key Data Validation Rules

| Entity | Field | Constraint | Source |
|---|---|---|---|
| User | `email` | Unique per tenant, valid email format | `backend/app/models/user.py` |
| User | `license_number` | Unique or NULL (empty string stored as NULL) | `backend/app/routes/users.py` |
| User | `password` | 8+ chars, upper, lower, digit, special | `backend/app/core/security.py` |
| Patient | `outpatient_no` | Unique, auto-generated (OP-YYYY-NNNN) | `backend/app/routes/patients.py` |
| Patient | `date_of_birth` | Not in the future | `backend/app/schemas/patients.py` |
| MedicalRecord | `blood_pressure` | String format "sys/dia" (not validated strictly) | `backend/app/models/clinical.py` |
| MedicalRecord | `calculated_bmi` | System-calculated, not user-settable | `backend/app/routes/clinical.py` |
| LabTest | `result_data` | JSONB with keys matching catalog parameter keys | `backend/app/routes/laboratory.py` |
| LabCatalogParameter | `choices` | Required (non-empty) when `value_type=choice` | `backend/app/routes/laboratory.py` |
| RadiologyResult | `request_id` | Unique (one result per request) | `backend/app/models/radiology.py` |
| Invoice | `amount_paid` | Cannot exceed `total_amount` | `backend/app/routes/billing.py` |
| MpesaTransaction | `receipt_number` | Unique (Safaricom guarantee) | `backend/app/models/mpesa.py` |
| MpesaConfig | (per tenant) | Singleton — one row per tenant | `backend/app/routes/admin_mpesa.py` |
| ConsentRecord | `consent_expires_at` | Required when `consent_type=Research` | `backend/app/routes/medical_history.py` |
| Tenant | `domain` | Unique across `hms_master.tenants` | `backend/app/models/master.py` |
| Tenant | `db_name` | Unique across `hms_master.tenants` | `backend/app/models/master.py` |
| Branding | `logo_data_url` | Max 1.2 MB | `backend/app/routes/branding.py` |
| Cheque | `bounce_reason` | Required when status→Bounced | `backend/app/routes/cheques.py` |
| Cheque | `cancel_reason` | Required when status→Cancelled | `backend/app/routes/cheques.py` |
