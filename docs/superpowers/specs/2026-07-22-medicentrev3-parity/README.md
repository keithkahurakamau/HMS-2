# MedicentreV3 → HMS-2 Parity & Gap Map

**Date:** 2026-07-22
**Author:** Parity audit (Claude Code, brainstorming → audit)
**Source material:** 156 unique screenshots of **MedicentreV3** (`medicentrev3.hanmak.co.ke` — a Kenyan enterprise Hospital Management System), captured at `C:\Users\keith-pc\Pictures\Screenshots\MEDICARE`.
**Subject under comparison:** the in-house **HMS-2** product in this repo (`frontend/` React + Vite + Tailwind, `backend/` FastAPI + SQLAlchemy, multi-tenant).

## Purpose

Treat MedicentreV3 as a **feature-parity specification**. For every screen and every interactive
element, record what MedicentreV3 does and whether HMS-2 already has it, then rank the gaps so we
can **upgrade HMS-2 in place** — build/restyle the missing pieces inside HMS-2's own design system,
one prioritized module at a time. Element-level, per the Phase-1 "strict parity — omission is a
failure" mandate. HMS-2 status is **verified against the actual code**, not guessed.

## Rebuild design principles (user directive)

**Preserve the full functional depth of MedicentreV3 — nothing dropped, no "lite" version.** The
redesign improves on MedicentreV3's cramped, dense Bootstrap UI, *not* on its feature set. Every
build cycle must honour four things:

- **Depth / parity** — every field, action, toggle, dropdown, and report MedicentreV3 exposes is
  carried over. That completeness is the entire point of this element-level map.
- **Flexibility** — keep the configurability: per-branch toggles, per-scheme pricing, templated
  forms / consents / reports, dynamic roles, merge-field messaging. Power users depend on it.
- **Usability** — standard iconography, predictable primary/secondary placement, and fewer clicks
  than MedicentreV3's deeply nested "Actions" menus (surface common actions; group the rest).
- **Space** — generous spacing and breathing room. Replace cramped data-tables with a calm,
  scannable layout (whitespace, clear hierarchy, responsive), while keeping **all** the data
  reachable. Depth *and* space are not in tension — density is organised, not removed.

## Legend

✅ **Have** · 🟡 **Partial** (exists, missing depth) · ❌ **Missing**.
Priority — *clinical necessity, then revenue*: **P1** = revenue leaking / SHA-mandated / can't operate without · **P2** = operational control · **P3** = polish.

## Module index

| # | Module | File | Overall | Headline gap |
|---|--------|------|---------|--------------|
| 1 | Billing | [01-billing.md](01-billing.md) | 🟡 Partial | Insurance RCM edge: pro-forma pre-auth, e-claims, credit-note/write-off, receipts register, gate pass |
| 2 | Clinical | [02-clinical.md](02-clinical.md) | 🟡 Partial | Strong core; **Theatre/Surgery**, Nutrition/special-clinics, **insurance eligibility**, order-sets/sick-note/optical |
| 3 | Dialysis | [03-dialysis.md](03-dialysis.md) | ❌ Missing | **Entire renal module** (orders, session state machine, observations, checklists) |
| 4 | Procurement | [04-procurement.md](04-procurement.md) | 🟡 Partial | Only the A/P *ledger*; **PRN→LPO→GRN→bill→voucher** P2P workflow + WHT missing |
| 5 | Inventory | [05-inventory.md](05-inventory.md) | 🟡 Partial | Items/batch/expiry have; **stock-take/variance**, multi-store, transfers, consumption missing |
| 6 | Accounts | [06-accounts.md](06-accounts.md) | 🟡 Partial | Real GL exists; **scheme depth (limits/copay/SHA/pricing)**, cashier-shifts UI, assets, capitation |
| 7 | Human Resource | [07-human-resource.md](07-human-resource.md) | ❌ Missing | **Full statutory payroll suite** (PAYE/NSSF/NHIF/Housing Levy, payslips, leave, attendance) |
| 8 | Security | [08-security.md](08-security.md) | ✅ Have (ahead) | RBAC+lockout+**audit** already present; gap = admin-editable roles/privileges UI |
| 9 | Configuration | [09-configuration.md](09-configuration.md) | 🟡 Partial | Spine exists; **granular per-branch billing toggles**, report templates, service-point rules |
| 10 | Communication | [10-communication.md](10-communication.md) | 🟡 Partial | Internal msg + email have; **patient SMS gateway + templated reminders** missing |
| 11 | Diary | [11-diary.md](11-diary.md) | ❌ Missing | Personal staff diary (patient calendar exists, staff diary doesn't) |
| 12 | Reports | [12-reports.md](12-reports.md) | 🟡 Partial | Dashboards have; **financial statements + debtors aging + statutory returns** gap — *purpose-built creative design* |
| 13 | Home / global chrome | [13-home-global.md](13-home-global.md) | ✅ Have (ahead) | Shell + dark-mode ahead; gap = active-room header/Queue, command palette, live chat |

## Executive summary

**HMS-2 is not behind — it's ahead in several places** (access control + audit log, a genuine
double-entry GL, dashboards, and workspace **dark mode** that MedicentreV3 lacks), and it already
owns the **core clinical flow** (registry, triage, consultation with ICD-10, lab, radiology,
admissions, appointments, referrals) and the **money backbone** (billing queue, M-Pesa, schemes,
claim schedules, deposits).

