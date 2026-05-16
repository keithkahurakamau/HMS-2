# Service Level Agreement (SLA)

> **Status:** DRAFT v0.1
> **Forms part of:** the Master Services Agreement (Document 01).
> **Scope:** the production HMS-2 / MediFleet Platform delivered to the Customer.

This SLA describes the availability, support, and remediation commitments
the Operator makes to the Customer. Capitalised terms not defined here have
the meaning given in the MSA.

---

## 1. Availability commitment

| Subscription tier | Monthly Uptime Target |
|---|---|
| Starter | 99.0% |
| Professional | 99.5% |
| Enterprise | 99.9% |

**Monthly Uptime** is calculated as:

```
Monthly Uptime % = (Total Minutes in Month − Downtime Minutes) / Total Minutes in Month × 100
```

**Downtime** means a period during which the Platform's primary API
(`https://hms-2-3o0p.onrender.com/api/...` or the Customer's configured
production endpoint) returns a server error (HTTP 5xx) on the documented
health-check endpoint for more than five (5) consecutive minutes, as
measured by the Operator's monitoring.

**Excluded from Downtime:**

- Scheduled maintenance announced at least seven (7) days in advance.
- Emergency security maintenance, where notice is given as early as
  reasonably practicable.
- Force majeure (per MSA Clause 13).
- Customer-caused failures (e.g., misconfigured credentials, exhausted
  storage quota, suspended account for non-payment).
- Third-party network failures outside the Operator's control between the
  Customer and the Platform.

---

## 2. Service Credits

If Monthly Uptime falls below the target for the Customer's tier, the
Customer may request a service credit against the next monthly invoice:

| Uptime achieved | Service Credit (% of monthly Fees for affected service) |
|---|---|
| < target but ≥ 99.0% | 10% |
| < 99.0% but ≥ 95.0% | 25% |
| < 95.0% | 50% (capped) |

**Conditions:**

- The Customer must request the credit in writing within thirty (30) days
  of the end of the affected month.
- Credits are the **sole and exclusive remedy** for SLA failures, save for
  the right of termination in Clause 7.
- Aggregate credits in any month cannot exceed the monthly Fees for that
  month.

---

## 3. Support

### 3.1 Channels

| Channel | Availability |
|---|---|
| In-app Support module | 24/7 (responses per response targets below) |
| Email **support@[PLACEHOLDER]** | 24/7 |
| Phone **[PLACEHOLDER]** | Mon–Sat 08:00–18:00 EAT (Enterprise only) |
| Emergency security line **[PLACEHOLDER]** | 24/7 for confirmed security incidents only |

### 3.2 Severity definitions and response targets

| Severity | Definition | First response | Resolution / workaround target |
|---|---|---|---|
| S1 — Critical | Platform unavailable or data integrity at risk; no workaround | 1 hour, 24/7 | 4 hours |
| S2 — High | Major feature broken or significant degradation; workaround difficult | 4 hours, business hours | 1 business day |
| S3 — Medium | Minor feature broken or with workaround | 1 business day | 5 business days |
| S4 — Low | Question, cosmetic issue, enhancement request | 2 business days | Best effort |

Business hours are **Mon–Fri 08:00–18:00 EAT**, excluding Kenyan public
holidays.

### 3.3 Severity is assigned by the Operator

… in good faith, after considering the Customer's input. The Customer may
appeal a severity assignment in writing.

---

## 4. Maintenance windows

| Window | Frequency | Notice |
|---|---|---|
| Standard maintenance | Up to 4 hours per month, **Sat 22:00–02:00 EAT** | 7 days |
| Major version upgrade | Up to 8 hours per quarter, off-peak | 14 days |
| Emergency security maintenance | As needed | As soon as practicable, with reason |

Maintenance times announced via the in-app banner and email to the
Customer's technical contact.

---

## 5. Backups, RTO, and RPO

| Tier | RPO (data loss tolerance) | RTO (restore time) |
|---|---|---|
| Starter | 24 hours | 8 hours |
| Professional | 6 hours | 4 hours |
| Enterprise | 1 hour | 2 hours |

The Operator runs an automated nightly backup at minimum, with monthly
restore tests recorded in the operations log.

---

## 6. Status communication

| Channel | Used for |
|---|---|
| Status page **[PLACEHOLDER — status URL]** | Live incident status |
| Email to Customer technical contact | Confirmed incidents, post-incident summary |
| In-app banner | Significant active incidents |

Post-incident summaries are sent within five (5) business days of
resolution for any S1 or S2 incident and include: timeline, root cause,
remediation, and prevention measures.

---

## 7. Termination for chronic SLA failure

If the Platform's Monthly Uptime is below the target tier in **three (3)
consecutive months** or **any four (4) months in a rolling twelve (12)
months**, the Customer may terminate the MSA on thirty (30) days' written
notice without further liability for unaccrued Fees and is entitled to
co-operation with data export per MSA Clause 12.

---

## 8. Excluded services

This SLA does not apply to:

- Pre-production / staging environments.
- Beta features clearly marked as such in the Platform.
- Integrations with third-party services to the extent the third party is
  the cause of the issue.

---

## 9. Reporting

On the Customer's reasonable request (no more than monthly), the Operator
will provide:

- Monthly Uptime calculation for the prior month.
- A summary of any S1 or S2 incidents.
- Status of pending changes affecting the Customer.

---

## 10. Review

This SLA is reviewed annually. Material changes follow the change-control
process in the MSA.

---

*Version 0.1 — Effective Date: [PLACEHOLDER].*
