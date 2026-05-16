# MediFleet Hospital Management System
## Billing Officer User Manual

**Role**: Billing Officer  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/billing`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Billing Queue — Invoice Status Meanings
4. Cash and Card Payments
5. M-Pesa STK Push Payments
6. Cheque Management
7. Invoice Printing
8. Common Errors
9. Keyboard Tips

---

## 1. Quick Start

As a Billing Officer, your primary workspace is the **Billing Module** at `/app/billing`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/billing`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Open the Billing Queue to review all outstanding invoices.
2. Process payments as patients present at the billing desk — cash, card, M-Pesa, or cheque.
3. Handle M-Pesa STK pushes and monitor for callback confirmations.
4. Manage cheques through their lifecycle (deposit, clearance, or bounce).
5. Print invoices and receipts as required.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `billing:read` | View invoices, payment history, and the billing queue |
| `billing:write` | Record payments, process M-Pesa, manage cheques |
| `billing:manage` | Full billing management including invoice adjustment and cancellation |
| `patients:read` | View patient demographic data linked to invoices |
| `messaging:write` | Communicate with clinical staff about billing queries |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Billing Queue — Invoice Status Meanings

The **Billing Queue** displays all invoices in the system, filterable by status and date range.

### Invoice Status Reference

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| Pending | Invoice created; no payment received yet | Collect full payment |
| Partially Paid | Invoice has received one or more payments, but the balance is still outstanding | Collect remaining balance |
| Pending M-Pesa | An M-Pesa STK push has been sent to the patient and is awaiting confirmation from Safaricom | Wait for callback; do not process another payment until resolved |
| Paid | Invoice is fully settled | No further payment action needed |
| Cancelled | Invoice was voided | No payment action; see Admin for any adjustments |

### Reading the Queue

Each invoice entry in the queue shows:

| Column | Description |
|--------|-------------|
| Invoice Number | Unique identifier for the invoice |
| Patient Name | Patient associated with the invoice |
| OP Number | Patient's unique identifier |
| Invoice Date | When the invoice was created |
| Total Amount | Full invoice amount |
| Amount Paid | Total received so far |
| Balance Due | Remaining amount owed |
| Status | Current invoice status (see table above) |
| Last Updated | Most recent change to the invoice |

### Procedure: Open an Invoice

