# MediFleet Hospital Management System
## Pharmacist User Manual

**Role**: Pharmacist  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/pharmacy`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Pharmacy Inventory View
4. Prescription Fulfillment
5. Over-the-Counter (OTC) Sales
6. Dispense Log
7. Stock Transfers from Main Store
8. Messaging — Communicating with Doctors and Nurses
9. Common Errors
10. Keyboard Tips

---

## 1. Quick Start

As a Pharmacist, your primary workspace is the **Pharmacy Module** at `/app/pharmacy`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/pharmacy`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Check inventory for low-stock alerts and items approaching expiry.
2. Process prescriptions from the clinical queue — locate each clinical record, select the correct batch (FEFO), and dispense.
3. Handle OTC (over-the-counter) walk-in sales.
4. Review the dispense log to verify all transactions.
5. Request stock transfers from the Main Store when pharmacy stock is low.
6. Communicate with doctors about prescription queries via the messaging system.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `pharmacy:read` | View inventory, prescription queue, and dispense log |
| `pharmacy:write` | Fulfill prescriptions, process OTC sales, record dispensing |
| `inventory:read` | View stock levels, batch details, and reorder alerts |
| `stock_transfers:write` | Request stock transfers from Main Store |
| `clinical:read` | View clinical records to read prescriptions |
| `messaging:read` | Read messages from colleagues |
| `messaging:write` | Send messages to colleagues |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Pharmacy Inventory View

The Inventory section shows all medications and supplies held at the Pharmacy location.

### Understanding FEFO (First-Expire-First-Out)

MediFleet manages stock in **batches**, each with its own expiry date. The system always presents the batch that expires soonest at the top of the list — this is the **FEFO** (First-Expire-First-Out) principle. Always use the first listed batch when dispensing to minimize waste and ensure no expired stock reaches patients.

### Inventory Display Columns

| Column | Description |
|--------|-------------|
| Item Name | Medication or supply name |
| Stock Location | Pharmacy (local), Main Store (hub) |
| Available Qty | Total units currently in stock at this location |
| Batch Number | Identifier for this stock batch |
| Expiry Date | Expiry date of this batch; soonest-expiring batch shown first |
| Reorder Level | Threshold below which a reorder alert is triggered |
| Status | Normal / Low Stock / Critical / Expired |

### Procedure: Check Inventory

1. Navigate to the **Inventory** tab within the Pharmacy module.
2. The list defaults to sorting by expiry date (FEFO order). Do not change this sort order during dispensing.
3. Items marked **Low Stock** or **Critical** appear highlighted — these require a stock transfer request.
4. Items marked **Expired** must not be dispensed. Report them to your Admin for removal from usable stock.

### Reorder Alerts

- When stock falls below the configured **reorder level**, an alert badge appears on the inventory screen.
- The Admin Dashboard also shows a "Low Stock Alerts" tile — your Admin will see this independently.
- Initiate a stock transfer request (Section 7) when you see a low-stock alert.

---

## 4. Prescription Fulfillment

Prescriptions written by doctors in the clinical module appear in the Pharmacy module for fulfillment. You must locate the correct clinical record, verify the prescription, select the appropriate stock batch (following FEFO), and record the dispense.

### Clinical Record Status at Pharmacy Stage

Encounters progress through: **Draft → Billed → Pharmacy → Completed**

Prescriptions become available to the Pharmacy when the encounter status is **Billed** or **Pharmacy**. You cannot fulfill prescriptions on Draft encounters.

### Understanding the Idempotency Key

When recording a dispense transaction, the system attaches an **idempotency key** — a unique identifier that prevents the same transaction from being processed twice, even if you click Submit more than once (e.g. due to a slow connection). You do not generate or manage this key; the system handles it automatically. It is important to understand that clicking Submit multiple times will not result in double charges.

### Procedure: Fulfill a Prescription

1. Navigate to the **Prescription Queue** tab in the Pharmacy module.
2. The queue lists all pending prescriptions. Each entry shows: **Patient Name**, **OP Number**, **Doctor**, **Date/Time**, and the number of items prescribed.
3. Click on the prescription entry to open the full prescription detail.
4. Review the prescription:
   - Verify **patient name and OP Number** against any paperwork brought by the patient.
   - Read all medications, doses, frequencies, and special instructions.
5. For each medication in the prescription:
   a. The system displays the **stock batches** available for that medication, sorted by expiry date (FEFO — earliest expiry first).
   b. Select the **first batch** in the list (the one expiring soonest).
   c. Enter the **quantity to dispense** (as written on the prescription).
   d. If the first batch has insufficient stock to fill the full quantity, use as much as possible from that batch, then select the next batch for the remainder. Record quantities for each batch separately.
6. Add any **dispensing notes** (e.g. "Counselled patient on dosing schedule").
7. Click **Dispense**. The system:
   - Deducts the quantity from the batch(es) selected.
   - Posts the medication charges to the patient's invoice automatically.
   - Updates the encounter status (if all prescriptions are fulfilled, status may advance toward Completed).
   - Records the transaction in the Dispense Log.
8. Hand the medication to the patient with verbal counselling on dosage and any special instructions.

### Partial Fulfillment

If a medication is temporarily out of stock:

1. Dispense the available quantity.
2. Note in the dispensing notes that the prescription was partially fulfilled.
3. Inform the patient of the shortage and when stock is expected.
4. Initiate a stock transfer request (Section 7) for the missing items.
5. Contact the prescribing doctor via messaging if a substitute is clinically required.

---

## 5. Over-the-Counter (OTC) Sales

OTC sales are for walk-in customers purchasing non-prescription items or medications that do not require a clinical encounter. No patient OP Number is required for OTC sales.

