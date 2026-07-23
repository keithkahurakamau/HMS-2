# Module 6 — Accounts / Finance (`Accounts`)

Sidebar sub-items (18): **Fiscal Periods · Ledger Accounts · Payment Modes · Banks · Schemes · Scheme Items · Cashier Shifts · Journal Vouchers · Taxes · Cash Transfers · Bank Deposits · Cheques · Bank Reconciliation · Currency Units · Asset Management · Budgeting · Capitations · Opening Balances**.

Screenshots: `082912–083024` (Ledger Accounts) · `083130–083141` (Payment Modes) · `083201` (Banks) · `083226` (Schemes) · `083254–083305` (Scheme Items) · `083526` (Cashier Shifts) · `083541` (Journal Vouchers) · `083552` (Taxes) · `083615` (Cash Transfers) · `083641` (Cheques) · `083710` (Bank Reconciliation).

HMS-2 refs: `accounting.py`, `accounting_bank.py`, `accounting_budget.py`, `accounting_config.py`, `accounting_debtors.py`, `accounting_notes.py`, `cheques.py` + `models/accounting.py`, `models/cheque.py` + `Accounting.jsx` (3,248 lines) + `accounting/` (BudgetingTab, NotesTab, BulkAllocateModal). Verified by grep: fiscal periods ✅, journals ✅, banks/bank-rec ✅, cheques ✅, budgets ✅, cashier-shifts (modeled) 🟡, asset-mgmt 🟡, tax-config 🟡, currency 🟡; **capitation ❌ (zero hits)**.

**This is HMS-2's second-strongest area** — a real double-entry GL already exists. Gaps are depth + a couple of specialized instruments.

---

## 6.1 Chart of Accounts & periods

**Ledger Accounts** (`082912`): Account Details (Account No, **Account Class** +, Account Name, **Cash Flow Category**, +); **Sub-Account Details** (Sub-Account Name, Account, Current balance, +). View: Accounts — full CoA (Inventory, Prepaid Salary, Cash, Fixed Assets, Bank, Accounts Receivable, Accounts Payable, Accrued Liabilities, Customer Deposits, Loans, Owners Equity, Revenue, Other Income). **[Actions ▾]**: Configure · Copy Ledger Accounts · Transfer Sub Account Balance · Cash Flow Categories · Change Ledger Account Names Case.

**Journal Vouchers** (`083541`): Source Reference, Description, Amount, Department, Transaction Date Time, Status, Posted By; **Journal Entries**, **Unpost Selected Journal**, Save. View (JV ID, Fiscal No, Transacted On, Source Ref, Description, Amount). Filters View (Manual – Not Posted / …), For All Periods.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Chart of accounts + sub-accounts + classes + cash-flow category | ✅ Have | `accounting_defaults_seed` + `accounting.py` | — |
| Fiscal Periods (open/close) | ✅ Have | grep-verified | — |
| Manual Journal Vouchers w/ post/unpost | ✅ Have | | — |
| Opening Balances | 🟡 Partial | verify dedicated opening-balance entry | P3 |
| Copy CoA / transfer sub-account balance / rename-case utilities | 🟡 Partial | admin conveniences | P3 |

## 6.2 Cash, bank & payments

**Payment Modes** (`083130`): Name, **Payment Mode Category** +, **Sub Account**, **API** (None / M-Pesa…), **Selection Level**, **Is Default**, **Can Be Received** toggles. Rows: Cash At Hand, MPESA, Cheque-Equity, Petty Cash, EFT-Equity, PAYBILL, Debit/Credit Card. Actions: Payment Mode Selection Levels.
**Banks** (`083201`): Name, Account No, Branch Code, Bank Code, Branch.
**Cashier Shifts** (`083526`): Shift ID, User, Beginning/Ending, Opening, Status. **[Actions ▾]**: End Shift · Shift Receipts · Cashier Shift Summary Report · Cashier Shift(s) Receipts Summary. Filter View (My Active Shift).
**Cash Transfers** (`083615`): Source/Destination Sub-Account (+ balances), Amount, Amount-in-words, Received By, DateTime, **[Transfer]**; view has **Ack By / Ack Amount** (two-sided acknowledgment).
**Cheques** (`083641`): Bank Account, Date Payable, **Offset (GL Account)**, Amount, Cheque No, Description, Destination GL Account, GL Sub Account, Reference, **[Post]**.
**Bank Reconciliation** (`083710`): Statement Balance, Cleared Book Balance, Adjusted Book Balance. **[Actions ▾]**: Create New · **Book Adjustments** · Clear Entries · Reconcile · Cancel · Reconciliation Report.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Configurable payment modes (GL sub-account + API + default/receivable) | 🟡 Partial | M-Pesa + cash exist; configurable-mode CRUD w/ selection levels? | P2 |
| Banks master | ✅ Have | | — |
| **Cashier Shifts** (till open/close, shift receipts, summary) | 🟡 Partial | shift **modeled** in `accounting.py`; verify UI + shift receipts | P2 |
| Cash Transfers w/ two-sided acknowledgment | 🟡 Partial | verify inter-account transfer + ack | P3 |
| Cheques w/ GL offset + post | ✅ Have | `cheques.py` + `Cheques.jsx` | — |
| Bank Reconciliation (statement vs book, adjustments) | ✅ Have | `accounting_bank.py` | — |
| Bank Deposits | 🟡 Partial | verify deposit slips | P3 |
| **Currency Units** (cash denominations for till counting: KES 1000/500/…/1 notes & coins, w/ multiplicand) | ❌ Missing | denomination-count helper for cashier reconciliation, **not** forex | P3 |

