# Data Subject Rights Procedure (Internal SOP)

> **Status:** DRAFT v0.1 — Operator-side internal SOP. The Hospital must have its own equivalent for clinical records.
> **Statutory basis:** KDPA ss 26, 38, 39, 40, 41 and the Data Protection (General) Regulations 2021, regs 12–17.
> **Audience:** DPO, Support team, Engineering on-call.

This SOP describes how [PLACEHOLDER — Operator] handles requests from data
subjects to exercise their rights under the KDPA. It covers requests
relating to:

(a) **Portal accounts** (where the Operator is Controller); and
(b) **Hospital-linked records** (where the Operator assists the Hospital as Processor — per Document 02 Clause 9.1).

---

## 1. The rights we must handle

| Right | KDPA section | Plain meaning |
|---|---|---|
| Right to be informed | s26(a), s28 | The data subject must know we hold their data and what we do with it |
| Right of access | s26(b), s39 | Provide a copy of the data we hold |
| Right of correction | s26(c), s40 | Fix inaccurate data |
| Right of erasure | s26(e), s40 | Delete data, subject to legal retention |
| Right to object | s26(d) | Stop processing for a stated reason |
| Right to restrict processing | s26(d), s40 | Freeze processing while a query is resolved |
| Right to data portability | s26(f) | Give a copy in a machine-readable format |
| Right to withdraw consent | s30(1) proviso | Take back consent previously given |
| Right not to be subject to automated decisions | s35 | Decline solely-automated decisioning |
| Right to lodge a complaint | s56 | Complain to us first; then ODPC |

---

## 2. Intake — channels

A data subject may exercise their rights through any of:

- **Email** to **dpo@[PLACEHOLDER — domain]**
- **In-portal form**: *Settings → Privacy → Submit a request*
- **Web form** at **[PLACEHOLDER — URL]/privacy/request**
- **Postal** to the registered office (Document 01)
- **Verbally** to support staff (must be logged immediately as a written request)

All requests are logged in the **DSR register** with a unique reference
(e.g., DSR-2026-0001).

---

## 3. Verifying the data subject

Before processing, verify the requester is who they say they are, in
proportion to the sensitivity of the data:

| Request type | Minimum verification |
|---|---|
| Withdraw newsletter / notification consent | Click confirmation link sent to email on file |
| Access portal account data | Sign-in + confirmation email |
| Erasure of portal account | Sign-in + confirmation email |
| Access clinical record (via Hospital) | Government ID + match with Hospital record; the Hospital owns this step |
| Request on behalf of a minor or incapacitated person | Proof of parental responsibility, guardianship, or power of attorney |

If we cannot verify within a reasonable time, we may decline or ask for
further evidence. The reason and steps taken must be recorded.

---

## 4. Routing

| Request scope | Owner | Why |
|---|---|---|
| Portal-account data only | Operator DPO | Operator is the Controller |
| Mixed (account + hospital record) | Operator DPO, with parallel handover to relevant Hospital DPO(s) | Hospital is the Controller for clinical |
| Hospital-record only | Forward to Hospital DPO within 5 business days; close with reason | Hospital is the Controller |

The Operator DPO is responsible for the routing decision and the
record-keeping.

---

## 5. Timeline

| Stage | Target |
|---|---|
| Acknowledge receipt | **Within 7 days** (Reg 14(2)) |
| Substantive response | **Within 30 days** of receipt (Reg 15(1)) |
| Extension for complex / multiple requests | Up to **further 60 days**, with written reasons given before day 30 |

Calendar days, not business days.

---

## 6. Handling specific rights

### 6.1 Access (s39)

1. Verify identity.
2. Generate an export bundle:
   - For portal: the account record + audit history + notifications log
     via the `/api/privacy/portal/export` endpoint (or query directly).
   - For Hospital-linked records: the Hospital does this; we provide
     technical assistance.
3. Provide via secure download link (expires in 7 days) or encrypted
   email.
4. Include the explanatory cover (what fields are what, retention reasons,
   how to ask follow-up questions).

### 6.2 Correction (s40)

1. Verify identity.
2. Confirm the proposed correction with the data subject.
3. Apply via the appropriate endpoint (portal: `PATCH /api/users/me`;
   Hospital: refer to Hospital).
