# Launch Readiness Plan — HMS-2 / MediFleet (Kenya)

> **Owner:** [PLACEHOLDER — Operator]
> **Date compiled:** 2026-05-15
> **Status:** decision record + execution plan for going from "working in production" to "officially operating as a multi-tenant hospital SaaS in Kenya."
> **Related documents:** `docs/legal/` (PR #8), `docs/DEPLOYMENT.md`.

This document captures the architectural and commercial decisions made in the
launch-readiness review on **15 May 2026**, the recommended technology stack,
the cost model, and the prioritised action list.

---

## 1. Architectural decisions

### 1.1 Stay on Render — do not migrate to Supabase

| Decision | Stay on Render |
|---|---|
| Decision date | 2026-05-15 |
| Decision-maker | [PLACEHOLDER — Operator] |
| Reasoning summary | Supabase is not a host swap — it's a different architectural model (one Postgres + RLS + Supabase Auth + Edge Functions in Deno). Migrating would require rewriting the per-tenant DB isolation (`get_tenant_engine` in `backend/app/config/database.py`), replacing the JWT cookie auth we just shipped (commit `cb209cb`), and re-platforming all FastAPI business logic. Security gaps to date have been application-level, not host-level. |
| Revisit when | A specific Supabase feature becomes commercially compelling (rare for this architecture), or Render stops meeting our needs. |

### 1.2 Hosting region: Render Frankfurt

| Decision | Render Frankfurt (`fra`) |
|---|---|
| Decision date | 2026-05-15 |
| Decision-maker | [PLACEHOLDER — Operator] |
| Reasoning summary | Render has no Kenyan region. Frankfurt gives ~150 ms RTT to Kenyan users (vs ~250 ms from Oregon/Ohio). The faster alternatives — AWS Cape Town (~80 ms), in-country Safaricom / Liquid / Africa Data Centres — require weeks of re-platforming and are premature optimisation for the current stage. Cross-border data-transfer paperwork (SCCs) is the trade-off, and is already an action item in the DPIA (Doc 12 action A1). |
| Revisit when | (a) a hospital contractually requires in-country hosting; (b) we exceed ~5 tenants and Frankfurt latency starts costing deals; or (c) ODPC guidance hardens against current SCC framework. |

### 1.3 No in-country migration before milestone X

We will **not** migrate to AWS Cape Town / Safaricom / Liquid / Africa Data
Centres until at least one of:

- A signed hospital contract has an in-country hosting requirement.
- We have ≥ 5 tenants and the latency cost is measurable.
- A regulator instructs us to.

---

## 2. Backend "official" checklist (Render)

| # | Item | Priority | Effort | Status |
|---|---|---|---|---|
| B1 | Upgrade web service: `starter` → `standard` ($25/mo) | **P0 — blocker** | 5 min in dashboard | [ ] |
| B2 | Upgrade Postgres to paid plan; enable point-in-time recovery (PITR) | **P0** | 10 min | [ ] |
| B3 | Move region to Frankfurt (`fra`) if currently on US region | **P0** | re-deploy with planned downtime | [ ] |
| B4 | Custom API domain (e.g., `api.medifleet.co.ke`) via Render's custom-domain UI | **P0** | 30 min + DNS propagation | [ ] |
| B5 | Lock `CORS_ORIGINS` env var to the production frontend domain only | **P0** | 1 line env change | [ ] |
| B6 | Sentry (or equivalent) error tracking with PII scrubbing | **P1** | 1 hour | [ ] |
| B7 | UptimeRobot / Render uptime monitor with email + SMS alerts | **P1** | 15 min | [ ] |
| B8 | Verify monthly backup restore test runs (DPIA action A4) | **P1 — recurring** | — | [ ] |
| B9 | Tune Uvicorn workers (`--workers 2-4` in `render-start.sh`) | P2 | 2 lines | [ ] |
| B10 | Add HTTP `Cache-Control` headers on read-heavy public endpoints | P2 | half a day | [ ] |
| B11 | PgBouncer in front of Postgres if connection limits become tight | P3 — conditional | half a day | [ ] |

> **Critical finding on 2026-05-15:** the backend first request took **94 seconds** because the `starter` plan spins down after 15 minutes of idle. B1 is non-negotiable before any hospital uses the platform.

---

## 3. Frontend "official" checklist (Vercel)

| # | Item | Priority | Effort | Status |
|---|---|---|---|---|
| F1 | Custom domain (e.g., `medifleet.co.ke` or `app.medifleet.co.ke`) | **P0** | 30 min + DNS | [ ] |
| F2 | Upgrade Vercel Hobby → Pro ($20/user/month) for commercial use | **P0** | 5 min | [ ] |
| F3 | Wire `/privacy`, `/terms`, `/cookies` routes to the published versions of `docs/legal/` (after advocate review) | **P0** | 1–2 hours | [ ] |
| F4 | Sentry for the SPA, same PII-scrubbing rules as backend | **P1** | 30 min | [ ] |
| F5 | Enable Vercel Web Analytics (privacy-respecting, no cookies) | P1 | 1 click | [ ] |
| F6 | `/status` link in footer pointing to status page | P1 | 15 min | [ ] |
| F7 | Strict CSP + `Strict-Transport-Security` headers in `frontend/vercel.json` | P2 | 30 min | [ ] |
| F8 | Prerender public routes (`vite-plugin-prerender` or `vite-ssg`) for SEO | P2 | 1 day | [ ] |
| F9 | Add `react-helmet-async` (or HTML-transform) for per-route `<title>`, `<meta>`, OpenGraph, Twitter Card | P2 | 2 hours | [ ] |
| F10 | `sitemap.xml`, `robots.txt`, canonical URLs, `Organization` + `SoftwareApplication` JSON-LD on landing | P2 | half a day | [ ] |

---

## 4. Database & performance plan

Target: **median API response under 200 ms** end-to-end for read endpoints
once warm.

| # | Item | Expected impact | Status |
|---|---|---|---|
| D1 | Co-locate Postgres in same Render region as the web service | DB-to-app RTT drops from 30–80 ms to < 2 ms | [ ] |
| D2 | Audit indexes on hot tables (`patients.outpatient_no`, `patients.telephone_1`, `audit_log(user_id, action, created_at)`, `medical_records(patient_id, created_at DESC)`) | Avoids degeneration to full scans as data grows | [ ] |
| D3 | Confirm Redis cache is on for analytics dashboard (`app.core.cache`) and tune TTLs | Repeated reads from ms-scale memory instead of DB | [ ] |
| D4 | Bump Uvicorn workers (`--workers 2-4`) once on Standard plan | Linear throughput gain | [ ] |
| D5 | Enable HTTP caching on public endpoints — Vercel will edge-cache | Removes traffic from Render entirely | [ ] |
| D6 | PgBouncer if connection saturation becomes a problem | Frees worker threads | [ ] |
| D7 | Monthly **EXPLAIN ANALYZE** review of the 10 slowest queries from `pg_stat_statements` | Targeted index/query tuning | [ ] |

> Connection pooling per-tenant is already implemented via the bounded LRU in
> `get_tenant_engine` (`backend/app/config/database.py:81-112`).

---

## 5. Cost model

### 5.1 Monthly recurring (USD; KES ≈ 130 / USD)

| Bucket | Item | "Ship now" tier | "10+ tenants" tier |
|---|---|---|---|
| Hosting — Render | Web service | Standard **$25** | Pro **$85** |
| | Postgres | Standard **$20** (1 GB RAM, 16 GB) | Pro **$95** (4 GB RAM, 256 GB) |
| | Redis | Starter **$10** | Standard **$50** |
| Hosting — Vercel | Pro plan | **$20** (1 user) | **$20 × team size** |
| Email — transactional | Postmark / Resend | **$15** (10–50k emails) | **$35** (100k emails) |
| Email — business mailboxes | Zoho Mail Standard | **$5** (~5 users) | **$40** (~10 users) |
| | *or* Google Workspace Business Starter | $30 (5 users) | $60 (10 users) |
| SMS | Africa's Talking pay-as-you-go (~$0.006/SMS) | **~$10** | ~$50 |
| Monitoring | Sentry Team (FE+BE) | **$26** | $80 |
| Status page | Instatus / Better Stack | **$20** | $20 |
| **Monthly total (Zoho path)** | | **~$151** | **~$485** |
| **Monthly total (Google path)** | | **~$176** | **~$505** |

In KES: **~KES 20,000/month at launch, ~KES 65,000/month at scale**.

### 5.2 Annual recurring

| Item | Cost |
|---|---|
| `.co.ke` domain (Truehost / EAC Directory / HostPinnacle) | KES 2,500–4,000 / year |
| `.co.ke` renewal | same |
| `.com` (if also registered) | $10–15 |
| TLS certificates | Free (Let's Encrypt — both Render and Vercel auto-issue) |
| Cloudflare DNS | Free |
| ODPC Data Controller registration (KDPA Reg 8) | KES 4,000 (small/medium) or KES 40,000 (large) / year |
| **Annual fixed** | **~KES 7,000–50,000** (~$50–400) |

### 5.3 One-time setup

| Item | Estimate |
|---|---|
| Advocate review of the 17 legal documents in `docs/legal/` | KES 200,000–500,000 (~$1,500–4,000) |
| External penetration test (recommended annually thereafter) | $3,000–10,000 |
| Company incorporation + KRA PIN (if not yet done) | ~KES 11,500 |
| **One-time** | **~$5,000–15,000** |

### 5.4 Year-1 realistic total

- **Going live:** ~$5,000–15,000 one-time + ~$1,800–2,000 first-year recurring = **~$7,000–17,000 (KES 900k–2.2M)**.
- **Year 2 onwards:** ~$2,500–6,000/year hosting + ~$3,000–10,000 if annual pentest is kept = **~$5,500–16,000/year (KES 700k–2M)**.

### 5.5 Recommended day-one stack (in order to pay for)

| # | Item | Cost | Why first |
|---|---|---|---|
| 1 | Render web service: **Standard** | $25/mo | Kills the cold-start nightmare |
| 2 | Render Postgres: **Standard** with PITR | $20/mo | Backups + restore actually work |
| 3 | `medifleet.co.ke` domain | KES 4,000/yr | Branded URLs everywhere |
| 4 | Zoho Mail Standard, 5 mailboxes | $5/mo | `dpo@`, `security@`, `support@`, `info@`, `admin@` — required by privacy notices |
| 5 | Postmark Starter | $15/mo | App-sent email (resets, notifications) |
| 6 | Africa's Talking SMS top-up | $20 initial | Appointment SMS + OTP |
| 7 | Render Redis: Starter | $10/mo | Already coded for it (`app.core.cache`) |
| 8 | Sentry Team | $26/mo | Visibility into prod errors |
| 9 | Vercel Pro | $20/mo | Commercial-use terms |
| 10 | Cloudflare DNS | Free | DNS + DDoS at the edge |

**Day-one running cost ≈ $121/month + KES 4,000/year** + one-time advocate fee.

---

## 6. Email system

You need both of the two interpretations of "email system":

| Type | Purpose | Provider recommendation | Cost |
|---|---|---|---|
| **Transactional outbound** | Password resets, appointment reminders, breach notices, invoices | **Postmark** (best deliverability, simple SMTP/API) or **Resend** (modern dev experience) | $15–35/month |
| **Business mailboxes** | `support@`, `dpo@`, `security@`, `info@`, `admin@` — humans send/receive | **Zoho Mail** ($1/user) or **Google Workspace** ($6/user) | $5–60/month |
| **SMS** (auxiliary) | Appointment reminders, OTP, breach SMS | **Africa's Talking** (Kenyan provider, KES pricing, in-country = no cross-border) | ~$0.006/SMS |

Document 03 (Patient Privacy Notice) and Document 10 (Breach Procedure) both
require a working, human-monitored `dpo@yourdomain` mailbox — business mail
is non-optional.

---

## 7. Domains

| Domain | Use | Registrar suggestions |
|---|---|---|
| `medifleet.co.ke` (or chosen `.co.ke`) | Primary brand, landing page, business email | Truehost, HostPinnacle, EAC Directory, Safaricom Business (all KENIC-accredited) |
| `app.medifleet.co.ke` | Patient & staff SPA on Vercel | Subdomain of above |
| `api.medifleet.co.ke` | FastAPI backend on Render | Subdomain of above |
| `status.medifleet.co.ke` | Status page (Instatus / Better Stack) | Subdomain of above |
| `medifleet.com` (optional) | Defensive registration | Namecheap, Cloudflare |

DNS hosted at **Cloudflare** (free tier) — better edge protection, faster
propagation, and the ability to put a WAF in front later if needed.

---

## 8. SEO plan

> **Calibration:** for B2B health SaaS in Kenya, SEO is rarely the highest-leverage channel — direct sales, KMPDC / county-health-officer networking, and admin-to-admin referrals convert better than search traffic. Don't overspend. Patient-portal SEO matters more (patients Google their hospital).

### 8.1 Technical SEO problem

Your frontend is a **Vite SPA** — the landing page (`Landing.jsx`) ships as
an almost-empty HTML shell. Google can render JS, but it's slow and
unreliable for ranking, and link-unfurls on social/WhatsApp often fail.

Fix options:

| Option | Effort | Result |
|---|---|---|
| **A. Prerender public routes** with `vite-plugin-prerender` or `vite-ssg` | 1 day | Landing + legal pages are real HTML; rest stays SPA |
| **B. Separate marketing site** (Astro / Framer / Webflow) on `medifleet.co.ke`, app on `app.medifleet.co.ke` | 1 week + $0–50/mo | Clean separation, fastest landing perf |
| **C. Migrate frontend to Next.js** | 3–6 weeks | Overkill |

**Recommendation: A** unless a non-technical team member needs to edit
marketing copy (then B).

### 8.2 Free DIY (do this regardless)

| # | Item | Cost | Effort |
|---|---|---|---|
| S1 | Google Search Console — submit sitemap, monitor coverage | Free | 30 min |
| S2 | Bing Webmaster Tools | Free | 15 min |
| S3 | Google Business Profile (Kenyan address, phone) | Free | 1 hour + verification |
| S4 | Per-route `<title>`, `<meta description>`, OpenGraph, Twitter Card via `react-helmet-async` | Free | 2 hours |
| S5 | Canonical URLs on landing + every legal page | Free | 30 min |
| S6 | `sitemap.xml` for public URLs only | Free | 30 min |
| S7 | `robots.txt` disallowing `/app/*`, `/superadmin/*`, `/api/*` | Free | 10 min |
| S8 | `Organization` + `SoftwareApplication` JSON-LD structured data on landing | Free | 1 hour |
| S9 | Vercel Analytics on for Core Web Vitals; fix any red metrics | Free with Pro | recurring |
| S10 | HTTPS + clean URLs | Free | already done |

### 8.3 Paid (only when revenue justifies)

| Tier | What | Cost |
|---|---|---|
| Content | One blog post/month from a freelance writer on KDPA-for-clinics, KMPDC compliance | KES 10,000–25,000 (~$80–200) |
| SEO tool | Ahrefs Lite $129 / Semrush Pro $139 / Ubersuggest $29 — skip until > 20 posts | — |
| Kenyan SEO agency | Only with B2B SaaS case studies | KES 50,000–200,000 (~$400–1,500) |
| Google Ads | Targeted "hospital management Kenya" search ads | KES 30,000+ test budget |

### 8.4 SEO spend timeline

| Phase | Monthly SEO spend |
|---|---|
| Now (pre-revenue, just shipping) | **$0** + free DIY items |
| Year 1, ~10 hospitals | ~$100–250 (content + Ubersuggest) |
| Year 2+, scale | $500–2,000 (content + tool + maybe agency) |

---

## 9. Action plan — prioritised

### This week (P0 — blocker)

1. **Upgrade Render web service** to Standard ($25/mo). Eliminates cold start.
2. **Upgrade Render Postgres** to a paid plan; enable PITR.
3. **Move to Frankfurt** if not already there.
4. **Buy `medifleet.co.ke`** (KES 4,000/year).
5. **Buy `medifleet.com`** (defensive, $12/year) — optional.
6. **Set up Cloudflare DNS** for the domain (free).
7. **Configure custom domains**: `app.medifleet.co.ke` → Vercel, `api.medifleet.co.ke` → Render.
8. **Lock `CORS_ORIGINS`** env var on Render to the new frontend domain.
9. **Upgrade Vercel** to Pro.

### This month (P1)

10. **Buy Zoho Mail Standard** (5 mailboxes) and configure DNS records (MX, SPF, DKIM, DMARC).
11. **Buy Postmark Starter** and wire it into the backend's transactional flows.
12. **Open Africa's Talking account** and load $20 of SMS credit.
13. **Sign up for Sentry**; integrate FE + BE; configure PII scrubbing.
14. **Sign up for Instatus / Better Stack** status page; point `status.medifleet.co.ke` at it.
15. **Engage a Kenyan advocate** to review the `docs/legal/` set; provide them this document and PR #8 link.
16. **Start ODPC registration** (KDPA Reg 4 — see `docs/legal/00-compliance-action-checklist.md`).
17. **Appoint the DPO** (formally, in writing, with a job description).

### This quarter (P2)

18. **Implement DIY SEO** (items S1–S10 above) — single PR.
19. **Add prerendering** for landing + legal page routes.
20. **Audit DB indexes** on hot tables.
21. **Configure strict CSP** + HSTS in `vercel.json`.
22. **First monthly backup-restore test** — log it.
23. **Sign SCCs** with Render, Vercel, GitHub, and your email/SMS providers (DPIA action A1).
24. **Wire `/privacy`, `/terms`, `/cookies` routes** to the published, advocate-reviewed versions of `docs/legal/`.

### Pre-first-customer (P0 for go-live, but soft on date)

25. **Engage an external pentester**; remediate any High/Critical findings.
26. **Ship MFA** for staff Authorised Users (DPIA action A2).
27. **Document tested erasure-from-backup workflow** (DPIA action A4).
28. **Complete training**: KDPA awareness for every staff member.

---

## 10. Open questions for the Operator to decide

| # | Question | Owner | Due |
|---|---|---|---|
| Q1 | Confirm the final brand name / domain. `medifleet.co.ke`? Something else? | [PLACEHOLDER] | This week |
| Q2 | Pick email provider: **Zoho** (cheaper) or **Google Workspace** (richer)? | [PLACEHOLDER] | This week |
| Q3 | Pick monitoring: **Sentry** (recommended) vs alternative | [PLACEHOLDER] | This week |
| Q4 | Pick status page: **Instatus** vs **Better Stack** vs build-in-house | [PLACEHOLDER] | This month |
| Q5 | Which Kenyan advocate to brief on `docs/legal/`? | [PLACEHOLDER] | This month |
| Q6 | Which external pentest vendor for the annual test? | [PLACEHOLDER] | Pre-launch |
| Q7 | Marketing site approach: **prerender public routes** (Option A above) or **separate static site** (Option B)? | [PLACEHOLDER] | This quarter |

---

## 11. Sign-off

| Role | Name | Decision approved | Date |
|---|---|---|---|
| Director / CEO | [PLACEHOLDER] | ☐ | ___________ |
| DPO | [PLACEHOLDER] | ☐ | ___________ |
| Head of Engineering | [PLACEHOLDER] | ☐ | ___________ |

---

*Compiled 2026-05-15 from launch-readiness conversation. Update this
document as decisions are revisited.*
