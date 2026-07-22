# Module 10 — Communication (`Communication`)

Sidebar sub-items: **Sms · Sms Templates**.

Screenshots: `085847` (Bulk SMS) · `085859` (SMS Templates).

HMS-2 refs: `messaging.py` + `Messages.jsx` (internal staff messaging), `notification.py` + `NotificationBell`, email (Resend-via-SMTP, `EMAIL_ENABLED`), `support_inbound.py` (support→tickets). Verified: **no** SMS gateway / bulk-SMS / SMS-template; `sms` hits are payment-OTP + marketing copy only.

**Split verdict:** HMS-2 has *internal* comms (staff messaging + email + support) but not *patient-facing SMS*.

---

## 10.1 Sms — Bulk SMS

**Elements:** **SMS Gateway** dropdown · **Message** textarea · **Message Parameters** (drag-drop merge fields: Patient Name, OP #, Residence, Employee Name, Employee Staff No, Facility Name) · **[Send]**. **Selected Contacts for Messaging** ↔ **All Contacts – Patients** dual-list (move ‹ ›), CSV/Excel/Print, Search.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| SMS gateway integration (Africa's Talking/etc.) | ❌ Missing | email only; no SMS transport | P2 |
| Bulk SMS to patients/staff w/ merge fields | ❌ Missing | patient-facing outreach absent | P2 |

## 10.2 Sms Templates — scheduled/triggered SMS

**Elements:** Title · Message · **Reminder** (Appointments / …) · **Within (Days)** · **Execute** (Manual / Auto) · Message Parameters (+ Current Timestamp / Current Date). View (No, Title, Reminder, Execute, Created By, Triggered On, Status).

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Templated SMS + auto-trigger (e.g. appointment reminder N days before) | ❌ Missing | **reduces no-shows → revenue-adjacent** | P2 |
| Internal staff messaging | ✅ Have | `messaging.py` + `Messages.jsx` | — |
| Email notifications | ✅ Have (ahead) | Resend/SMTP; MedicentreV3 emphasis is SMS | — |

---

## Communication summary

HMS-2 leads on **internal** comms + email; MedicentreV3 leads on **patient SMS**:

- ❌ **SMS gateway + bulk SMS + templated/scheduled SMS reminders** — **P2** (appointment/results reminders reduce no-shows and collections friction; email is a partial substitute)
- ✅ Internal messaging + email + support tickets already at/above parity.

Cheapest high-value slice: add an **SMS transport + appointment-reminder template** on top of HMS-2's existing appointment + notification plumbing.