4. Record in audit log.
5. Notify the data subject and any recipients with whom we shared the
   inaccurate data (reasonable steps).

### 6.3 Erasure (s40)

For portal accounts:

1. Verify identity.
2. Mark account inactive immediately so no further processing occurs.
3. After 14 days (grace period in case of mistake), purge personal data
   from the live database via `DELETE /api/users/me` (or DPO operator
   action).
4. Purge from backups within 90 days (backups rotate out naturally;
   forced purge only if requested in writing).
5. Confirm completion in writing.

Refusal grounds: when the data is required for the establishment, exercise,
or defence of a legal claim; or where statutory retention applies. Reasons
must be documented and communicated.

### 6.4 Withdrawal of consent

1. Identify the specific consent being withdrawn.
2. Update the consent record (e.g., `consent_revoked_at`).
3. Stop the relevant processing immediately.
4. Confirm to the data subject.

Note: withdrawal does not invalidate processing already done; this should be
clearly communicated.

### 6.5 Objection (s26(d))

1. Determine the lawful basis being objected to. If consent, treat as
   withdrawal. If legitimate interest, weigh the data subject's rights
   against the legitimate interest and decide.
2. If the objection is upheld, stop processing and log the decision.
3. If declined, give written reasons referencing the balancing analysis.

### 6.6 Restriction (s40)

1. Apply a "do not process" flag on the record (portal: `is_locked = true`
   or equivalent; Hospital workflow: refer to Hospital).
2. Notify the data subject when restriction is lifted.

### 6.7 Data portability (s26(f))

1. Verify identity.
2. Export only the data the subject provided (not derived data unless
   they ask for it).
3. Provide in JSON or CSV with a schema description.

### 6.8 Complaint (s56)

1. Acknowledge in writing within 7 days.
2. Investigate with the relevant function (Engineering, Support, etc.).
3. Substantive response within 30 days with the outcome, reasoning, and
   the data subject's right to escalate to the ODPC.

---

## 7. Refusal grounds (Reg 16)

We may refuse a request only on grounds permitted by KDPA / Regulations:

- The request is manifestly unfounded or excessive (e.g., repetitive).
- The request would prejudice rights and freedoms of others.
- Statutory retention requires us to keep the data.
- A legal claim is being established, exercised, or defended.
- National security / public order grounds (s51 exceptions) — must be
  documented and signed off by the DPO and senior management.

Every refusal must include:

- The specific reason.
- The fact that the data subject can escalate to the ODPC.
- The DPO's signature and date.

---

## 8. Fees

- The **first request in any 12-month period is free**.
- A reasonable fee may be charged for manifestly unfounded, repetitive, or
  excessive requests (Reg 17). The fee must reflect the administrative
  cost only.

---

## 9. DSR register fields

Each record in the DSR register contains:

| Field | Example |
|---|---|
| DSR reference | DSR-2026-0001 |
| Date received | 2026-05-15 |
| Channel | email / form / phone / postal |
| Data subject identifier | (hashed; raw kept in encrypted vault) |
| Right(s) being exercised | access / erasure / etc. |
| Scope | portal / hospital / mixed |
| Verification method | sign-in / ID match / etc. |
| Assigned to | DPO assistant name |
| Acknowledgement sent | yyyy-mm-dd |
| Substantive response sent | yyyy-mm-dd |
| Outcome | granted / partly granted / refused (with reason code) |
| Closed by | DPO name |
| Closed at | yyyy-mm-dd |

Register retention: **6 years** from closure. The register itself is
restricted to the DPO and the Hospital DPO for joint cases.

---

## 10. Metrics and reporting

The DPO publishes a quarterly internal metric:

- Number of requests by type
- Median and 95th-percentile response time
- Refusal rate and reasons
- Number escalated to ODPC

Significant deviations (e.g., > 5% missed response deadlines in a quarter)
trigger a remediation plan presented to senior management.

---

## 11. Annual review

This SOP is reviewed annually by the DPO. Reviews are recorded in the
header.

---

| Reviewed by | Date | Outcome |
|---|---|---|
| [PLACEHOLDER — DPO] | [PLACEHOLDER] | Initial draft v0.1 |