## 6.3 Insurance schemes & pricing

**Schemes** (`083226`): Name, Description, Underwriter, Category, addresses, Telephones, Email, **Credit Period From/To**, **Receivable SubAccount**, **Deposit SubAccount**, Current Balance, Pin Number, Code; flags **Is Active · Is Default Scheme · Is Employee Scheme · Uses Smart Card · Is SHA Scheme**. View: Schemes (Scheme No, Name, Underwriter, **OPD Limit**, **IPD Limit**, **Copayment**, Flags). Real schemes: Cash Payers, NHIF OP/IP/Dialysis/Maternity/Dental, SHA DIALYSIS, THIKA GREENS.
**Scheme Items** (`083305`) = "Scheme Prices": select scheme; **Scheme Items** (Name, **Markup**, **Factor**, Price) vs **All Items (Default Scheme Prices)** (Name, Unit Price); Item Type Products/Services; move ‹ › ; **Copy Prices From Scheme → To Scheme**; Actions: Export/Import Scheme Prices.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Insurance scheme master (underwriter, credit period, AR/deposit sub-accounts) | ✅ Have | `accounting.py` scheme model | — |
| **OPD/IPD limits + copayment per scheme** | 🟡 Partial | verify per-scheme limit/copay fields | P1 |
| **SHA-scheme flag + Smart Card + Employee scheme** | 🟡 Partial | SHA flag drives e-claim eligibility | P1 |
| **Per-scheme pricing (markup/factor, copy between schemes)** | 🟡 Partial | verify scheme price lists + copy | P1 |

## 6.4 Tax, assets, budget & capitation

**Taxes** (`083552`): VAT Type (Name, **Per Rate%**, VAT Liability Sub-Account, Tax Code) — rows VAT Exempt 0 / Zero Rated 0 / Reduced 12 / **Standard 16**; Other Tax (Name, Per Rate%).
**Asset Management / Budgeting / Capitations / Opening Balances** (not individually screenshotted; standard finance modules).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| VAT types (16%/exempt/zero) + other tax + GL liability mapping | 🟡 Partial | `accounting_config` tax; verify VAT-type CRUD + tax code | P2 |
| Budgeting | ✅ Have | `accounting_budget.py` + `BudgetingTab.jsx` | — |
| **Asset Management** (fixed-asset register + depreciation) | 🟡 Partial | asset referenced; depreciation schedule? | P2 |
| **Capitations** (insurance PMPM contracts) | ❌ Missing | zero hits — specialized recurring insurance revenue | P2 |

---

## Accounts summary

HMS-2 already runs a **genuine double-entry GL** (CoA, periods, journals, banks, bank-rec, cheques, budgets, debtors/claims). Parity work here is **depth + two specialized pieces**, not a rebuild:

- 🟡 **Scheme depth** — OPD/IPD limits, copayment, **SHA flag**, smart-card, **per-scheme markup pricing** — **P1** (drives correct insurance billing + e-claim eligibility; ties to Billing §1.5–1.7)
- 🟡 **Cashier Shifts** UI (till reconciliation, shift receipts) — P2
- 🟡 **Asset Management** (depreciation), **Tax-type CRUD**, configurable **Payment Modes** — P2
- ❌ **Capitations** (PMPM) — P2
- 🟡 Currency Units, Bank Deposits, Opening Balances utilities — P3
