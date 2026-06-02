# Inbound Support Email — Design Spec

**Status:** Proposed (design only — not yet implemented)
**Goal:** Let clients email `support@medifleet.app` and have those messages flow
into the existing platform **Support Inbox** (`SupportTicket` / `SupportMessage`
in the master DB), visible to the superadmin team — with replies threaded back
into the same ticket.

This complements the outbound email system (PR #99). Outbound already sets
`Reply-To: support@medifleet.app`, so a client hitting "reply" on a system
email is the primary inbound path we must handle.

---

## 1. Why this isn't trivial

The current `SupportTicket` model assumes the submitter is an **authenticated
tenant staff member**:

- `tenant_id` / `tenant_name` are **NOT NULL** and come from the logged-in user.
- `submitter_user_id` is a tenant-DB user id.
- `SupportMessage.author_kind` is only `staff | platform`.

An inbound email can come from **anyone** — a prospect with no tenant, a patient,
or a staff member emailing from a personal address. We can't assume a tenant or a
known user. The design must handle "unknown sender" gracefully.

---

## 2. Transport — how email reaches us

Use **Resend Inbound** (same vendor as outbound; one account, one dashboard).
Alternatives with identical shape: Mailgun Routes, SendGrid Inbound Parse,
AWS SES + SNS.

Setup (ops, one-time):
1. Point MX records for the receiving domain at Resend. Recommended: a dedicated
   subdomain `support.medifleet.app` (or `inbound.medifleet.app`) so inbound MX
   is isolated from the outbound sending domain's records.
2. Configure an **inbound route / webhook** in Resend that POSTs each received
   email (parsed JSON) to our endpoint below.
3. Store the provider's **webhook signing secret** in env.

```
Client ──email──▶ support@medifleet.app
                     │ (MX → Resend Inbound)
                     ▼
              Resend parses MIME
                     │ HTTPS POST (signed)
                     ▼
   POST /api/public/support/inbound   ◀── our new endpoint
                     │ verify signature → parse → thread
                     ▼
        SupportTicket / SupportMessage (master DB)
                     │
                     ▼
        Superadmin Support Inbox (existing UI)
                     │ reply (existing admin_reply)
                     ▼
        Outbound email back to the client (PR #99 EmailService)
```

---

## 3. Webhook endpoint

```
POST /api/public/support/inbound
```

- **CSRF-exempt** — called by Resend's servers, not a browser. Add to
  `_CSRF_EXEMPT_PATHS` in `app/main.py` (same pattern as the Pay Hero callback).
- **Signature verification (mandatory).** Verify the provider's HMAC signature
  header against `SUPPORT_INBOUND_SIGNING_SECRET`. Reject with 401 on mismatch.
  Optionally pin to the provider's published IP ranges (mirror
  `PAYHERO_WEBHOOK_CIDRS`).
- **Idempotent.** Providers retry. Dedupe on the email `Message-ID` (store it;
  ignore if already seen). Return 200 quickly even on duplicates so the provider
  stops retrying.
- **Fast + safe.** Validate size, strip/sanitize HTML before persisting, cap
  attachments (see §6).

### Expected payload (provider-normalized)
```
from:        "Jane Client <jane@example.com>"
to:          ["support@medifleet.app"]   # may include support+<ref>@…
subject:     "Re: [#MF-000123] Cannot log in"
text:        "...plaintext body..."
html:        "...optional html body..."
message_id:  "<abc@mail.example.com>"
in_reply_to: "<our-outbound-id@medifleet.app>"   # for threading
references:  ["<...>", ...]
spam_score:  0.1
attachments: [{filename, content_type, size, url|content}]
```

---

## 4. Threading — new ticket vs. reply

Resolve in this order; first match wins:

1. **Plus-addressed recipient** — outbound emails use a per-ticket reply address
   `support+ticket-<id>@medifleet.app`. If the inbound `to` contains
   `support+ticket-123@…`, it's a reply to ticket 123. (Most reliable; survives
   subject edits.)
2. **Subject token** — outbound subjects carry `[#MF-000123]`. Parse it as a
   fallback when plus-addressing is stripped by the client.
3. **`In-Reply-To` / `References`** — match against `external_message_id`s we
   stored on prior outbound `SupportMessage`s.
4. **No match → new ticket.**

