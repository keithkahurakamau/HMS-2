# MediFleet — Superadmin (Platform Team) User Manual

**Role**: SUPERADMIN (MediFleet Platform Team)  
**System**: MediFleet Superadmin Console  
**Version**: 1.0 | **Date**: 2026-05-16 | **Review**: 2027-05-16

---

## Quick Start

| Item | Detail |
|---|---|
| **Login URL** | `/superadmin/login` |
| **Landing Page** | `/superadmin/dashboard` |
| **Auth Method** | Email + password → Bearer token (stored in localStorage) |
| **Scope** | Platform-wide access to all tenants |

> **Note:** Superadmin authentication uses a Bearer token stored in `localStorage`, not the HttpOnly cookie used for hospital staff. This is intentional — superadmins operate from a dedicated console, not from within a hospital tenant.

---

## Section 1: Superadmin Console Overview

The Superadmin Console manages the entire MediFleet platform. From this console you can:

- **Provision** new hospital tenants (creates an isolated PostgreSQL database per hospital)
- **Manage** tenant feature flags and subscription limits
- **Monitor** platform-wide KPIs (tenant count, active users, MRR/ARR)
- **Respond** to support tickets from all hospitals
- **View** patients across all tenants
- **Manage** platform billing and subscriptions

The console is separate from the hospital staff interface at `/app`. Hospital staff cannot access the Superadmin Console.

---

## Section 2: Platform Dashboard

Navigate to `/superadmin/dashboard`. Key metrics:

| Metric | Description |
|---|---|
| Total Tenants | Number of active hospital tenants |
| Active Users | Total staff users across all tenants logged in within last 30 days |
| MRR / ARR | Monthly/annual recurring revenue (if billing integration configured) |
| Open Support Tickets | Platform-wide unresolved ticket count |
| Recent Tenant Activity | Latest new registrations, logins, and API activity |

---

## Section 3: Tenant Management

### 3.1 Viewing All Tenants

1. Navigate to `/superadmin/tenants`.
2. The table shows: Tenant Name, Domain, DB Name, Plan, Active Status, Created Date.
3. Click a tenant row to view full details.

### 3.2 Provisioning a New Hospital Tenant

Provisioning creates a fully isolated hospital environment with its own database, roles, and Admin account.

1. Click **Create New Hospital**.
2. Fill in the provisioning form:
   - **Hospital Name** — display name (e.g., "Nairobi General Hospital")
   - **Domain** — unique subdomain identifier (e.g., `nairobi-general`); must be unique across the platform
   - **Database Name** — PostgreSQL database name (e.g., `hms_nairobi_general`); must be unique; use lowercase, underscores only
   - **Admin Email** — email address for the hospital's first Admin user
   - **Admin Full Name** — full name of the hospital administrator
3. Click **Provision Hospital**.

**What happens during provisioning (automatically):**
1. A new row is inserted in the master `hms_master.tenants` table
2. A new PostgreSQL database is created: `CREATE DATABASE {db_name}`
3. The full schema is built (all tables created)
4. Built-in roles and permissions are seeded (Admin, Doctor, Nurse, Pharmacist, etc.)
5. Default inventory locations are created (Main Store, Pharmacy, Laboratory, Wards)
6. Default hospital settings are populated
7. An Admin user account is created with `must_change_password = True`
8. A random temporary password is generated and displayed **once**

> **Critical:** The temporary password is displayed only once and is never stored in plaintext. Copy it immediately and share it securely with the hospital administrator.

4. If provisioning fails after the database was created, the master `tenants` row is automatically deleted (best-effort cleanup). You can retry provisioning.

### 3.3 Activating and Deactivating Tenants

1. Find the tenant in the Tenants Manager.
2. Click the **Active** toggle to enable or disable the tenant.
3. When deactivated (`is_active = False`), the hospital no longer appears in the public hospital picker at `/portal`. Staff cannot log in.
4. Existing session tokens may still function until they expire (up to 15 minutes for access tokens, 7 days for refresh tokens). Contact IT if immediate lockout is required.

### 3.4 Editing Tenant Details

1. Click the tenant name → **Edit**.
2. You can update: Hospital Name, Domain, Plan Notes, Theme Color, Premium Status.
3. To update feature flags or plan limits, see Section 4.

---

## Section 4: Module Entitlements (Feature Flags)

### 4.1 How Feature Flags Work

Each tenant has a `feature_flags` JSON object that controls which modules are available. Example:

```json
{
  "clinical": true,
  "laboratory": true,
  "radiology": false,
  "pharmacy": true,
  "inventory": true,
  "wards": true,
  "billing": true,
  "cheques": false,
  "medical_history": true,
  "mpesa": true,
  "analytics": false,
  "patient_portal": true,
  "branding": true,
  "referrals": true,
  "privacy": true
}
```

**Always-on modules** (cannot be disabled regardless of feature flags):
`patients`, `appointments`, `dashboard`, `settings`, `support`, `messaging`, `notifications`, `users`, `auth`

### 4.2 Enabling or Disabling a Module

1. Navigate to `/superadmin/tenants` → find the tenant → click **Edit**.
2. Go to the **Feature Flags** section.
3. Toggle the desired module on or off.
4. Click **Save**.

