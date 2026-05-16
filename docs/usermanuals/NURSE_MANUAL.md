# MediFleet Hospital Management System
## Nurse User Manual

**Role**: Nurse  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/wards`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Ward Board — Overview and Bed Status Colors
4. Admitting a Patient to a Ward
5. Ward Rounds — Consumable Recording
6. Discharge Procedure
7. Viewing Lab Results for Admitted Patients
8. Messaging — Team Communication
9. Common Errors
10. Keyboard Tips

---

## 1. Quick Start

As a Nurse, your primary workspace is the **Ward Management Module** at `/app/wards`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/wards`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Open the Ward Board to review all bed statuses in your assigned ward.
2. Admit patients authorized by a doctor to available beds.
3. Conduct ward rounds, recording consumables used during care.
4. Check lab results for admitted patients and communicate abnormal findings to the doctor.
5. Process discharges and update bed status upon patient departure.
6. Use Messaging to coordinate with doctors, pharmacists, and other nurses.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `wards:read` | View ward board, bed status, and admission records |
| `wards:write` | Admit patients, update admission details, and discharge patients |
| `consumables:write` | Record consumable and reusable item usage during ward rounds |
| `lab_results:read` | View laboratory results for admitted patients |
| `messaging:read` | Read messages from colleagues |
| `messaging:write` | Send messages to colleagues |
| `patients:read` | View basic patient demographic information |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Ward Board — Overview and Bed Status Colors

The **Ward Board** is the main visual interface showing all beds in your ward and their current status. It updates in real time.

### Bed Status Color Codes

| Color | Status | Meaning |
|-------|--------|---------|
| Green | Available | Bed is clean, ready, and can accept a new patient |
| Orange | Occupied | Bed has an admitted patient currently in it |
| Red | Maintenance | Bed is out of service (equipment fault, structural issue) |
| Yellow | Cleaning | Bed has been vacated and is being cleaned before next use |

### Reading the Ward Board

1. Each bed tile displays: **Bed Number/Name**, **Status Color**, and (if occupied) the **Patient Name** and **OP Number**.
2. Click any occupied bed tile to see the patient's admission details.
3. Click any available bed tile (green) to begin an admission.
4. Beds in Maintenance or Cleaning status cannot receive new admissions.

### Procedure: Change Bed Status to Maintenance

If a bed needs to be taken offline for repair or servicing:

1. Click the bed tile.
2. Select **Mark as Maintenance**.
3. Enter a brief reason (e.g. "Bed rail broken — awaiting repair").
4. Click **Confirm**. The tile turns red.
5. To restore, click the bed tile and select **Mark as Available** once servicing is complete.

---

## 4. Admitting a Patient to a Ward

Admissions are authorized by a Doctor. The doctor creates the admission order in the clinical module; the nurse completes the physical admission in the ward module.

### Important Rule: Only Admit to Available (Green) Beds

You can only place a patient in a bed with status **Available** (green). Occupied, Maintenance, and Cleaning beds cannot receive new patients.

### Procedure: Admit a Patient

1. From the Ward Board, locate the **pending admission** list — this shows patients for whom a doctor has written an admission order.
2. Click on the patient's pending admission entry.
3. Review the following information before proceeding:
   - Patient name and OP Number
   - Admitting doctor's name
   - Reason for admission / diagnosis
   - Any special care requirements noted by the doctor
4. On the Ward Board, identify a suitable **Available (green)** bed.
5. Click **Admit to Bed**.
6. From the bed selection dialog, click the green bed you identified.
7. Complete the required admission fields:

   | Field | Notes |
   |-------|-------|
   | Admission Date and Time | Defaults to current date/time; adjust if needed |
   | Admitting Doctor | Pre-filled from the admission order |
   | Ward | Pre-filled based on the bed selected |
   | Bed | Pre-filled based on your selection |
   | Admission Reason | Brief clinical reason for admission |
   | Diet Instructions | E.g. NPO (nil by mouth), soft diet, diabetic diet |
   | Special Care Notes | Any nursing care requirements (e.g. fall risk, pressure sore prevention) |
   | Next of Kin Notified | Checkbox — tick if next of kin has been informed of admission |

8. Click **Confirm Admission**.
9. The selected bed immediately changes from **Available (green)** to **Occupied (orange)**.
10. The patient's name and OP Number appear on the bed tile.

### After Admission

- Document the time of admission in the nursing notes.
- Perform an initial nursing assessment and record vitals.
- Confirm any standing medications are prescribed and available.

---

## 5. Ward Rounds — Consumable Recording

Ward rounds are regular visits to admitted patients to assess their condition and deliver care. Consumables (dressings, gloves, IV fluids, syringes, etc.) used during care must be recorded for billing and inventory accuracy.

### Understanding FEFO (First-Expire-First-Out)

MediFleet tracks consumable stock in batches by expiry date. The system automatically uses the batch that expires soonest first — this is the **FEFO** (First-Expire-First-Out) principle. You do not need to manually select batches; the system handles this automatically.

### Item Types

| Type | Description |
|------|-------------|
| Consumable | Single-use items (dressings, syringes, gloves, IV cannulas). Deducted from stock permanently. |
| Reusable | Items that are returned and sterilized (certain instruments). These are logged but not deducted from stock. |

### Procedure: Record Consumables During a Ward Round

1. From the Ward Board, click the occupied bed tile of the patient you are visiting.
2. Open the **Ward Round** or **Consumables** tab in the patient's admission record.
3. Click **+ Add Consumable Entry**.
4. Search for the item by name in the catalog search field.
5. Select the item from the results.
6. The system displays the item type (Consumable or Reusable) and the available stock.
7. Enter the **quantity used**.
8. For reusable items, confirm the item will be returned for sterilization.
9. Add any nursing notes about the care delivered.
10. Click **Save Entry**.
11. Repeat steps 3–10 for each item used during the round.

