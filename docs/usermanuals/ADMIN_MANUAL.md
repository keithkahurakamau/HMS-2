# MediFleet — Hospital Administrator User Manual

**Role**: ADMIN (Hospital Administrator)  
**System**: MediFleet Hospital Management System  
**Version**: 1.0 | **Date**: 2026-05-16 | **Review**: 2027-05-16

---

## Quick Start

| Item | Detail |
|---|---|
| **Login URL** | `/portal` → select hospital → `/login` |
| **Landing Page** | `/app/admin` |
| **Primary Permission** | `users:manage` |
| **Session** | 15-minute access token (auto-refreshed), 7-day refresh |

On first login, you will be prompted to change your temporary password. It must contain at least 8 characters including an uppercase letter, a lowercase letter, a digit, and a special character.

---

## Permissions Required

| Feature | Permission Codename |
|---|---|
| View and manage staff | `users:manage` |
| Manage roles and permissions | `roles:manage` |
| View audit logs | `users:manage` |
| Configure settings | `settings:manage` |
| Read settings | `settings:read` |
| Manage M-Pesa config | `settings:manage` |
| View analytics | `users:manage` |
| Manage departments | `departments:manage` |

---

## Section 1: Admin Dashboard Overview

Navigate to `/app/admin`. The dashboard has seven tabs across the top:

**Overview** — Four KPI tiles at the top:
- **Total Patients**: All registered patients in your hospital's database
- **Active Admissions**: Patients currently admitted to a ward bed
- **Daily Revenue**: Sum of payments recorded today (KES)
- **Low Stock Alerts**: Count of inventory items at or below their reorder threshold

Below the KPIs: recent activity feed showing the latest patient registrations, admissions, and payments.

---

## Section 2: Staff Management

### 2.1 Viewing All Staff

1. Navigate to `/app/admin` → click the **Staff Directory** tab.
2. The table shows: Full Name, Email, Role, Specialization, License Number, Status (Active/Inactive).
3. Use the search box to filter by name or email.

### 2.2 Creating a New Staff Account

1. Click **Add Staff Member**.
2. Fill in the form:
   - **Full Name** — required
   - **Email** — required; must be unique within your hospital
   - **Password** — temporary password (the new user must change it on first login)
   - **Role** — select from the dropdown (see Section 3 for built-in roles)
   - **Specialization** — for clinical staff (e.g., "Cardiology", "General Medicine")
   - **License Number** — professional licence number; leave blank if not applicable (stored as null, not empty string)
3. Click **Create Account**.
4. The system sets `must_change_password = True` on the new account automatically.
5. Communicate the temporary password to the staff member securely.

> **Warning:** Never send passwords via unencrypted email or public messaging.

### 2.3 Deactivating a Staff Account

1. Locate the staff member in the Staff Directory.
2. Click the action menu (⋮) → **Deactivate**.
3. Confirm the action.
4. The account is set to `is_active = False`. The user cannot log in.
5. All active sessions are not automatically revoked — if immediate lockout is needed, contact IT to revoke sessions from the database.

### 2.4 Reactivating a Staff Account

1. Filter the Staff Directory to show inactive users.
2. Locate the user → action menu → **Reactivate**.

### 2.5 Resetting a Locked Account

If a staff member is locked out after 5 failed login attempts:
- Wait 15 minutes for the lockout to expire automatically, **or**
- Contact your IT administrator to reset the lockout in the database.

---

## Section 3: Roles and Permissions (RBAC)

### 3.1 Built-In Roles and Default Landing Pages

| Role | Default Landing Page |
|---|---|
| Admin | /app/admin |
| Doctor | /app/clinical |
| Nurse | /app/wards |
| Pharmacist | /app/pharmacy |
| Laboratory Technician | /app/laboratory |
| Radiologist | /app/radiology |
| Billing Officer | /app/billing |
| Receptionist | /app/patients |
| Custom Role | /app/messages |

### 3.2 Permission Codenames

Permissions follow the pattern `resource:action`. Common codenames:

