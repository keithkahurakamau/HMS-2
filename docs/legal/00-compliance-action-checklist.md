# Operator Compliance Action Checklist — Kenya

> **Status:** DRAFT v0.1 — to be reviewed by Kenyan counsel before go-live.
> **Owner:** [PLACEHOLDER — name, title]
> **Last reviewed:** 2026-05-15

Signing the documents in this directory is necessary but not sufficient. The
following operational, registration, and governance steps must also be
completed for HMS-2 to lawfully operate as a SaaS provider processing patient
data in Kenya.

---

## 1. Statutory registrations (do these first)

| # | Action | Statute | Status | Target date | Owner |
|---|---|---|---|---|---|
| 1.1 | **Incorporate the operating entity** with the Business Registration Service (eCitizen) if not already done | Companies Act 2015 | [ ] | [PLACEHOLDER] | [PLACEHOLDER] |
| 1.2 | **Obtain KRA PIN** for the operating entity | Income Tax Act | [ ] | [PLACEHOLDER] | [PLACEHOLDER] |
| 1.3 | **Register with the Office of the Data Protection Commissioner (ODPC)** as both a Data Controller (for portal users) and Data Processor (for hospital data) — KDPA s18, Reg 4 of the Registration Regs | Data Protection Act 2019 | [ ] | Before processing begins | [PLACEHOLDER] |
| 1.4 | Pay annual ODPC registration fee | Reg 8 of Registration Regs | [ ] | Annually | [PLACEHOLDER] |
| 1.5 | If processing payroll: register with **NSSF** and **NHIF/SHIF** | NSSF Act 2013, NHIF Act | [ ] | [PLACEHOLDER] | [PLACEHOLDER] |
| 1.6 | If providing telemedicine bridges or e-pharmacy features: review **Pharmacy and Poisons Board** and **KMPDC Telemedicine Guidelines (2020)** for any additional licensing | Pharmacy and Poisons Act, KMPDC Act | [ ] | Before launching feature | [PLACEHOLDER] |

> **KDPA registration thresholds:** Any entity processing personal data with an
> annual turnover of KES 5 million or more, or processing data of more than
> 30 data subjects, must register. A health-tech SaaS easily crosses both
> thresholds — registration is mandatory.

---

## 2. Governance appointments

| # | Action | Statute | Status | Notes |
|---|---|---|---|---|
| 2.1 | Appoint a **Data Protection Officer (DPO)** | KDPA s24(7) | [ ] | Mandatory because HMS-2 processes sensitive health data at scale. DPO must be reasonably independent and contactable. Name and email must be published on the website. |
| 2.2 | Appoint an **Information Security Officer (ISO)** | KDPA s41, best practice | [ ] | May be the same person as DPO in a small org, but document the dual role. |
| 2.3 | Define and document the **incident response team** | DPA s43 + DPIA | [ ] | Required by Document 10 procedure. |
| 2.4 | Maintain a **Board-level information security and privacy oversight cadence** | KDPA Reg 31 (governance) | [ ] | Minimum quarterly review of incidents, DPIAs, audit findings. |

---

## 3. Internal policies & artefacts that must exist on file

| # | Artefact | Where it lives | Status |
|---|---|---|---|
| 3.1 | Master Services Agreement signed by each Tenant | Contract repo / Document Control Register | [ ] |
| 3.2 | Data Processing Agreement signed by each Tenant | As above | [ ] |
| 3.3 | Record of Processing Activities (ROPA) (Doc 13) | Internal | [ ] |
| 3.4 | Sub-processor Register (Doc 15) | Internal + published | [ ] |
| 3.5 | DPIA for HMS-2 platform (Doc 12) | Internal | [ ] |
| 3.6 | DPIA refresh whenever scope changes materially (new module, new sub-processor, new transfer abroad) | Internal | Ongoing |
| 3.7 | Information Security Policy (encryption, access control, BYOD, MDM) | Internal | [ ] |
| 3.8 | Business Continuity / Disaster Recovery Plan including RTO/RPO targets | Internal | [ ] |
| 3.9 | Backup verification log (monthly restore test) | Operations | [ ] |
| 3.10 | Vulnerability management & penetration test report (annual) | Security | [ ] |
| 3.11 | Staff confidentiality and Acceptable Use Policy acknowledgements | HR file | [ ] |
| 3.12 | KDPA awareness training records (annual refresh) | HR / DPO file | [ ] |

---

## 4. Public-facing requirements