1. Locate the invoice in the billing queue using the patient's name, OP Number, or invoice number.
2. Click the invoice row to open the full detail view.
3. Review the **line items** — these are auto-populated from:
   - Consultation fee (from the doctor's encounter)
   - Laboratory test fees
   - Radiology exam fees
   - Pharmacy/dispensed medications
   - Ward admission charges
   - Consumables used during care

---

## 4. Cash and Card Payments

### Understanding the Idempotency Key

When you submit a payment, the system automatically attaches an **idempotency key** — a unique identifier for that transaction. This prevents double-charging even if you accidentally click the Submit button more than once (e.g. due to a slow network). You do not manage this key yourself; the system handles it. This means you can safely click Submit once and trust the system — additional clicks will be ignored.

### Procedure: Record a Full Cash or Card Payment

1. Open the invoice (Section 3).
2. Verify the **balance due** with the patient and confirm the amount being paid.
3. Click **+ Record Payment**.
4. In the payment dialog, set the **Payment Method**:
   - **Cash**: for physical currency
   - **Card**: for debit/credit card transactions (processed through your card terminal)
5. Enter the **Amount Received**. For a full payment, this equals the balance due.
6. For **Cash**: enter the **amount tendered** by the patient. The system calculates and displays the change to be returned.
7. For **Card**: enter the **card authorization reference number** from your card terminal.
8. Enter any **notes** if needed (e.g. "Patient paid in USD — converted to KES at rate X").
9. Click **Submit Payment**.
10. The system records the payment and updates the invoice status:
    - If the full balance is paid: status changes to **Paid**.
    - If a partial amount is paid: status remains at (or changes to) **Partially Paid**.
11. A receipt is available immediately for printing (Section 7).

### Partial Payment Logic

A patient may pay part of their invoice today and the remainder at a later visit.

1. Follow steps 1–5 above.
2. Enter only the **amount the patient is paying now** (less than the full balance).
3. Click **Submit Payment**.
4. Invoice status changes to **Partially Paid**.
5. The balance due is updated to reflect the new remaining amount.
6. The next time the patient returns, open the same invoice — the remaining balance will be shown, and you can record another payment.

### Important: Do Not Create a New Invoice for Partial Payments

Always record additional payments on the **same invoice**. Do not create a new invoice for the outstanding balance.

---

## 5. M-Pesa STK Push Payments

M-Pesa is a mobile money payment method. The system sends a payment request directly to the patient's phone (STK push), and the patient approves it with their M-Pesa PIN. The transaction is confirmed by a Safaricom callback.

### How M-Pesa STK Push Works

1. You initiate the payment in MediFleet.
2. The system sends a push notification to the patient's phone through Safaricom's gateway.
3. The patient's phone displays a prompt asking them to enter their M-Pesa PIN.
4. The patient approves the transaction.
5. Safaricom sends a callback to MediFleet confirming success or failure.
6. The invoice is updated automatically based on the callback result.

### Phone Number Format

M-Pesa phone numbers are normalized to the format **2547XXXXXXXX** (12 digits starting with 254).

Examples of what the system accepts and normalizes:
- `0712345678` → normalized to `254712345678`
- `+254712345678` → normalized to `254712345678`
- `254712345678` → accepted as-is

You do not need to manually format the number — the system normalizes it automatically.

### Procedure: Initiate an M-Pesa STK Push

1. Open the invoice.
2. Click **Pay via M-Pesa**.
3. The M-Pesa payment dialog opens.
4. Confirm or enter the **patient's M-Pesa phone number**. The field pre-fills from the patient's registered primary phone if available.
   - Ask the patient to confirm their M-Pesa number if you are unsure.
   - Enter it in any standard format; the system normalizes it.
5. Confirm the **amount** to be charged. For full payment, this equals the balance due. For partial M-Pesa payment, enter the amount the patient has agreed to pay via M-Pesa.
6. Click **Send STK Push**.
7. The invoice status changes immediately to **Pending M-Pesa**.
8. Inform the patient: "You will receive a prompt on your phone — please enter your M-Pesa PIN to complete the payment."

### Monitoring the M-Pesa Callback

After sending the STK push:

1. The billing screen shows the invoice with status **Pending M-Pesa**.
2. The system polls for the Safaricom callback automatically — you do not need to do anything.
3. When the callback arrives:
   - **If successful**: Invoice status changes to **Paid** (or **Partially Paid** if it was a partial payment). A receipt is generated.
   - **If failed**: Invoice status returns to **Pending** (or reverts to **Partially Paid** if there was a prior partial payment). A failure reason is displayed.

### Procedure: Check M-Pesa Payment Status Manually

If the patient says they approved the payment but the status has not updated:

1. Open the invoice.
2. Click **Check Payment Status** (or **Refresh M-Pesa Status**).
3. The system queries Safaricom for the latest status.
4. If confirmed, the invoice updates automatically.
5. If still pending after several minutes, ask the patient to check their M-Pesa transaction history.

### Common M-Pesa Scenarios

| Scenario | Status After | What to Do |
|----------|-------------|------------|
| Patient approved and PIN entered | Paid / Partially Paid | Print receipt |
| Patient cancelled the prompt | Pending | Re-initiate or use alternative payment method |
| Patient's phone was off | Pending | Try again once phone is on; or use cash/card |
| STK push timed out (no action) | Pending | Re-initiate the push |
| Insufficient M-Pesa balance | Pending | Patient must top up M-Pesa; re-initiate or use alternative |
| Wrong PIN entered (M-Pesa locked) | Pending | Patient must resolve with Safaricom; use alternative payment |

### Important: Do Not Send Multiple STK Pushes at the Same Time

Only one M-Pesa payment can be active per invoice at a time. If the status is **Pending M-Pesa**, wait for the callback before attempting another payment method. Sending a second STK push before the first is resolved can cause reconciliation issues.

---

## 6. Cheque Management

Cheques are accepted as a payment method but require additional processing steps through a lifecycle before the invoice is considered settled.

### Cheque Lifecycle

```
Received → Deposited → Cleared (invoice marked Paid)
                    → Bounced (invoice reverts to Pending)
                    → Cancelled
```

### Procedure: Register (Receive) a Cheque

When a patient presents a cheque at the billing desk:

1. Open the patient's invoice.
2. Click **+ Record Payment** and select **Cheque** as the payment method.
3. Complete the cheque registration fields:

   | Field | Description |
   |-------|-------------|
   | Cheque Number | As printed on the cheque |
   | Drawer Name | Name of the person or organization who wrote the cheque |
   | Drawer Type | Individual or Organization |
   | Bank | Name of the bank on which the cheque is drawn |
   | Amount | The amount written on the cheque |
   | Cheque Date | The date printed on the cheque (not today's date unless they match) |

4. Click **Save Cheque**. The cheque is registered with status **Received**.
5. The invoice status does **not** change to Paid at this point. The invoice remains **Pending** or **Partially Paid** — the balance is only cleared when the cheque clears at the bank.

### Procedure: Mark a Cheque as Deposited

When you physically take the cheque to the bank for deposit:

1. Go to the **Cheques** tab in the Billing module.
2. Find the cheque by patient name, cheque number, or date.
3. Click on the cheque entry.
4. Click **Mark as Deposited**.
5. Enter the **deposit date** (today's date).
6. Click **Save**. The cheque status changes to **Deposited**.

### Procedure: Mark a Cheque as Cleared

When the bank confirms the cheque has cleared (funds received):

1. Open the cheque record from the **Cheques** tab.
2. Click **Mark as Cleared**.
3. Enter the **clearance date** (as confirmed by the bank).
4. Click **Save**.
5. The system automatically posts the payment to the linked invoice.
6. Invoice status updates to **Paid** (if this cheque covers the full balance) or **Partially Paid** (if partial).
7. A receipt is generated for the patient.

### Procedure: Mark a Cheque as Bounced

If the bank returns the cheque unpaid (insufficient funds, account closed, signature mismatch, etc.):

1. Open the cheque record.
2. Click **Mark as Bounced**.
3. A **bounce reason** is required — enter the reason as given by the bank:
   - Examples: "Insufficient funds", "Account closed", "Signature mismatch", "Post-dated cheque"
4. Click **Confirm Bounce**.
5. The cheque status changes to **Bounced**.
6. The linked invoice **automatically reverts to Pending** (or Partially Paid if other payments exist). The bounced cheque amount is removed from the invoice's payment history.
7. Contact the patient immediately to arrange an alternative payment method.
8. You may apply a **bounced cheque fee** if your hospital has this policy — this must be added as a manual line item by your Admin.

### Procedure: Cancel a Cheque

If a cheque was registered in error and has not yet been deposited:

1. Open the cheque record.
2. Click **Cancel Cheque**.
3. Enter a brief reason for cancellation.
4. Click **Confirm**. The cheque status changes to **Cancelled**.
5. The invoice reverts to its previous status.

### Bounce Handling — Summary of Effects on Invoice

| Cheque Status | Invoice Effect |
|---------------|---------------|
| Received | No effect — invoice stays Pending/Partially Paid |
| Deposited | No effect — invoice stays Pending/Partially Paid |
| Cleared | Invoice advances to Paid or Partially Paid |
| Bounced | Bounced amount removed; invoice reverts to Pending/Partially Paid |
| Cancelled | No effect — invoice unaffected |

---

## 7. Invoice Printing

### Procedure: Print an Invoice

1. Open the invoice from the billing queue.
2. Click **Print Invoice** (or the printer icon).
3. A print preview opens. Verify:
   - Patient name and OP Number are correct.
   - All line items are present and amounts are correct.
   - The invoice status and amount due are shown clearly.
4. Select your printer and click **Print**.

### Procedure: Print a Receipt

After a payment is recorded:

1. Open the invoice.
2. In the Payments section, find the payment entry you want to receipt.
3. Click **Print Receipt** next to that payment entry.
4. A receipt print preview opens showing: payment amount, method, date, and reference.
5. Print and hand to the patient.

### Print Template Styles

Your Admin may have configured the print template style (Modern, Classic, or Minimal) and hospital branding (logo, colors). The print output will reflect these settings automatically — you do not need to configure them.

---

## 8. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Payment amount exceeds balance" | Entered amount is more than what is owed | Reduce the amount to the balance due; if overpaying, consult Admin |
| "Invoice is cancelled" | Attempting to record payment on a cancelled invoice | Do not process payment; contact Admin to confirm the correct action |
| "Pending M-Pesa — payment in progress" | An STK push is active; another payment cannot be processed yet | Wait for the M-Pesa callback to resolve; then use another method if needed |
| "M-Pesa phone number invalid" | Phone number does not normalize to a valid format | Verify the patient's M-Pesa number and re-enter |
| "Cheque bounce reason required" | Attempted to mark as bounced without entering a reason | Enter the bank's stated reason for the return |
| "Idempotency error" | Duplicate submission detected | The original transaction was already recorded; do not submit again; refresh the page |
| "Access denied" / 403 | Missing permission | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Billing module not in subscription | Contact Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 9. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between fields in the payment dialog |
| `Escape` | Close dialogs without saving |
| Type in the search field | Search invoices by patient name, OP Number, or invoice number |
| Click status filter | Filter queue to show only Pending, Partially Paid, etc. |
| Browser `F5` or `Ctrl+R` | Refresh if M-Pesa status or queue does not update |
| Click column header | Sort the invoice queue by that column |

---

*MediFleet HMS — Billing Officer Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Staff Only*