### Viewing Cumulative Consumable Usage

- The consumable usage list for each patient is visible in their admission record.
- Usage from each ward round is timestamped and attributed to the nurse who recorded it.
- Billing staff can view cumulative consumable charges linked to the admission.

---

## 6. Discharge Procedure

Discharge releases the patient from the ward, frees the bed, and triggers billing finalization.

### Procedure: Discharge a Patient

1. Confirm that the discharging doctor has written a **Discharge Order** in the clinical module. You cannot discharge without this.
2. From the Ward Board, click the patient's occupied bed tile (orange).
3. Click **Initiate Discharge**.
4. Complete the **Discharge Form**:

   | Field | Notes |
   |-------|-------|
   | Discharge Date and Time | Defaults to now; adjust if needed |
   | Discharging Doctor | Pre-filled; verify it is correct |
   | Discharge Type | E.g. Discharged Home, Transferred, Discharged Against Advice, Died |
   | Discharge Diagnosis | Final diagnosis at time of discharge |
   | Discharge Instructions | Patient instructions to take home — medications, activity, diet, follow-up |
   | Follow-Up Appointment | Date of next clinic visit if applicable |
   | Discharge Notes | Full nursing summary of the admission |

5. Ensure all nursing notes for the admission are completed before proceeding.
6. Click **Confirm Discharge**.
7. A prompt asks you for the **bed status after discharge**:
   - Select **Cleaning (yellow)** if the bed needs to be cleaned before the next patient (standard practice).
   - Select **Maintenance (red)** if you have identified a problem with the bed.
8. Click **Set Bed Status**.
9. The bed tile on the Ward Board changes from Occupied (orange) to the status you selected.
10. Once housekeeping completes cleaning, update the bed to **Available (green)** so it can receive the next patient.

### Updating Bed to Available After Cleaning

1. Click the bed tile showing **Cleaning (yellow)**.
2. Click **Mark as Available**.
3. Confirm that the bed is clean and ready.
4. The tile changes to **Available (green)**.

---

## 7. Viewing Lab Results for Admitted Patients

Doctors may order laboratory tests for admitted patients. As a nurse, you can view these results to monitor patient progress and alert the doctor to critical values.

### Procedure: View Lab Results for an Admitted Patient

1. From the Ward Board, click the patient's occupied bed tile.
2. Open the **Lab Results** tab in the patient's admission detail panel.
3. All lab orders and their current status are listed:
   - **Pending**: Sample not yet collected or test not yet started
   - **In Progress**: Specimen received; testing underway
   - **Completed**: Results entered by the lab technician
4. Click a completed result entry to view the detailed results, including reference ranges.
5. Out-of-range values are highlighted — pay close attention to these.

### When to Alert the Doctor

Immediately notify the attending doctor via messaging or in person if you observe any of the following:

- Any result marked as critically abnormal (typically highlighted in red).
- STAT test results that have become available.
- A significant change from previous results.

### Procedure: Message the Doctor About a Result

1. Open the **Messages** panel.
2. Click **+ New Message** and search for the attending doctor's name.
3. Write a clear, specific message. Example: "Patient [Name], OP-2026-0042, Bed 14A — potassium result is 6.1 mmol/L (high). Please review."
4. Send the message. The doctor will be notified in real time.

---

## 8. Messaging — Team Communication

MediFleet's messaging system allows real-time communication between nurses, doctors, pharmacists, and other staff.

### Message Types

| Type | Description |
|------|-------------|
| Direct Message (DM) | Private conversation between you and one other staff member |
| Group Message | Conversation with multiple named staff members |
| Department Channel | Auto-managed channel for your entire department |

### Procedure: Send a Direct Message

1. Click the **Messages** icon in the navigation bar.
2. Click **+ New Message**.
3. Search for the staff member by name.
4. Type your message.
5. Press **Enter** or click **Send**.

### Procedure: Use the Department Channel

1. Open the **Messages** panel.
2. Under **Channels**, select your ward's or department's channel.
3. Type your message and click **Send**.
4. All staff members in the department receive the message.

### Good Messaging Practices

- Always include the patient's **name and OP Number** when discussing a specific patient.
- Use direct messages for urgent, patient-specific concerns.
- Use the department channel for general shift communications.
- For emergencies, always supplement messaging with direct verbal communication.

---

## 9. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Bed not available" | Attempting to admit to a non-green bed | Select only green (Available) beds for admission |
| "No discharge order found" | Discharge attempted without doctor's discharge order | Ask the attending doctor to write the discharge order in the clinical module |
| "Consumable not in catalog" | Item searched does not exist in the inventory catalog | Contact your Admin or pharmacy to add the item to the catalog |
| "Stock depleted" | Item is out of stock in the ward location | Request a stock transfer from Main Store via pharmacy; use a substitute if clinically safe |
| "Admission record not found" | Pending admission was cancelled or already processed | Check with the doctor; the order may have been revised |
| "Access denied" / 403 | Missing permission | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Ward module not included in subscription | Contact your Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 10. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between fields in admission and discharge forms |
| `Escape` | Close dialogs without saving |
| Click bed tile | Opens the bed or patient detail immediately |
| Browser `F5` or `Ctrl+R` | Refresh the Ward Board if updates are not showing |
| Search field on consumables | Type at least 3 characters for fast catalog search |

---

*MediFleet HMS — Nurse Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Staff Only*
