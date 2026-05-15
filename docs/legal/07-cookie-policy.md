# Cookie & Tracking Policy

> **Status:** DRAFT v0.1
> **Issued by:** [PLACEHOLDER — Operator] for the Patient Portal, the public MediFleet website, and the Hospital-facing Platform.
> **Statutory basis:** KDPA s30 (consent for non-essential processing); ODPC guidance on cookies (2023).

This Cookie Policy explains what cookies and similar technologies we use, why
we use them, and how you can control them.

---

## 1. What is a cookie?

A cookie is a small text file placed on your device when you visit a
website. We also use related technologies (local storage, session storage)
to store small amounts of information in your browser. In this Policy,
"cookies" refers collectively to all of these.

---

## 2. Categories of cookies we use

We classify cookies into the categories below. **We only set
strictly-necessary cookies by default**; all other categories require your
consent.

### 2.1 Strictly necessary (always on)

| Name | Purpose | Lifetime |
|---|---|---|
| `session` (HttpOnly, Secure, SameSite=None) | Keeps you signed in to the Platform or Patient Portal. Without it, every page load would require a fresh login. | Session, refreshed via rotation |
| `refresh_token` (HttpOnly, Secure) | Renews your session token without requiring a fresh password. | Up to 30 days |
| `csrf_token` (Secure) | Protects against cross-site request forgery. Required for state-changing requests. | Session |
| `hms_tenant_id` (localStorage, not a cookie) | Stores the Hospital you have selected so the Platform sends the correct `X-Tenant-ID` header. | Until you sign out or change Hospital |

These are required for the Platform to function. They do not require
consent under KDPA / ODPC guidance because they are essential to provide
the service you have requested.

### 2.2 Functional (consent-based)

| Name | Purpose | Lifetime |
|---|---|---|
| `ui_prefs` | Remembers your interface preferences (sidebar collapsed, table density, dark mode where supported). | 12 months |
| `i18n_lang` | Remembers your preferred language (English / Swahili). | 12 months |

These improve usability but are not essential. You can turn them off
without losing core functionality.

### 2.3 Analytics (consent-based; may not yet be in use)

If we enable analytics, we will list the specific tool and cookies here
(e.g., a privacy-respecting product analytics tool that is configured to
honour KDPA principles — no individual profiling, no cross-site tracking).
The current default is **analytics is not enabled**. Before enabling we
will:

- Update this Policy.
- Add a consent banner to the public website and the patient portal.
- Disclose the tool, the categories of data, the retention period, and the
  sub-processor (if any) in **Document 15**.

### 2.4 Marketing / advertising

We **do not** set marketing or advertising cookies. We do not run
behavioural-advertising integrations.

---

## 3. Cookies set by sub-processors

Some sub-processors set their own cookies on our pages:

| Sub-processor | Cookie | Purpose |
|---|---|---|
| Vercel (edge delivery) | None on cookie path; uses HTTP-level routing | Performance |
| Cloudflare / Render | Operational cookies on the API domain | Load balancing, security |

We document any changes in **Document 15 (Sub-processor Register)**.

---

## 4. How to control cookies

| Where | How |
|---|---|
| Patient Portal | *Settings → Privacy* — toggle functional / analytics consent. |
| Public website | Cookie consent banner at first visit (once enabled). |
| Your browser | Browsers let you block or delete cookies. Doing so for strictly-necessary cookies will sign you out and you may need to sign in again. |

If you sign out, your session cookies are cleared server-side
(JWT revocation list) within minutes. The token rotation pattern is
described in `backend/app/auth/auth.py`.

---

## 5. Mobile apps

If we publish a mobile app, it may use platform-equivalent storage
(Keychain on iOS, EncryptedSharedPreferences on Android) for the same
purposes as the strictly-necessary cookies. The same retention applies.

---

## 6. Children

The portal is intended for users **18 years and older**. We do not
knowingly set non-essential cookies on devices used by children under 18.

---

## 7. Changes

We update this Policy when we change cookies or related technologies. The
version and effective date are at the top. Material changes are surfaced
via the consent banner on your next visit.

---

## 8. Contact

For questions about cookies or to exercise your rights:

- DPO email: **dpo@[PLACEHOLDER — domain]**
- ODPC: https://www.odpc.go.ke

---

*Version 0.1 — Effective Date: [PLACEHOLDER].*
