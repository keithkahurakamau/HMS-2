# Data Breach Notification Procedure (Internal SOP)

> **Status:** DRAFT v0.1 — Operator internal SOP.
> **Statutory basis:** KDPA s43 (notification within 72 hours); Data Protection (General) Regulations 2021, regs 20–22; ODPC Guidance Note on Data Breach Notification (2023).
> **Audience:** DPO, Security on-call, Engineering on-call, Senior management, Legal counsel.

A **personal data breach** is a breach of security leading to the accidental
or unlawful destruction, loss, alteration, unauthorised disclosure of, or
access to, personal data transmitted, stored, or otherwise processed.

The Operator must notify the **ODPC** and, in serious cases, **affected data
subjects**, within strict timelines. This SOP defines the steps.

---

## 1. Severity matrix

| Tier | Description | Examples |
|---|---|---|
| **T0 — Critical** | Confirmed unauthorised access to or exfiltration of significant sensitive data; service down with potential data integrity impact | Database dump exfiltrated; admin credentials compromised |
| **T1 — High** | Confirmed unauthorised access to sensitive data, limited scope; or significant service degradation with possible data exposure | Single tenant's data exposed to another tenant; insider snooping detected |
| **T2 — Medium** | Suspected unauthorised access; vulnerability that *could* lead to a breach; lost/stolen device | Lost staff laptop with no full-disk encryption; near-miss SQL injection |
| **T3 — Low** | Operational incident with no realistic data risk | Misdirected internal email; brief outage with no data impact |

ODPC notification is mandatory for T0 and T1, and for T2 where the risk to
data subjects is more than low. The DPO is the final decision-maker on
classification.

---

## 2. Detection and intake

A potential breach may be detected via:

- Application logs, monitoring alerts (uptime, error spikes, anomalous DB queries).
- Sub-processor incident notification (Render, Vercel, payment provider).
- Customer (Hospital) report (`security@[PLACEHOLDER]`, `dpo@[PLACEHOLDER]`).
- Bug bounty / responsible-disclosure submission.
- Internal staff member.
- Audit-log review.

Anyone who suspects a breach must report it to **security@[PLACEHOLDER]** or
contact the on-call engineer directly. There is **no penalty for a
good-faith false alarm**.

---

## 3. Incident response team

| Role | Person | Responsibility |
|---|---|---|
| Incident Commander (IC) | Designated DPO or senior engineer | Decisions, comms approval |
| Technical Lead | On-call senior engineer | Containment, evidence preservation |
| Communications Lead | DPO | Notifications to ODPC, customers, data subjects |
| Legal Counsel | [PLACEHOLDER — external advocate] | Legal review of notifications |
| Executive Sponsor | CEO / Director | Approves T0 communications |

Contact details are kept in the **on-call runbook** (internal, not in this
file).

---

## 4. The clock starts when…

**"Becoming aware"** under KDPA s43 = the moment a senior technical or DPO
function has reasonable certainty that a personal-data breach has occurred.
Investigation time to *confirm* the breach is part of the 72 hours, not
before it. Document the detection time precisely.

> The 72-hour clock starts **the moment the Operator becomes aware** — not
> when the investigation is complete. If the full picture is not known by
> hour 70, file a **preliminary** notification with whatever is known and
> follow up.

---

## 5. The eight-step playbook

### Step 1 — Triage (target: within 30 minutes of detection)
- Form the response team (one channel; no parallel scattered conversations).
- IC assigns tier (preliminary).
- Begin **incident log** in the IR repo (single source of truth).

### Step 2 — Contain (target: within 1 hour)
- Cut off the active attack vector (rotate keys, revoke tokens, take
  affected service offline if necessary).
- Preserve evidence: snapshot logs, DB state, application config. **Do not**
  destroy or modify before evidence is captured.

### Step 3 — Investigate (rolling, target: confirm scope within 24 hours)
- Identify: what data was involved, how many records, which data subjects,
  which Hospitals/tenants, when, how.
- Distinguish between confirmed exposure and potential exposure.
- Engage Legal counsel for advice on notification scope.

### Step 4 — Classify (by hour 24 at the latest)
- IC + DPO confirm the final tier.
- Decide: does this require ODPC notification? Does it require data-subject
  notification? Record reasons.

### Step 5 — Notify the Hospitals (target: within 48 hours)
- For each affected Hospital, the DPO sends the **Hospital Breach
  Notification** (template below). This is required by Document 02 Clause 10
  (which gives us 48 hours).
- Provide the technical contact, the description (per s43(2) elements), and
  the planned next steps.

