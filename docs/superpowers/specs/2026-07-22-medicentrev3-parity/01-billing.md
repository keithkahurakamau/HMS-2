# Module 1 — Billing (`$ Billing`)

Sidebar sub-items: **Pharmacy · Over The Counter · Patients Bills · Receipts · A/R Invoices · Gate Pass · Pro Forma Invoices · Refunds on Advance**.

Screenshots: `153059, 153112` (Pharmacy) · `153134–153210` (OTC) · `153230–153327` (Patients Bills) · `153357` (Receipts) · `153424–153526` (A/R Invoices) · `153545` (Gate Pass) · `153615` (Pro Forma) · `153649–153701` (Refunds on Advance).

Legend: ✅ Have · 🟡 Partial · ❌ Missing. HMS-2 refs verified against `backend/app/routes/{billing,pharmacy,accounting_debtors}.py`, `backend/app/models/{billing,accounting}.py`, `frontend/src/pages/{Billing,Pharmacy,Accounting}.jsx`.

---

## 1.1 Pharmacy — dispense & bill

**Screen elements**
- Collapsible **Patients Details** panel ("click here to hide") — read-outs: OPD No, Surname, Othernames, Age, Sex, Residence, Occupation, **Scheme** (blue), **Rem. Credit** (red), Note (orange).
- **Queue** panel: `Search` input; table cols: Queue No, OPD No, Name, From, Mins.
- **Bill No** header + **[Actions ▾]** menu: Prescription Refills · Billing · Finalize Bill · Finalize Bill & New · Prescription · Queue Patient · Pick Patient In Admission · View Invoices · Prescription Report · Visit Summary · Lab Report · Theatre Report · Examination Report.
- **Bill Payment Details** read-outs: Bill No, Amount Deposited, Total Amount Used, Total Amount Refunded, Deposit Balance, Total Bill Amount, Amount Due.
- Action buttons: **[Mark as dispensed]**, **[Dispensed & Finalize]**.
- **View: Bill Items** table — export `Excel / CSV / Print`; select-all checkbox; cols: Name, Storage, Billed On, Scheme, Status, Instruction, Refills, Qty, Rate, Net Amount (+ overflow).

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Patient details panel (scheme, rem-credit) at dispense point | 🟡 Partial | `ActivePatientBar` + pharmacy queue exist; **Rem. Credit / Scheme** not surfaced at dispense | P2 |
| Room/branch queue with wait-mins | ✅ Have | `queue.py` + `DepartmentQueue` | P3 |
| Bill payment ledger (deposited/used/refunded/due) | 🟡 Partial | payments exist; **deposit ledger read-out** not shown | P1 |
| Mark as Dispensed / Dispensed & Finalize | ✅ Have | pharmacy dispense flow | P3 |
| **Prescription Refills** | ❌ Missing | no refill tracking | P2 |
| Bill-items grid + Excel/CSV/Print export | 🟡 Partial | grid yes; universal export no | P3 |
| Report actions (Prescription/Visit/Lab/Theatre/Examination) | 🟡 Partial | some reports exist; not this bundled action menu | P3 |

## 1.2 Over The Counter — direct sale (walk-in)

**Screen elements**
- **[Create New]** → **Create Direct Sale** modal (Customer Name input, [+], close X).
- Item entry: **Change Item Storage Location** toggle → storage dropdown (Pharmacy); **Item Type** dropdown (Product); **Product Name** searchable dropdown; read-outs Qty in stock / Units / Unit Cost / VAT %; **Change Billing DateTime** toggle → datetime; **Scheme** dropdown (Cash Payers); **Unit Price** + **Change Unit Price** toggle; **Sale Quantity**; **% Discount** + **Use Discount Amount** toggle → amount; **Amount**; **Net Amount**; **Update (If Item exists)** toggle; **Comment**; **[+]** add.
- **Direct Sales** table: Search; cols No, Name, DateTime Created, Net Amount, **[Dispense & Finalize]** per row.
- **Payment Details**: Sales No, Total Amount, Type of Sale (Cash Sale), Amount To Pay, Payment Mode (Cash), Amount Tendered, Cash dropdown, Change, **[Save Payment]**.
- **View: Sale Items** table: Name, Timestamp, Scheme, Status, Qty, Rate, % Disc, Net Amount. Legend: Sold / Invoiced / Pending.

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Walk-in direct-sale entry (non-patient) | ❌ Missing | no OTC/`direct_sale` path — retail/walk-in revenue uncaptured | P2 |
| Cash-sale payment (tendered/change) | 🟡 Partial | patient payments exist; no standalone cash-sale tender/change | P2 |
| Discount by % or absolute amount at line | 🟡 Partial | verify pharmacy line discounts | P3 |
| Sale-items status legend (Sold/Invoiced/Pending) | ❌ Missing | — | P3 |

