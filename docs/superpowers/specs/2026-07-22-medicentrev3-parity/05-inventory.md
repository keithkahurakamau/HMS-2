# Module 5 — Inventory / Stores (`Inventory`)

Sidebar sub-items: **Inventory · Internal Orders · Interbranch Orders · Material Consumption · Stock Take · Unit Of Measure**.

Screenshots: `160000–160015` (Inventory Items) · `160137` (Internal Orders) · `160151` (Interbranch Orders) · `160206` (Material Consumption) · `160218–160254` (Stock Take).

**Multi-store:** every screen begins with **"Select Your Storage Location First"** — stores seen: Pharmacy, Main Store, Triage, Nutrition, Laboratory, Radiology, Dental Unit, Theatre, Housekeeping, Inpatient, Kilifi Chemist, Dialysis.

HMS-2 refs: `inventory.py` (model + routes) + `Inventory.jsx`. Verified: **has** items/batch/expiry/reorder; **no** stock-take / interbranch / material-consumption / multi-store-location / UoM-config.

---

## 5.1 Inventory Items

**Elements:** barcode-scan **Search**. Item form: Name, Item Category, Item Class, **Inventory Sub-Account**, **Cost Of Sale Sub-Account**, **Income Sub-Account** (GL mapping), VAT Type, Other Tax, **Unit Cost (BP)**, **Unit Price (cash payers)**, **Min Unit Price**, Available Quantity, Total Quantity, Unit Of Measure, **Batch No**, **Batch Expiry Date**, Item Code, Barcode, **Reorder Level**, **Create a new batch** toggle, [+]. Side actions: **View Reserved · Import Products · Export Products · Create Opening Stock · Sync Inventory Items · Retire Old Batches · Merge Batches · View Expired Batches · Item Classes · Item Categories**. **View: Inventory Items** (Name, Batch No, Unit Cost, Unit Price, Total Qty, Available Qty, Expires On; Excel/CSV/Print; Search).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Item master w/ batch + expiry + reorder | ✅ Have | `inventory.py` + `Inventory.jsx` | — |
| Multi-tier pricing (cost/cash/min) | 🟡 Partial | verify min-price + cash-price fields | P2 |
| **Per-item GL sub-account mapping** (inventory/COS/income) | 🟡 Partial | schemes exist; item→GL mapping? | P2 |
| **Multi-store storage locations** (12 stores) | 🟡 Partial | no `storage_location` split — HMS-2 likely single logical store | P2 |
| Import/Export products, opening stock | ❌ Missing | | P3 |
| Merge / Retire / View-Expired batches | ❌ Missing | expiry-loss control | P2 |
| View Reserved (committed-but-undispensed) | ❌ Missing | | P3 |

## 5.2 Internal Orders (intra-branch store requisition)

**Elements:** Requesting Location, Issuing Location, Order Type (Stock…), Requesting/Issuing Location Comments; workflow checkboxes **Approve Order · Send Order · Cancel Order · Dispatch Items · Receive Items Without Dispatch · Receive Items**; Order Items, View Order, Save. **View** (Internal Order No, Requesting Location, Issuing Location, Order Status, Prepared By, Approved By, Received By). Filters View (Not Sent), Between.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Store-to-store requisition w/ approve→dispatch→receive | ❌ Missing | no inter-store transfer workflow | P2 |

## 5.3 Interbranch Orders (cross-branch transfer)

**Elements:** Issuing **Branch**, Requesting Location, Order Type, Issuing Location, comments; same Approve/Send/Cancel/Dispatch/Receive workflow. **View: Interbranch Orders** (Order No, Requesting Location, Issuing Branch, Issuing Location, Order Status, Prepared By, Approved By, Received By).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Cross-branch stock transfer | ❌ Missing | relevant for multi-branch tenants | P3 |

## 5.4 Material Consumption (internal non-sale usage)

**Elements:** Storage Location, Item, Qty in stock, Unit Of Measure, Batch No, **Quantity Consumed**, DateTime Consumed, Description, Reference, [+]; **[Commit material consumption to stock (Selected)]**, Load committed only. **View: Consumed Items** (Item, Batch, Storage Location, Quantity, UoM, Reference, User, Date Time Consumed). Filters Consumed Between.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Record internal consumption (deduct stock, no sale) | ❌ Missing | e.g. theatre/ward consumables | P2 |

## 5.5 Stock Take (physical count & variance)

**Elements:** storage-location select; **[New Stock Take]**; View: Stock Takes (No, Created On, Created By); **View: Stock Take Items** (Name, Batch, Units, **Sys Qty**, **New Qty**); View: Products (Name, Batch, Cost, **Physical Qty**, **System Qty**); barcode search. **[Actions ▾]**: Create an Empty Stock Take · **Create Stock Take from Excel** · **Freeze Stock Take** · **Commit Adjustment to Stock** · **Variance Report** · Variance Report (Grouped by Category).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Physical count → variance → commit adjustment | ❌ Missing | pharmacy/store loss control | P2 |
| Variance report | ❌ Missing | | P2 |

## 5.6 Unit Of Measure

**Elements:** Unit Of Measure Details — Name, Measurement Unit, Dosage Unit [e.g. mL, Tablet], Packaging Unit, **Prescription Verb** [Take/Apply], **Is smallest unit**, **Is Computable on Prescriptions** toggles, [+]. **Unit Conversion Details** — From (UoM), To (UoM), Quantity, [+]. View: Unit Of Measures (No, Name, Dosage, Verb, Flags: Smallest/Computable) + View: Unit Conversions. Drives **prescription dosing computation** (Tablet/Capsule/mL/Vial → verb + smallest + conversions).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| UoM w/ prescription-dosing (verb, computable, conversions) | ❌ Missing | inline units only; affects dose auto-calc & dispensing math | P2 |

---

## Inventory summary

Item-level fundamentals are **Have** (batch, expiry, reorder). The gaps are **store-operations depth**:

- ❌ **Stock take / variance / adjustment** — P2 (loss control)
- ❌ **Multi-store locations + internal / interbranch transfers** — P2 (multi-site tenants)
- ❌ **Material consumption**, **expiry batch tools** (merge/retire/view-expired) — P2
- 🟡 **Per-item GL sub-accounts**, multi-tier pricing — P2 (ties inventory → accounting)
- ❌ Import/export, opening stock, UoM config — P3

Overall **P2** — important operational control (especially for multi-store pharmacies), sequenced after the P1 clinical/revenue gaps.
