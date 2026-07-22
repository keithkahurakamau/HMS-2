# Module 12 — Reports (`Reports`)

> **Design note:** MedicentreV3's Reports screens were **not** in the 156-shot capture (the walkthrough
> ended at Diary). Per the user's direction ("be creative, build up something for all the reports"),
> this is a **proposed, purpose-built Reports design** for HMS-2 — synthesised from (a) the per-screen
> report actions seen throughout the other 12 modules, (b) HMS-2's existing analytics/accounting code,
> and (c) the standard reporting a Kenyan HMS needs (SHA/NHIF, KRA, MOH/KHIS). It honours the rebuild
> principles: full depth, flexible filters, clean/spacious layout.

HMS-2 refs: `dashboard.py`, `analytics.py`, `InteractiveDashboard.jsx`, `AdminDashboard.jsx`, accounting routes, and the per-encounter printouts already wired into Actions menus.

---

## 12.1 The Reports hub (proposed UX)

A single **Reports** landing organised into **domain cards** (Financial · Receivables & Insurance ·
Cash · Revenue · Clinical · Pharmacy & Inventory · Procurement · HR/Payroll · Statutory · Printouts).
Selecting a report opens a **three-zone view**, spacious by design:

1. **Filter rail** (left, collapsible): date range + period presets, branch, scheme/underwriter,
   department, doctor/clinic, care type — only the filters relevant to the chosen report render.
2. **Preview** (centre): paginated, print-styled preview with subtotals/grand totals; drill-down where
   it helps (click a scheme → its invoices).
3. **Toolbar** (top): **Export** (PDF / Excel / CSV / Print), **Save view** (named filter preset),
   **Schedule** (email/SMS on a cron — reuses Communication + Configuration), and a favourite star.

Every report shares the same shell, so a new report = a query + a column spec, not a new page.

## 12.2 Report catalog

| Domain | Reports | HMS-2 today | Priority |
|---|---|---|---|
| **Financial statements** | Trial Balance · Income Statement (P&L) · Balance Sheet · Cash Flow · GL detail · Journal listing | 🟡 GL exists; statement rollups to build | P2 |
| **Receivables & insurance** | **Debtors Aging (by scheme)** · Scheme Statement · **Claim Status / Reconciliation** · Outstanding Invoices · Copayment Collections · Credit Notes & Write-offs | 🟡 claim schedules exist; aging/statements to build | **P1** |
| **Cash & cashier** | Daily Collections · **Cashier Shift Summary** · Receipts Register · Payment-mode Breakdown · M-Pesa Reconciliation | 🟡 payments exist; cashier rollups pending §6.2 | P2 |
| **Revenue analytics** | **Revenue by Scheme / Service / Department / Doctor / Clinic** · Revenue trend · Top items/services | 🟡 dashboards exist; sliceable reports to build | **P1** |
| **Clinical & operational** | Visit/Encounter stats · **Diagnosis / Morbidity (ICD-10)** · Lab TAT & test volumes · Radiology volumes · **Queue / wait-time** · Bed occupancy · Admissions/Discharges · Referrals | 🟡 analytics + queue metrics partial | P2 |
| **Pharmacy & inventory** | Stock Valuation · Stock Movement · **Expiry / Near-expiry** · Reorder · Dispensing Summary · Consumption · **Stock-take Variance** | 🟡 ties Inventory §5 | P2 |
| **Procurement** | Purchases by Supplier · GRN Summary · **Creditors Aging** · WHT Summary | ❌ ties Procurement §4 | P2 |
| **HR & payroll** | Payroll Summary · **PAYE / NSSF / NHIF / Housing Levy returns** · Attendance · Leave balances | ❌ ties HR §7 | P2 |
| **Statutory / regulatory** | **VAT Return** · **WHT Return** · SHA/insurance submission summaries · **MOH / KHIS 711/705** indicators | ❌ Kenya compliance | P2 |
| **Per-encounter printouts** | Visit Summary · Lab / Exam / Theatre report · Bill / Receipt / A/R Invoice · Prescription · Sick Note · Referral letter | ✅ mostly present in Actions menus | — |

## 12.3 Build approach

- **Report engine first:** one `reports` route module + a small registry (`{key → {title, filters,
  query, columns, exporters}}`) and one reusable React `<ReportView>` shell. Ship 3–4 reports on it to
  prove the shell, then add the rest as registry entries.
- **Start with the P1 set** — Debtors Aging (by scheme), Claim Status, Revenue by Scheme/Service —
  because they protect insurance revenue and pair with the Billing/Accounts P1 work. They read from
  data HMS-2 already has (invoices, claim schedules, payments).
- **Exports** reuse a shared PDF/Excel helper so every report gets all four output formats for free.

## Reports summary

HMS-2 has dashboards + per-encounter printouts; the gap is a **central, filterable Reports hub** with
financial statements, **debtors/scheme aging**, revenue slicing, and statutory returns. Highest value
is **P1** (aging + claim-status + revenue-by-scheme) — revenue protection that dovetails with Epic A.
Built on a shared report engine so all ~40 reports share one spacious, exportable shell.