> **Cache:** Feature flag changes are cached for **60 seconds**. The change will propagate to hospital staff within 60 seconds of saving. If a hospital reports the change hasn't taken effect, wait 60 seconds.

### 4.3 Plan Limits

The `plan_limits` field sets operational caps. Common limits:

| Limit Key | Description |
|---|---|
| `max_users` | Maximum number of staff user accounts |
| `max_patients` | Maximum registered patients |
| `storage_gb` | Data storage allocation |

Update these in the tenant's **Plan Limits** section of the Edit form.

---

## Section 5: Branding Per Tenant

1. Navigate to the tenant → **Edit** → **Branding** tab.
2. **Logo**: Upload or paste a base64 data URL. Maximum size: 1.2 MB after base64 encoding (approximately 900 KB original file). Supported formats: PNG, JPG, SVG.
3. **Background Image**: Background for the hospital's login page. Same size limits.
4. **Brand Primary Color**: Main brand color in hex format (e.g., `#0891b2`).
5. **Brand Accent Color**: Secondary accent color in hex format.
6. **Print Template Style**: Select `modern`, `classic`, or `minimal` for printed reports and documents.
7. **Print Header/Footer Text**: Custom text for the top and bottom of printed documents.
8. Click **Save Branding**.

> **Note:** Branding is stored in the master `tenants` table, not in the individual tenant's database. The hospital's login page fetches branding from a public endpoint that does not require authentication.

---

## Section 6: Cross-Tenant Patient Search

1. Navigate to `/superadmin/patients`.
2. Enter a search term (patient name, OP number, or ID number).
3. Select the **Tenant** from the dropdown to scope the search to a specific hospital, or leave blank to search all tenants.
4. Results show: Patient Name, OP Number, Tenant (hospital name), Registration Date.
5. Click a result to view the full patient record for that tenant.

> **Important:** Cross-tenant patient access is logged in the master audit trail. Use this feature only for legitimate platform support purposes.

---

## Section 7: Support Inbox

### 7.1 Viewing All Support Tickets

1. Navigate to `/superadmin/support`.
2. All tickets from all hospitals appear in a unified inbox.
3. Filter by: Status (Open/In Progress/Waiting on Customer/Resolved/Closed), Priority, Category, Tenant.

### 7.2 Responding to a Ticket

1. Click a ticket to open the thread.
2. Read the full conversation history.
3. Type your reply in the message box.
4. Click **Send Reply**. Your reply is tagged as being from the "Platform Team".

### 7.3 Updating Ticket Status

1. In the ticket detail view, use the **Status** dropdown to change status.
2. Common transitions:
   - Open → In Progress (you are actively working on it)
   - In Progress → Waiting on Customer (you need more information from the hospital)
   - Waiting on Customer → In Progress (customer replied)
   - In Progress → Resolved (issue fixed)
   - Resolved → Closed (after confirmation period)

### 7.4 Ticket Priorities

| Priority | Response Target |
|---|---|
| Urgent | Within 2 hours |
| High | Within 8 hours |
| Normal | Within 24 hours |
| Low | Within 72 hours |

---

## Section 8: Platform Billing and Subscriptions

1. Navigate to `/superadmin/billing`.
2. The billing dashboard shows: active subscriptions per tenant, MRR breakdown, recent invoice generation.
3. Manage subscription tiers, renewal dates, and payment status per tenant.
4. Generate invoices for hospital billing cycles.

---

## Section 9: Platform Settings

1. Navigate to `/superadmin/settings`.
2. Platform-level configuration affecting all tenants (e.g., default module catalogue, global rate limit overrides, SMTP configuration for password reset emails).

---

## Section 10: Security Responsibilities

As a Superadmin, you have the highest level of access in the platform. Follow these guidelines:

1. **Never share your Superadmin credentials.** Each Superadmin should have their own account.
2. **Use the Superadmin Console only from trusted, secure devices.** Superadmin Bearer tokens are stored in `localStorage` — do not use on shared or public computers.
3. **Review cross-tenant access.** Use cross-tenant patient search only when directly supporting a hospital's IT request.
4. **Treat temporary passwords as secrets.** After provisioning a tenant, communicate the temporary password only through secure channels.
5. **Monitor for anomalies.** Unusual patterns in tenant activity or support tickets may indicate a security incident.
6. **Follow the breach response protocol.** If you discover a data breach in any tenant, follow the KDPA S.43 breach notification procedure (72-hour ODPC notification requirement).

---

## Section 11: Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| New tenant not appearing in `/portal` picker | Tenant `is_active = False` | Activate the tenant in Tenants Manager |
| Module change not taking effect | 60-second entitlement cache | Wait 60 seconds or restart the backend |
| Hospital admin cannot log in after provisioning | Temporary password not communicated | Re-provision or IT can reset the password in the DB |
| Provisioning failed partway through | DB creation succeeded but schema failed | The system deletes the master row automatically; retry provisioning |
| Superadmin Bearer token expires | Tokens are not auto-refreshed in the same way as staff tokens | Log out and log in again to get a fresh token |
| Cannot access `/superadmin/*` — redirected to `/portal` | Navigating without a valid Superadmin token | Go to `/superadmin/login` first |
