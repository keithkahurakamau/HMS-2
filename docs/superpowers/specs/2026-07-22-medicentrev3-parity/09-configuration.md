# Module 9 — Configuration (`Configuration`)

Sidebar sub-items (19): **Services · Lab Test · Rooms · Ward Beds · Departments · Storage Location · Branch Profile · Hospital Info · Medical Clinics · Vitals · Billables & Charges · Automated Notifications · Consent Forms · API Configurations · ICD Configuration · Barcodes · Attach Storage · Report Templates · Service Point Rules**.

Screenshots: `084855` (Services) · `084924` (Rooms) · `084942` (Ward Beds) · `085003` (Departments) · `085041–085105` (Branch Profile: Accounts + Billing tabs).

HMS-2 refs: `settings.py` + `Settings.jsx`, `branding.py` + `Branding.jsx`, `MpesaSettings.jsx`, `platform_payhero.py`, feature-flags (billing/accounting/laboratory/wards), `IcdDiagnosisPicker`, `queue.py`, `Wards.jsx`.

**This is the enabler layer.** HMS-2 has settings/feature-flags/branding/M-Pesa/ICD, but MedicentreV3's per-branch config is far more **granular** — most rows are 🟡 Partial. The granular **billing toggles** are the highest-value gap because they govern revenue behavior.

---

## 9.1 Branch Profile — per-branch feature flags ⭐

**Tabs:** Security · Accounts · Billing · Clinical · Queue · Laboratory · Inventory · Procurement · Digital Stamp · Email Settings.
**Accounts toggles:** Restrict Cash Transactions To Cashiers Only · Auto Manage Cashier Shifts · Allow Negatives on Cash SubAccounts · Post Customer Deposits to AR SubAccounts · Treat Consultant Pay as Expense.
**Billing toggles:** Auto-finalize bills older than N hrs (0=off) · **Default Payment Gateway** · **Enforce Scheme Item Cover Exclusion** · **Invoice Prefix** · **Auto Bill on Prescription** · **Default Receipt Size (80mm)** · Can Bill Product Against Consultant · **Enforce Service Point Rules** · **Default to Cash Payers Unit Price When Zero** · Trigger Billables on Clinic Change · **Enforce Minimum Unit Price**.
**Clinical toggles:** Disease Standard (ICD-10) · Lock Diagnosis To Standard · Autofill Prescription · Queue To Room With Available User Only · In/Outpatient Prefix · Include Date as Suffix on OP Number · Can View Patient Notes from Other Branches · **Allow Prescription before Diagnosis** · Validate Patient PhoneNumber (min/max length).
**Queue toggles:** Prefer to Queue to User not Room · Enforce Queue Current Before Selecting Next Patient.
**Inventory toggles:** Prescribe Specific Batch · **Prescribe Expired Drugs** · Disable Item Batching · Near-Expiry Period (months, dflt 3) · Request Unavailable Interbranch Order Items · Prescribe Items with Positive Quantity Only · Hide Products Added to Stock Take.
Also **Laboratory / Procurement** tabs.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Per-branch feature-flag panel | 🟡 Partial | HMS-2 has module feature-flags; not this granular billing/clinical toggle set | P1 |
| Revenue-governing toggles (auto-bill-on-Rx, min-price, scheme-cover-exclusion, receipt size, invoice prefix) | 🟡 Partial | control leakage + billing correctness → **revenue-adjacent** | P1 |
| Digital Stamp (signature/stamp on printed reports) | ❌ Missing | | P3 |
| Email Settings (per-branch SMTP) | 🟡 Partial | HMS-2 email is global (`EMAIL_ENABLED`) | P3 |

## 9.2 Services (billable service catalog)

**Elements:** Search; Name, Item Category, Item Code, Rate, **Income SubAccount**, Item Class, **Expense SubAccount**, VAT Type, Other Tax; flags **Is a procedure / Is an Examination / Is Theatre Operation**; Sync/Import/Export Services, Input Items, Item Classes, Item Categories. View (No, Name, Category, Code, Rate).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Billable services catalog w/ GL income/expense mapping + VAT | 🟡 Partial | HMS-2 bills services; verify a config CRUD w/ GL + procedure/examination/theatre flags | P2 |