- **Reply** → append a `SupportMessage(author_kind="customer")`; if the ticket
  was `Waiting on Customer` flip it back to `Open`/`In Progress` (mirrors the
  existing staff-reply status logic); reject/append-and-reopen if terminal.
- **New** → create a `SupportTicket` (see §5 for the tenant question).

---

## 5. Schema changes (Alembic migration)

Minimal, additive:

**`support_tickets`**
- `tenant_id` → make **nullable** (inbound from non-tenant senders). Keep
  `tenant_name` nullable too. Add `origin` (`app | email`, default `app`).
- Optional: `external_thread_ref` (the `support+ticket-<id>` token is derived
  from `ticket_id`, so this may be unnecessary).

**`support_messages`**
- Widen `author_kind` to allow **`customer`** (currently `staff | platform`).
  No DB enum is used today (plain `String(20)`), so this is a code/validation
  change only.
- `external_message_id` (`String`, nullable, indexed, **unique**) — for
  dedupe + `In-Reply-To` threading.
- `source` (`app | email`, default `app`).
- Optional `from_email` / `from_name` for inbound where there's no `author_id`.

**Tenant attribution for inbound:**
- Try to match `from` email to a known tenant by maintaining a lightweight
  `email → tenant_id` lookup, OR leave `tenant_id = NULL` and surface these as
  an **"Unassigned"** bucket in the superadmin inbox for manual triage/assignment
  (assignment endpoint already exists: `admin_assign`).
- Recommended v1: **NULL + Unassigned bucket.** Cheap, no cross-tenant scans,
  and the superadmin already triages tickets.

---

## 6. Security & abuse

- **Signature verification** is non-negotiable (anyone could POST otherwise).
- **HTML sanitization** before storing/rendering the body (defense vs. stored
  XSS in the superadmin UI). Prefer persisting the plaintext part; sanitize HTML
  if shown.
- **Attachments**: v1 = drop (store filenames/metadata only) or push to blob
  storage with size/type limits; never execute or inline.
- **Spam**: honor provider `spam_score`; route high scores to a Spam status or
  drop. Rate-limit the endpoint.
- **PII**: inbound bodies may contain patient info — same encryption/redaction
  posture as the rest of the support system (master DB).

---

## 7. Auto-acknowledgement (nice-to-have)

On a successful new ticket, send the client an acknowledgement via the existing
`EmailService`: *"We received your message — ticket #MF-000123."* This closes the
loop and is readable on any device. Suppress for replies to avoid loops, and
never auto-reply to auto-responders (`Auto-Submitted` header / `no-reply` senders).

---

## 8. New config (env)

```
SUPPORT_INBOUND_ENABLED=false
SUPPORT_INBOUND_ADDRESS=support@medifleet.app
SUPPORT_INBOUND_SIGNING_SECRET=        # from Resend inbound webhook
SUPPORT_INBOUND_CIDRS=                 # optional provider IP allow-list
```

Outbound (PR #99) gains a per-ticket Reply-To at send time:
`support+ticket-<id>@medifleet.app` (overrides the static `EMAIL_REPLY_TO` when
sending ticket correspondence).

---

## 9. Phased implementation plan

1. **Migration** — nullable `tenant_id`, new `support_messages` columns, widen
   `author_kind`. (1 Alembic revision.)
2. **Inbound service** — `app/services/support_inbound.py`: signature verify,
   parse, dedupe, thread-resolve, persist. Pure + unit-testable (mirror the
   email unit tests: feed sample payloads, assert ticket/message rows).
3. **Endpoint** — `POST /api/public/support/inbound` + CSRF exemption + rate
   limit.
4. **Outbound threading** — per-ticket Reply-To + `[#MF-000123]` subject token;
   store `external_message_id` on platform replies.
5. **Superadmin UI** — show `origin=email`, `author_kind=customer`, and the
   "Unassigned" bucket; allow assigning a tenant.
6. **Auto-ack** (optional).
7. **Tests** — unit tests for parse/thread/dedupe; one integration test posting a
   signed sample payload to the endpoint.

---

## 10. Open questions for product

- Do inbound senders who aren't tenants ever need to *see* their ticket status,
  or is email-only correspondence enough? (Affects whether we build a public
  ticket-view link.)
- Should patient-origin emails be allowed here at all, or is support strictly
  B2B (hospitals ↔ platform)? Impacts PII handling.
- Attachment policy — drop vs. store vs. blob.
