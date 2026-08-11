# Module 4 — Procurement / Procure-to-Pay (`Procurement`)

Sidebar sub-items: **Suppliers · Supplier Bills (A/P Invoices) · Purchase Requisition Note · Purchase Orders · Goods Received Notes · A/P Payment Vouchers · Supplier Prepayments**.

Screenshots: `155546–155601` (Suppliers) · `155633` (Supplier Bills) · `155651` (PRN) · `155710–155739` (Purchase Orders) · `155818` (GRN) · `155855` (Payment Vouchers) · `155923` (Supplier Prepayments).

HMS-2 refs: `accounting.py` (A/P control account, supplier refs), `inventory.py`, `Accounting.jsx`. Verified: **no** GRN / payment-voucher / withholding / LPO implementation — only ledger accounts + a module flag in `core/modules.py`.

The full **procure-to-pay chain (PRN → LPO → GRN → Supplier Bill → Payment Voucher)** is essentially Missing; HMS-2 only has the accounting *ledger* endpoint of it.

---

## 4.1 Suppliers

**Elements:** Supplier Details — Supplier Name, Contact Person, Country (+add), Description, Physical Address, Town/City (+add), Telephone 1, Postal Address, Website, Telephone 2, Postal Code, **Sub Account** (GL link), Email, [+]. **[Actions ▾]**: Activate / Deactivate / Delete Supplier · Import Suppliers. **View: Supplier(s)** (Supplier No, Supplier Name, Telephone, Email, Contact Person; Excel/CSV/Print; Search).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Supplier master (contacts, GL sub-account) | 🟡 Partial | supplier refs in `accounting`/`inventory`; no dedicated supplier CRUD screen | P2 |
| Activate/Deactivate/Import suppliers | ❌ Missing | | P3 |

## 4.2 Supplier Bills (A/P Invoices)

**Elements:** Supplier Bill Details — Supplier, Alias, Description, Reference, A/P Invoice No, Terms, DateTime Created, Due Date; tab buttons: **Supplier Bill Items · Credit Notes · Withholding Taxes · View Invoice Payments · View Invoice Report · Create Payment Voucher · View Payment Vouchers**; Supply Bill Payment (Is Partial Payment, Selected Total, Payment Mode, Cash, Balance, **[Pay Bill]**), Save. **View: Supplier Bills** (Bill No, AP Inv No, Supplier, Alias, Created On, Net Amount, Credit Note, **Withholding Tax**, Amount Paid, Balance, Approved Payment).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| A/P control account in CoA | ✅ Have | `accounting_defaults_seed` | — |
| Supplier bill (invoice) capture + items | ❌ Missing | no A/P bill entry workflow | P2 |
| **Withholding tax** on supplier bills (KRA WHT) | ❌ Missing | tax-compliance gap | P2 |
| Supplier credit notes | ❌ Missing | | P3 |
| Partial payment / pay-bill | ❌ Missing | | P2 |

## 4.3 Purchase Requisition Note (PRN)

**Elements:** PRN No, DateTime Created, Storage Location, Authorized By, Created By, DateTime Authorized, **Is Authorized** toggle, **Committed To Stock** toggle; buttons PRN Items, View PRN Report, Save. **View: PRNs** (PRN No, DateTime Created, Created By, Storage Location, Department). Filters: View (Pending…), Between.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Internal stock requisition | 🟡 Partial | `Inventory.jsx` has requisition-ish flow; not a PRN→approve→commit chain | P2 |

## 4.4 Purchase Orders (LPO)

**Elements:** Storage Location, Order Reference, DateTime Created, Supplier, Valid Before, Terms & Conditions, Alias, DateTime Issued; Selected LPO Details (PO #, Is Committed To Stock, Prepared By); buttons Purchase Order Report, **Purchase Order Report W/O Prices**, Purchase Order Items, Mark as Received, Save. **[Actions ▾]**: PO Items · Mark as Checked · Mark as Approved · Authorize · Cancel LPO · Unlock · Edit Non-Stock Items · Receive Non-Stock · **Run Budget Check** · View PO / View PO W/O Prices. **View: Purchase Order** (LPO No, Supplier, Alias, Created On, Checked By, Approved By, Authorized By, Net Amount). Filters: View (Pending), Between.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| LPO with check→approve→authorize workflow | ❌ Missing | no purchase-order lifecycle | P2 |
| **Budget check** against accounting budgets | ❌ Missing | `accounting_budget` exists → could integrate | P2 |
| PO report with/without prices | ❌ Missing | | P3 |
| Non-stock item purchasing | ❌ Missing | | P3 |

## 4.5 Goods Received Notes (GRN)

**Elements:** GRN Details — GRN No, Delivery Note No, A/P Invoice No, Date Time Received; Purchase Order Details (Order No, Location, Supplier, Order ref); buttons Create GRN, ⋮, GRN Items, View Report. **View: GRNs** (GRN No, Supplier, P/O Number, Delivery Note No, A/P Invoice No, Net Amount). Filters: View (Pending), Between.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Receive goods against a PO → update stock + create A/P bill | ❌ Missing | breaks the 3-way match (PO/GRN/Invoice) | P2 |

## 4.6 A/P Payment Vouchers

**Elements:** filters View (Pending), Between; table (Voucher ID, Created By, Date Time Created, Status, Date Time Approved). Status actions: **Approve / Reject / Cancel Payment Voucher · Undo Approval · View Payment Voucher**. Payment Voucher Items (Inv No, Supplier, Alias, Date, Balance, **Approved Amount [click-to-edit]**, Approval Status).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Payment voucher w/ approve/reject/undo + line approval | ❌ Missing | no supplier-payment authorization flow | P2 |

## 4.7 Supplier Prepayments

**Elements:** Supplier, Payment Mode (Cash…), Cash, Reference, Paid On, Paid By, Prepayment Amount; read-outs Amount Used / Amount Refunded / Balance; **[Save Prepayment]**; **[Actions ▾]**: Allocate Prepayment · Prepayment Allocations · Prepayment Refunds · Cancel Prepayment · Prepayment Summary. **View: Supplier Prepayments** (No, Supplier, Payment Mode, Paid On, Status, Amount, Used, Refunded, Balance). Filters: Status (Active), From/To.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Supplier prepayment + drawdown tracking | 🟡 Partial | customer prepayment exists; supplier side absent | P3 |

---

## Procurement summary

HMS-2 has the **ledger endpoint** (A/P control account, budgets, partial supplier refs) but not the **operational P2P workflow**. Full parity here is a coherent **"Procurement" epic**:

- ❌ **Supplier master + PRN → LPO (approve/authorize/budget-check) → GRN → Supplier Bill → Payment Voucher** — P2
- ❌ **Withholding tax** on supplier bills (KRA compliance) — P2
- 🟡 Supplier prepayments, credit notes — P3

Not clinical and not direct patient-revenue, so **P2 overall** under the chosen lens — valuable cost-control + tax compliance, but sequenced after the P1 revenue/clinical gaps. Rides on existing `accounting_budget` + A/P accounts.