| # | Action | Status |
|---|---|---|
| 4.1 | Publish Platform Privacy Notice (Doc 05) at a stable URL | [ ] |
| 4.2 | Publish Cookie Policy (Doc 07) at a stable URL | [ ] |
| 4.3 | Publish Acceptable Use Policy (Doc 06) at a stable URL | [ ] |
| 4.4 | Provide functioning **Data Subject Rights** contact route (email + web form) | [ ] |
| 4.5 | Provide functioning **DPO contact** (dedicated email, e.g., `dpo@[PLACEHOLDER-domain]`) | [ ] |
| 4.6 | Provide functioning **Security disclosure** contact (`security@[PLACEHOLDER-domain]`) | [ ] |
| 4.7 | Provide a clear in-product link to relevant notices at every collection point | [ ] |

---

## 5. Cross-border data transfer audit

KDPA s48–50 restrict cross-border transfers. The current HMS-2 stack uses
several non-Kenyan sub-processors. Each must be assessed:

| Sub-processor | Service | Region | Lawful transfer basis | Status |
|---|---|---|---|---|
| Render | Backend hosting (FastAPI) | US / EU | Adequacy or Standard Contractual Clauses | [ ] Review |
| Vercel | Frontend hosting | Global edge | Adequacy or SCC | [ ] Review |
| Cloudflare / Render Postgres | Database | US / EU | SCC | [ ] Review |
| Redis Cloud | Cache / WebSocket fan-out | US / EU | SCC | [ ] Review |
| Safaricom (M-Pesa Daraja) | Payments | Kenya | N/A (Kenya) | ✓ |
| GitHub | Source control | US | SCC | [ ] Review |
| Vercel email / SendGrid (if used) | Transactional email | US / EU | SCC | [ ] Review |

For each non-Kenyan processor, file:
- The SCC or DTIA (Data Transfer Impact Assessment).
- A note in the ROPA (Doc 13) describing the transfer.
- A disclosure to Tenants in the Sub-processor Register (Doc 15).

> **In-country option:** Where commercially viable, hosting in Kenya
> (e.g., **iColo / Africa Data Centres / Safaricom DCs**) removes the transfer
> question entirely. This is a strategic decision worth taking as the customer
> base grows.

---

## 6. Sector-specific obligations beyond KDPA

| # | Obligation | Source | Status |
|---|---|---|---|
| 6.1 | Retention of patient records — minimum **10 years for adults**, **25 years for paediatric** records after last contact (KMPDC). Mental health records: per Mental Health Act. | KMPDC + Health Act s11 | Codified in Doc 14 |
| 6.2 | Provide patients access to their own records on request without unreasonable delay | Health Act s11 | Doc 09 covers procedure |
| 6.3 | Records must be **legible, accurate, contemporaneous, and signed** (digitally is fine if non-repudiable) | KMPDC Code | Verify audit log in `app/utils/audit.py` meets this |
| 6.4 | Mental Health / HIV / Obstetric data: heightened sensitivity safeguards | Mental Health Act, HIV and AIDS Prevention and Control Act 2006 | Doc 14 + code already flags via `is_sensitive` |
| 6.5 | Communicable diseases reporting to the Ministry of Health | Public Health Act | Not yet implemented — log as roadmap |
| 6.6 | If processing minors' data (paediatric patients): parental consent + extra DPIA | KDPA s33 | Doc 08 covers; verify in code |

---

## 7. Audits and review cadence

| Review | Frequency | Owner | Output |
|---|---|---|---|
| ODPC registration renewal | Annually | DPO | Receipt + renewal certificate |
| DPIA refresh | On material change + annually | DPO + Security | Updated DPIA document |
| Sub-processor list & SCCs | Quarterly | DPO + Procurement | Updated Doc 15 |
| ROPA review | Quarterly | DPO | Updated Doc 13 |
| Penetration test | Annually | External vendor | Report + remediation plan |
| Backup restore test | Monthly | Operations | Log entry |
| Internal KDPA audit | Annually | Internal Audit or external advocate | Audit report |
| Staff KDPA training | On onboarding + annually | HR + DPO | Attendance + completion records |
| Document Control Register reconciliation | Every PR that changes `docs/legal/` | DPO | Register update |

---

## 8. Penalties — why this matters commercially

KDPA enforcement under s63:
- Up to **KES 5,000,000** per offence, or
- Up to **1% of annual turnover**, whichever is lower.

Plus reputational damage if ODPC publishes an enforcement notice (the
ODPC publishes redacted decisions on its website).

Health-sector regulators (KMPDC, Pharmacy and Poisons Board) can also
suspend a hospital's licence if its data-handling vendor is found
non-compliant — which would terminate the operator's commercial relationships
with affected Tenants.

---

## 9. Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| Director / CEO | [PLACEHOLDER] | _______________ | ___________ |
| DPO | [PLACEHOLDER] | _______________ | ___________ |
| Legal counsel (external) | [PLACEHOLDER] | _______________ | ___________ |
