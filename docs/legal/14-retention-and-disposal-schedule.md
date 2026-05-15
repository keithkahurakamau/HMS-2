# Retention & Disposal Schedule

> **Status:** DRAFT v0.1
> **Statutory basis:** Health Records and Information Managers Act 2016; KMPDC Code of Professional Conduct (retention); KDPA s39(1)(e) — retention only as long as necessary; Tax Procedures Act (financial records); Mental Health Act; HIV and AIDS Prevention and Control Act 2006.
> **Audience:** DPO, Hospital DPOs, Operations.

This schedule sets out **minimum** retention periods. Hospitals may keep
records longer where required by a specific case or by their internal
governance. After the retention period, records are anonymised or
destroyed per the procedure in Section 3.

---

## 1. Retention table — clinical records

| Record type | Minimum retention | Source / rationale |
|---|---|---|
| Adult patient clinical record (general) | **10 years** after the last clinical contact | KMPDC retention rule |
| Paediatric record | **25 years** from date of birth, **OR** 10 years after last contact — **whichever is longer** | KMPDC; Health Records Act |
| Obstetric and maternity records (mother and baby) | **25 years** from date of birth of the baby | KMPDC; Health Records Act |
| Mental-health records | **20 years** after last contact (or per the Mental Health Act) | Mental Health Act / KMPDC |
| HIV-related records | Treated as standard clinical record but with heightened access control. Retention per KMPDC. Avoid premature disclosure even to authorised staff who do not need it for care | HIV and AIDS Prevention and Control Act 2006 |
| Genetic test results | **30 years** from date of report (longer where multi-generational relevance) | International best practice; ODPC sector guidance |
| Imaging studies (X-ray, CT, MRI) | **15 years** from date of study | KMPDC; storage cost weighed against clinical re-use |
| Laboratory raw data and reports | **10 years** | KMPDC |
| Theatre / operative records | **30 years** after the procedure | KMPDC |
| Vaccination / immunisation records | **Lifetime of patient** (or transfer to public-health registry) | Public-health value |
| Notifiable-disease registers | Per Public Health Act, transferred to MoH as required | Public Health Act |
| Death certificate / mortuary records | **30 years** after death | KMPDC; Births and Deaths Registration Act |
| Consent forms | For the duration of the related clinical record | KDPA s30 (consent must remain demonstrable) |

---

## 2. Retention table — administrative and financial records

| Record type | Minimum retention | Source / rationale |
|---|---|---|
| Invoices, receipts, M-Pesa references | **7 years** | Tax Procedures Act |
| Payroll and statutory deductions (NSSF, NHIF/SHIF, PAYE) | **7 years** | Tax / NSSF / NHIF |
| Procurement records and supplier contracts | **7 years** after end of relationship | Best practice; civil claim limitation |
| Insurance claim records | **7 years** | Tax / Insurance Act |
| Operator subscription / Hospital billing records | **7 years** | Tax |
| Bank reconciliation, cheque register, ledger entries | **7 years** | Tax |

---

## 3. Retention table — operational / IT

| Record type | Minimum retention | Maximum retention | Notes |
|---|---|---|---|
| Application logs (request/response, errors) | 90 days | 12 months | Security investigation; longer triggers a privacy review |
| Audit log of patient-record access and changes | **6 years** | 10 years | KDPA s41 demonstrability; KMPDC audit |
| Authentication logs (sign-in attempts, MFA events) | 90 days | 6 years (security investigations) | Same |
| Backup snapshots | 30 days rolling | 30 days unless legal hold | Hosting provider retains per their contract |
| Incident response logs and post-incident reviews | **6 years** from closure | 10 years | Legal claim limitation |
| DSR register entries | **6 years** from closure | — | Reg 16 implication |
| Source code repositories | Lifetime of the product | — | Operator's IP |
| CI/CD logs | 90 days | 12 months | — |
| Email correspondence with customers | **6 years** from end of contract | — | Civil claim limitation |
| Support tickets | **3 years** from closure | — | Quality assurance |

---

## 4. Retention table — staff records

| Record type | Minimum retention | Source |
|---|---|---|
| Employment contract and HR file | **7 years** after end of employment | Tax / Employment Act |
| Disciplinary records | **6 years** after end of matter | — |
| Training records (incl. KDPA training) | **6 years** after end of employment | KDPA demonstrability |
| Background-check records | **2 years** after end of employment | KDPA s39(1)(e) — minimisation |
| Health information (e.g., medical leave certificates) | **6 years** after end of employment, then secure destruction | KDPA s30 |

---

## 5. Triggers for **earlier** destruction

A record may, and in some cases must, be destroyed before the minimum
retention expires if:

- The data subject withdraws consent and there is no other lawful basis (apply with caution; clinical records have statutory retention duties that override consent).
- A court or regulator orders destruction.
- The data subject's right to erasure (KDPA s40) is exercised and no legal-retention duty applies.
- A scheduled deletion under DSR procedure (Doc 09) is approved.

---

## 6. Disposal procedure

### 6.1 Electronic records

- **Live database:** records flagged for deletion are purged using the
  appropriate API (`DELETE /api/patients/{id}` or `/api/privacy/patients/{id}/erase`),
  cascading to related records per foreign-key configuration. Audit trail
  is preserved in the audit log (recording the *fact* of deletion, not the
  deleted data).
- **Backups:** the deletion takes effect on backups by natural rotation
  (30-day rolling). For erasure requests where this is too slow, a forced
  purge can be requested via the operations team; a written confirmation
  follows.
- **Logs:** rotated automatically per Section 3 above.
- **Caches (Redis):** invalidated on the same delete via the cache prefix
  bust pattern (`_bust_dashboard` etc.).

### 6.2 Physical records (if any)

- Cross-cut shredding or incineration with a witness log.
- For high-sensitivity records (HIV, mental health), use a destruction
  service certified to NIST 800-88 (or equivalent) and obtain a
  certificate of destruction.

### 6.3 Devices (laptops, mobile)

- Full-disk overwrite before reissue or disposal.
- Devices that held sensitive data and cannot be wiped to verifiable
  standard are physically destroyed.

### 6.4 Destruction log

The DPO maintains a register with:

| Field | Example |
|---|---|
| Destruction reference | DESTROY-2026-0001 |
| Record class | Adult clinical |
| Volume | 1,250 records |
| Reason | Statutory retention expired |
| Method | Soft-delete + 90-day backup cycle |
| Approver | DPO |
| Witness (where physical) | [PLACEHOLDER] |
| Date | 2026-05-15 |

---

## 7. Hospital-controlled vs Operator-controlled records

| Class | Controller | Operator's role |
|---|---|---|
| Clinical records (Sections 1, 2) | Hospital | Storage and assistance with deletion |
| Operational/IT (Section 3) | Operator (for its infrastructure); Hospital (for its tenant) | Operator manages its own |
| Staff (Section 4) | Operator (its staff); Hospital (its staff) | Each maintains its own |
| Financial records of Operator's subscription billing | Operator | — |

---

## 8. Review

This schedule is reviewed annually and when any source statute changes.
The DPO maintains it.

| Reviewed | Date | Changes |
|---|---|---|
| [PLACEHOLDER] | [PLACEHOLDER] | Initial draft v0.1 |
