# Perfect Deletion Across All Queues — Design

**Date:** 2026-06-25
**Branch:** `feat/queue-deletion-all-modules` (off `development`)
**Delivery:** one combined PR → `development` (then promote `development → beta → main`)

## Context

After shipping the triage-routing `DepartmentQueue` panels (PR #158), an audit of every
queue in the system showed that staff cannot cleanly remove an entry that shouldn't be
there from several worklists. The user asked for "perfect deletion of someone from the
queue" in **all** queues.

### Audit — deletion capability today

| Queue | Source | Remove today? |
|-------|--------|---------------|
| Consultation (Clinical Desk) | `PatientQueue` | ✅ checkout + end-of-day |
| Reception/Lab/Pharmacy/Radiology/Wards patient panels | `PatientQueue` via `DepartmentQueue` | ✅ Remove + Cancel (#158) |
| Lab tests worklist | `LabTest` | ✅ reject (with reason) |
| **Triage "Awaiting Triage"** | `PatientQueue` (dept=Triage) | ❌ select-only, no remove |
| **Pharmacy "Pending prescriptions"** | `MedicalRecord` (record_status="Pharmacy") | ⚠️ only "return to doctor" |
| **Radiology requests** | `RadiologyRequest` | ❌ status-only, no cancel |
| **Billing invoice queue** | `Invoice` (status Pending) | ❌ no void |

This design closes the four ❌/⚠️ gaps.

## Decisions (confirmed with user)

1. **Scope:** all four queues — Triage, Pharmacy prescriptions, Radiology requests, Billing invoices.
2. **Semantics:** **soft-cancel everywhere** — mark the entry Cancelled/Voided, keep the row
   for history/analytics/KDPA, require a **reason**, write an **audit** row. Never hard-delete.
3. **Billing void scope:** only fully-unpaid `Pending` invoices may be voided, and the void
   **must post a reversing GL entry**. `Paid`/`Partially Paid` are blocked (collected money
   needs a refund/credit-note flow, out of scope here).
4. **Permissions:** per-module manage perms — `patients:write` (triage), `pharmacy:manage`
   (scripts), `radiology:manage` (imaging), `billing:manage` (invoices). No new permissions.

## Global constraints

- **No schema change.** Every status string already exists (`Invoice.status` already includes
  `"Cancelled"`; `RadiologyRequest.status` and `MedicalRecord.record_status` are free strings).
  The migration gate stays a no-op — call this out in the PR.
- Each list endpoint already excludes terminal statuses, so a cancelled entry drops out of its
  worklist with no list-query change.
- Follow the soft-cancel + reason + audit pattern established by `PATCH /api/queue/{id}/cancel`.

---

## Stream 1 — Triage "Awaiting Triage" remove/cancel (frontend only)

**No backend change** — reuse the shipped `PATCH /api/queue/{id}/checkout` (Remove → Completed)
and `PATCH /api/queue/{id}/cancel` (Cancel → Cancelled + reason). `triage.py::get_triage_queue`
already filters `status in ("Waiting","In Progress")`, so both drop out.

- `frontend/src/pages/Triage.jsx`: each "Awaiting Triage" card currently is a single select
  button. Add small **Remove** and **Cancel** actions per card (Cancel prompts for a reason),
  without breaking patient-select. Refetch the triage queue after either action.

## Stream 2 — Pharmacy "Pending prescriptions" cancel (backend + frontend)

**Backend** — `backend/app/routes/clinical.py`:
- `POST /api/clinical/prescriptions/{record_id}/cancel` (perm `pharmacy:manage`), body
  `{ "reason": str | null }`.
- Loads the `MedicalRecord`; 404 if missing. If `record_status == "Pharmacy"`, set
  `record_status = "Cancelled"`, append the reason to `internal_notes` (or `prescription_notes`),
  write an audit row, commit. Idempotent: if already non-Pharmacy, return without re-writing.
- The pending query filters `record_status == "Pharmacy"`, so the script leaves the queue. The
  encounter row (diagnosis, notes) is retained — only the dispensing task is cancelled.

**Frontend** — `frontend/src/pages/Pharmacy.jsx`:
- Add a **Cancel** action on each pending-prescription card (distinct from the existing
  "Return to doctor" and "Dispense"), prompting for a reason, then refetch the pending list.

## Stream 3 — Radiology request cancel (backend + frontend)

**Backend** — `backend/app/routes/radiology.py`:
- `POST /api/radiology/{request_id}/cancel` (perm `radiology:manage`), body `{ "reason" }`.
- Loads the `RadiologyRequest`; 404 if missing. If status not already terminal, set
  `status = "Cancelled"`, record the reason (append to a notes/result field if present),
  audit, commit. Idempotent.

**Frontend** — `frontend/src/pages/Radiology.jsx`:
- Add a **Cancel** action on each request row (reason prompt). The UI already filters out
  `status === "Cancelled"`, so the row drops after refetch.

## Stream 4 — Billing invoice void (backend + frontend)  ⚠️ GL-aware

Invoices post to the ledger **at creation** via
`post_from_event(source_key="billing.invoice.created", source_id=<item.id>, amount=<amt>)`
(Dr A/R, Cr Revenue, mapping-driven, idempotent). A void must reverse that or A/R + revenue
stay overstated.

**Backend** — `backend/app/routes/billing.py`:
- `POST /api/billing/invoices/{invoice_id}/void` (perm `billing:manage`), body `{ "reason" }`.
- **Guard:** load the invoice with `with_for_update()`. If `status != "Pending"` (i.e. it's
  `Paid`, `Partially Paid`, `Pending M-Pesa`, or already `Cancelled`), return **400** with a
  clear message ("Only fully-unpaid Pending invoices can be voided; this one is <status>.").
  Only fully-unpaid invoices proceed.
- Set `status = "Cancelled"`, store the reason, write an audit row.
- **Reverse the GL posting** so the entry nets to zero. Recommended mechanism (contained, no
  new seeded mapping, keeps the migration gate a no-op): post a **mirror reversing journal
  entry** for the same amount that swaps the original's debit/credit (Dr Revenue, Cr A/R),
  referenced to the invoice (e.g. `reference=f"VOID-INV-{invoice_id}"`), idempotent on
  `(source, source_id)` so a double-void cannot double-reverse. The reversal must reuse the SAME
  accounts the `billing.invoice.created` mapping used for this invoice (look them up from the
  original posted `JournalEntry`/mapping rather than hard-coding), and run inside the void's
  transaction (SAVEPOINT, like `post_from_event`) so the status flip and the reversal commit or
  roll back together.
  - *Alternative considered:* add a seeded `billing.invoice.voided` ledger mapping and post via
    `post_from_event`. Rejected for now: it requires a new accounting DATA seed mirrored into the
    legacy-tenant seed hooks (per the `migrate_all_tenants` seed rule), enlarging scope and
    touching the seed gate. Revisit if a configurable reversal account is later needed.

**Frontend** — `frontend/src/pages/Billing.jsx`:
- Add a **Void** action on each invoice-queue row (confirm dialog + reason prompt). `/billing/queue`
  already filters to `["Pending","Partially Paid","Pending M-Pesa"]`, so a `Cancelled` invoice drops
  out after refetch.

---

## Testing

- **Backend (pytest, live-server, tenant `mayoclinic_db`, CSRF + cookie fixtures):**
  - Prescription cancel: auth gate, 404 unknown, status flips to `Cancelled` and drops from
    `/clinical/prescriptions/pending`.
  - Radiology cancel: auth gate, 404, status flips to `Cancelled`, drops from the queue.
  - Billing void: auth gate, 404, **400 when invoice is Paid/Partially Paid**, success path flips a
    Pending invoice to `Cancelled` + drops from `/billing/queue`, and the **GL nets to zero** (assert
    the reversing entry exists / the invoice's net A/R is zero), idempotent on double-void.
- **Frontend (Vitest + RTL):** Triage card Remove/Cancel calls the right endpoints; Pharmacy/
  Radiology/Billing rows expose the cancel/void action and call the right endpoint with the reason;
  existing page suites (`Pharmacy.test.jsx`, `Patients.test.jsx`) stay green.

## Migration / release notes

- **No schema change, no migration** — all status values already exist; the migration gate stays a
  no-op. Call this out in the PR.
- The Billing void is the only piece that touches accounting; it reverses the creation posting so the
  ledger stays balanced. No new ledger mapping/seed is introduced (recommended mechanism).

## Out of scope / YAGNI

- Refund/credit-note flow for Paid / Partially Paid invoices.
- Bulk "clear the whole queue" actions beyond the existing end-of-day (per-row is the ask).
- Hard deletion of any clinical/financial record.
- A configurable reversal account / `billing.invoice.voided` seeded mapping (noted as a future option).
