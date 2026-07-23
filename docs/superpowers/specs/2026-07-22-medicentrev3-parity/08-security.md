# Module 8 — Security / Access Control (`Security`)

Sidebar sub-items (3): **User Roles · Privileges · System Users**.

Screenshots: `084539` (User Roles) · `084559` (Privileges) · `084614–084625` (System Users).

HMS-2 refs: `core/dependencies.py` (`RequirePermission`, `PERMISSION_CATALOG`, `ROLE_GRANTS`), `routes/users.py`, `routes/admin.py`, `models/user.py`, `models/audit.py`, `auth/auth.py`, `ModuleGuard`. Verified by grep: RBAC catalog+grants ✅, account lockout/block/disable ✅, **audit-log model ✅** (MedicentreV3 shows no audit UI here). `login-from-anywhere`/IP-restrict → **zero hits**.

**HMS-2 is at parity or ahead** on access control. The one meaningful gap is *admin-editable* roles/privileges (HMS-2's are code-defined).

---

## 8.1 User Roles

**Elements:** Name, Description, **Requires Cashier Shift** toggle, [+]. View (UserRoleID, Name, Description). Seeded roles: Administrator, Super Administrator, Medical Officer, Clinical Officer, Nurse, Health Records Officer/Receptionist, Patient Attendant, Pharmaceutical Technologist, Pharmacist, Laboratory Technologist, Admin/Accountant.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Role definitions mapped to clinical job titles | ✅ Have | `ROLE_GRANTS` (module-aligned RBAC) | — |
| **Admin-editable role CRUD** (create roles in UI, no deploy) | 🟡 Partial | HMS-2 roles are **code-defined**; add-role-via-UI absent | P2 |
| **Requires Cashier Shift** (role forces open till) | ❌ Missing | ties to Accounts §6.2 cashier shifts | P2 |

## 8.2 Privileges

**Elements:** select role → **Role Privileges** vs **All Privileges** dual-list w/ move arrows (‹ ›); "Add a privilege"; **Copy privileges From Role → To Role**; Excel/CSV/Print. Fine-grained privileges: Can Add/Delete/Edit/View Privilege, Can Assign/Remove Privileges To/From Role, Can View User Roles, Can View/Create/Update System User, Can Reset User Password, Can View Hospital Information, Can Create/Update/Delete Company Branch, Can Add Town, …

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Fine-grained permission catalog | ✅ Have | `PERMISSION_CATALOG` + `RequirePermission` | — |
| **Admin UI to assign/unassign privileges per role + copy between roles** | 🟡 Partial | assignment is code (`ROLE_GRANTS`), not a UI dual-list | P2 |

## 8.3 System Users

**Elements:** Surname, Othernames, Username, Password, Confirm Password, **Roles** (multi), **Branches** (multi; blank = all branches); flags **Is Employee · Is Disabled · Is Locked · Is Blocked · Has Limited Logon Attempts · Can Login From Anywhere**. View (No, Name, Username, Created On, Last Login, Logins count, Blocked?, Locked?, Disabled?). Actions: **Import Users**. View Disabled toggle.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| User CRUD + role assignment | ✅ Have | `users.py` | — |
| Lock / Block / Disable + limited logon attempts | ✅ Have | `user.py` + `auth.py` lockout (see locked-account fix) | — |
| Login analytics (last login, login count) | 🟡 Partial | audit exists; verify per-user login counter | P3 |
| **Branch-scoped user access** (multi-branch) | 🟡 Partial | `branch` in `security.py`/`auth.py`; verify per-user branch allowlist | P2 |
| **Can Login From Anywhere / IP restriction** | ❌ Missing | no IP allowlist | P3 |
| Import Users (bulk) | ❌ Missing | | P3 |
| **Audit log** | ✅ Have (ahead) | `models/audit.py` — MedicentreV3 shows none here | — |

---

## Security summary

Access control is a **HMS-2 strength** — RBAC, lockout, and audit already exist (audit puts HMS-2 *ahead*). Parity work is thin and mostly **P2/P3**:

- 🟡 **Admin-editable roles + per-role privilege assignment UI** (HMS-2 is code-defined) — **P2** (lets admins reshape access without a deploy)
- ❌ **"Requires Cashier Shift"** role flag — P2 (needs Accounts §6.2 cashier shifts first)
- 🟡 **Branch-scoped users** — P2 (multi-branch tenants)
- ❌ IP restriction, bulk user import — P3

No P1 here.
