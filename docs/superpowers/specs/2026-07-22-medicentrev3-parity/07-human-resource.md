# Module 7 — Human Resource / Payroll (`Human Resource`)

Sidebar sub-items (11): **Consultants · Employees · Pay Periods · Payroll Parameters · PAYE Tax Ranges · Salary Advances · Payslips · Leaves · Scheduling · Attendances · Employee Credentials**.

Screenshots: `084106` (Employees) · `084144` (Pay Periods) · `084203–084221` (Payroll Parameters) · `084251` (PAYE Tax Ranges) · `084306–084322` (Salary Advances) · `084351` (Payslips) · `084404–084419` (Leaves) · `084452` (Attendances).

**HMS-2 status: ❌ almost entirely Missing.** Verified: no payroll/payslip/attendance/pay-period routes; `NSSF`/`PAYE` appear only as GL accounts in `accounting_defaults_seed`; `users.py` is system-login accounts, not an HR employee master. `Calendar.jsx` has generic "leave" calendar strings only.

This is a **full Kenyan HR + statutory payroll suite**. It is a large greenfield module — but note it's back-office (neither clinical nor patient-revenue), so **P2** under the chosen lens, and many tenants run payroll in external software.

---

## 7.1 Employees (HR master)

**Elements:** Staff Number*, Surname*, Other Names*, Sex*, Date Of Birth*, ID Type*, ID Number*, Marital Status*, Telephone 1*/2, Email, Postal Address/Code, Physical Address, Current Residence, Street And House No, Town/City*, Nationality*, **Next Of Kin** (+ Relationship, NOK Contact/Place Of Work/Occupation/ID Type/ID Number), **Department***, Designation, **Employment Type***, Date Employed*, **Mode of Payment***, Payment Ref, Bank/Branch/Branch Code/Account No, Payroll No, **NSSF No**, **KRA Pin No**, **NHIF No**, **Link To System User**, **Can Access the Portal**. **[Actions ▾]** + View: Employees (Staff No, Surname, Other Names, Sex, ID No, Telephone No).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Employee master w/ statutory IDs (NSSF/NHIF/KRA PIN) | ❌ Missing | `users` ≠ HR employees; no statutory fields | P2 |
| Link employee ↔ system user + portal access | 🟡 Partial | users exist; no HR↔user link | P3 |

## 7.2 Pay Periods

**Elements:** Pay Year, Pay Month, Period Beginning/Ending Date, **Is Current Pay Period**. View: Pay Periods (Period ID, Pay Year, Pay Month, Beginning/Ending Date, Is Current). Year filter.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Monthly pay-period ledger | ❌ Missing | | P2 |

## 7.3 Payroll Parameters + 7.4 PAYE Tax Ranges

**Payroll Parameters:** Name, Category (+), Round To, Default Value; flags Is Default / Is Required / Is Salary Advance / **Is Employee Medical Invoice Deduction** / Use Configured Rates. Rows: Basic Pay, **NHIF**, **NSSF**, Personal Relief (2,400), **PAYE**, Salary Advance, Insurance relief, **Housing Levy**. **[Actions ▾]**: Parameter Rates · Employer Contribution · Categories.
**PAYE Tax Ranges:** Lower/Upper Limit, Tax Rate %, Has No Limit; KRA bands (0–24k→10%, 24k–32.3k→25%, 32.3k–500k→30%, 500k–800k→32.5%, 800k+→35%); Minimum Taxable Pay 24,001.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Configurable earnings/deductions (Basic, NHIF, NSSF, PAYE, Housing Levy, reliefs) | ❌ Missing | full statutory payroll engine | P2 |
| **Employee medical-invoice deduction** (staff treated on credit → payroll deduct) | ❌ Missing | neat HMS↔payroll tie-in | P2 |
| KRA PAYE bands + employer contributions | ❌ Missing | statutory compliance | P2 |

## 7.5 Salary Advances

**Elements:** Employee, Amount Requested, Purpose, Pay From Month/Year, **Payment Plan** (Clear fully at specified period / …). View: Salary Advance Requests (Request #, Employee, Requested On, Plan, Begin, Status, Requested, Approved, Disbursed, Cleared). **[Actions ▾]**: Approve · Reject · Disburse · View Payments · Cancel.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Salary advance request → approve → disburse → clear from payroll | ❌ Missing | | P3 |

## 7.6 Payslips

**Elements:** Pay-period selector; Employee details panel + **[View Payslip]**. View: Payslips For Period (Surname, Other Names, Department, Basic Pay, Gross Earning, Total Deductions, Net Pay, Status). **[Pay Selected Payslip(s) ▾]**: Single Payment Mode / Multi Payment Modes; Cancel Payslip(s); Print Payslip(s).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Payslip generation (gross/deductions/net) + pay + print | ❌ Missing | | P2 |

## 7.7 Leaves

**Elements:** Leave Management **calendar** (month/week/day, List View). **[Actions ▾]**: Create Leave Request · Leave Types · Pending Leave Requests · Configure Holidays.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Leave requests + types + holidays + calendar | ❌ Missing | `Calendar.jsx` is patient calendar, not staff leave | P3 |

## 7.8 Attendances · 7.9 Scheduling

**Attendances:** table (Employee, Check In, Break, Check Out, **Tardiness**, Status, Working Hrs, **Overtime**); filter Status (Present/…), date range.
**Scheduling:** staff rota/shift scheduling (sidebar item; screen not captured).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Attendance (check-in/out, tardiness, overtime, working hrs) | ❌ Missing | | P3 |
| Staff scheduling / rota | ❌ Missing | ties to consultation-room assignment | P3 |

## 7.10 Consultants · 7.11 Employee Credentials

**Consultants:** visiting/consultant doctors (fee arrangements) — overlaps HMS-2's per-user **consultation fee** (`billing.py /consultation-fee`).
**Employee Credentials:** professional licence/certification tracking (likely w/ expiry).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Consultant doctors + fee arrangements | 🟡 Partial | consultation-fee per user exists; no consultant fee-split/payout | P2 |
| Employee credential/licence + expiry tracking | ❌ Missing | compliance (practising licences) | P3 |

---

## Human Resource summary

An entire **Kenyan HR + statutory payroll suite** that HMS-2 lacks. Big, but **P2** under "clinical → revenue" (back-office, not patient-facing):

- ❌ **Statutory payroll engine** (Basic/PAYE/NSSF/NHIF/**Housing Levy**/reliefs, KRA bands, payslips) — P2, but only if the tenant wants payroll in-HMS vs external software
- ❌ **Employee master + attendance + leaves + scheduling** — P2–P3
- 🟡 **Consultants fee-split** (partial via consultation-fee) — P2
- **Nice tie-in:** *Employee medical-invoice deduction* links staff treatment (Billing) → payroll, which external payroll can't do — the one genuinely HMS-native reason to build payroll here.
