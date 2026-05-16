# Data Processing Agreement (DPA)

> **Status:** DRAFT v0.1 — to be reviewed by Kenyan counsel before signature.
> **Statutory basis:** Kenya Data Protection Act, 2019 — particularly Sections 25, 38, 40, 41, 42, 43, 47, and the Data Protection (General) Regulations, 2021.
> **Forms part of:** the Master Services Agreement (Document 01).

This Data Processing Agreement ("**DPA**") is entered into between the
**Customer** (the Data Controller) and the **Operator** (the Data Processor)
as defined in the MSA (Document 01). It governs the processing of Patient
Personal Data and other Customer Personal Data through the HMS-2 Platform.

---

## 1. Definitions

Capitalised terms have the meaning given in the MSA. In addition:

| Term | Meaning |
|---|---|
| **Personal Data** | Has the meaning given in section 2 of the KDPA. Includes Patient Personal Data and Authorised User Personal Data. |
| **Sensitive Personal Data** | Has the meaning given in section 2 of the KDPA — including health data, genetic data, biometric data, and data revealing race, sex life, religion. |
| **Processing** | Has the meaning given in section 2 of the KDPA. |
| **Data Subject** | The individual to whom Personal Data relates (typically a patient, employee, or Authorised User). |
| **Sub-processor** | Any third party engaged by the Operator to process Personal Data on the Customer's behalf, listed in Document 15. |
| **TOMs** | Technical and Organisational Measures, set out in Schedule 1. |
| **ODPC** | Office of the Data Protection Commissioner. |

---

## 2. Scope, nature, and purpose of processing

| Element | Description |
|---|---|
| Subject matter | Provision of the HMS-2 hospital management Platform to the Customer. |
| Duration | The Term of the MSA, plus the wind-down period in Clause 11 below. |
| Nature of processing | Storage, retrieval, transmission, indexing, organisation, structuring, modification, and erasure of Personal Data. |
| Purpose | To enable the Customer to provide healthcare services to patients, manage clinical and administrative operations, and comply with its own legal obligations. |
| Categories of Data Subjects | (a) Patients of the Customer; (b) Authorised Users (Customer's staff); (c) Patient next-of-kin and emergency contacts; (d) third parties referenced in clinical notes. |
| Categories of Personal Data | Identity (name, ID, DOB, sex); contact (phone, email, address); clinical (diagnoses, vitals, medication, lab/imaging results, history); financial (billing, payment references); authentication (hashed passwords, session tokens); audit (access logs). |
| Categories of Sensitive Personal Data | Health data (all clinical), and where recorded: HIV status, mental health information, obstetric data, genetic results — flagged in the Platform's `medical_history` model as `is_sensitive`. |

---

## 3. Roles

3.1 With respect to Patient Personal Data and Authorised User Personal Data
processed through the Platform on the Customer's instructions, the **Customer
is the Data Controller** and the **Operator is the Data Processor**.

3.2 Where the Operator independently processes Personal Data for its own
purposes (such as Operator account administration, security monitoring of the
Operator's own infrastructure, or operating the public-facing Patient Portal
sign-in), the Operator is the Controller. That processing is governed by the
Platform Privacy Notice (Document 05), not this DPA.

---

## 4. Customer's instructions

4.1 The Operator shall process Personal Data only on the Customer's
**documented instructions**, which are:

  (a) the MSA and this DPA;
  (b) any subsequent written instructions agreed by the Parties; and
  (c) the Customer's lawful use of the Platform's features and APIs.

4.2 If the Operator believes an instruction infringes the KDPA or other
applicable law, it shall notify the Customer and may suspend the disputed
processing pending clarification.

---

## 5. Confidentiality and personnel

5.1 The Operator shall ensure that its personnel authorised to process
Personal Data:

  (a) are bound by written confidentiality undertakings or are under a
       statutory duty of confidence;
  (b) receive KDPA awareness training on or before access and at least
       annually thereafter;
  (c) access Personal Data only on a need-to-know basis.

5.2 The Operator maintains an internal access register identifying personnel
with privileged production access to Personal Data.

---

## 6. Technical and organisational measures (TOMs)

6.1 The Operator shall implement and maintain the TOMs in **Schedule 1** at no
less than the standard described, taking into account:

  (a) the state of the art;
  (b) the costs of implementation;
  (c) the nature, scope, context, and purposes of processing; and
  (d) the risks to Data Subjects.

6.2 The Operator may update the TOMs from time to time but shall not
materially lessen the protection. Material changes shall be notified to the
Customer with thirty (30) days' notice.

---

## 7. Sub-processors

7.1 The Customer **authorises the Operator to engage the sub-processors listed
in Document 15 (Sub-processor Register)** as at the Effective Date.

7.2 The Operator shall:

  (a) impose written obligations on each sub-processor that are no less
       protective than those imposed on the Operator by this DPA;
  (b) remain fully liable to the Customer for the acts and omissions of any
       sub-processor as if they were its own.

7.3 **Notice of new sub-processors.** The Operator shall give the Customer at
least **thirty (30) days' prior written notice** of the addition or replacement
of a sub-processor. The Customer may object on reasonable data-protection
grounds within fifteen (15) days of notice. If the Parties cannot resolve the
objection, the Customer may terminate the MSA on written notice, without
liability for fees beyond the date of termination.

7.4 **Emergency replacement.** If a sub-processor must be replaced urgently
for operational reasons, the Operator may do so with shorter notice but shall
notify the Customer as soon as practicable and afford the same termination
right.

---

## 8. Cross-border data transfers

8.1 The Operator shall not transfer Personal Data outside Kenya unless:

  (a) the transfer is to a jurisdiction with adequacy as recognised by the
       ODPC; or
  (b) the transfer is covered by appropriate safeguards under KDPA s48–49
       (standard contractual clauses, binding corporate rules, or written
       contract terms approved by the ODPC); or
  (c) one of the derogations in KDPA s48(3) applies.

8.2 The Operator shall maintain a Data Transfer Impact Assessment ("DTIA") for
each non-Kenyan sub-processor and shall make it available to the Customer on
reasonable request.

8.3 The Operator's current cross-border transfer landscape is described in
Document 15.

---

## 9. Assistance to the Customer

9.1 **Data Subject Rights (KDPA ss 26, 39–41).** The Operator shall assist the
Customer in responding to Data Subject requests by:

  (a) providing technical features in the Platform that permit the Customer
       to export, rectify, restrict, and erase a Data Subject's records (see
       `/api/privacy/*` endpoints — KDPA Section 40 erasure is implemented);
  (b) responding within five (5) business days to any request from the
       Customer that requires the Operator's specific assistance.

