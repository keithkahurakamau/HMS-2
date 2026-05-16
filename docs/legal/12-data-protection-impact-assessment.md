# Data Protection Impact Assessment (DPIA)

> **Status:** DRAFT v0.1 — initial assessment to be reviewed and signed off by the DPO and Senior Management.
> **Statutory basis:** KDPA s31; Data Protection (General) Regulations 2021 regs 18–19; ODPC Guidance Note on DPIAs (2023).
> **Scope:** the HMS-2 / MediFleet Platform as a multi-tenant SaaS for hospitals in Kenya, including the Patient Portal.
> **Owner:** [PLACEHOLDER — DPO]
> **Review cadence:** annual, plus on material change.

A DPIA is **required** because the Platform processes:

- sensitive personal data (health, HIV status, mental-health, genetic);
- data on a large scale;
- data of children and other vulnerable persons;
- data that involves combining records from multiple sources;
- data that crosses borders (some sub-processors are outside Kenya).

Any one of these would suffice under KDPA s31 / Reg 18; all five are
present.

---

## 1. The processing

### 1.1 Purpose and scope

- Provide a hospital management software platform to Kenyan hospitals.
- Enable clinical, administrative, billing, and reporting workflows.
- Offer a Patient Portal for patients to view their records, schedule, and
  communicate with the hospital.

### 1.2 Data flows (high-level)

```
Patient ──→ Hospital staff ──→ Platform UI ──→ FastAPI backend
                                                    │
                                                    ├──→ Tenant-specific Postgres (Render)
                                                    ├──→ Redis (sessions / pub-sub)
                                                    ├──→ M-Pesa Daraja (payments)
                                                    └──→ Notification channels (SMS / email)

Patient ──→ Patient Portal (Vercel) ──→ same backend
```

### 1.3 Data categories

See Document 02 Clause 2 for the full table. Notable sensitive categories:

- Health data (all clinical entries).
- HIV status (separately flagged).
- Mental health information.
- Obstetric and reproductive-health information.
- Genetic and biometric (where collected).

### 1.4 Data subjects

- Patients (adults and minors).
- Hospital staff (Authorised Users).
- Next-of-kin and emergency contacts.
- Third parties referenced in clinical notes.

### 1.5 Volume estimates

| Metric | Estimate at launch | 12-month projection |
|---|---|---|
| Hospitals (tenants) | [PLACEHOLDER] | [PLACEHOLDER] |
| Active staff users | [PLACEHOLDER] | [PLACEHOLDER] |
| Patient records | [PLACEHOLDER] | [PLACEHOLDER] |
| Patient portal users | [PLACEHOLDER] | [PLACEHOLDER] |
| Daily clinical events | [PLACEHOLDER] | [PLACEHOLDER] |

---

## 2. Necessity and proportionality

| Question | Assessment |
|---|---|
| Is the processing necessary for the purpose? | Yes — clinical, billing, and reporting are core hospital functions; software is the established means. |
| Is each data category necessary? | Each clinical category is necessary for the relevant module; non-clinical (e.g., religion) is only collected because the registration form supports it — the Hospital may choose not to collect it. |
| Is there a less intrusive alternative? | Paper records (rejected — worse accuracy, worse audit, worse access for patient). |
| Are data subjects informed? | Yes — via Documents 03 and 05. |
| Are lawful bases identified? | Yes — Document 03 maps purpose to KDPA s30 ground. |
| Are retention periods proportionate? | Yes — follow Health Records Act / KMPDC retention (Document 14). |

---

## 3. Identified risks and mitigations

