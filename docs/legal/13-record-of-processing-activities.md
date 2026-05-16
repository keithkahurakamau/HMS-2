# Record of Processing Activities (ROPA)

> **Status:** DRAFT v0.1 — internal register maintained by the DPO.
> **Statutory basis:** KDPA s24; Data Protection (General) Regulations 2021 reg 6.
> **Audience:** DPO, Senior Management, ODPC on request.
> **Format:** maintained as this document with one row per activity; mirrored in the DPO's internal register tooling if any.

The ROPA must reflect the Operator's processing as **Controller** (its own
processing — portal accounts, billing) and as **Processor** (hospital
clinical data on instructions). The required content is set out below; for
each activity, the same fields are populated.

---

## A. Operator as Data Controller

### A1. Patient Portal accounts

| Field | Value |
|---|---|
| Activity ID | OP-CTRL-01 |
| Name of activity | Patient Portal account management |
| Purpose | Authenticate portal users, support, notifications |
| Categories of data subjects | Patients of partner hospitals (adults) |
| Categories of personal data | Email, phone, hashed password, session/CSRF tokens, IP, user-agent, hospital link |
| Categories of sensitive data | None directly (clinical data viewed in the portal is processed under the Hospital's authority) |
| Categories of recipients | Hosting sub-processors, email/SMS provider, the Hospital(s) the user is linked to |
| Cross-border transfers | Yes — US/EU (Render, Vercel, email provider). Safeguards: SCCs (Document 15) |
| Retention | Active account + 12 months after closure; logs 90 days; audit 6 years |
| TOMs reference | Schedule 1 of Document 02 |
| Lawful basis | s30 — contract; s30 with consent for marketing/notifications |
| DPIA reference | Document 12 |
| Last reviewed | [PLACEHOLDER] |

### A2. Operator employee records

| Field | Value |
|---|---|
| Activity ID | OP-CTRL-02 |
| Purpose | Employment administration, payroll, statutory filings (NSSF, NHIF, KRA) |
| Data subjects | Operator employees |
| Categories | Identity, contact, NHIF/NSSF/KRA, banking, employment history |
| Sensitive | Health (sick leave certificates), trade-union membership where applicable |
| Recipients | Payroll provider, NSSF, NHIF, KRA, statutory pension scheme |
| Cross-border | None (Kenyan providers) |
| Retention | 7 years post-employment (tax law minimum) |
| Lawful basis | s30 — contract, legal obligation |
| Reviewed | [PLACEHOLDER] |

### A3. Customer (Hospital) account and billing

| Field | Value |
|---|---|
| Activity ID | OP-CTRL-03 |
| Purpose | Manage Hospital accounts, invoicing, M-Pesa / bank reconciliation |
| Data subjects | Hospital administrators, signatories, billing contacts |
| Categories | Identity, contact, role, payment references |
| Sensitive | None |
| Recipients | Payment provider (M-Pesa Daraja), accounting software |
| Cross-border | Accounting software [PLACEHOLDER — check region] |
| Retention | 7 years (tax law) |
| Lawful basis | s30 — contract, legal obligation |
| Reviewed | [PLACEHOLDER] |

### A4. Marketing and website analytics

| Field | Value |
|---|---|
| Activity ID | OP-CTRL-04 |
| Purpose | Public website performance and product analytics |
| Data subjects | Website visitors (mostly hospital prospects) |
| Categories | IP, browser, page interactions, voluntarily-provided contact details |
| Sensitive | None |
| Recipients | Analytics provider [PLACEHOLDER — name once enabled] |
| Cross-border | Per provider |
| Retention | 24 months (raw) / longer (aggregated) |
| Lawful basis | Consent (cookie banner) |
| Reviewed | [PLACEHOLDER] |

---

## B. Operator as Data Processor

For activities under Section B, the **Controller** is the Hospital named in
the relevant Order Form. The Operator processes on documented instructions.

### B1. Patient registration & demographics

| Field | Value |
|---|---|
| Activity ID | OP-PROC-01 |
| Controller | Each contracting Hospital |
| Purpose (per controller) | Identify and register patients for clinical and administrative care |
| Categories of data subjects | Patients of the Hospital |
| Categories of personal data | Identity, contact, demographic, NHIF/SHIF |
| Sensitive | None at this stage (sensitive data lives in clinical activities) |
| Recipients | Hospital staff with `patients:read` / `patients:write`; sub-processors (hosting, infra) |
| Cross-border | Hosting in US/EU; SCCs in place |
| Retention | Per Doc 14 (Hospital decides; KMPDC minimum applies) |
| Lawful basis (controller's) | s30(b)(c) — care; performance of contract |
| Reviewed | [PLACEHOLDER] |

### B2. Clinical encounters, vitals, diagnoses, prescriptions

| Field | Value |
|---|---|
| Activity ID | OP-PROC-02 |
| Controller | Each contracting Hospital |
| Purpose | Clinical care, audit, continuity of care, billing |
| Categories of data subjects | Patients |
| Categories of personal data | Identity link; clinical entries |
| Sensitive | Health data (all); HIV, mental health, obstetric flagged where applicable |
| Recipients | Authorised clinical staff; pharmacy/lab where ordered; sub-processors |
| Cross-border | As above |
| Retention | Doc 14 |
| Reviewed | [PLACEHOLDER] |

### B3. Laboratory & radiology orders and results

| Field | Value |
|---|---|
| Activity ID | OP-PROC-03 |
| Controller | Each contracting Hospital |
| Purpose | Diagnostic ordering, result delivery, report management |
| Sensitive | Health; potentially HIV / genetic; images |
| Retention | Doc 14 |
| Reviewed | [PLACEHOLDER] |

### B4. Pharmacy and inventory

| Field | Value |
|---|---|
| Activity ID | OP-PROC-04 |
| Controller | Each contracting Hospital |
| Purpose | Dispensing, inventory and procurement, drug-stock-out tracking |
| Sensitive | Medication can reveal sensitive conditions |
| Retention | Doc 14 — dispensing records |
| Reviewed | [PLACEHOLDER] |

### B5. Billing, invoicing, and M-Pesa payments

| Field | Value |
|---|---|
| Activity ID | OP-PROC-05 |
| Controller | Each contracting Hospital |
| Purpose | Generate invoices, accept payments, reconcile |
| Categories | Identity link; amount; M-Pesa reference; insurance details |
| Recipients | M-Pesa Daraja; insurance schemes with patient consent |
| Cross-border | None for M-Pesa; insurance schemes per scheme |
| Retention | 7 years (tax) |
| Reviewed | [PLACEHOLDER] |

### B6. Appointments and queue management

| Field | Value |
|---|---|
| Activity ID | OP-PROC-06 |
| Controller | Each contracting Hospital |
| Purpose | Schedule, queue, route patients |
| Sensitive | None at this stage (department choice may imply category — handled by access control) |
| Retention | Per Doc 14 — typically with the encounter record |
| Reviewed | [PLACEHOLDER] |

### B7. Internal messaging between Hospital staff

| Field | Value |
|---|---|
| Activity ID | OP-PROC-07 |
| Controller | Each contracting Hospital |
| Purpose | Clinical handover, departmental coordination |
| Categories | Staff identity, message content |
| Recipients | Hospital staff |
| Retention | 3 years (or per Hospital's policy if longer) |
| Reviewed | [PLACEHOLDER] |

### B8. Audit logs of access and changes

| Field | Value |
|---|---|
| Activity ID | OP-PROC-08 |
| Controller | Each contracting Hospital |
| Purpose | Demonstrate KDPA compliance, investigate misuse |
| Categories | User identity, action, target record, timestamp, IP |
| Recipients | Hospital DPO / authorised reviewers; Operator security on authorised investigation |
| Retention | 6 years from event (minimum) |
| Reviewed | [PLACEHOLDER] |

### B9. Cheques register and financial documents

| Field | Value |
|---|---|
| Activity ID | OP-PROC-09 |
| Controller | Each contracting Hospital |
| Purpose | Track issued/received cheques, lifecycle, reconciliation |
| Categories | Payer/payee identity, amount, bank reference |
| Retention | 7 years (tax law) |
| Reviewed | [PLACEHOLDER] |

### B10. Patient portal communications and notifications

| Field | Value |
|---|---|
| Activity ID | OP-PROC-10 |
| Controller | Each contracting Hospital (for clinical content); Operator (for portal-account notifications) |
| Purpose | Deliver appointment reminders, lab result alerts, password resets |
| Categories | Identity link, notification body |
| Recipients | Patient via SMS / email |
| Retention | 18 months |
| Reviewed | [PLACEHOLDER] |

---

## C. Review and maintenance

The ROPA is reviewed:

- At every quarterly governance meeting.
- Whenever a new module, integration, or sub-processor is added.
- After any material incident.

Material additions (e.g., new module, new sub-processor) require an
updated DPIA section (Doc 12), an entry here, and where applicable an
update to Document 02 / 15.

---

## D. Access to this register

| Audience | Access |
|---|---|
| DPO | Full write |
| Senior management | Read |
| Customers (Hospitals) | Read of activities affecting their data, on request |
| ODPC | Provided on lawful request |
| Public | Not published; the Sub-processor Register (Doc 15) is the public-facing summary |

---

*Version 0.1 — Effective Date: [PLACEHOLDER]. Last reviewed: 2026-05-15.*
