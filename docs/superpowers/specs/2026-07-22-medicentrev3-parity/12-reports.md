# Module 12 — Reports (`Reports`)

> ⚠️ **Coverage note:** the screenshot walkthrough ended at Diary (`085912`); the **Reports module's own screens were not captured**. This section is mapped at *feature level* from (a) the persistent `Reports` sidebar item, (b) the many per-screen report actions seen throughout other modules, and (c) HMS-2's actual reporting code. If Reports parity becomes a build priority, capture its screens first for an element-level pass.

HMS-2 refs: `dashboard.py`, `analytics.py`, `InteractiveDashboard.jsx`, `AdminDashboard.jsx`, `superadmin/` dashboards, plus per-module reports already referenced in Actions menus (Visit Summary, Lab Report, Examination Report, Theatre Report, Bill Report, Prescription Report) and accounting reports (`accounting*`).

---

## 12.1 Expected report catalog (inferred)

MedicentreV3 surfaces reports both **inline** (each screen's Actions → *Report*) and via a central **Reports** hub. Likely hub contents, by domain:

| Report domain | Examples | HMS-2 | Gap notes | Pri |
|---|---|---|---|---|
| **Financial statements** | Trial Balance, P&L, Balance Sheet, Cash Flow | 🟡 Partial | GL exists (`accounting`); verify statement generation | P2 |
| **Receivables/Payables** | Debtors/Creditors Aging, Scheme statements, Claim status | 🟡 Partial | claim schedules exist; aging reports? | P1 |
| **Cash & cashier** | Cashier Shift Summary, Receipts Summary, Daily Collections | 🟡 Partial | ties Accounts §6.2 cashier shifts | P2 |
| **Revenue** | Revenue by service/scheme/department/doctor | 🟡 Partial | dashboards exist; slice-and-dice reports? | P1 |
| **Inventory** | Stock Valuation, Variance, Expiry, Reorder | 🟡 Partial | ties Inventory §5 stock-take gap | P2 |
| **Clinical/operational** | Visit/Diagnosis stats, Lab TAT, Queue/wait-time, Morbidity | 🟡 Partial | `analytics` + queue metrics exist | P2 |
| **Statutory** | VAT return, WHT, PAYE/NSSF/NHIF summaries | ❌ Missing | ties HR §7 + Accounts §6.4 tax | P2 |
| Per-encounter printouts | Visit Summary, Lab/Exam/Theatre report, Bill/Receipt | ✅ Have (mostly) | already in Actions menus | — |

---

## Reports summary

HMS-2 has **dashboards + analytics + per-encounter printouts**, but a **central Reports hub with financial statements + aging + statutory returns** is the likely gap. Highest-value items are **P1** because they protect revenue (debtors aging, revenue-by-scheme, claim status) and pair directly with the Billing/Accounts P1 work:

- 🟡 **Debtors/scheme aging + revenue-by-scheme/service reports** — **P1**
- 🟡 **Financial statements** (TB/P&L/BS), **cashier/collections**, **inventory valuation/variance** — P2
- ❌ **Statutory returns** (VAT/WHT/PAYE) — P2 (depends on HR + tax config)

**Action:** capture the Reports module screens to convert this inferred map into an element-level catalog before building.