| # | Risk | Likelihood | Impact | Severity | Mitigation | Residual |
|---|---|---|---|---|---|---|
| R1 | Unauthorised cross-tenant data access (one hospital reading another's records) | Low | Catastrophic | High | Per-tenant database isolation; mandatory `X-Tenant-ID` header; backend rejects requests without it (no silent fallback); JWT tenant claim validated | Low |
| R2 | Staff snooping on patient records | Medium | High | High | RBAC + permissions; full audit log of access; access-trail visible to patient on request; deterrent in Terms of Use | Medium |
| R3 | Credential compromise (phishing, password reuse) | High | High | High | Strong password policy; refresh-token rotation; rate-limiting on `/auth/login`; MFA roadmap | Medium |
| R4 | Backend or sub-processor breach causing exfiltration of sensitive data | Low | Catastrophic | High | TLS everywhere; column-level encryption of sensitive free-text; sub-processor due diligence; SCC for cross-border transfers; incident response per Doc 10 | Medium |
| R5 | Data exposure in logs (PII leaked into application logs) | Medium | Medium | Medium | Log filter strips known PII fields; review of log fields in code review; retention of logs limited to 90 days | Low |
| R6 | Cross-border transfer challenge by ODPC | Medium | Medium | Medium | DTIA for each non-Kenyan sub-processor; SCC in place; consider in-country hosting on the roadmap | Low |
| R7 | Insufficient consent capture for sensitive categories | Medium | High | High | Consent form (Doc 08) breaks out HIV / mental-health / obstetric / minors; consent stored in record | Low |
| R8 | Children's data processed without parental authority | Low | High | Medium | Portal sign-up limited to 18+; Hospital consent process for minors recorded in `medical_history.consent_obtained` | Low |
| R9 | Data subject rights request not handled within KDPA timeline | Medium | Medium | Medium | DSR SOP (Doc 09); 30-day SLA; quarterly metrics | Low |
| R10 | Erasure right ignored due to multi-tenant complexity | Medium | High | High | `/api/privacy/patients/{id}/erase` exists; verify backups are also purged within 90 days; document tested erasure workflow | Medium |
| R11 | Loss of clinical records (e.g., RTO/RPO miss) | Low | High | Medium | Daily backups; monthly restore test; RTO/RPO per SLA (Doc 11) | Low |
| R12 | Inability to export data on Customer termination | Low | Medium | Medium | Doc 01 Clause 12 export commitment; structured JSON/CSV; tested | Low |
| R13 | Insider (employee of Operator) misuse | Low | High | Medium | Named-personnel access list; access logged; least-privilege; KDPA training | Low |
| R14 | Patient mis-identification across tenants in superadmin view | Low | High | Medium | Superadmin cross-tenant read is read-only; logged; restricted to platform operator; reviewed quarterly | Low |
| R15 | M-Pesa transaction data inadvertently exposed | Low | Medium | Medium | Restricted scope of payment-route logs; payment receipts marked sensitive; tokens not stored unhashed | Low |
| R16 | Communicable-disease reporting non-compliance (Public Health Act) | Medium | Medium | Medium | Roadmap item to add Ministry-of-Health reporting integration | Medium |

Severity scale: Likelihood × Impact, 1–3 each, summed.

---

## 4. Sub-processor risk register

| Sub-processor | Service | Region | Data | DTIA needed | Status |
|---|---|---|---|---|---|
| Render | Hosting | US/EU | All Platform data | Yes | [ ] In progress |
| Vercel | Frontend / edge | Global edge | Static assets, headers | Yes | [ ] In progress |
| Postgres provider | Database | US/EU | All Platform data | Yes | [ ] In progress |
| Redis Cloud | Cache, WebSocket | US/EU | Session metadata | Yes | [ ] In progress |
| Safaricom M-Pesa Daraja | Payments | Kenya | Phone, amount, ref | N/A | ✓ |
| GitHub | Source / CI | US | Source code only | Yes | [ ] In progress |

Full register: Document 15.

---

## 5. Consultation

| Stakeholder | Date consulted | Outcome |
|---|---|---|
| Customer Hospitals (sample) | [PLACEHOLDER] | [PLACEHOLDER — feedback summary] |
| Legal counsel | [PLACEHOLDER] | [PLACEHOLDER] |
| Clinical advisor | [PLACEHOLDER] | [PLACEHOLDER] |
| Patient advisory group (if any) | [PLACEHOLDER] | [PLACEHOLDER] |
| ODPC pre-consultation (if required for high residual risk) | [PLACEHOLDER] | [PLACEHOLDER] |

Per KDPA s31(7), the ODPC must be consulted *before* commencing processing
where the DPIA indicates that the processing would result in a high risk in
the absence of measures taken to mitigate. If residual risks above are all
reduced to Low/Medium with mitigations in place, prior consultation should
not be required, but the DPO should record the analysis.

---

## 6. Action plan

| # | Action | Owner | Due | Status |
|---|---|---|---|---|
| A1 | Complete and sign SCCs with each non-Kenyan sub-processor | DPO + Legal | [PLACEHOLDER] | [ ] |
| A2 | Roll out MFA for staff Authorised Users | Engineering | [PLACEHOLDER] | [ ] |
| A3 | Implement automated quarterly access-review report | Engineering | [PLACEHOLDER] | [ ] |
| A4 | Document tested erasure-from-backup workflow | DPO + Operations | [PLACEHOLDER] | [ ] |
| A5 | First annual external penetration test | Security | [PLACEHOLDER] | [ ] |
| A6 | Communicable-disease reporting roadmap and design doc | Product | [PLACEHOLDER] | [ ] |
| A7 | DPIA refresh after each major module release | DPO | Ongoing | [ ] |

---

## 7. Decision and sign-off

Residual risk assessment: **[PLACEHOLDER — acceptable / acceptable subject to action plan / not acceptable]**.

Recommendation: **[PLACEHOLDER — proceed / proceed with mitigations / do not proceed]**.

| Role | Name | Signature | Date |
|---|---|---|---|
| DPO | [PLACEHOLDER] | _______________ | ___________ |
| CEO / Director | [PLACEHOLDER] | _______________ | ___________ |
| Head of Engineering | [PLACEHOLDER] | _______________ | ___________ |
| Head of Clinical (advisor) | [PLACEHOLDER] | _______________ | ___________ |
