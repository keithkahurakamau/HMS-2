# Legal & Compliance Documentation — Kenya

This directory contains the template legal and compliance documents required to
operate **HMS-2 / MediFleet** as a multi-tenant hospital management software-as-a-service
in the Republic of Kenya.

> **IMPORTANT — Not legal advice.** These are *templates* drafted to align with
> the **Kenya Data Protection Act, 2019 (KDPA)**, the **Health Act, 2017**, the
> **Health Records and Information Managers Act, 2016**, and the regulations and
> guidance notes issued by the **Office of the Data Protection Commissioner
> (ODPC)** and the **Kenya Medical Practitioners and Dentists Council (KMPDC)**.
> They must be reviewed and adapted by a Kenyan advocate (ideally with
> health-tech or data-protection experience) before being signed, published,
> or relied upon.

---

## 1. The customer model these documents assume

HMS-2 is delivered to **hospitals** ("Tenants") as a SaaS platform. The legal relationships are:

```
[HMS-2 Operator]  ──── MSA + DPA ───→  [Hospital / Tenant]
       │                                       │
       │ Platform Privacy Notice               │ Patient Privacy Notice
       │ (portal users)                        │ (clinical/administrative use)
       ▼                                       ▼
   [Patient using portal]              [Patient receiving care]
```

- The **Hospital** is the **Data Controller** for patient clinical records.
- The **HMS-2 Operator** is a **Data Processor** acting on documented instructions from the Hospital (KDPA s2, s42).
- When a patient uses the **patient portal**, HMS-2 also processes a narrow subset of personal data **as an independent controller** for portal authentication, sessions, and notifications. The Platform Privacy Notice (doc 05) covers that scope.

---

## 2. Document index

### High priority — required before production go-live

| # | Document | Purpose |
|---|---|---|
| [01](./01-master-services-agreement.md) | Master Services Agreement (MSA) | Commercial terms between Operator and Hospital |
| [02](./02-data-processing-agreement.md) | Data Processing Agreement | KDPA s42 processor obligations, Schedule 1 (TOMs), Schedule 2 (sub-processors) |
| [03](./03-patient-privacy-notice.md) | Patient Privacy Notice (issued by Hospital) | Article 31 Constitution, KDPA ss 28–30 transparency |
| [04](./04-platform-terms-of-use.md) | Platform Terms of Use (staff users) | Acceptable behaviour, IP, account security |
| [05](./05-patient-portal-privacy-notice.md) | Patient Portal Privacy Notice (issued by Operator) | KDPA notice for portal-side processing |
| [08](./08-patient-consent-form.md) | Patient Consent Form | KDPA s30 explicit consent for sensitive data |
| [09](./09-data-subject-rights-procedure.md) | Data Subject Rights SOP | KDPA ss 26, 39–41 internal handling |
| [10](./10-data-breach-notification-procedure.md) | Data Breach Notification SOP | KDPA s43 — 72-hour reporting to ODPC |

### Medium priority — required by ODPC audit or recommended within first 90 days

| # | Document | Purpose |
|---|---|---|
| [06](./06-acceptable-use-policy.md) | Acceptable Use Policy | Anti-abuse, prohibited uses |
| [07](./07-cookie-policy.md) | Cookie & Tracking Policy | KDPA s30 / ODPC cookie guidance |
| [11](./11-service-level-agreement.md) | Service Level Agreement | Uptime, support response, credits |
| [12](./12-data-protection-impact-assessment.md) | DPIA | KDPA s31 — required for high-risk processing |
| [13](./13-record-of-processing-activities.md) | ROPA | KDPA s24 — internal register |
| [14](./14-retention-and-disposal-schedule.md) | Retention & Disposal Schedule | Health Records Act + KMPDC retention rules |
| [15](./15-subprocessor-register.md) | Sub-processor Register | KDPA s42(2)(d) disclosure to controllers |

### Operator action checklist (non-document items)

| Item | Reference |
|---|---|
| [Operator compliance action checklist](./00-compliance-action-checklist.md) | What you must DO beyond signing the documents |

---

## 3. How to use these documents

1. **Read the [compliance action checklist](./00-compliance-action-checklist.md) first.** Documents alone do not make you compliant — ODPC registration, DPO appointment, and operational controls do.
2. Replace every `[PLACEHOLDER]` token with the real value. Search across the directory:
   ```
   grep -rn "PLACEHOLDER" docs/legal/
   ```
3. Have a **Kenyan advocate** review the customised set. The MSA (01), DPA (02), and any document the public will rely on (03, 05, 07) are the highest-risk items.
4. Set effective dates and version each document in the header.
5. Publish public-facing documents (03, 05, 06, 07) at stable URLs on the MediFleet website and link them from the SPA footer + portal sign-up flow.
6. Establish an internal **Document Control Register** — every revision should bump the version, restate the effective date, and (for DPA/MSA changes) be re-signed by the Tenant.

---

## 4. Statutes and guidance referenced

| Instrument | Used in |
|---|---|
| Constitution of Kenya, 2010 — Article 31 (Privacy) | 03, 05 |
| Data Protection Act, 2019 (Act No. 24 of 2019) | All |
| Data Protection (General) Regulations, 2021 | All |
| Data Protection (Registration of Data Controllers and Data Processors) Regulations, 2021 | 00, 02 |
| Data Protection (Complaints Handling Procedure) Regulations, 2021 | 09 |
| Health Act, 2017 (Act No. 21 of 2017) | 03, 08, 14 |
| Health Records and Information Managers Act, 2016 | 14 |
| Kenya Information and Communications Act, 1998 (electronic records) | 01 |
| Computer Misuse and Cybercrimes Act, 2018 | 06 |
| Consumer Protection Act, 2012 | 03, 05 |
| KMPDC Code of Professional Conduct | 14 |
| ODPC Guidance Note on Consent (2023) | 08 |
| ODPC Guidance Note on Data Subject Rights (2023) | 09 |
| ODPC Guidance Note on Data Breach Notification (2023) | 10 |
| ODPC Sector Guidance — Health (2023) | 03, 12, 14 |

---

## 5. Version control

Each document carries a header like:

```
Version: 0.1 (DRAFT — pre-advocate review)
Effective Date: [PLACEHOLDER — DD MMM YYYY]
Document Owner: [PLACEHOLDER — name, title]
Last Reviewed: 2026-05-15
```

Bump the version on every material change. The `MEMORY.md` and the operator's
internal Document Control Register should mirror this.