## 1.3 Patients Bills — consolidated register

**Screen elements**
- **Search bill by patient details** (Name, ID, OPNO) input + search button.
- **Bill Details** read-outs: Bill No, Created On, Status, Visit ID, Patient, Age, Net Amount, Amount Paid, Balance.
- **[Billing ▾]**: View Selected Bill Report · **Finalize Selected Bill** · **Unlock Selected Bill**.
- **View: Patient bills** table — export `Copy / CSV / Excel / Print`; Search; select-all; cols: Bill No, Ref, Patient, Created On, Net Amount, Amount Paid, Discount, Copayment, Balance.
- Footer totals: G Amount, G Paid, G Disc, G Bal; **[Finalize Bill(s)]** **[Force Finalize Bill(s)]**.
- Filters: View (Pending), Scheme (All), Care Type (All), From, To, **[View]**.

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Consolidated patient-bill register + search | 🟡 Partial | billing queue exists; not a full searchable bill register | P1 |
| Finalize / Unlock / **Force-Finalize** lifecycle | ❌ Missing | only invoice void; no lock/unlock/force lifecycle | P1 |
| Filters by scheme + **care type** + date | 🟡 Partial | date yes; scheme/care-type filters no | P2 |
| Grand-total footer (amount/paid/disc/balance) | 🟡 Partial | verify totals row | P3 |

## 1.4 Receipts — register, reprint, cancel

**Screen elements**
- Filter/Search: View (Not Cancelled), From, To, [View]; Search Word + **[Search Receipt(s)]** (Issued To / Paid in by / Receipt No).
- Right panel: Receipt No, Issued To, Paid By, **[Update]**.
- **View Receipts** table — export Excel/CSV/Print; Search; cols: Receipt No, Created On, Issued To, Issued By, Amount Paid, Mode, **[print icon]** per row.
- **Receipts Items** table: Search; select-all; cols No, Item, Rate, Qty, % VAT, % Disc, Net Amount.
- Right: Receipt No, Issued To, Date Issued, **Ticked Item(s) Total**, **Cancellation Reason** textarea, **[Cancel Ticked Item(s)]**.

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Receipt register (issued to/by, mode, amount) | 🟡 Partial | payments/transactions logged; no dedicated receipt register UI | P1 |
| Reprint receipt | 🟡 Partial | verify receipt print | P2 |
| **Cancel receipt item with reason** (audit) | ❌ Missing | no receipt cancellation-with-reason | P1 |
| Edit "Issued To / Paid By" | ❌ Missing | — | P3 |

## 1.5 A/R Invoices — insurance receivables (RCM)

**Screen elements**
- Search: Search Word + **[Search Invoice(s)]** (Invoice To/Invoice No).
- **Invoice** read-outs: A/R Invoice No, Bill No, Customer Name, Invoice To, Telephone#1, Address, Email, Status, DateTime Created, Due date, Amount Receivable, Cover Amount, Discount Amount, Write-Off Amount, Total Amount Paid, Outstanding Balance.
- **Selected Invoices**: **Batch Payment** toggle, Total.
- **Action buttons**: View Invoice Detailed · **View Invoice ▾** (Summary Report / Condensed by Item Report / With Underwriter Info Report) · **Receive Payment** · **Apply Copayment** · **Reconcile Payment ▾** (From File / From Selected Invoice(s) / Pending Reconciliations) · **Create Credit Note** · **Sales Discount** · **Send Smart Claim** · **Mark as Dispatched** · **Write-Off ▾** (Single Selected Invoice / Multiple Ticked Invoices) · **Cancel Invoice**.
- **View: Invoices** table — export Copy/CSV/Excel/Print; Search; select-all; cols: Inv No, Scheme, Patient, Claim ID, Mem No, Created On, Net Amount, Amount Paid, Discount, Credit Note, Write-Off, Rebate, Balance.
- Filters: View (Pending), Scheme (All), From, To, [View].

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Insurance schemes + provider master | ✅ Have | `accounting.py` Insurance company + scheme models | P3 |
| Claim schedules draft→submitted→settled/rejected | ✅ Have | `accounting_debtors.py` | P2 |
| Client deposits + allocate deposit across claim items | ✅ Have | `accounting_debtors.py` bulk-allocate | P2 |
| A/R invoice register with claim-id / mem-no columns | 🟡 Partial | claim schedules exist; not a per-invoice register w/ these cols | P1 |
| **Receive Payment** on invoice | 🟡 Partial | payments exist; not invoice-scoped receive | P1 |
| **Apply Copayment** | ❌ Missing | copay not applied at invoice | P1 |
| **Reconcile Payment (from file / bulk)** | 🟡 Partial | deposit allocation ≈ partial; no bank-file reconcile | P1 |
| **Create Credit Note** | ❌ Missing | no adjustment instrument | P1 |
| **Write-Off (single/multi)** | ❌ Missing | no bad-debt write-off | P1 |
| **Send Smart Claim** (electronic e-claim submission) | ❌ Missing | internal schedules only; **SHA e-claims** absent | P1 |
| Sales Discount / Rebate post-invoice | ❌ Missing | — | P2 |
| Underwriter/condensed report variants | ❌ Missing | — | P3 |