9.2 **DPIAs and prior consultation (KDPA s31).** The Operator shall provide
reasonable assistance to the Customer in conducting Data Protection Impact
Assessments and consulting the ODPC where required.

9.3 **Security (KDPA s41).** The Operator's TOMs (Schedule 1) describe its
security measures. The Operator shall provide reasonable assistance to the
Customer in demonstrating compliance.

---

## 10. Personal data breach notification

10.1 The Operator shall notify the Customer **without undue delay and in any
event within forty-eight (48) hours** of becoming aware of a personal data
breach affecting the Customer's Personal Data.

10.2 The notice shall, to the extent then known, describe:

  (a) the nature of the breach, including categories and approximate numbers
       of Data Subjects and records affected;
  (b) the likely consequences;
  (c) the measures taken or proposed to mitigate; and
  (d) the contact point for further information.

10.3 The Operator's own internal procedure is set out in Document 10. The
Operator shall provide further updates as the investigation progresses.

10.4 **KDPA s43 reporting to ODPC.** The Customer is responsible for any
notification to the ODPC and to affected Data Subjects under KDPA s43 (and the
seventy-two (72) hour limit). The Operator shall co-operate.

---

## 11. Return and deletion on termination

11.1 On termination of the MSA, the Operator shall, at the Customer's choice
notified within thirty (30) days of termination:

  (a) export the Personal Data in a structured machine-readable format and
       deliver it to the Customer; and/or
  (b) delete the Personal Data from live systems within thirty (30) days of
       termination and from backups within ninety (90) days, save where
       retention is required by Kenyan law.

11.2 The Operator shall provide a written certificate of deletion on request.

11.3 During the wind-down period the Operator shall continue to apply the TOMs.

---

## 12. Audits and inspections

12.1 The Operator shall make available to the Customer the information
necessary to demonstrate compliance with this DPA, including:

  (a) the latest TOMs document;
  (b) the latest ROPA extract relevant to the Customer;
  (c) the latest third-party security report (e.g. penetration test summary).

12.2 The Customer may, no more than once per twelve-month period (or more
frequently following a confirmed breach or material change), audit the
Operator's compliance with this DPA. The audit shall:

  (a) be conducted on no less than thirty (30) days' written notice;
  (b) take place during business hours;
  (c) not unreasonably interfere with the Operator's operations;
  (d) respect the confidentiality of other Operator customers' data;
  (e) be at the Customer's cost (the Operator's cost in the event the audit
       reveals a material non-compliance).

12.3 The Operator may satisfy the audit obligation by providing an
independent third-party report (e.g. an ISO 27001 certificate or SOC 2 Type II
report) that materially covers the scope.

---

## 13. Liability and indemnification

