# Sub-processor Register

> **Status:** DRAFT v0.1 — keep current. The publicly-accessible URL of this register is announced in Documents 02 and 05.
> **Statutory basis:** KDPA s42(2)(d); Data Protection (General) Regulations 2021 reg 7.
> **Audience:** internal DPO; published in summary form for Customers (Hospitals) and Patient Portal users.

The Operator engages the following sub-processors to deliver the HMS-2 /
MediFleet platform. Each is bound by a written contract that imposes data
protection obligations no less protective than those owed by the Operator
to the Customer.

---

## 1. How to read this register

| Field | Meaning |
|---|---|
| Service | What this provider does for us |
| Categories of data processed | Type of personal data the provider can access or hold |
| Hosting region | Country / region where data is processed |
| Cross-border safeguard | KDPA s48–49 basis (e.g., SCCs) |
| Last reviewed | Date of last contract / DTIA review |

---

## 2. Active sub-processors

### 2.1 Render

| Field | Value |
|---|---|
| Service | Application hosting (FastAPI backend, Postgres database, cron jobs) |
| URL | https://render.com |
| Categories of data processed | All Platform data (clinical, identity, audit, billing) — at rest and in transit |
| Hosting region | Configured: **[PLACEHOLDER — Frankfurt / Ohio / Oregon]** |
| Cross-border safeguard | Standard Contractual Clauses (Render's DPA, accepted as Customer) |
| Sub-processors of Render | Render's own sub-processors (cloud infra), per their published list |
| Last reviewed | [PLACEHOLDER] |
| Action items | Confirm hosting region; verify Render DPA signed; record DTIA |

### 2.2 Vercel

| Field | Value |
|---|---|
| Service | Frontend hosting and edge delivery for the SPA and Patient Portal |
| URL | https://vercel.com |
| Categories of data processed | Only request metadata at the edge (URL, headers, IP); no Personal Data stored at rest |
| Hosting region | Global edge network |
| Cross-border safeguard | Vercel's Customer DPA (SCCs incorporated) |
| Sub-processors | Vercel's published sub-processor list |
| Last reviewed | [PLACEHOLDER] |
| Notes | The `/api/*` paths are rewritten to the Render backend (Document 03 — internal note: `frontend/vercel.json`); only request-routing metadata transits Vercel |

### 2.3 Postgres provider (via Render or separately managed)

| Field | Value |
|---|---|
| Service | Managed Postgres database |
| Region | [PLACEHOLDER — same as Render] |
| Categories | All Platform data |
| Encryption at rest | Provider default (AES-256 disk encryption); column-level encryption for sensitive free-text fields applied by application |
| Backup | Provider-managed, 30-day rolling, encrypted |
| Cross-border safeguard | SCCs |
| Last reviewed | [PLACEHOLDER] |

### 2.4 Redis Cloud (or in-region equivalent)

| Field | Value |
|---|---|
| Service | Cache, session pub/sub for WebSockets |
| URL | https://redis.com/cloud (or hosted by Render) |
| Region | [PLACEHOLDER] |
| Categories | Cache fragments (analytics dashboard rollups, session tokens) — limited Personal Data |
| TTL | Most keys 5–30 minutes; max 7 days |
| Cross-border safeguard | SCCs |
| Last reviewed | [PLACEHOLDER] |

### 2.5 Safaricom — M-Pesa Daraja API

| Field | Value |
|---|---|
| Service | Payment initiation, status callbacks |
| URL | https://developer.safaricom.co.ke |
| Categories | Patient or payer phone number, transaction amount, M-Pesa reference, timestamp |
| Hosting region | Kenya |
| Cross-border safeguard | N/A — in-country |
| Last reviewed | [PLACEHOLDER] |
| Notes | Daraja's terms apply; we do not retain unhashed payer phone numbers beyond reconciliation needs |

### 2.6 Email transactional provider

| Field | Value |
|---|---|
| Service | Outbound transactional email (password reset, notifications, support replies) |
| Provider | [PLACEHOLDER — e.g., Postmark / SendGrid / AWS SES] |
| Hosting region | [PLACEHOLDER] |
| Categories | Email address, subject, body (which may include patient identifiers) |
| Cross-border safeguard | SCCs |
| Retention at provider | [PLACEHOLDER — typically 30 days for log; subject-line and body for shorter] |
| Last reviewed | [PLACEHOLDER] |
| Notes | Avoid sending sensitive clinical content in email; prefer notification + portal sign-in |

### 2.7 SMS provider

| Field | Value |
|---|---|
| Service | Outbound SMS for appointment reminders, OTP, password reset |
| Provider | [PLACEHOLDER — e.g., Africa's Talking] |
| Hosting region | Kenya |
| Categories | Phone number, message body |
| Cross-border safeguard | N/A (Kenya) |
| Last reviewed | [PLACEHOLDER] |

### 2.8 GitHub

| Field | Value |
|---|---|
| Service | Source-code hosting, CI/CD workflows |
| URL | https://github.com |
| Categories | Source code (which may incidentally contain example/test data); CI logs |
| Hosting region | US |
| Cross-border safeguard | SCCs (GitHub Enterprise DPA) |
| Last reviewed | [PLACEHOLDER] |
| Notes | No production Personal Data is committed; GitGuardian secret scanning in CI; Dependabot enabled |

### 2.9 Error monitoring (if enabled)

| Field | Value |
|---|---|
| Service | Application error and performance monitoring |
| Provider | [PLACEHOLDER — e.g., Sentry] |
| Hosting region | [PLACEHOLDER — choose EU if available] |
| Categories | Error stacks, request metadata; **must scrub PII** before sending (configure scrubbing rules) |
| Cross-border safeguard | SCCs |
| Last reviewed | [PLACEHOLDER] |
| Notes | Enable PII scrubbing; do not capture request bodies |

### 2.10 DNS, CDN, WAF

| Field | Value |
|---|---|
| Service | Domain DNS, edge WAF, DDoS protection |
| Provider | [PLACEHOLDER — e.g., Cloudflare, or built-in via hosting] |
| Categories | Request metadata, IP |
| Cross-border safeguard | SCCs |
| Last reviewed | [PLACEHOLDER] |

---

## 3. Sub-processors **considered but not engaged**

| Provider | Considered for | Decision | Reason |
|---|---|---|---|
| [PLACEHOLDER] | [PLACEHOLDER] | Not engaged | [PLACEHOLDER] |

---

## 4. Changes to this register

The Operator notifies Customers (Hospitals) of additions or replacements
under the procedure in DPA Document 02 Clause 7.3 — **thirty (30) days'
prior written notice**, with the Customer's right to object.

| Change | Effective | Notified |
|---|---|---|
| Initial register | [PLACEHOLDER] | n/a |

---

## 5. Public summary version

A simplified public-facing version of this register (without contract
specifics or vendor-confidential information) is published at
**[PLACEHOLDER — URL]** so that Patient Portal users can review it on
demand per Document 05 Clause 5.

---

*Version 0.1 — Last reviewed: 2026-05-15.*
