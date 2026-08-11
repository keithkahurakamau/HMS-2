# Module 11 — Diary (`Diary`)

Single screen (no sub-items).

Screenshots: `085912` (My-Diary).

HMS-2 refs: `Calendar.jsx` (patient **appointment** calendar), `appointments.py`. Verified: `diary` hits are onboarding copy only — no personal staff diary.

---

## 11.1 My-Diary

**Elements:** personal **calendar** (month / week / day views, prev/next/today nav) · **[Switch Employee]** (view another staff member's diary). Per-user diary/notes/reminders distinct from patient appointments.

| Capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Personal staff diary/calendar (own entries, not patient bookings) | ❌ Missing | `Calendar.jsx` is patient appointments only | P3 |
| Switch-employee (view another user's diary; supervisor) | ❌ Missing | | P3 |

---

## Diary summary

A **staff-productivity calendar** separate from patient appointments. HMS-2 has a patient appointment calendar but no personal diary. **P3** — neither clinical nor revenue; a nice-to-have that could reuse `Calendar.jsx` for a personal-events variant.
