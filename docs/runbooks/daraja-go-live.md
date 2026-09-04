# Daraja go-live runbook

Nothing in this migration can be verified against production M-Pesa before merge,
because neither MediFleet nor any hospital holds production credentials. Every flow
is proven against sandbox and mocked responses. **The first real transaction on
either rail is a human with a handset.** This is that procedure.

Work through it in order. Steps 1 and 2 are prerequisites: nothing else works
without them.

---

## 1. Safaricom certificates (blocks refunds entirely)

Download both certificates from the Daraja portal while logged in, and commit them:

```
backend/app/vendor/safaricom/sandbox.cer
backend/app/vendor/safaricom/production.cer
```

They are public certificates containing a public key only, so committing them is
expected and safe.

**Why this blocks:** B2C refunds RSA-encrypt the initiator password with these
certificates to build `SecurityCredential`. Without them, two tests skip and no
refund can be sent. The certificates are generated per call rather than stored, so
a Safaricom certificate rotation is a redeploy rather than a support ticket to
every hospital.

**Verify:** `cd backend && REDIS_URL="" ./venv/bin/python -m pytest tests/daraja -q`
The two skips become passes.

## 2. Credentials

Per hospital, in that hospital's M-Pesa settings page:
consumer key, consumer secret, passkey, shortcode, shortcode type, environment.
For refunds and for C2B verification: initiator name and initiator password.

For MediFleet's own subscription rail, in the superadmin console.

**Never commit credentials.** `backend/.env` is gitignored; production values go in
the Render dashboard.

**The coupling that catches people:** Transaction Status requires the initiator
credentials. A till configured for C2B *without* them can never verify a payment,
so every walk-in payment stays unsettled forever. The settings page shows this as a
blocker, and the transaction's `result_desc` says so in plain words. Set initiator
credentials even if you do not intend to issue refunds.

---

## 3. Register the C2B URLs

Use the register action on the M-Pesa settings page. Each till registers its own
URLs against its own shortcode, so a hospital with per-department tills registers
each one.

Safaricom enables the validation URL only on request. Until they do, only
confirmation fires. The code is correct in both configurations.

**Some account types require portal-side registration instead.** For those, the
settings page shows the callback URLs. The token inside them is revealed once, at
rotation; thereafter it is masked and identified by its rotation timestamp.

## 4. Confirm the callback URL is publicly reachable

From outside your network:

```
curl -i -X POST https://<your-domain>/api/payments/mpesa/stk/callback/<hint>/<token>
```

Expect HTTP 200. A 502 or a timeout means Safaricom cannot reach you either, and
every callback will be lost silently.

**This is the single most common go-live failure.** Check it before blaming
anything else.

---

## 5. The live smoke test

Do these in order, with a real handset and a real KES 1.

1. **STK push.** Raise a KES 1 invoice, push to your own phone, enter the PIN.
   Confirm the receipt lands, the invoice settles, and the M-Pesa ledger shows it.
2. **Pay a partially-paid invoice by M-Pesa.** Part-pay in cash first, then settle
   the remainder. This path had a defect that made it fail on exactly this shape,
   so it is worth exercising deliberately.
3. **C2B.** Pay the till directly from a handset, without a prompt. Confirm the
   payment records as `Unverified`, then settles once Safaricom's Transaction
   Status result corroborates it. **Settlement is deliberately deferred by a few
   seconds:** that is the corroboration working, not a fault.
4. **Refund.** Refund the KES 1 back. Confirm it reaches `Completed` and that the
   invoice's `amount_paid` decreases.
5. **A dropped callback.** Kill the callback (block it at your edge, or use a
   shortcode whose URL is briefly wrong) and confirm reconciliation resolves the
   transaction within a cycle by asking Safaricom, rather than guessing.

## 6. Confirm the crons

Two scheduled services, both with `DATABASE_URL` set to `sync: false` in
`render.yaml`, meaning the blueprint does **not** populate them:

- `medifleet-billing`, daily
- the reconciliation cron, every 15 minutes

**If either variable is unset or points at the wrong database, the job finds
nothing, reports zero, and exits 0.** That is success-looking silence, not an
error. Set both in the Render dashboard and confirm with one manual run.

---

## Rollback

Set `is_active = false` on the hospital's M-Pesa config. That stops new pushes
without touching any data. Callbacks for pushes already in flight still settle.

There is no need to redeploy, and no need to touch the database.

---

## Known limitations, stated plainly

**The "still processing" error code is unverified.** Daraja's STK Query is
documented as returning HTTP 500 with `errorCode 500.001.1001` while a push is in
flight, and reconciliation treats exactly that code as "no verdict yet" rather
than a failure. If your sandbox returns a different shape, the reconciliation cron
will report failures on ordinary in-flight traffic. **Check this on your first
sandbox run.** It is one constant to change.

**Rotation invalidates registered URLs.** Rotating a callback token kills every URL
already registered with Safaricom. The settings page offers to re-register in the
same action, and flags a registration older than the last rotation as broken. If
re-registration fails, the token has still rotated: re-register before taking
payments.

**One-shot token reveal.** The plaintext token appears once, in the rotation
response. Anything that logs full response bodies (an API gateway, a debug proxy)
would capture it. Do not enable response-body logging on that path.

**Quarantined transactions need a human.** A callback claiming an amount different
from the one requested, a C2B payment Safaricom will not corroborate, or a
settlement that would exceed the invoice balance are all quarantined rather than
settled or discarded. They appear in the M-Pesa ledger and notify billing staff.
Money has arrived in every one of those cases; the record simply is not safe to
write automatically.

**Reconciliation stops asking after 24 hours** and surfaces the row instead. A late
verdict after that point is not picked up automatically, by design: at that age it
needs a human, not another query.

**Sandbox in production.** The environment is per till, so a hospital can sit in
sandbox while its Go-Live is pending. The operator console warns when a production
deployment holds an active sandbox till. Do not ignore it.