## 9.3 Rooms & Queue routing ⭐

**Elements:** Name, Category, **Room Type**, **Bind to panel**, Description, Department, Is Active, **Is Entry Point (Where Queue Begins)**. View shows rooms bound to functional panels (Triage/Doctor/Laboratory/Pharmacy/Radiology/Special-Clinic/Ward) and marks RECEPTION as the queue entry point.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Room config that **binds a room → module panel** + defines queue entry point | 🟡 Partial | HMS-2 has queue + department queues; verify room↔panel binding + entry-point config | P2 |

## 9.4 Facility catalogs (Ward Beds · Departments · Storage Location · Medical Clinics · Vitals · Lab Test)

**Ward Beds:** Bed No, Ward, Bed Status, Capacity (Available/Fully Booked). **Departments:** Name, Company Branch. **Storage Location:** stores (ties Inventory §5 multi-store). **Medical Clinics:** special-clinic types (ties Clinical §2.5). **Vitals:** configurable vital-sign definitions. **Lab Test:** test catalog + components + reference ranges.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Ward/bed config | ✅ Have | `Wards.jsx` | — |
| Departments config | 🟡 Partial | verify department CRUD | P3 |
| **Storage Location config** (multi-store) | ❌ Missing | ties Inventory §5 gap | P2 |
| **Medical Clinics config** (special-clinic types) | ❌ Missing | ties Clinical §2.5 gap | P2 |
| Configurable **Vitals** definitions | 🟡 Partial | verify vitals config vs hard-coded | P3 |
| **Lab Test** catalog + reference ranges | ✅ Have | `laboratory.py` | — |

## 9.5 Billing/clinical config catalogs (Billables & Charges · Consent Forms · Service Point Rules · ICD · Barcodes · Report Templates · Automated Notifications · API Configurations · Attach Storage · Hospital Info)

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| **ICD Configuration** (ICD-10 catalog + custom codes) | ✅ Have | `IcdDiagnosisPicker` + custom ICD | — |
| **API Configurations** (integration registry: SMS · **DICOM/PACS** · IPay · M-Pesa · **Smart card** · Mini Apps · **Patient Portal** · **KCB Buni** bank · **OAuth2**) | 🟡 Partial | M-Pesa/PayHero + Patient Portal exist; DICOM, KCB Buni, OAuth2, Smart-card, IPay registry missing | P2 |
| **Automated Notifications** (event→SMS/email rules) | 🟡 Partial | notifications exist; rules-engine config no | P2 |
| **Billables & Charges** (auto-charge rules e.g. bed-day, consultation) | 🟡 Partial | consultation-fee exists; general auto-charge rules no | P2 |
| **Service Point Rules** (per-point billing enforcement) | ❌ Missing | referenced by a Branch-Profile toggle | P2 |
| **Consent Forms** (templated procedure consents) | 🟡 Partial | `consent.py` util; templated clinical consent library no | P2 |
| **Report Templates** (customizable print templates) | ❌ Missing | | P2 |
| **Barcodes** (label/barcode config) | ❌ Missing | ties Inventory barcode fields | P3 |
| **Attach Storage** (document attachment backend config) | ❌ Missing | | P3 |
| **Hospital Info** (facility identity, logo, KRA/registration) | 🟡 Partial | `Branding.jsx` covers logo/identity | P3 |

---

## Configuration summary

The enabler layer. HMS-2 has the spine (settings, feature-flags, branding, M-Pesa, ICD, lab catalog), but MedicentreV3 is **far more granular**, and the gaps cluster around things other modules depend on:

- 🟡 **Granular per-branch billing toggles** (auto-bill-on-Rx, enforce-min-price, scheme-cover-exclusion, receipt size, invoice prefix, default gateway) — **P1** (revenue-governing; pairs with Billing §1)
- ❌ **Report Templates**, ❌ **Service Point Rules**, ❌ **Storage Location / Medical Clinics config**, ❌ **Digital Stamp** — P2 (each unlocks a matching module gap)
- 🟡 **Services catalog GL mapping**, **Automated Notifications rules**, **Consent Form templates**, **API-config registry** — P2
- **Overall P2 as an epic**, but the billing-toggle subset is P1 and cheap (mostly settings rows).