Where MedicentreV3 is materially ahead falls into five themes:

1. **Insurance revenue cycle** (the dominant P1) — pro-forma pre-authorization, electronic
   **"Send Smart Claim"** e-claims, credit-note/write-off/copay/reconcile, scheme OPD/IPD limits +
   **SHA flags** + per-scheme pricing, insurance **member-eligibility** lookup, receipts register,
   and debtors-aging reporting. This is SHA-mandated and directly protects revenue.
2. **Specialty clinical modules** — a whole **Dialysis/renal** module, a **Theatre/Surgery** module
   (MedicentreV3 sells it separately), and a **Nutrition** special-clinic (template-driven).
3. **Operational depth** — Procurement P2P (PRN→LPO→GRN→voucher + WHT), Inventory stock-take /
   multi-store / transfers, and a full **HR + statutory payroll** suite.
4. **Granular configuration** — per-branch billing/clinical/queue/inventory feature toggles,
   report-template selection, service-point billing rules.
5. **Patient outreach** — SMS gateway + templated appointment reminders.

## Prioritized backlog (build order)

Grouped into epics; each becomes its own brainstorm → spec → plan → implement cycle inside HMS-2's
design system.

### P1 — revenue & SHA compliance
- **Epic A · Insurance Revenue Cycle** (highest unconditional value; every tenant bills insurance):
  scheme depth (OPD/IPD limits, copay, **SHA flag**, smart-card, per-scheme pricing) → **pro-forma
  pre-auth** → **e-claims (Send Smart Claim)** → credit-note / write-off / apply-copay / reconcile →
  receipts register + cancel-with-reason → patient-bills finalize/unlock/force lifecycle →
  member-eligibility lookup → debtors-aging + revenue-by-scheme reports → granular billing toggles.
  *(Billing §1, Accounts §6.3, Clinical §2.1, Config §9.1, Reports §12.)*
- **Epic B · Theatre / Surgery module** (clinical + revenue; MedicentreV3 licenses it separately).

### P1* — conditional on services offered
- **Epic C · Dialysis / Renal module** — P1 **if the tenant runs a renal unit** (recurring, SHA-covered,
  insurable revenue). Cleanest greenfield in the whole audit.

### P2 — operational control
- Procurement P2P + withholding tax · Inventory stock-take/multi-store/transfers · Nutrition &
  special-clinics framework · Cashier shifts + asset depreciation + capitation · Configuration
  granular toggles / report templates / service-point rules · Patient **SMS reminders** · order-sets /
  sick-note / optical / consent templates · active-room header + Queue.

### P2/P3 — back-office & polish
- HR + statutory payroll (P2, but many tenants use external payroll) · Diary · command palette /
  live chat / contextual Guide · currency-denomination + misc finance utilities.

## Recommended first build target

Two sensible entry points — **the user picks in the next cycle**:

- **Dialysis (Epic C)** — recommended as the *first vertical slice to prove the redesign end-to-end*:
  entirely missing, self-contained, **no restyle risk to existing screens**, yet exercises the full
  stack (new model + alembic migration + `migrate_all_tenants` registration + RBAC permission +
  React page in HMS-2's design system) and delivers recurring insurance revenue. Best "prove the
  pattern" choice **if the tenant offers dialysis**.
- **Insurance Revenue Cycle (Epic A)** — the highest *unconditional* value and SHA-relevant, but
  larger and entangled with existing billing/accounting screens (more restyle risk). Best if
  protecting insurance revenue is the immediate priority; start with **pro-forma pre-auth +
  scheme depth**, which unlock e-claims.

**Suggested path:** build **Dialysis** first as the clean end-to-end proof of the upgrade approach,
then take **Epic A (Insurance Revenue Cycle)** as the flagship revenue programme.

## Coverage note

Element-level detail is complete for Modules 1–11 and 13 (from the screenshots). **Module 12
(Reports)** is a **purpose-built creative design** — no MedicentreV3 Reports screens were in the
capture (the walkthrough ended at Diary), so §12 designs the reporting suite from first principles
per the user's direction ("be creative, build up something for all the reports").