### Procedure: Process an OTC Sale

1. Navigate to the **OTC Sales** tab in the Pharmacy module.
2. Click **+ New OTC Sale**.
3. The OTC sale form does not require a patient ID — it is a walk-in transaction.
   - Optionally, enter a **customer name** for the receipt.
4. Search for each item:
   a. Type the medication or product name in the search field.
   b. Select the item from the catalog results.
   c. The system shows the FEFO-sorted batches — select the first (earliest-expiry) batch.
   d. Enter the **quantity** being sold.
   e. Click **Add to Sale**.
5. Repeat step 4 for all items in the sale.
6. Review the sale summary (items, quantities, prices, total).
7. Click **Process Sale**.
8. Select the **payment method** (Cash, Card, or M-Pesa if configured).
9. Record payment received and give the customer their receipt.
10. The transaction is logged in the Dispense Log as an OTC entry.

### OTC vs. Prescription Sales

| Feature | OTC Sale | Prescription Fulfillment |
|---------|----------|--------------------------|
| Patient OP Number required | No | Yes |
| Linked to clinical encounter | No | Yes |
| Invoice auto-updated | No (standalone receipt) | Yes |
| Prescription required | No | Yes |

---

## 6. Dispense Log

The **Dispense Log** is a complete audit trail of all dispensing transactions — both prescription fulfillments and OTC sales.

### Procedure: View the Dispense Log

1. Navigate to the **Dispense Log** tab in the Pharmacy module.
2. The log shows all recent transactions with:
   - Transaction date and time
   - Patient name / OP Number (OTC entries show "Walk-In" or customer name)
   - Item dispensed
   - Batch number used
   - Quantity dispensed
   - Dispensing pharmacist name
   - Transaction type (Prescription / OTC)
3. Use the **Date Filter** to narrow results by date range.
4. Use the **Search** field to find transactions by patient name or item name.

### Using the Log for Verification

- If a patient disputes a charge, locate their OP Number in the log to see exactly what was dispensed and when.
- If there is a stock discrepancy, use the log to trace when stock was dispensed and in what quantities.

---

## 7. Stock Transfers from Main Store

The **Main Store** is the central inventory hub. Pharmacy, Laboratory, and Wards all receive stock from the Main Store. When your pharmacy stock is low, you request a transfer.

### Inventory Location Hierarchy

| Location | Role |
|----------|------|
| Main Store | Central hub; receives all purchases |
| Pharmacy | Spoke; dispenses to patients |
| Laboratory | Spoke; uses reagents and consumables |
| Wards | Spoke; uses nursing consumables |

### Procedure: Request a Stock Transfer

1. Navigate to the **Stock Transfers** tab in the Pharmacy module.
2. Click **+ New Transfer Request**.
3. The **From** field defaults to **Main Store** and the **To** field defaults to **Pharmacy** — verify these are correct.
4. Add items to the request:
   a. Search for the item by name.
   b. Enter the quantity requested.
   c. Click **Add to Request**.
5. Repeat step 4 for all low-stock items.
6. Add a note if needed (e.g. "Urgent — amoxicillin depleted").
7. Click **Submit Request**.
8. The request appears in the Main Store module for an Admin or storekeeper to fulfill.
9. When the transfer is approved and processed, your pharmacy stock levels update automatically.

### Tracking Transfer Requests

- Go to the **Stock Transfers** tab to see all pending and completed requests.
- Each request shows its status: **Pending**, **Approved**, or **Completed**.
- If a request is **Rejected**, a reason is provided — contact your Admin.

---

## 8. Messaging — Communicating with Doctors and Nurses

The pharmacy team frequently needs to communicate with prescribing doctors about prescription queries, substitutions, or stock issues.

### Procedure: Message a Doctor About a Prescription

1. Click the **Messages** icon in the navigation bar.
2. Click **+ New Message**.
3. Search for the doctor by name.
4. Write a clear message, always including the patient's **OP Number** and the specific medication in question. Example: "OP-2026-0042 — the prescribed metronidazole 500mg is currently out of stock. Can you approve a substitute of 250mg x2?"
5. Click **Send**. The doctor will receive a real-time notification.

### Procedure: Message a Nurse About Ward Supplies

1. Open the **Messages** panel.
2. Search for the nurse by name or open the relevant ward department channel.
3. Message about supply availability or stock transfer status.

### Department Channels

- Your pharmacy department has an auto-created department channel. All pharmacy staff are members.
- Use this channel for shift handover notes, general stock updates, and team communications.

---

## 9. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Prescription not found" | Attempting to fulfill a prescription that does not exist or was cancelled | Verify the OP Number; check with the doctor that the prescription was submitted |
| "Encounter not in Pharmacy status" | Encounter is still in Draft or not yet billed | Wait for the doctor to finalize the encounter; contact them if urgent |
| "Insufficient stock" | Quantity requested exceeds available batch stock | Fulfill partially with available stock; request transfer from Main Store |
| "Batch expired" | Selected batch has passed its expiry date | Do not dispense from this batch; report to Admin for stock write-off; use next available batch |
| "Transfer request rejected" | Main Store rejected the transfer request | View the rejection reason; contact Admin to resolve |
| "Access denied" / 403 | Missing permission | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Pharmacy module not included in subscription | Contact your Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 10. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between form fields |
| `Escape` | Close dialogs without saving |
| Type in item search | Real-time search; use 3+ characters for fast results |
| Click column headers in inventory | Sort the list by that column |
| Browser `F5` or `Ctrl+R` | Refresh if the prescription queue does not update |

---

*MediFleet HMS — Pharmacist Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Staff Only*