13.1 The liability provisions of the MSA (Clause 10) apply to this DPA, save
that the Operator's liability for **regulatory fines lawfully imposed on the
Customer by the ODPC** as a direct result of the Operator's breach of this DPA
is subject to the separate cap in MSA Clause 10.4.

13.2 Each Party shall indemnify the other for damage (including reasonable
legal costs) suffered as a result of that Party's breach of this DPA.

---

## 14. Term, conflict, and amendment

14.1 This DPA takes effect on the Effective Date of the MSA and continues until
all Personal Data has been deleted, returned, or anonymised per Clause 11.

14.2 In case of conflict between this DPA and the MSA on a data-protection
matter, this DPA prevails.

14.3 The Parties shall promptly negotiate amendments to this DPA if KDPA or
ODPC guidance changes in a way that requires it.

---

## Schedule 1 — Technical and Organisational Measures (TOMs)

The Operator implements and maintains at least the following measures:

### A. Access control
- Role-based access control (RBAC) for all platform features.
- Permissions are evaluated server-side on every request via `RequirePermission`.
- Authorised User accounts use strong password hashing (bcrypt with a cost factor consistent with current OWASP guidance).
- Session cookies are HttpOnly, Secure, and SameSite=None (cross-domain) or Strict.
- Refresh tokens are rotated on every refresh; revocation list is maintained server-side.
- Privileged production access is limited to named personnel and logged.

### B. Encryption
- All traffic between the Patient Portal / Tenant frontend and the API is encrypted in transit using TLS 1.2 or higher.
- Database connections from the application to the Postgres tier are TLS-encrypted.
- Sensitive columns (clinical free-text, ID numbers) use column-level encryption (`app/utils/db_types.py`) at rest.
- Backups are encrypted at rest by the hosting provider.

### C. Multi-tenancy isolation
- Each Tenant's data lives in a dedicated Postgres database identified by `db_name` in the master registry (`backend/app/config/database.py`).
- The application enforces a mandatory `X-Tenant-ID` header on every authenticated tenant request — there is no silent fallback to a default DB.
- JWT access tokens carry the tenant claim and are validated server-side against the requested tenant.

### D. Logging and audit
- All write operations on patient records are logged via `app/utils/audit.py` including user_id, action, entity, before/after value summary, and IP address.
- Access events on patient records are logged via `POST /api/patients/{id}/access`.
- Application logs are retained for at least ninety (90) days.

### E. Backups and disaster recovery
- Postgres backups are taken at least daily by the hosting provider and retained for at least thirty (30) days.
- Monthly restore test from backup into an isolated environment with documented success/failure log.
- Recovery Time Objective (RTO): [PLACEHOLDER — e.g. 4 hours]. Recovery Point Objective (RPO): [PLACEHOLDER — e.g. 24 hours].

### F. Vulnerability management
- Dependencies are monitored continuously through GitHub Dependabot.
- High and critical vulnerabilities are triaged within five (5) business days and patched within thirty (30) days.
- Annual external penetration test conducted by a qualified vendor.
- Security disclosure contact: **security@[PLACEHOLDER-domain]**.

### G. Personnel
- Written confidentiality undertakings before access.
- KDPA awareness training before access and annually thereafter.
- Access removed within one (1) business day of role change or departure.

### H. Physical and environmental security
- Production infrastructure is hosted at the sub-processors listed in Document 15 (Render, Vercel, Postgres provider). Physical and environmental controls are inherited from those providers and are subject to periodic review.

### I. Resilience and segregation
- Application and database instances are isolated from non-production environments.
- Test data does not contain real Patient Personal Data unless properly de-identified.

---

## Schedule 2 — Sub-processors

The list of authorised sub-processors at the Effective Date is set out in
**Document 15 (Sub-processor Register)** and incorporated by reference. The
Operator shall keep that register current.

---

## Schedule 3 — Customer's documented instructions

In addition to the MSA, the Customer's documented instructions include:

1. Process Personal Data only for the purposes set out in Clause 2.
2. Apply the security measures in Schedule 1 throughout the Term.
3. Engage only the sub-processors in Document 15 unless otherwise instructed.
4. Locate hosting in the regions identified in Document 15.
5. Apply retention durations set out in Document 14, save where the Customer
   instructs an earlier deletion or where Kenyan law requires longer retention.
6. Respond to Data Subject Rights requests per Document 09.
7. Notify the Customer of personal data breaches per Clause 10.

---

## Signatures

| For the Operator (Processor) | For the Customer (Controller) |
|---|---|
| Name: [PLACEHOLDER] | Name: [PLACEHOLDER] |
| Title: [PLACEHOLDER] | Title: [PLACEHOLDER] |
| Signature: ____________________ | Signature: ____________________ |
| Date: ____________________ | Date: ____________________ |