| Codename | What it allows |
|---|---|
| `patients:read` | View patient records and search |
| `patients:write` | Register and edit patients; manage queue |
| `clinical:write` | Create medical records (SOAP notes) |
| `clinical:read` | View clinical records |
| `laboratory:read` | View lab orders and results |
| `laboratory:manage` | Manage lab catalog; enter results |
| `radiology:read` | View radiology requests and results |
| `radiology:manage` | Complete radiology exams; manage catalog |
| `pharmacy:read` | View pharmacy inventory |
| `pharmacy:manage` | Dispense medications |
| `billing:manage` | Process payments and invoices |
| `users:manage` | Manage staff and admin settings |
| `roles:manage` | Create and modify roles |
| `settings:read` | View hospital settings |
| `settings:manage` | Update hospital settings and branding |
| `departments:manage` | Create and manage departments |
| `messaging:read` | View conversations |
| `messaging:write` | Send messages |
| `cheques:read` | View cheque records |
| `cheques:manage` | Process cheques |
| `referrals:manage` | Create and manage referrals |

### 3.3 How Effective Permissions Work

A staff member's effective permissions are calculated as:

```
Effective Permissions = (Role Permissions ∪ Explicit Grants) − Explicit Revokes
```

- **Role Permissions**: all permissions assigned to the user's role
- **Explicit Grants**: individual permissions granted directly to this user (even if their role doesn't have them)
- **Explicit Revokes**: individual permissions explicitly removed from this user (even if their role has them)

### 3.4 Creating a Custom Role

1. Navigate to **Admin** tab → **Roles & Permissions**.
2. Click **Create New Role**.
3. Enter a role name and description.
4. Select permissions from the permission matrix (check the boxes for each allowed codename).
5. Click **Save Role**.
6. Users assigned this custom role will land on `/app/messages` unless their most common module is configured.

### 3.5 Editing Role Permissions

1. In the **Roles & Permissions** tab, find the role.
2. Click **Edit Permissions**.
3. The permission matrix shows all available codenames.
4. Check or uncheck permissions.
5. Click **Save**.

> **Note:** Changes take effect immediately for new logins. Existing sessions may not reflect changes until the next token refresh (up to 15 minutes).

### 3.6 Overriding Individual User Permissions

To grant or revoke a specific permission for one user (without changing their role):

1. Go to **Staff Directory** → find the user → click **Manage Permissions**.
2. The **User Permissions Editor** shows:
   - Current role permissions (cannot be changed here — edit the role instead)
   - **Explicit Grants**: permissions added on top of the role
   - **Explicit Revokes**: permissions removed from the role
3. To add a grant: click **+ Add Grant** → select the permission codename.
4. To add a revoke: click **+ Add Revoke** → select the permission codename.
5. Click **Save Changes**.

---

## Section 4: Department Management

### 4.1 Creating a Department

1. Navigate to **Admin** → **Departments** tab.
2. Click **Create Department**.
3. Enter: Department Name (required), Description (optional).
4. Click **Create**.
5. A department messaging channel is automatically created. All department members will see this channel in `/app/messages`.

### 4.2 Managing Department Members

1. Find the department → click **Manage Members**.
2. Select staff members to add using the staff picker.
3. Click **Save Membership**.
4. Removed members lose access to the department messaging channel immediately.

---

## Section 5: M-Pesa Configuration

### 5.1 Setting Up M-Pesa

1. Navigate to **Admin** → **M-Pesa Config** tab.
2. Enter the following (obtain from the Safaricom Developer Portal):
   - **Paybill Number**: your M-Pesa Business Paybill
   - **Consumer Key**: Daraja API consumer key
   - **Consumer Secret**: Daraja API consumer secret
   - **Passkey**: provided by Safaricom for STK push
   - **Account Reference**: displayed on the customer's M-Pesa prompt (max 12 characters)
   - **Transaction Description**: short descriptor (e.g., "Hospital Payment")
3. Toggle **Active** to enable M-Pesa payments.
4. Click **Save Configuration**.

> **Security:** All credentials are encrypted using AES before being stored. They cannot be read back from the UI — only updated.

> **Sandbox vs Production:** Your IT administrator configures the environment (`MPESA_ENV`). Do not enter production credentials in a sandbox environment.

### 5.2 Viewing M-Pesa Transaction Logs

1. Navigate to **Admin** → **M-Pesa Logs** tab.
2. The table shows: date/time, phone number, amount (KES), status, receipt number (from Safaricom), result description.
3. Status values: Pending (awaiting callback), Success (paid), Failed (declined), Timeout (no response).

---

## Section 6: Lab and Service Pricing

### 6.1 Updating Lab Test Prices

1. Navigate to **Admin** → **Pricing** tab.
2. The table lists all active tests from the laboratory catalog.
3. Click the edit icon on any row.
4. Update the **Base Price (KES)**.
5. Click **Save**.

> **Note:** Price changes apply to new lab orders only. Existing invoices are not retroactively updated.

---

## Section 7: Audit Logs

### 7.1 Viewing the Audit Trail

1. Navigate to **Admin** → **Audit Logs** tab.
2. The table shows: Timestamp, User (who performed the action), Action (CREATE/UPDATE/DELETE), Entity Type (Patient/User/Invoice/etc.), Entity ID, IP Address.
3. Click any row to expand and view **Old Value** and **New Value** (JSON format showing exactly what changed).

### 7.2 Filtering Audit Logs

Use the filter bar to narrow by:
- **Date Range**: start date and end date
- **User**: filter by staff member
- **Action**: CREATE, UPDATE, or DELETE
- **Entity Type**: Patient, User, Invoice, MedicalRecord, etc.

### 7.3 What to Look For

| Situation | What to search |
|---|---|
| Investigating unauthorized data access | Action=UPDATE, Entity=Patient, specific user |
| Checking who registered a patient | Action=CREATE, Entity=Patient |
| Verifying payment was recorded | Action=CREATE, Entity=Payment |
| Auditing permission changes | Entity=UserPermissionOverride |

---

## Section 8: Hospital Settings

### 8.1 Viewing Settings

1. Navigate to `/app/settings`.
2. Settings are grouped by category (General, Clinical, Billing, Notifications, Privacy, etc.).
3. Each setting shows its label, current value, and data type.
4. Sensitive settings (marked with a lock icon) are displayed as masked dots.

### 8.2 Updating a Setting

1. Find the setting in the appropriate category.
2. Click **Edit** or click directly on the value field.
3. Enter the new value.
4. Click **Save**.

### 8.3 Adding a Custom Setting

1. Click **+ Add Setting** at the bottom of any category.
2. Fill in: Category, Key (machine-readable, e.g., `lab_report_footer`), Label (human-readable), Value, Data Type (string/number/boolean/json/secret), Description.
3. Click **Create**.

---

## Section 9: Branding

### 9.1 Updating Hospital Branding

1. Navigate to `/app/branding`.
2. **Logo Upload**: Click the upload area. Select a PNG, JPG, or SVG file. Recommended maximum: 600 KB. The system accepts up to 1.2 MB.
3. **Sign-In Background**: Upload a background image for the login page. Recommended maximum: 900 KB.
4. **Brand Primary Color**: Enter a hex color code (e.g., `#0891b2`). This affects the sidebar and accent elements.
5. **Brand Accent Color**: Secondary accent color.
6. **Print Template**: Select Modern, Classic, or Minimal for printed documents.
7. Click **Save Branding**.

> **Note:** Branding changes propagate to the login page immediately (the public branding endpoint is uncached).

---

## Section 10: Support Tickets

### 10.1 Submitting a Support Ticket to MediFleet

1. Navigate to `/app/support`.
2. Click **New Ticket**.
3. Fill in: Subject, Category (Billing/Bug/Feature/Account/Onboarding/Other), Priority (Low/Normal/High/Urgent), and a detailed description.
4. Click **Submit**.
5. Tickets go directly to the MediFleet platform team.

### 10.2 Tracking Ticket Status

Status progression: Open → In Progress → Waiting on Customer → Resolved → Closed.

Click any ticket to view the message thread and reply.

---

## Section 11: Common Errors for Admins

| Error | Cause | Fix |
|---|---|---|
| "Email already registered" when creating staff | Email used in another account | Use a different email or deactivate the old account |
| Staff cannot log in — "Account locked" | 5 failed login attempts | Wait 15 min or ask IT to clear the lockout |
| Module not appearing in staff's sidebar | Module not in subscription or user lacks permission | Check feature flags (Superadmin) or assign missing permission |
| "License number already exists" | Duplicate licence number entry | Check if another account has this number; use blank if not applicable |
| M-Pesa STK push not working | Config inactive or wrong credentials | Verify credentials in Admin → M-Pesa Config tab |
| Audit log shows unexpected DELETE | Possible unauthorized action | Review the entry; consider creating a support ticket if suspicious |