### Step 6 — Notify the ODPC (within 72 hours of awareness)
- Use the ODPC online portal (https://complaints.odpc.go.ke) or the email
  channel current per ODPC guidance.
- Include the elements of s43(2):
  - nature of the breach, categories and approximate numbers of data subjects and records;
  - name and contact details of the DPO;
  - likely consequences;
  - measures taken or proposed.
- If full picture is incomplete, file preliminary and commit to update.
- Keep the submission receipt in the incident log.

### Step 7 — Notify affected data subjects (timing per s43(3))
- Required where the breach is **likely to result in high risk to the
  rights and freedoms** of data subjects.
- Communication must be in **clear and plain language**.
- Channels: email + SMS to the patient portal contact details, or via the
  Hospital where direct contact is impractical.
- Must include: nature of the breach, contact point, likely consequences,
  measures taken, and what the data subject can do to protect themselves
  (e.g., change password, watch for phishing).

### Step 8 — Remediate and learn (within 30 days)
- Implement permanent fix.
- Conduct **post-incident review** (blameless).
- Update controls, DPIA, ROPA, and where needed this SOP.
- Document lessons in the post-incident review register.

---

## 6. Notification templates

### A. Hospital notification (sent within 48 hours)

> Subject: **Security Incident Notification – HMS-2 / MediFleet**
>
> Dear [PLACEHOLDER — Hospital DPO],
>
> We are writing to notify you, in accordance with Clause 10 of our Data
> Processing Agreement, of a personal data incident affecting data we
> process on your behalf.
>
> **Time of detection:** [yyyy-mm-dd hh:mm EAT]
> **Time of likely onset:** [yyyy-mm-dd or "unknown"]
> **Nature of the incident:** [brief description]
> **Data categories involved:** [identification / contact / clinical / etc.]
> **Approximate volume:** [number of patient records affected / "still being assessed"]
> **Current status:** [contained / under investigation / resolved]
> **Measures taken so far:** [list]
> **Likely consequences:** [for example, "we have no evidence of misuse but
>  data was accessible to an unauthorised account for X minutes"]
> **Your responsibility under KDPA s43:** As Data Controller you may need to
> notify the ODPC within 72 hours of your awareness. We will support this.
> **Operator contact for this incident:** [PLACEHOLDER — IC name, phone, email]
>
> We will provide an update no later than [yyyy-mm-dd], or sooner if material
> new information emerges.
>
> [DPO signature]

### B. ODPC notification (within 72 hours)

Use the ODPC online form; the elements required are listed in step 6 above.
Keep a PDF copy of the submission and the receipt in the incident log.

### C. Data-subject notification (when required)

> Subject: **Important: a security incident affecting your information**
>
> Dear [name or "Sir / Madam"],
>
> We are writing to inform you of a security incident that may have affected
> some of your information held in the [PLACEHOLDER — Hospital] / MediFleet
> system.
>
> **What happened:** [plain language description]
> **When:** [dates]
> **What information was involved:** [categories]
> **What we are doing:** [containment, investigation, remediation in plain
>  terms]
> **What you should do:**
>   - [practical step 1]
>   - [practical step 2]
> **Who to contact for questions:** [PLACEHOLDER — phone, email]
> **Your rights:** You can complain to the Office of the Data Protection
> Commissioner at https://www.odpc.go.ke if you are not satisfied with our
> response.
>
> We are sorry. We take this very seriously and will keep you informed.
>
> [DPO signature]

---

## 7. Records and retention

- The **incident log** for each incident is retained for **6 years** from
  closure.
- The **breach register** (one row per incident with key fields) is
  maintained by the DPO and reviewed at every quarterly governance
  meeting.

Required register fields:

| Field | Example |
|---|---|
| Incident reference | INC-2026-0001 |
| Tier | T1 |
| Detection time | 2026-05-15 09:23 EAT |
| Containment time | 2026-05-15 09:55 EAT |
| Cause | [phishing / vulnerability / misconfiguration / insider] |
| Data subjects affected (approx) | 1,200 |
| Hospitals affected | [list] |
| ODPC notified | yyyy-mm-dd, receipt ref |
| Data subjects notified | yyyy-mm-dd, channel |
| Closed | yyyy-mm-dd |
| Lessons learned | [link to post-incident review] |

---

## 8. Do **not** do these things in an incident

- Don't restore from backup before evidence is preserved.
- Don't change account passwords on the affected accounts before forensics
  has captured the state.
- Don't speculate publicly or on social media before notification is sent.
- Don't issue commercial or PR statements without DPO and Legal sign-off.
- Don't omit the ODPC step because the breach looks minor — document the
  classification reason instead.

---

## 9. Review

| Reviewed by | Date | Outcome |
|---|---|---|
| [PLACEHOLDER — DPO] | [PLACEHOLDER] | Initial draft v0.1 |

The SOP is reviewed annually and immediately after any Tier 0 or Tier 1
incident.
