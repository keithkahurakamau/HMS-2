# MediFleet Hospital Management System
## User Manuals Index

**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Audience**: All Staff and Patients

---

## How to Find Your Manual

Locate your role in the table below, then open the corresponding manual file. Each manual is a standalone document — you do not need to read any other file to use your section of the system.

If you are unsure of your role, ask your department administrator or check the landing page you see immediately after logging in.

---

## Role-to-Manual Directory

| Role | Manual File | Landing Page After Login | Key Modules |
|------|-------------|--------------------------|-------------|
| Receptionist | `RECEPTIONIST_MANUAL.md` | `/app/patients` | Patient Registry, Queue, Appointments |
| Doctor | `DOCTOR_MANUAL.md` | `/app/clinical` | Encounters, SOAP Notes, Lab/Radiology Orders, Referrals |
| Nurse | `NURSE_MANUAL.md` | `/app/wards` | Ward Board, Admissions, Discharge, Consumables |
| Pharmacist | `PHARMACIST_MANUAL.md` | `/app/pharmacy` | Inventory, Prescriptions, OTC Sales, Stock Transfers |
| Laboratory Technician | `LAB_TECH_MANUAL.md` | `/app/laboratory` | Worklist, Specimen Collection, Results Entry, Catalog |
| Radiologist | `RADIOLOGIST_MANUAL.md` | `/app/radiology` | Worklist, Exam Completion, Radiology Catalog |
| Billing Officer | `BILLING_OFFICER_MANUAL.md` | `/app/billing` | Invoices, Cash/Card, M-Pesa, Cheques |
| Admin | `ADMIN_MANUAL.md` | `/app/admin` | Staff, RBAC, Departments, Settings, Branding, Audit |
| Patient | `PATIENT_PORTAL_MANUAL.md` | `/patient` | Appointments, Invoices, Medical History (read-only) |
| Superadmin | `SUPERADMIN_MANUAL.md` | `/superadmin/dashboard` | Tenants, Modules, Platform Billing, Support |

---

## System URL Quick Reference

| Purpose | URL |
|---------|-----|
| Hospital selection (multi-site) | `/portal` |
| Staff login | `/login` |
| Patient self-service portal | `/patient` |
| Superadmin console | `/superadmin/login` |

---

## Authentication Quick Reference (All Staff Roles)

This section applies to every staff role (Receptionist through Admin). Patient portal authentication is different — see `PATIENT_PORTAL_MANUAL.md`.

### Logging In

1. Open a web browser and navigate to your hospital's `/login` URL.  
   If your organization has multiple sites, go to `/portal` first, select your hospital, then proceed to login.
2. Enter your **username** and **password**.
3. Click **Sign In**.
4. If this is your **first login**, the system will immediately prompt you to set a new password before you can proceed. You cannot skip this step.

### Password Requirements

Your password must meet **all** of the following:

- Minimum **8 characters**
- At least one **uppercase letter** (A–Z)
- At least one **lowercase letter** (a–z)
- At least one **digit** (0–9)
- At least one **special character** (e.g. `!@#$%^&*`)

### Session Tokens

- **Access token**: valid for **15 minutes**. The system silently refreshes it while you remain active.
- **Refresh token**: valid for **7 days**. If you close the browser for more than 7 days, you must log in again.
- Tokens are stored in secure **HttpOnly cookies**. You cannot read them from the browser console, and they are protected automatically against CSRF attacks.

### Account Lockout

After **5 consecutive failed login attempts**, your account is locked for **15 minutes**. You do not need to do anything — the lock lifts automatically after 15 minutes. If you need immediate access, contact your Admin.

### Logging Out

Click your username or avatar in the top-right corner and select **Log Out**. Always log out when leaving a shared workstation.

### Module Access Restriction (HTTP 402)

If you navigate to a module and see an **"Access Restricted"** or payment-related screen, that module has been disabled by your hospital's subscription plan. Contact your Admin or the platform support team.

---

## Permissions System Overview

MediFleet uses a role-based access control (RBAC) system. Permissions follow the format:

```
resource:action
```

Examples: `patients:read`, `clinical:write`, `billing:manage`

Your **effective permissions** are calculated as:

```
(role default permissions + explicit grants) − explicit revokes
```

An Admin can grant or revoke individual permissions on your account without changing your role. If you believe you are missing access you need, contact your Admin.

---

## Getting Help

- **In-system messages**: Use the Messaging module to contact colleagues or your department.
- **Support tickets**: Raise a ticket through the Help/Support section visible in your navigation bar.
- **Admin assistance**: For account issues (locked out, wrong role, missing permissions), contact your hospital Admin.
- **Platform issues**: Escalated issues go to the MediFleet platform support team via the superadmin console.

---

*MediFleet HMS — Confidential Internal Documentation*  
*Do not distribute outside authorized staff.*
