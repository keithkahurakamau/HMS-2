# MediFleet Hospital Management System
## Receptionist User Manual

**Role**: Receptionist  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/patients`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Patient Registry — Searching for Patients
4. Patient Registration — Creating a New Patient
5. Editing Patient Records
6. Queue Management
7. Appointment Booking
8. ActivePatientBar
9. Messaging
10. Common Errors
11. Keyboard Tips

---

## 1. Quick Start

As a Receptionist, your primary workspace is the **Patient Registry** screen at `/app/patients`. This is the first screen you see after logging in.

**First-time login**: You will be forced to set a new password before reaching `/app/patients`. See the INDEX manual for password requirements.

Your daily workflow typically follows this order:

1. Search for a returning patient OR register a new one.
2. Add the patient to the clinical queue with the correct acuity level.
3. Book or confirm appointments as needed.
4. Monitor the ActivePatientBar to track patients currently being seen.
5. Use Messaging to communicate with clinical staff.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `patients:read` | Search and view patient records |
| `patients:write` | Register new patients and edit existing records |
| `queue:write` | Add patients to the clinical queue, update acuity |
| `appointments:read` | View appointment schedule |
| `appointments:write` | Book, confirm, reschedule, and cancel appointments |
| `messaging:read` | Read messages |
| `messaging:write` | Send messages |

If any of these actions are unavailable (buttons greyed out or missing), contact your Admin to verify your permissions.

---

## 3. Patient Registry — Searching for Patients

Always search before registering. This prevents creating duplicate records.

### Procedure: Search for a Patient

1. From the **Patient Registry** screen (`/app/patients`), locate the search bar at the top of the patient list.
2. Type any of the following to search:
   - Patient's **first name** or **last name**
   - **OP Number** (format: `OP-YEAR-NNNN`, e.g. `OP-2026-0001`)
   - **Phone number**
   - **National ID number**
3. Results update as you type. Click the patient's row to open their record.
4. Verify the record by confirming **date of birth** and **phone number** with the patient before proceeding.

### Tips for Accurate Searching

- If no results appear, try a shorter search term (e.g. just the surname).
- Phone numbers can be searched with or without the country code.
- If the patient has a common name, use the OP Number if they have their card.

---

## 4. Patient Registration — Creating a New Patient

Only register a new patient after confirming they do not already exist in the system.

### Procedure: Register a New Patient

1. Click the **+ New Patient** button (top-right of the Patient Registry screen).
2. Complete the **Required Fields** — the form will not submit without these:

   | Field | Notes |
   |-------|-------|
   | First Name | As on official ID |
   | Last Name | As on official ID |
   | Date of Birth | Use the date picker; format DD/MM/YYYY |
   | Gender | Select from dropdown |
   | Phone Number (Primary) | Enter with country code; system normalizes automatically |

3. Complete the **Optional Fields** as available:

   | Field | Notes |
   |-------|-------|
   | Middle Name | Include if provided |
   | National ID / Passport Number | Important for identity verification |
   | Email Address | Used for appointment reminders if configured |
   | Secondary Phone Number | Alternative contact |
   | Physical Address | Home address |
   | Next of Kin Name | Emergency contact |
   | Next of Kin Phone | Emergency contact phone |
   | Next of Kin Relationship | E.g. Spouse, Parent, Sibling |
   | Blood Group | If known |
   | Occupation | Optional background information |
   | Religion | Optional; used for dietary/care preferences |
   | Marital Status | Optional |

4. Click **Save Patient**.
5. The system automatically generates an **OP Number** in the format `OP-YEAR-NNNN` (e.g. `OP-2026-0042`). This number is displayed immediately after saving.
6. **Print or note the OP Number** and give it to the patient — they will need it to access the patient portal and for future visits.

### Important Notes on OP Numbers

- OP Numbers are assigned sequentially within each year.
- They cannot be edited or reassigned.
- The patient should keep their OP Number on their physical registration card.

---

## 5. Editing Patient Records

Patient details can change (new phone number, address update, etc.). Edit the record rather than creating a new one.

### Procedure: Edit a Patient Record

1. Search for the patient using the procedure in Section 3.
2. Open the patient's record by clicking their row.
3. Click the **Edit** button (pencil icon) in the patient detail panel.
4. Modify the relevant fields.
5. Click **Save Changes**.
6. The system logs the change automatically for audit purposes.

### What Cannot Be Changed

- **OP Number**: Permanently assigned at registration, never editable.
- **Date of Birth**: If incorrectly entered, contact your Admin — changes to DOB require admin-level correction with audit justification.

---

## 6. Queue Management

The Queue module routes patients to the correct clinical department and prioritizes them by urgency.

### Acuity Levels

| Acuity Level | Code | Description | Example |
|--------------|------|-------------|---------|
| Emergency | 1 | Immediate threat to life | Chest pain, major trauma, unconscious patient |
| Urgent | 2 | Serious condition, needs prompt attention | High fever, moderate pain, acute infection |
| Standard | 3 | Routine consultation | Prescription renewal, follow-up, minor complaint |

**Higher acuity numbers wait longer. Lower acuity numbers (especially 1 = Emergency) go first.**

### Procedure: Add a Patient to the Queue

1. Open the patient's record (search first, Section 3).
2. Click the **Add to Queue** button.
3. A dialog opens. Select the **Department** (e.g. General Outpatient, Pediatrics, Cardiology).
4. Select the **Acuity Level**:
   - Choose **1 - Emergency** only for life-threatening presentations.
   - Choose **2 - Urgent** for significant but non-life-threatening complaints.
   - Choose **3 - Standard** for routine visits.
5. Add a brief **Chief Complaint** (one or two sentences describing the reason for the visit).
6. Click **Confirm**. The patient appears in the clinical queue visible to doctors and nurses.

### Procedure: Update Acuity

If a patient's condition changes while waiting:

1. Locate the patient in the queue list.
2. Click the **pencil/edit** icon next to their entry.
3. Change the acuity level and click **Update**.
4. The queue automatically re-sorts.

### Procedure: Remove a Patient from the Queue

If a patient leaves without being seen (e.g. decides not to wait):

1. Locate the patient in the queue.
2. Click the **Remove** or **No-Show** option.
3. Confirm the action. The patient's slot is released.

---

## 7. Appointment Booking

Appointments are pre-scheduled visits linked to a specific doctor.

### Appointment Status Lifecycle

| Status | Meaning |
|--------|---------|
| Scheduled | Booked but not yet confirmed |
| Confirmed | Patient confirmed to attend |
| Completed | Visit took place |
| Cancelled | Visit will not occur |
| No-Show | Patient did not attend without cancelling |

### Procedure: Book a New Appointment

1. Open the patient's record.
2. Click the **Appointments** tab.
3. Click **+ New Appointment**.
4. Select the **Doctor** from the dropdown list.
5. The system displays the doctor's **available time slots** based on their schedule. Select a slot.
6. Select the **appointment type** (e.g. Consultation, Follow-up, Procedure).
7. Add any **notes** (reason for visit, special requirements).
8. Click **Book Appointment**.
9. The appointment status is set to **Scheduled**.

### Procedure: Confirm an Appointment

1. Open the patient's record and go to the **Appointments** tab.
2. Find the appointment with status **Scheduled**.
3. Click **Confirm**. Status changes to **Confirmed**.

### Procedure: Cancel an Appointment

1. Open the appointment from the patient's record or the appointments calendar.
2. Click **Cancel Appointment**.
3. Enter a **cancellation reason** (required).
4. Click **Confirm Cancellation**. Status changes to **Cancelled**.

### Procedure: Mark a Patient as No-Show

1. After the scheduled appointment time has passed without the patient arriving:
2. Open the appointment.
3. Click **Mark as No-Show**. Status changes to **No-Show**.

### Procedure: Reschedule an Appointment

1. Open the appointment.
2. Click **Reschedule**.
3. Select the new date and time slot.
4. Click **Save**. The original appointment is cancelled and a new one is created.

---

## 8. ActivePatientBar

The **ActivePatientBar** is a persistent panel (usually at the top or side of the screen) that shows patients currently checked in and being processed.

### Reading the ActivePatientBar

- Each entry shows: **Patient Name**, **OP Number**, **Current Status** (e.g. In Queue, With Doctor, At Pharmacy).
- The bar updates in real time as doctors, nurses, and pharmacists progress the patient through the system.

### Using the ActivePatientBar

- **Click a patient's entry** to jump directly to their record.
- Use this to quickly answer queries from patients or family members asking about progress.
- You cannot change statuses from the bar itself — it is a monitoring view only for the Receptionist.

---

## 9. Messaging

MediFleet includes an internal messaging system for communication between staff.

### Message Types

| Type | Description |
|------|-------------|
| Direct Message (DM) | Private conversation between you and one other staff member |
| Group Message | Conversation with multiple named staff members |
| Department Channel | Automatically created for each department; all department members are included |

### Procedure: Send a Direct Message

1. Click the **Messages** icon in the navigation bar (speech bubble icon).
2. Click **+ New Message**.
3. Search for the staff member by name.
4. Type your message in the text field.
5. Press **Enter** or click **Send**.

### Procedure: Send a Message in a Department Channel

1. Open the **Messages** panel.
2. Under **Channels**, select your department channel.
3. Type your message and click **Send**. All department members will receive it.

### Good Messaging Practices

- Use direct messages for patient-specific information (e.g. "Patient OP-2026-0042 is asking about wait time").
- Use department channels for general announcements (e.g. "Queue is very long, please advise earliest available slot").
- Do not share sensitive clinical information in group channels unless all members need it.

---

## 10. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Patient already exists" | Duplicate registration attempted | Search for the existing record instead of creating a new one |
| "OP Number not found" | Incorrect OP Number entered in search | Double-check the number with the patient; ensure format is OP-YEAR-NNNN |
| "No available slots" | Doctor has no open time in the selected period | Choose a different doctor or a different date |
| "Queue entry failed" | Network error or missing required field (department or acuity) | Check all fields are filled and try again; if persistent, contact IT |
| "Access denied" / 403 | Missing permission for the action | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Subscription does not include this module | Contact your Admin or platform support |
| "Account locked" | 5 failed login attempts | Wait 15 minutes, then try again; or ask Admin to verify |
| "Session expired" | Access token could not be refreshed | Log in again; this happens if the browser was left idle for many hours |

---

## 11. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| Click the search bar and start typing | Immediately searches as you type |
| `Tab` | Move between form fields |
| `Enter` in a search field | Confirms search |
| `Escape` | Close dialogs without saving |
| Browser `F5` or `Ctrl+R` | Refresh the page if data appears stale (you will not lose your session) |
| Click column headers in the patient list | Sort the list by that column |

---

*MediFleet HMS — Receptionist Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Staff Only*