## 1.6 Gate Pass — discharge/exit clearance

**Screen elements**
- **Gate Pass Details**: Gate Pass No, Created By, Created On, Status, OP/No, Surname, Othernames, **Total Bill, Payments, Balance**; **[View Gate Pass]**.
- **View: Gate Passes** table — export Excel/CSV/Print; Search; select-all; cols No, Surname, Othernames, Created On, Status, Created By.
- Filters: View (Not Cancelled), From, To, [View]; **[Cancel Selected]** **[Authorize Selected]**.

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Exit clearance tied to bill balance | ❌ Missing | no gate-pass — discharge revenue leakage risk | P2 |
| Authorize / Cancel gate pass | ❌ Missing | — | P2 |

## 1.7 Pro Forma Invoices — pre-authorization estimate

**Screen elements**
- **Pro Forma Invoice** read-outs: Invoice No, Scheme, Visit No, Patient, OPD No, IP No, Date of Admission, Date of Discharge, Status, Created On, Created By, Cost.
- **[Actions ▾]**: New Pro Forma Invoice · Invoice Items · **Mark as Checked** · **Mark as Approved** · **Bill Invoice Item(s)** · View Report.
- **View: Pro Forma Invoices** table: Search; cols No, Patient, Scheme, Created On, Created By, Status, DOA, DOD, Total Cost. Real rows use **SHA SURGICAL / SHA INPATIENT** schemes.
- Filters: Status (Pending Approval), Between (From/And), [View].

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Pre-admission cost estimate (DOA/DOD/IP) | ❌ Missing | no pro-forma — **blocks SHA surgical pre-auth** | P1 |
| Workflow Pending→Checked→Approved→Bill | ❌ Missing | — | P1 |
| Convert approved pro-forma → real bill items | ❌ Missing | — | P1 |

## 1.8 Refunds on Advance _(rendered under Accounts breadcrumb)_

**Screen elements**
- Form: **Description** textarea, **Refund By** input, **Returned On** datetime, **Payment Mode** (Cash), **Cash** dropdown, **Amount**, **[+]**.
- **[Actions ▾]**: **Approve Refund** · **Receipt Refund** · **Cancel Refund** · **Print Receipt**.
- **View: Refunds** table: Search; cols No, Created By, Refund On, Refund By, Mode, Status, Receipted By.

| Element / capability | HMS-2 status | Gap notes | Pri |
|---|---|---|---|
| Refund unused patient deposit | 🟡 Partial | some refund handling in `billing.py` | P2 |
| Approve → Receipt → Print refund workflow | ❌ Missing | no multi-step advance-refund workflow | P2 |

---

## Billing summary

HMS-2 owns the **money backbone** (billing queue, M-Pesa payments, insurance schemes, claim
schedules, client deposits, deposit allocation). MedicentreV3 is materially ahead on the
**insurance revenue-cycle edge**, and nearly all of it is **P1 revenue**:

- ❌ **Pro-forma pre-authorization** (SHA surgical/inpatient) — P1
- ❌ **Electronic e-claims** ("Send Smart Claim") — P1, SHA-relevant
- ❌ **Credit note / write-off / apply-copayment / reconcile-from-file** — P1
- 🟡 **Receipts register + cancel-with-reason** — P1
- ❌ **Patient-bills finalize/unlock/force-finalize lifecycle** — P1
- ❌ **Gate pass**, ❌ **OTC direct sale**, 🟡 **advance-refund workflow** — P2

**Build-cluster suggestion:** a single "Insurance Revenue Cycle" epic (pro-forma → e-claim →
credit-note/write-off → reconcile) captures most P1 value and rides on the existing accounting
models.
