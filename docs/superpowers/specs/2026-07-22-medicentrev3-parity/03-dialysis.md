# Module 3 — Dialysis / Renal (`Dialysis`)

Sidebar sub-items: **Dialysis Orders · Dialysis Checklists**. Also surfaces as a **Special Clinic** (§2.5).

Screenshots: `155406, 155505` (Dialysis Orders + Actions) · `155526` (Dialysis Checklists).

**HMS-2 status: ❌ entirely Missing.** Verified — zero `dialysis`/`renal`/`dialyzer` references anywhere in `backend/app` or `frontend/src`. This is the cleanest, best-bounded greenfield module in the whole audit.

---

## 3.1 Dialysis Orders

**Elements — Dialysis Order Details (read-outs / captured fields):** Order No · Other Names · OP NO · HIV/HBC (serology status) · Created By · DateTime Created · **Vascular Access** · Treatment No · Surname · **Intake** · **Weight** (pre/post) · **Total UF** (ultrafiltration) · **Treatment Time** · Screening Date · **Priming** · **Dialysis Solution** (dialysate) · **Membrane Type** · **Dialyzer** · **K+ Bath** (potassium) · Blood Group · Status.

**[Actions ▾]:** Create Dialysis Order · Dialysis Checklist · **Dialysis Observations** · Capture Notes · **Mark as Connected** · **Mark as Disconnected** · **Mark as Completed** · Lab Request · Prescription · Diagnosis · Schedule Appointment · Billing · Queue Patient · Cancel Dialysis Order · **Dialysis Flow Chart** · Visit Summary · Lab Report.

**View: Dialysis Orders** table: Treatment No, Patient, Type, Ordered On, Ordered By, Treatment Time, Status. Filters: View (Pending completion / …), From, To, [View].

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Dialysis order w/ renal parameters (UF, dialysate, membrane, dialyzer, vascular access, K+ bath, priming, pre/post weight) | ❌ Missing | core renal prescription | P1* |
| Session state machine: Connected → Disconnected → Completed | ❌ Missing | intradialytic workflow | P1* |
| **Dialysis Observations** (intradialytic obs: BP/pulse/UF/venous pressure over time) | ❌ Missing | safety monitoring | P1* |
| **Dialysis Flow Chart** (session trend chart) | ❌ Missing | — | P2 |
| Capture Notes / Cancel Order | ❌ Missing | — | P2 |
| Link to Lab / Prescription / Diagnosis / Billing / Appointment | ❌ Missing | reuse existing HMS-2 modules | P2 |

## 3.2 Dialysis Checklists (machine safety pre-checks)

**Elements:** Name, Description, **Is Active** toggle, **[+]** add. **View: Dialysis Checklists** table (No, Name, Description). Seeded rows: _Blood leak test Check_, _Air Detect test check_, _Machine Function Test_.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Configurable pre-treatment machine safety checklist | ❌ Missing | run per session before "Connected" | P2 |

---

## Dialysis summary

A **self-contained, well-bounded specialty module** that HMS-2 lacks entirely. It is:

- **High recurring revenue** (dialysis is a repeat, insurable, SHA-covered service) → strong P1 *if the hospital runs a renal unit*.
- **Cleanly scoped** — order + session state machine + observations + checklists, reusing HMS-2's existing patient/queue/billing/lab/prescription plumbing.
- The natural **"prove the redesign end-to-end" first build** because it doesn't entangle with existing HMS-2 screens (no restyle risk), yet exercises the full stack (new model, migration, routes, RBAC permission, React page in HMS-2's design system).

\* P1 is conditional on the tenant offering renal services; otherwise P2.
