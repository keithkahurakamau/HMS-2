# MediFleet Training Program

**Official Training Documentation — MediFleet Hospital Management System**

---

## Document Information

| Field | Detail |
|---|---|
| **Version** | 1.0 |
| **Effective Date** | 2026-05-16 |
| **Maintained By** | MediFleet Platform Team |
| **Audience** | All staff users, patient portal users, and system administrators |
| **Review Cycle** | Annually or following major platform releases |

### How to Use This Document

This training program is organized into four parts:

- **Part 1** is mandatory for every user regardless of role. Complete it before proceeding to your role path.
- **Part 2** contains role-specific training paths. Navigate directly to your assigned role. Each module includes step-by-step procedures, key concepts, and an end-of-module assessment.
- **Part 3** covers cross-cutting compliance, security, and communication topics that apply to multiple roles. All clinical staff must complete Section 3.1 (KDPA Compliance).
- **Part 4** is for training coordinators and system administrators managing the training program.

Each assessment section presents scenario-based questions. Attempt each question independently before consulting the Answer Key in Section 4.3.

---

# Part 1: Platform Orientation (ALL ROLES)

---

## 1.1 What Is MediFleet?

MediFleet is a multi-tenant Software-as-a-Service (SaaS) Hospital Management System designed for healthcare facilities across Kenya and beyond. Understanding its architecture will help you use it effectively and recognize normal system behavior.

### Multi-Tenant Architecture

Each hospital that subscribes to MediFleet operates in a fully isolated environment. Your hospital has its own dedicated PostgreSQL database — patient records, staff accounts, billing data, and configuration from your facility are never mixed with those of another hospital on the platform. When you log in, you are automatically scoped to your hospital's environment. You cannot see data from other hospitals, and they cannot see yours.

### Module-Based Subscriptions

MediFleet is sold as a core platform with optional feature modules. Your hospital's subscription determines which modules are active. The following modules are always available to every subscriber:

- Patients, Appointments, Dashboard, Settings, Support, Messaging, Notifications, Users, and Authentication.

The following modules are optional and must be enabled by the platform operator for your hospital:

- Clinical, Laboratory, Radiology, Pharmacy, Inventory, Wards, Billing, Cheques, Medical History, M-Pesa, Analytics, Patient Portal, Branding, Referrals, and Privacy.

### The HTTP 402 "Module Unavailable" Screen

If you navigate to a section of the system and see a screen displaying a **402 — Module Unavailable** error, it means that particular module has not been enabled for your hospital's subscription. This is not a technical fault or a permissions error on your account. Contact your system administrator or your organization's MediFleet account manager to inquire about activating the module.

> **Important:** Do not attempt to bypass this screen. If you believe a module should be available for your role and work, report it to your administrator — do not interpret the 402 screen as a system failure requiring IT intervention.

---

## 1.2 Your Login Journey

### Step 1: Navigate to the Portal

Open your web browser and navigate to your hospital's MediFleet URL. The exact address will be provided by your system administrator during onboarding. You will arrive at the platform landing page.

### Step 2: Select Your Hospital

On the landing page you will see a hospital selection screen. Type the name of your hospital or scroll to locate it, then click to select it. This step scopes your session to your hospital's environment.

### Step 3: Enter Your Credentials

Enter your registered email address and password. Click **Sign In**.

### Step 4: Mandatory Password Change (First Login)

If this is your first login, or if your administrator has flagged your account for a required password change, you will be redirected to a password change screen before proceeding further. You must set a new password before gaining access to any other part of the system.

**Password Policy Requirements** — your password must satisfy all of the following:

1. Minimum 8 characters in length.
2. At least one uppercase letter (A–Z).
3. At least one lowercase letter (a–z).
4. At least one digit (0–9).
5. At least one special character (e.g., `!`, `@`, `#`, `$`, `%`).

The system will reject any password that does not meet all five criteria. You will receive a specific error message indicating which requirement was not met.

### Step 5: Landing on Your Role's Home Page

After successful authentication (and password change if required), you are automatically directed to the landing page assigned to your role:

| Role | Landing Page |
|---|---|
| Receptionist | /app/patients |
| Doctor | /app/clinical |
| Nurse | /app/wards |
| Pharmacist | /app/pharmacy |
| Laboratory Technician | /app/laboratory |
| Radiologist | /app/radiology |
| Billing Officer | /app/billing |
| Admin | /app/admin |
| Patient (portal) | /patient |
| Superadmin | /superadmin/dashboard |
| Custom Role | /app/messages |

### Account Lockout

After **5 consecutive failed login attempts**, your account is automatically locked for **15 minutes**. You will see a lockout message on the login screen indicating when you may try again. Do not attempt further logins during the lockout window as this does not reset the timer. After 15 minutes, you may attempt login again.

### Forgot Password

If you cannot remember your password, click the **Forgot Password** link on the login screen. Enter your registered email address and submit the form. You will receive a password reset email containing a secure link. This link is valid for **60 minutes**. Clicking the link takes you to a page where you can set a new password (subject to the same password policy requirements above). If the link expires, return to the Forgot Password page and request a new one.

---

## 1.3 Navigation Fundamentals

### The Sidebar

The left-hand sidebar is your primary navigation tool. The items displayed in your sidebar are determined entirely by your assigned role and your hospital's active modules. You will only see links to sections you are authorized to access. If a colleague's sidebar looks different from yours, this is expected — they have a different role or your hospital has a different module configuration.

Clicking any sidebar item navigates you to that section. The currently active section is highlighted.

### Notification Bell

The Notification Bell icon appears in the top navigation bar. A numeric badge on the bell indicates the number of unread notifications. Clicking the bell opens a notification panel listing recent events relevant to your work (e.g., a lab result returning for one of your patients, a new message, a queue update). Click an individual notification to navigate directly to the relevant resource and mark it as read.

### ActivePatientBar

The ActivePatientBar is a persistent strip displayed across the top of clinical and operational screens when you have set an active patient context. It shows the current patient's name, OP number, and other key identifiers so you always know which patient's record you are working in.

**Setting the active patient:** Navigate to the patient's record (typically via the Patients module or the queue) and click the patient's name or the "Set as Active" control. The bar will populate.

**Clearing the active patient:** Click the clear (X) control on the ActivePatientBar. Always clear the active patient when you have finished working on a record and before moving to an unrelated task. Failing to do so risks inadvertently attaching actions to the wrong patient.

### ThemeToggle

The ThemeToggle control (typically a sun/moon icon in the top navigation bar) switches the interface between light mode and dark mode. Select whichever theme is most comfortable for your work environment. Your preference is saved to your session.

### ModuleGuard (402 Card)

When you navigate to a route protected by a module that is not active for your hospital, the ModuleGuard component renders a 402 card in place of the normal page content. This card will display the name of the module that is unavailable. As noted in Section 1.1, contact your administrator if you believe this module should be active.

---

## 1.4 Real-Time Features

MediFleet uses WebSocket technology to deliver live updates to your browser without requiring you to refresh the page.

### WebSocket Connection

When you log in, the system automatically establishes a WebSocket connection at the path `/ws/notifications/{your_user_id}`. This connection remains active throughout your session. If the connection drops (e.g., due to a network interruption), the system will attempt to reconnect automatically. A brief banner may appear notifying you of the reconnection attempt.

### Events That Trigger Real-Time Notifications

The following events will deliver a notification to your Notification Bell in real time:

- **Queue updates:** A patient has been added to or moved within a queue you are monitoring.
- **Lab results:** A laboratory result has been completed for one of your patients (relevant to Doctors).
- **New messages:** A direct message, group message, or department channel message has been sent to you or a channel you belong to.
- **Radiology results:** A radiology report has been completed.
- **Ward events:** Bed status changes relevant to your ward.

You do not need to take any action to activate these notifications — they are delivered automatically as part of your session.

---

## 1.5 Assessment: Orientation

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question O-1**
You attempt to log in and receive a message stating your account is locked. You check the clock and it has been 20 minutes since your last attempt. What is the most likely explanation, and what should you do?

**Question O-2**
A colleague tells you that the Radiology section appears in their sidebar but it does not appear in yours. You have both been using the system for the same amount of time. Provide two distinct reasons that could explain this difference.

**Question O-3**
You are working on Patient A's clinical record and receive an urgent phone call. By the time you return to your workstation, you need to update Patient B's information. What step must you take before beginning work on Patient B's record, and why?

**Question O-4**
You navigate to /app/pharmacy and see a card displaying "402 — Module Unavailable." You are a pharmacist. Describe what this means and the correct escalation path.

**Question O-5**
You receive a notification on the bell icon while working on a form. Describe what you should do and what will happen when you click the notification.

*Answers are provided in Section 4.3.*

---

# Part 2: Role-Specific Training Paths

---

## 2.1 RECEPTIONIST Training

**Landing Page:** /app/patients
**Core Permissions:** patients:read, patients:write

---

### Module A: Patient Registration

**Learning Objectives**

Upon completing this module, the Receptionist will be able to:

1. Register a new patient accurately using all required fields.
2. Explain the OP number format and how it is assigned.
3. Identify optional fields and understand when they should be captured.
4. Confirm successful registration and locate the new patient record.

**Step-by-Step: Registering a New Patient**

1. From your landing page (/app/patients), click the **Register New Patient** button.
2. The patient registration form opens. Work through each field in order.
3. Enter the patient's **First Name** and **Last Name** exactly as they appear on their official identification document.
4. Enter the patient's **Date of Birth** using the date picker (format: DD/MM/YYYY or as directed by the form).
5. Enter the patient's **Gender** by selecting from the dropdown.
6. Enter the patient's **National ID Number** or **Passport Number**.
7. Enter the patient's **Primary Phone Number**. This is the number that will be used for M-Pesa STK push prompts if the patient makes mobile payments, so accuracy is critical.
8. Enter the patient's **Email Address** (if available).
9. Enter the patient's **Physical Address** / County.
10. Capture **Next of Kin** name and phone number.
11. Record any known **Allergies** in the allergies field. If the patient reports none, record "NKDA" (No Known Drug Allergies). Do not leave this field blank.
12. Capture **Insurance/NHIF** information if applicable.
13. Review all entered data with the patient for accuracy.
14. Click **Save Patient**.

**Required Fields**

The following fields are mandatory and the form will not submit without them:

- First Name
- Last Name
- Date of Birth
- Gender
- Primary Phone Number

**Optional Fields**

The following fields are strongly recommended but not system-enforced:

- National ID / Passport Number
- Email Address
- Physical Address
- Next of Kin
- Allergies
- Insurance details

**OP Number Generation**

Upon saving, the system automatically assigns the patient a unique Outpatient (OP) number. The format is:

```
OP-YEAR-NNNN
```

For example, the first patient registered in 2026 receives **OP-2026-0001**, the second receives **OP-2026-0002**, and so on. The NNNN counter is sequential within each calendar year. The OP number is displayed prominently on the patient record and confirmation screen. Provide this number to the patient — it is their unique identifier for all future visits to this facility.

**Confirmation**

After saving, you are redirected to the patient's profile page. Verify the OP number is displayed and all fields reflect the data entered. The record is now active in the system.

---

### Module B: Patient Search

**Step-by-Step: Searching for an Existing Patient**

1. From /app/patients, locate the **Search** bar at the top of the patient list.
2. You may search by any of the following:
   - **Full name or partial name** (e.g., "Wanjiku" will return all patients with that name)
   - **OP number** (e.g., "OP-2026-0042")
   - **National ID number**
   - **Phone number**
3. Type your search term and press Enter or click the search icon. Results appear in the list below.
4. If multiple results appear, review the patient card details (name, DOB, OP number) to confirm you have the correct patient before clicking.

**Reading the Patient Card**

Each patient card in the search results displays:

- Full name
- OP number
- Date of birth
- Gender
- Primary phone number
- Any active allergy flags (shown as an alert badge)

Click the patient card to open the full patient profile.

---

### Module C: Queue Management

**Adding a Patient to the Queue**

1. Open the patient's profile.
2. Click **Add to Queue**.
3. A queue entry dialog opens. Complete the following:

**Setting Acuity Level**

Select the appropriate acuity level. Acuity determines how urgently the patient needs to be seen:

| Acuity Level | Label | Meaning |
|---|---|---|
| 1 | Emergency | Highest priority — life-threatening or critical condition |
| 2 | Urgent | Needs prompt attention — cannot wait extended periods |
| 3 | Standard | Routine visit — can wait in normal queue order |

**Routing to Department**

Select the destination department from the dropdown. Available departments include:

- Triage
- Consultation
- Laboratory
- Pharmacy
- Billing
- Wards

Select the department that matches the patient's immediate care need. In most new walk-in cases, patients are first routed to **Triage**.

4. Add any queue notes if relevant (e.g., presenting complaint as reported by patient).
5. Click **Add to Queue**.

**How the Queue Sorts**

The queue is ordered first by **acuity level** (1-Emergency patients always appear before level-2, who appear before level-3), and then, within the same acuity level, by **time of arrival** (first in, first served). You cannot manually reorder patients within the same acuity level — the system enforces this order to ensure clinical equity and safety.

---

### Module D: Appointment Booking

**Finding Doctor Availability**

1. From the patient's profile or the Appointments section, click **Book Appointment**.
2. Select the **Doctor** from the dropdown. Only doctors registered in the system will appear.
3. Select the **Appointment Date** using the date picker.
4. Available time slots populate based on the doctor's schedule. Select a slot.

**Completing the Booking**

1. Confirm the **Appointment Type** (e.g., New Visit, Follow-Up, Procedure).
2. Add any relevant **Notes** (reason for visit, patient preferences).
3. Click **Confirm Appointment**.

**Appointment Status Lifecycle**

| Status | Meaning |
|---|---|
| Scheduled | Appointment created but not yet confirmed by the doctor or clinical team |
| Confirmed | Appointment has been acknowledged and confirmed |
| Completed | Patient attended and the encounter is concluded |
| Cancelled | Appointment was cancelled by staff or patient |
| No-Show | Patient did not attend without cancelling |

Update appointment statuses as events occur to maintain an accurate schedule record. Marking a patient as No-Show is important for scheduling analytics.

---

### Assessment: Receptionist

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question R-1**
A patient presents at reception and tells you their name is "James Mwangi." You search for this name and find three patients with the same name. Describe the steps you take to confirm you have the correct patient before adding them to the queue.

**Question R-2**
You have registered a patient named Fatima Hassan. After clicking Save, what OP number format should you expect the system to assign if this is the 87th patient registered in 2026?

**Question R-3**
A patient arrives in apparent distress, breathing rapidly, and states they have chest pain. You need to add them to the Consultation queue. What acuity level should you assign and why?

**Question R-4**
A doctor calls to say their afternoon schedule is blocked from 14:00 to 16:00 but all slots appear open in the system. A patient is standing in front of you needing a 14:30 appointment with that doctor. What should you do?

**Question R-5**
A patient calls to say they cannot make their appointment tomorrow. You update the appointment status to Cancelled. The same patient calls the next day saying they never cancelled — they said they might be late. What appointment status would have been more appropriate, and why?

**Question R-6**
You attempt to register a new patient and the Save button does not respond. The form highlights the Phone Number field in red. What is the most likely issue, and what information do you need from the patient?

**Question R-7**
A patient says they have been here before and asks if you can look them up by their "hospital number." What field in MediFleet corresponds to this, and what format should it be in?

**Question R-8**
After adding a patient to the queue for Triage at acuity level 2 (Urgent), another Urgent patient arrives 10 minutes later. In what order will the clinical team see these two Urgent patients, and what determines this?

*Answers are provided in Section 4.3.*

---

## 2.2 DOCTOR Training

**Landing Page:** /app/clinical
**Core Permissions:** patients:read, clinical:write

---

### Module A: The Clinical Queue

**Reading the Queue**

Your landing page (/app/clinical) displays the clinical consultation queue. Each row in the queue shows:

- Patient name and OP number
- Acuity level badge (color-coded: red = Emergency, orange = Urgent, blue = Standard)
- Time waiting (calculated from when they joined the queue)
- Assigned doctor (if claimed) or "Unassigned"
- Any allergy flags

**Acuity Sorting**

The queue is sorted identically to the reception queue: acuity level 1 (Emergency) patients always appear at the top, followed by level 2 (Urgent), then level 3 (Standard). Within each level, patients are ordered by time of arrival.

**Claiming an Unassigned Patient**

1. Locate an unassigned patient in the queue.
2. Click **Claim Patient** on their queue row.
3. The patient is now assigned to you and removed from the unassigned pool. Other doctors can see the patient is assigned to you.
4. The patient's allergy banner (if any allergies are recorded) will display prominently at the top of every clinical screen for that patient. Review this banner before prescribing anything.

---

### Module B: Creating a Clinical Encounter (SOAP Note)

**Opening an Encounter**

1. From the clinical queue, click on the patient's name or the **Open Encounter** button.
2. The encounter screen opens with the SOAP note form ready for input.

**Vitals Entry**

Before beginning the SOAP note, enter the patient's current vitals. All eight fields are available:

| Vital Sign | Format / Unit | Notes |
|---|---|---|
| Blood Pressure | Systolic/Diastolic (e.g., 120/80) | Must use slash-separated format |
| Heart Rate | bpm (beats per minute) | Numeric value only |
| Respiratory Rate | breaths per minute | Numeric value only |
| Temperature | °C | Decimal allowed (e.g., 37.5) |
| SpO2 | % (oxygen saturation) | Numeric value only |
| Weight | kg | Used for BMI calculation |
| Height | cm | Used for BMI calculation |
| BMI | Calculated automatically | Do not enter manually |

BMI is computed by the system from Weight and Height using the standard formula (weight in kg divided by height in metres squared). Do not attempt to enter BMI manually.

**The SOAP Structure**

The SOAP note is organized into four sections:

**S — Subjective**

1. **Chief Complaint (CC):** The patient's primary reason for the visit, in their own words. Keep concise (e.g., "chest pain for 3 hours").
2. **History of Present Illness (HPI):** Detailed narrative describing the onset, duration, character, associated symptoms, relieving and aggravating factors, and any prior treatment.
3. **Review of Systems (ROS):** Structured checklist of system-by-system symptoms. Stored as a JSON object — use the form checkboxes provided. Do not attempt to free-type JSON.

**O — Objective**

4. **Physical Examination (PE):** Your clinical findings from examining the patient. Document by system (General, Cardiovascular, Respiratory, Abdomen, etc.).

**A — Assessment**

5. **Diagnosis:** Your clinical diagnosis.
6. **ICD-10 Code:** The corresponding International Classification of Diseases code. Use the search field to look up codes — do not enter codes from memory.

**P — Plan**

7. **Treatment Plan:** Describe planned interventions, referrals, investigations, and management approach.
8. **Prescription Notes:** Medication orders. These notes are transmitted directly to the Pharmacy queue when the record advances. Write clearly: drug name, dose, route, frequency, and duration.
9. **Follow-Up Date:** Select a date for the next appointment if applicable.
10. **Internal Notes:** Free-text notes visible only to clinical staff. Billing and other non-clinical roles cannot see this field. Use for clinical reasoning, differential diagnoses, or staff-to-staff communication.

**Medical Record Status Flow**

A clinical encounter record follows this lifecycle:

```
Draft → Billed → Pharmacy → Completed
```

- **Draft:** Record is actively being worked on by the doctor.
- **Billed:** Record has been finalized and handed off to Billing for invoice generation.
- **Pharmacy:** Prescription has been transmitted to Pharmacy for fulfillment.
- **Completed:** All steps (billing and dispensing) have been completed.

---

### Module C: Ordering Lab Tests

1. From within an open encounter, navigate to the **Lab Orders** tab.
2. Click **Add Lab Test**.
3. Use the search field to find the test from the laboratory catalog.
4. Select the **Priority**:
   - **Routine:** Standard turnaround, non-urgent.
   - **Urgent:** Expedited processing required.
   - **STAT:** Highest priority — process immediately. Reserve for genuinely critical situations.
5. Add **Clinical Notes** to guide the laboratory technician (e.g., suspected diagnosis, relevant history).
6. To order multiple tests, click **Add Lab Test** again. All tests are submitted as a batch when you save the encounter or the orders section.

---

### Module D: Ordering Radiology

1. From within an open encounter, navigate to the **Radiology Orders** tab.
2. Click **Add Radiology Order**.
3. Select the **Examination Type** from the radiology catalog. The catalog entry will display:
   - **Modality** (e.g., X-Ray, CT, MRI, Ultrasound)
   - **Contrast required** flag — if contrast is indicated, inform the patient and note any contrast contraindications in the order.
   - **Patient preparation instructions** — if listed, communicate these to the patient and the relevant nursing staff.
4. Add clinical indication notes.
5. Save the order.

---

### Module E: Prescriptions

Prescription orders are entered in the **Prescription Notes** field of the SOAP note Plan section. When the encounter record transitions from **Draft** to **Billed**, the prescription notes are transmitted to the Pharmacy queue. The pharmacist will see the prescription attached to the patient's record and proceed with fulfillment.

Write prescription notes in full clinical format: Drug name (generic), dose, route, frequency, duration. Example: "Amoxicillin 500mg PO TDS for 7 days."

---

### Module F: Referrals

**Creating a Referral from an Encounter**

1. From within an open encounter, navigate to the **Referrals** tab.
2. Click **Create Referral**.
3. Complete the referral form:
   - **Referring to:** Specialty or specific facility.
   - **Reason for Referral:** Clinical summary and specific question for the receiving clinician.
   - **Urgency Level:**

| Urgency | Meaning |
|---|---|
| Routine | Standard referral — no immediate time pressure |
| Urgent | Should be seen within 24–48 hours |
| Emergency | Immediate transfer required |

4. Save the referral.

**Referral Status Tracking**

| Status | Meaning |
|---|---|
| Pending | Referral created but not yet sent |
| Sent | Referral transmitted to receiving facility or specialist |
| Accepted | Receiving party has confirmed acceptance |
| Completed | Patient has been seen by the receiving clinician |
| Cancelled | Referral was withdrawn |

You can view the status of all referrals for your patients from the Referrals section of each patient's profile.

---

### Module G: Medical History and KDPA Consent

**Viewing Longitudinal Medical History**

A patient's medical history module stores nine entry types:

1. Chronic Conditions
2. Previous Surgeries
3. Hospitalisations
4. Family History
5. Obstetric / Gynaecological History
6. Mental Health History
7. Immunisations
8. Allergies
9. Social History

**Sensitive Data Flag**

Certain categories of health information are classified as sensitive under KDPA (Kenya Data Protection Act 2019) and are flagged with `is_sensitive = True` in the system. The categories currently designated as sensitive are:

- Mental health records
- Obstetric / gynaecological records
- HIV-related records

Access to these records requires an additional consent verification step (see below). Sensitive records are not visible to all clinical staff — access is restricted to those with explicit authorization.

**Consent Verification Before Access**

Before the system allows you to view a patient's medical history (particularly sensitive records), it will prompt you to confirm that patient consent has been obtained. You must:

1. Confirm verbally with the patient that they consent to you viewing their historical records.
2. Acknowledge consent in the system when prompted.

Bypassing or falsely acknowledging consent is a serious KDPA violation. See Section 3.1 for full KDPA compliance guidance.

---

### Assessment: Doctor

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question D-1**
A patient in the clinical queue has been waiting for 45 minutes at acuity level 3 (Standard). A new patient arrives with acuity level 1 (Emergency). Where does the new patient appear in your queue, and what happens to the waiting patient's position?

**Question D-2**
You enter a patient's weight as 70 kg and height as 175 cm. The BMI field remains blank. What action should you take?

**Question D-3**
You are about to prescribe a penicillin-based antibiotic. The patient's chart shows an allergy banner at the top of the screen. Describe the steps you must take before proceeding with the prescription.

**Question D-4**
You have finished examining a patient and your clinical notes are complete. You click to advance the record status. A colleague asks why the pharmacist cannot yet see the prescription. What record status must be reached before the prescription appears in the pharmacy queue?

**Question D-5**
A patient requests that you not share their mental health history with the attending nurse. What system mechanism enforces this restriction, and what must you do before you can view this information yourself?

**Question D-6**
You are ordering a CT scan. When you select the exam from the catalog, a flag appears indicating "Contrast Required." What two actions should you take in response?

**Question D-7**
You need to refer a patient to a cardiologist at another facility immediately — the patient needs to be seen today. What urgency level should you select for this referral?

**Question D-8**
A patient's ICD-10 code field shows an error when you try to save the encounter. You entered "J18.9" from memory. What is the recommended approach to ICD-10 code entry?

**Question D-9**
You write clinical reasoning about a differential diagnosis that you do not want to appear on the billing invoice. In which SOAP field should this information be recorded?

**Question D-10**
You need to order a full blood count (FBC), liver function tests (LFTs), and a malaria rapid test for a patient presenting with fever. A fourth test — a blood culture — is genuinely time-critical. Describe how you should handle the priority assignments for these four tests.

*Answers are provided in Section 4.3.*

---

## 2.3 NURSE Training

**Landing Page:** /app/wards
**Core Permissions:** patients:read, wards:read, wards:write

---

### Module A: The Ward Board

The ward board at /app/wards displays a real-time grid of all beds in your assigned ward(s). Each bed is represented by a tile showing:

- Bed number
- Room / ward location
- Current status (indicated by both color and label)
- Patient name (if occupied)

**Bed Status Color Codes**

| Color | Status | Meaning |
|---|---|---|
| Green | Available | Bed is clean, ready, and may be assigned to a new patient |
| Orange | Occupied | Bed is currently assigned to an admitted patient |
| Red | Maintenance | Bed is out of service (e.g., equipment fault, repairs) |
| Yellow | Cleaning | Bed has been vacated and is awaiting cleaning before re-use |

These colors are consistent throughout the system. Never admit a patient to a bed that is not showing **Available (green)**.

---

### Module B: Admitting a Patient

1. Verify the patient has a valid encounter and an admission order from the attending doctor.
2. On the ward board, identify an **Available (green)** bed appropriate for the patient's needs.
3. Click the bed tile to open the bed detail panel.
4. Click **Admit Patient**.
5. Search for and select the patient by name or OP number.
6. Complete the required admission fields:
   - Admitting doctor
   - Admission reason / diagnosis
   - Any immediate nursing care instructions
7. Click **Confirm Admission**.
8. The bed status changes immediately from **Available (green)** to **Occupied (orange)**.

> **Important:** You may only admit a patient to an **Available** bed. The system will not permit selection of Occupied, Maintenance, or Cleaning beds in the admission workflow.

---

### Module C: Ward Consumables (FEFO)

Nurses routinely use consumable supplies from ward inventory during patient care.

**FEFO — First-Expire-First-Out**

The system enforces FEFO stock selection. When you log supply usage, the system automatically presents the batch with the earliest expiry date for selection first. Always dispense or use the batch presented at the top of the list. Using a later-expiry batch before an earlier one wastes stock and violates inventory management policy.

**Logging Supply Usage**

1. From the patient's ward record, navigate to the **Consumables** tab.
2. Click **Log Usage**.
3. Search for the supply item.
4. The system presents available batches ordered by expiry date (earliest first). Select the appropriate batch.
5. Enter the **Quantity Used**.
6. Click **Save**.

The system deducts the quantity from the selected batch's stock count.

**Reusable Items**

Some items in the ward catalog are flagged as reusable (e.g., certain monitoring probes, reusable containers). When you log usage of a reusable item:

- The item is recorded in the patient's usage log for clinical documentation purposes.
- Stock quantity is **not deducted** — the system recognizes these items are returned and sterilized for re-use.

The reusable flag is visible in the item detail. If you are unsure whether an item is consumable or reusable, check the item catalog entry before logging.

---

### Module D: Discharging a Patient

1. Confirm the attending doctor has written a discharge order in the patient's clinical record.
2. Navigate to the patient's bed on the ward board (the bed will show **Occupied/orange**).
3. Click the bed tile, then click **Discharge Patient**.
4. Enter **Discharge Notes** — this field is mandatory. Include:
   - Condition at discharge (e.g., "Improved, afebrile for 24 hours")
   - Any discharge instructions given to patient
   - Follow-up arrangements
   - Any take-home medication details if applicable
5. Click **Confirm Discharge**.
6. The bed status changes from **Occupied (orange)** to **Cleaning (yellow)**, indicating it must be cleaned before the next patient.
7. Once the bed has been cleaned and prepared, update the bed status to **Available (green)** using the **Mark Clean** action.

---

### Assessment: Nurse

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question N-1**
You need to admit a new patient to Ward 3. You look at the ward board and see the following beds: Bed 3A (orange), Bed 3B (red), Bed 3C (yellow), Bed 3D (green). Which bed can you use, and which beds are unavailable and why?

**Question N-2**
You are logging usage of sterile gauze pads. The system presents three batches: Batch A (expires Jan 2027), Batch B (expires Aug 2026), and Batch C (expires Mar 2028). Which batch should you select first, and what principle governs this choice?

**Question N-3**
A doctor verbally tells you to discharge a patient but has not yet written a discharge order in the system. What should you do before proceeding with the discharge?

**Question N-4**
You discharge a patient from Bed 5C. The ward board shows the bed is now yellow. Two hours later a new patient arrives needing admission. The bed is still showing yellow. Can you admit the new patient to Bed 5C? What must happen first?

**Question N-5**
You log the use of a blood pressure cuff (which is marked as reusable in the catalog) for a patient. After submitting, you check the inventory and the stock count has not decreased. Is this a system error?

**Question N-6**
While preparing discharge notes, you realize you do not know what follow-up the doctor ordered. The discharge notes field is mandatory. What is the appropriate action?

*Answers are provided in Section 4.3.*

---

## 2.4 PHARMACIST Training

**Landing Page:** /app/pharmacy
**Core Permissions:** pharmacy:read, pharmacy:manage

---

### Module A: Pharmacy Inventory

The pharmacy inventory screen displays all medication stock held in the Pharmacy spoke store.

**FEFO Sorting**

Stock is displayed and sorted by expiry date (earliest first), consistent with the FEFO (First-Expire-First-Out) principle. When filling prescriptions, you must always dispense from the earliest-expiry batch available. The system enforces this during the dispense workflow.

**Reorder Threshold Alerts**

Each item in the catalog has a defined reorder threshold. When current stock falls at or below this threshold, the item displays a reorder alert (typically a warning badge or color indicator on the inventory screen). Communicate low-stock alerts to your inventory manager or administrator promptly. Do not wait until stock runs out.

---

### Module B: Prescription Fulfillment

**Finding the Prescription**

1. From the pharmacy queue (/app/pharmacy), prescriptions that have been transmitted by the doctor appear as pending items.
2. Click the prescription to open it. You will see:
   - Patient name and OP number
   - Prescribing doctor
   - Prescription notes as entered by the doctor
   - Clinical encounter reference

**Selecting the Correct Batch (FEFO)**

1. For each medication in the prescription, click **Dispense**.
2. The system presents available batches for that medication ordered by expiry date (earliest first).
3. Select the batch at the top of the list (earliest expiry) unless it has insufficient quantity to fill the order, in which case move to the next batch.
4. If two batches are needed to fill a single prescription line, document both.

**Entering Quantity**

1. Enter the quantity to dispense exactly as prescribed.
2. Confirm the dose and formulation match the prescription.

**Idempotency Key**

Each dispense action carries an idempotency key generated by the system. This key prevents a duplicate dispense transaction if you accidentally click **Submit** more than once (e.g., due to a double-click or a slow network response). If you encounter a message stating "Transaction already processed," this is the idempotency protection functioning correctly — do not submit again. The medication has already been dispensed.

**Invoice Update**

When you complete a dispense, the patient's invoice is automatically updated to include the dispensed medication charge. You do not need to manually add this to the bill.

---

### Module C: OTC Sales

For over-the-counter medications sold without a prescription (e.g., walk-in patients purchasing paracetamol):

1. From the pharmacy screen, click **OTC Sale**.
2. You may optionally link the sale to a patient by entering their OP number. For anonymous walk-in sales, this field can be left blank.
3. Search for the medication in the catalog.
4. Select the batch (FEFO applies — earliest expiry first).
5. Enter the quantity.
6. Confirm the sale. A receipt can be generated.

---

### Module D: Stock Transfers

When pharmacy stock is running low, request a transfer from the Main Store (hub).

1. Navigate to the **Stock Transfers** tab.
2. Click **Request Transfer**.
3. Select the item(s) and quantity needed.
4. Submit the request.
5. The Main Store manager or administrator will review and fulfill the transfer. The transferred stock will appear in your pharmacy inventory once processed.

All transfers are tracked with a full audit trail (item, quantity, batch, requesting user, fulfilling user, timestamp).

---

### Assessment: Pharmacist

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question P-1**
You are filling a prescription for Metformin 500mg. The system shows three batches: Batch X (expires June 2026, 200 tablets), Batch Y (expires February 2026, 50 tablets), and Batch Z (expires December 2026, 300 tablets). The prescription requires 60 tablets. Which batch(es) should you dispense from and in what order?

**Question P-2**
You click the **Submit** button to dispense a prescription and nothing appears to happen. You click Submit again. A message appears: "Transaction already processed." What does this mean and what should you do?

**Question P-3**
A walk-in patient (not registered in the system) requests to buy antacid tablets. Describe the correct workflow for this sale.

**Question P-4**
After dispensing a medication, a colleague asks why the billing officer can already see the medication charge on the patient's invoice without the pharmacist manually entering it. Explain how this works.

**Question P-5**
The pharmacy shows a reorder alert for Amoxicillin 500mg capsules. There are still 15 capsules in stock. Is there a supply crisis? What is the appropriate action?

**Question P-6**
A prescription arrives for a medication that is out of stock in the pharmacy. The Main Store inventory shows it is available. What is the correct process?

*Answers are provided in Section 4.3.*

---

## 2.5 LAB TECHNICIAN Training

**Landing Page:** /app/laboratory
**Core Permissions:** laboratory:read, laboratory:write

---

### Module A: Lab Worklist

The lab worklist at /app/laboratory displays all pending test orders.

**Worklist Sort Order**

Tests are sorted by priority:

1. **STAT** — displayed first (must be processed immediately)
2. **Urgent** — displayed second
3. **Routine** — displayed last

Within each priority group, tests are sorted by time of order (earliest first).

**Requires Barcode Flag**

Some tests in the catalog are flagged as `requires_barcode = True`. For these tests, a specimen ID or barcode label must be generated or manually entered at the time of specimen collection. Check this flag on each order before collecting the specimen.

**Reading Patient and Clinical Information**

Each worklist entry shows:

- Patient name and OP number
- Test name and priority
- Ordering doctor
- Clinical notes provided by the doctor
- Time of order

Review clinical notes before processing — they may indicate specific collection requirements or relevant patient history.

---

### Module B: Specimen Collection

1. Identify the test order in the worklist.
2. Confirm the patient's identity using at least two identifiers (name and OP number).
3. If `requires_barcode = True`, generate or affix a barcode label to the specimen container and enter the specimen ID in the system.
4. Collect the specimen using the appropriate technique for the test type.
5. Click **Mark Collected** on the worklist entry.
6. The test status changes from **Pending** to **In Progress**.

---

### Module C: Entering Results

**Step-by-Step: Completing a Test**

1. From the worklist, open the **In Progress** test entry.
2. The results form displays all parameters for the test, auto-populated from the catalog definition. You will see:
   - Parameter key and name
   - Expected unit of measure
   - Value type (Number, Text, or Choice)
   - Reference range (for numeric parameters)
3. Enter the result value for each parameter.
4. Parameters with numeric results that fall outside the reference range are automatically highlighted in **red**. Do not suppress or ignore these flags — they indicate clinically significant values.
5. Add **Technician Notes** for any relevant observations (e.g., haemolyzed specimen, sample quality issues, repeat testing performed).

**Reagent Consumption Logging**

1. After entering results, navigate to the **Reagents Used** section.
2. For each reagent consumed during the test:
   - Select the reagent from the catalog.
   - Select the batch (FEFO — earliest expiry first).
   - Enter the quantity consumed.
3. Click **Add Reagent**.
4. Reusable items (e.g., certain calibration standards): log their use for documentation; stock quantity will not be deducted.

**Completing the Test**

1. Review all entered results and reagent consumption.
2. Click **Complete Test**.
3. The test status changes from **In Progress** to **Completed**.
4. The ordering doctor receives a real-time notification via the WebSocket notification system.
5. Results are immediately visible to authorized clinical staff on the patient's record.

---

### Module D: Lab Catalog Management

The laboratory catalog defines available tests, their parameters, and their bill of materials.

**Adding a New Test**

1. Navigate to the **Catalog** tab in the laboratory section.
2. Click **Add Test**.
3. Enter:
   - **Test Name** (e.g., "Full Blood Count")
   - **Test Code** (e.g., "FBC")
   - **Department / Category** (e.g., Haematology)
   - **Default Priority** (Routine, Urgent, or STAT)
   - **Requires Barcode:** Yes or No
   - **Base Price** (can be updated later via the Pricing tab)

**Adding Parameters**

Each test is made up of one or more reportable parameters. For each parameter:

1. Click **Add Parameter**.
2. Enter:
   - **Parameter Key** — unique identifier (e.g., "wbc_count")
   - **Parameter Name** — human-readable label (e.g., "White Blood Cell Count")
   - **Unit** — unit of measure (e.g., "×10⁹/L")
   - **Value Type** — select from:
     - **Number:** For quantitative results (e.g., 7.2)
     - **Text:** For qualitative or narrative results (e.g., "Positive", free text)
     - **Choice:** For results from a defined pick list (e.g., "Reactive / Non-Reactive")
   - **Reference Low / Reference High** — normal range boundaries (for Number type only). Results outside this range will be flagged in red.
3. Save the parameter.

**Bill of Materials (BOM)**

The Bill of Materials defines which reagents are consumed when performing this test. Adding a BOM allows the system to automate reagent deduction when results are entered.

1. From the test detail, navigate to the **Bill of Materials** tab.
2. Click **Add Material**.
3. Select the reagent item and enter the expected quantity per test.

---

### Assessment: Lab Technician

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question L-1**
Your worklist shows four pending tests ordered at the same time: a routine urine microscopy, a STAT blood culture, an urgent malaria rapid test, and a routine lipid profile. In what order should you process them?

**Question L-2**
You are about to collect a blood specimen for a liver function test. You notice the order is flagged `requires_barcode = True`. What two actions must you take before you can mark the specimen as collected?

**Question L-3**
You enter a haemoglobin result of 6.2 g/dL (reference range: 12.0–17.5 g/dL). The value is highlighted in red on the form. What does this indicate, and what should you do?

**Question L-4**
After completing a STAT test, you try to log reagent usage and realize you used a new box of reagent instead of the box that was already open (which expires sooner). What FEFO principle have you violated, and what is the correct procedure going forward?

**Question L-5**
You are adding a new test to the catalog: "HIV Antibody Test." The result is either "Reactive" or "Non-Reactive." What value type should you select for the result parameter?

**Question L-6**
A doctor calls to say they have not received a result notification for a patient whose test you processed an hour ago. You check the worklist and the test status shows "In Progress." What is the likely cause, and what should you do?

*Answers are provided in Section 4.3.*

---

## 2.6 RADIOLOGIST Training

**Landing Page:** /app/radiology
**Core Permissions:** radiology:read, radiology:manage

---

### Module A: Radiology Worklist

The radiology worklist at /app/radiology displays all pending imaging requests.

**Reading Pending Requests**

Each entry shows:

- Patient name and OP number
- Examination type and modality (e.g., Chest X-Ray, CT Abdomen with contrast)
- Ordering doctor and clinical indication
- Time of order
- **Contrast Required** flag
- **Patient Preparation Instructions** (if applicable, sourced from the catalog)

Review the contrast and preparation flags before calling the patient in. Ensure any required preparation (e.g., fasting, bowel prep) has been completed. If preparation is incomplete, do not proceed — return the patient and document the reason.

---

### Module B: Completing an Exam

1. Open the pending examination from the worklist.
2. Verify patient identity using at least two identifiers.
3. Confirm any preparation requirements have been met.
4. Conduct the examination.
5. In the **Report** section, complete the following fields:

**Findings**

The findings field may be pre-populated with a default template from the catalog (e.g., a structured chest X-ray report template). Use the template as a starting structure and overwrite the placeholder text with your actual observations. Document findings systematically by region or organ system.

**Conclusion / Impression**

Summarize your diagnostic interpretation. This is the most clinically critical part of the report — be clear and specific.

**Image URL**

Enter the URL or reference path to the stored images (PACS or image storage system reference). This links the report to the actual images.

**Contrast Used**

If contrast was administered:
- Toggle the **Contrast Used** flag to Yes.
- Document the contrast agent, volume administered, and any adverse reactions.

6. Click **Complete Examination**.
7. The examination status changes from **Pending** to **Completed**.
8. The ordering doctor receives a real-time notification.

---

### Module C: Radiology Catalog Management

**Adding a New Examination Type**

1. Navigate to the **Catalog** tab.
2. Click **Add Examination Type**.
3. Enter:
   - **Examination Name** (e.g., "CT Chest with Contrast")
   - **Modality** — select from available options (e.g., X-Ray, CT, MRI, Ultrasound, Fluoroscopy, Nuclear Medicine)
   - **Requires Contrast:** Yes or No
   - **Patient Preparation Required:** Yes or No; if Yes, enter the preparation instructions text
   - **Default Report Template:** Enter a structured template that will pre-populate the Findings field for this exam type
   - **Base Price**

---

### Assessment: Radiologist

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question Rad-1**
A patient arrives for a CT abdomen with contrast. You check the worklist and see the "Contrast Required" flag is set. The patient tells you they had a severe allergic reaction to contrast dye three years ago. What should you do?

**Question Rad-2**
You open an examination report and find the Findings field is already partially filled with structured text. A colleague says the system must have made an error. Explain what has actually happened.

**Question Rad-3**
You complete a chest X-ray report and click Complete Examination. What happens immediately in the system, and who is notified?

**Question Rad-4**
You are adding a new examination type to the catalog: "MRI Brain without contrast." The default report template field is left blank. What is the consequence for radiologists who later receive orders for this examination?

*Answers are provided in Section 4.3.*

---

## 2.7 BILLING OFFICER Training

**Landing Page:** /app/billing
**Core Permissions:** billing:manage

---

### Module A: The Billing Queue

The billing queue at /app/billing lists all patient invoices requiring action.

**Invoice Status Meanings**

| Status | Meaning |
|---|---|
| Pending | Invoice generated; no payment received |
| Partially Paid | One or more payments received but total amount not yet settled |
| Pending M-Pesa | An M-Pesa STK push has been triggered; awaiting mobile network callback |
| Paid | Invoice fully settled |
| Cancelled | Invoice voided (typically by an administrator) |

**Sorting**

The billing queue is typically sorted with outstanding invoices (Pending, Partially Paid, Pending M-Pesa) at the top, and settled invoices (Paid, Cancelled) below. Use the filter controls to narrow the list by status, date range, or patient name.

---

### Module B: Cash and Card Payments

1. Open the patient's invoice from the billing queue.
2. Review the invoice line items (consultation, lab tests, medications, radiology, etc.).
3. Confirm the amount tendered or charged by the patient.
4. Click **Record Payment**.
5. Select **Payment Method:** Cash or Card.
6. Enter the **Amount Received**.

**Idempotency Key**

Each payment submission carries an idempotency key. If you click **Submit** more than once (e.g., network lag causes you to double-click), the system will process the payment only once and return a "Transaction already processed" message on the second attempt. Do not resubmit.

**Partial Payments**

If the patient is paying part of the total:

1. Enter the partial amount in the Amount field.
2. Submit. The invoice status updates to **Partially Paid**.
3. Repeat the payment recording process for subsequent payments.
4. When the final payment brings the balance to zero, the invoice status automatically updates to **Paid**.

---

### Module C: M-Pesa STK Push

M-Pesa payments are initiated as an STK (SIM Toolkit) push — a prompt is sent directly to the patient's mobile phone.

1. Open the invoice.
2. Click **Pay via M-Pesa**.
3. Enter the patient's phone number. The system accepts numbers in 07XXXXXXXX format — it automatically normalizes the number to the international format **2547XXXXXXXX** before transmitting to the M-Pesa API. Do not manually change the format.
4. Click **Send STK Push**.
5. The invoice status changes to **Pending M-Pesa**.
6. Instruct the patient to check their phone, enter their M-Pesa PIN when prompted, and confirm the transaction.
7. Once the patient completes the payment on their phone, the M-Pesa callback is received by the system automatically.
8. The invoice status updates to **Paid** (or **Partially Paid** if partial) and the M-Pesa receipt number is recorded on the invoice.

> **Note:** Do not manually update the invoice status while it is showing "Pending M-Pesa." The callback will update it automatically. If the status does not update within 5 minutes, the patient may not have confirmed the payment or the network timed out. You may retry or use an alternative payment method.

---

### Module D: Cheques

**Drawer Types**

Cheques may be received from individual patients or from insurance companies and corporate accounts. The system records the **drawer type** to categorize the source.

**The Full Cheque Lifecycle**

```
Received → Deposited → Cleared
                    → Bounced
                    → Cancelled
```

1. **Received:** When a patient presents a cheque, click **Record Cheque**. Enter:
   - Cheque number
   - Drawer name and type
   - Bank name
   - Cheque amount
   - Date on cheque
2. The cheque status is set to **Received**.
3. When the cheque is physically taken to the bank, click **Mark Deposited**. Status becomes **Deposited**.
4. After the bank clears the funds:
   - If cleared: click **Mark Cleared**. Status becomes **Cleared** and the system automatically posts a payment against the invoice.
   - If the cheque is returned unpaid: click **Mark Bounced**. You must enter a **bounce_reason** (this field is mandatory). The invoice payment is reversed.
5. If a cheque must be voided before deposit, click **Cancel**. Status becomes **Cancelled**.

**Handling a Bounced Cheque**

When a cheque bounces:
1. Mark the cheque as Bounced and enter the bounce reason (e.g., "Refer to Drawer," "Insufficient Funds").
2. The invoice returns to its previous payment status.
3. Contact the patient or organization to arrange an alternative payment method.
4. Document the bounce in the notes field for audit purposes.

---

### Assessment: Billing Officer

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question B-1**
A patient's invoice shows a total of KES 4,500. They pay KES 2,000 in cash today. What invoice status should you expect after recording this payment?

**Question B-2**
You click "Submit" to record a payment and nothing appears to happen. You click Submit a second time and receive a message: "Transaction already processed." What should you do, and what does this message mean?

**Question B-3**
A patient wants to pay via M-Pesa. Their registered phone number is 0712 345 678. What number format does the system actually transmit to M-Pesa, and do you need to change anything before sending the STK push?

**Question B-4**
An invoice has been showing "Pending M-Pesa" for 8 minutes. The patient is still at the counter. What steps should you take?

**Question B-5**
An insurance company submits a cheque for KES 15,000. The cheque clears. What happens to the corresponding invoice automatically, and what action do you need to take in the billing system to trigger this?

**Question B-6**
A cheque is returned by the bank. When you click "Mark Bounced," the system will not save without additional input. What mandatory field is blocking the save, and why is it important?

*Answers are provided in Section 4.3.*

---

## 2.8 ADMIN Training

**Landing Page:** /app/admin
**Core Permissions:** users:manage

---

### Module A: Command Center

The Admin dashboard at /app/admin provides a centralized control panel for facility management.

**KPI Tiles**

The top section of the dashboard displays key performance indicator (KPI) tiles showing:

- Total registered patients
- Active staff accounts
- Today's appointments
- Open invoices (Pending/Partially Paid)
- Any pending alerts (low stock, lockout events, etc.)

**Tab Navigation**

The admin dashboard is organized into functional tabs. Navigation between tabs does not require a page reload. Common tabs include: Staff, Departments, Roles & Permissions, Audit Logs, Configuration, Pricing, and Modules.

---

### Module B: Staff Management

**Creating a New Staff Account**

1. Navigate to the **Staff** tab.
2. Click **Add Staff Member**.
3. Complete the required fields:
   - **Email Address** (will be used as login username)
   - **First Name** and **Last Name**
   - **Role** — select from the defined system roles
   - **Specialization** (for clinical staff, e.g., "Cardiologist", "Paediatric Nurse")
   - **License Number** (professional registration number as applicable)
   - **Department** (assign to the relevant department)
4. Click **Create Account**.
5. The system generates a temporary password and sets `must_change_password = True` by default. The staff member will be forced to change their password on first login.
6. Communicate the temporary password to the new staff member through a secure channel.

> **Security Note:** Never send temporary passwords via unencrypted email. Use an in-person handover, secure SMS, or a password manager-shared secret.

**Deactivating a Staff Account**

When a staff member leaves the organization or should no longer have system access:

1. Locate the staff member in the Staff list.
2. Click **Deactivate**.
3. The account is immediately suspended — the user cannot log in, and any active sessions are invalidated.
4. Deactivated accounts are retained in the system for audit and historical record purposes. Patient records created by the user are preserved.

**Reactivating a Staff Account**

If a staff member returns (e.g., from extended leave):

1. Locate the deactivated staff member.
2. Click **Reactivate**.
3. The account is restored. Set `must_change_password = True` and communicate a new temporary password.

---

### Module C: RBAC and Permission Overrides

MediFleet uses Role-Based Access Control (RBAC) with the ability to apply individual permission overrides.

**Permission Codename Scheme**

Permissions follow the format: `resource:action`. Examples:

- `patients:read` — view patient records
- `patients:write` — create or edit patient records
- `clinical:write` — create clinical encounters
- `billing:manage` — manage billing and payments
- `users:manage` — manage staff accounts

**Effective Permissions Formula**

A user's effective access is calculated as:

```
Effective Permissions = (Role Permissions ∪ Explicit Grants) − Explicit Revokes
```

- **Role Permissions:** All permissions assigned to the user's role by default.
- **Explicit Grants:** Individual permissions added to this specific user that are not part of their role.
- **Explicit Revokes:** Individual permissions removed from this specific user that would otherwise be provided by their role.

This means you can expand a specific user's access beyond their role (via grants) or restrict a specific user below their role's default (via revokes) without changing the role definition itself.

**Using the UserPermissionsEditor**

1. Navigate to the Staff member's detail page.
2. Click the **Permissions** tab to open the UserPermissionsEditor.
3. The editor displays three sections:
   - **Role Permissions** (read-only — shows what the role provides)
   - **Explicit Grants** — add individual permissions here
   - **Explicit Revokes** — add individual permission removals here
4. Save changes. The user's effective permissions update immediately.

---

### Module D: Departments

**Creating a Department**

1. Navigate to the **Departments** tab.
2. Click **Add Department**.
3. Enter:
   - Department name (e.g., "Paediatrics", "Radiology")
   - Description
4. Click **Save**.

> **Automatic Channel Creation:** When a department is created, the system automatically creates a corresponding department messaging channel. All members added to the department will have access to this channel.

**Managing Department Membership**

1. Open the department detail.
2. Click **Manage Members**.
3. Add staff members by searching for their name or email.
4. Remove members as needed.
5. Changes take effect immediately — the staff member's sidebar will show or hide the department channel accordingly.

---

### Module E: M-Pesa Configuration

This module requires the M-Pesa optional module to be active for your hospital.

1. Navigate to **Configuration → M-Pesa**.
2. Enter the following credentials (provided by Safaricom for your organization):
   - **Paybill Number** — your organization's M-Pesa paybill or till number
   - **Consumer Key** — from the Daraja API portal
   - **Consumer Secret** — from the Daraja API portal
   - **Passkey** — from Safaricom
   - **Account Reference** — maximum 12 characters; this appears on the customer's M-Pesa statement
3. All credentials are encrypted at rest using AES encryption — they are never stored in plain text.
4. Toggle **Active** to enable M-Pesa for your facility.
5. Run a test transaction using the test credentials before going live.

---

### Module F: Lab Pricing

Laboratory test prices are managed separately from the test catalog.

1. Navigate to the **Pricing** tab.
2. Locate the test you want to update.
3. Click **Edit Price**.
4. Enter the new `base_price` value.
5. Save. The new price applies immediately to new orders — existing invoices are not retroactively updated.

---

### Module G: Audit Logs

MediFleet maintains a comprehensive audit trail of all significant actions performed in the system.

**Reading the Audit Log**

1. Navigate to the **Audit Logs** tab.
2. Each log entry shows:
   - **Timestamp** — when the action occurred
   - **User** — who performed the action
   - **Action** — what was done (e.g., "Patient Updated", "Role Permission Revoked")
   - **Resource** — the record that was affected
   - **Old Value** (JSONB) — the data before the change
   - **New Value** (JSONB) — the data after the change

**Filtering**

Use the filter controls to narrow logs by:
- Date range
- User (staff member)
- Action type
- Resource type

**Understanding Old Value / New Value**

The `old_value` and `new_value` fields store data as JSON objects. For example, a change to a patient's phone number might show:

```json
old_value: {"phone": "0712345678"}
new_value: {"phone": "0798765432"}
```

This provides an unambiguous record of exactly what changed. Audit logs cannot be edited or deleted by any user, including administrators.

---

### Assessment: Admin

Attempt each scenario independently before reviewing the Answer Key in Section 4.3.

**Question A-1**
A new nurse joins the hospital. When you create their account, is it correct that they will need to change their password before they can access the system? What system setting ensures this?

**Question A-2**
A doctor needs read access to the billing module to review their patients' outstanding invoices, but they should not be able to modify or settle payments. Their current role (DOCTOR) does not include any billing permissions. How do you grant this limited access without changing the DOCTOR role definition?

**Question A-3**
You need to revoke the `patients:write` permission from a specific receptionist who should now only view records, not create or edit them. Walk through the steps using the UserPermissionsEditor. Will this affect other receptionists?

**Question A-4**
The finance manager asks you to find all payment-related changes made by user "Sarah Kamau" in the last 30 days. Which part of the admin interface do you use, and what filters do you apply?

**Question A-5**
You create a new department called "Physiotherapy." A staff member in that department immediately messages you saying they cannot find the Physiotherapy channel in their messaging inbox. What are the two most likely causes?

**Question A-6**
Your hospital is about to go live with M-Pesa payments. You have entered the Paybill, Consumer Key, Consumer Secret, and Passkey. The Account Reference field currently reads "KenyaGeneralHospitalNairobi". What issue do you need to correct before saving?

**Question A-7**
A staff member's account has been deactivated. A request comes in to retrieve a patient record created by that former staff member. Is the record still accessible?

**Question A-8**
You review an audit log entry and see: `old_value: {"role": "NURSE"}`, `new_value: {"role": "DOCTOR"}`. What does this entry tell you, and why is this information significant from a security perspective?

*Answers are provided in Section 4.3.*

---

## 2.9 PATIENT (Patient Portal) Training

**Landing Page:** /patient
**Authentication:** OP number + Date of Birth + Last 4 digits of registered phone number

---

### Module A: Accessing the Portal

The MediFleet patient portal gives you secure, direct access to your own health records.

**Three-Factor Verification**

To protect your privacy, the portal uses a three-factor verification system. You will need all three pieces of information to log in:

1. **Your OP Number** — your unique patient identifier assigned at your first registration. Format: OP-YEAR-NNNN (e.g., OP-2026-0042). You will find this on any receipt, appointment card, or letter from the facility.
2. **Your Date of Birth** — as registered with the facility.
3. **Last 4 digits of your registered phone number** — the mobile number you provided when you registered as a patient.

If any one of these three factors is incorrect, access will be denied. Contact the reception desk if you cannot locate your OP number.

**Session Duration**

Your portal session is active for **60 minutes**. After 60 minutes of inactivity, you will be automatically logged out and will need to verify again to re-enter. This limit exists to protect your health information if you leave a shared device unattended.

---

### Module B: Viewing Your Record

The patient portal is a **read-only** view of your health information. You cannot edit, add, or delete any records through the portal.

**What You Can View**

1. **Appointments** — upcoming and past appointments at this facility, including status (Scheduled, Confirmed, Completed, Cancelled, No-Show).
2. **Invoices** — your billing history, payment status, and amounts.
3. **Medical History** — general medical history entries that have been recorded by the clinical team and are not classified as sensitive.

**What Is Not Shown**

Records flagged as sensitive (`is_sensitive = True`) are not displayed in the patient portal. These include:

- Mental health records
- Obstetric / gynaecological records
- HIV-related records

These restrictions exist to protect your most private health information from inadvertent disclosure. If you need to discuss these records, please do so directly with your care team.

---

### Assessment: Patient

Attempt each scenario independently. Answers are provided in Section 4.3.

**Question Pat-1**
You try to log in to the patient portal with your OP number and date of birth but you cannot remember which phone number you registered with. You try several last-4-digit combinations. What will happen after multiple failed attempts, and what is the correct course of action?

**Question Pat-2**
You log in and can see your last blood test results from your general checkup but cannot see any records related to your mental health consultation from last month. Is this a system error?

**Question Pat-3**
You logged into the portal on a shared hospital computer. You finished viewing your records but did not log out. What protection does the system provide in this situation?

*Answers are provided in Section 4.3.*

---

## 2.10 SUPERADMIN Training

**Landing Page:** /superadmin/dashboard
**Authentication:** Bearer token (separate from hospital-level JWT cookies)

The Superadmin role operates at the platform level — above any individual hospital tenant. Superadmins can see across all tenants and manage platform-wide configuration. This role should be held by an absolute minimum number of individuals, and all actions are logged.

---

### Module A: Tenant Management

**Provisioning a New Hospital Tenant**

1. Navigate to **Tenant Management** on the superadmin dashboard.
2. Click **Provision New Tenant**.
3. Enter the hospital's details:
   - Hospital name
   - Contact email (for the initial admin account)
   - Subscription plan
4. Click **Provision**.
5. The system performs the full provisioning sequence:
   a. Creates an isolated PostgreSQL database for the new hospital.
   b. Runs schema migrations to set up all tables.
   c. Seeds the initial RBAC configuration (default roles and permissions).
   d. Creates the initial Admin user account.
   e. Generates and displays a **temporary password** — this is shown **once only**. Copy it immediately and transmit it securely to the hospital's designated administrator.
6. The new tenant is created in an **Inactive** state by default.

**Activating and Deactivating Tenants**

- **Activate:** Click **Activate** on the tenant record. Users at the hospital can now log in.
- **Deactivate:** Click **Deactivate**. All user sessions at that hospital are immediately terminated. No data is deleted — the database is preserved. Reactivation restores full access.

---

### Module B: Module Entitlements

**Feature Flags JSON Structure**

Each tenant's module access is controlled by a `feature_flags` JSON object stored against the tenant record. Each optional module appears as a key with a boolean value. Example:

```json
{
  "clinical": true,
  "laboratory": true,
  "radiology": false,
  "pharmacy": true,
  "billing": true,
  "mpesa": false,
  "patient_portal": true,
  "analytics": false
}
```

**Always-On vs Optional Modules**

Always-on modules (patients, appointments, dashboard, settings, support, messaging, notifications, users, auth) do not appear in the feature_flags object — they are always enabled and cannot be disabled.

Optional modules appear in feature_flags. Setting a module to `false` will render the 402 screen for all users at that hospital who attempt to access that module.

**Plan Limits**

Each subscription plan may include numeric limits (e.g., maximum number of active staff accounts, maximum patient records). These are stored in a `plan_limits` object on the tenant record. Review plan limits before activating a new tenant to ensure the limits match the contracted plan.

**Cache Propagation Delay**

Feature flag changes are cached for performance. After updating a tenant's feature flags, allow up to **60 seconds** for the change to propagate to all active user sessions at that hospital. If a hospital admin reports that a newly enabled module is still showing the 402 screen, advise them to wait 60 seconds and refresh.

---

### Module C: Platform Visibility

**Cross-Tenant Patient Search**

Superadmins can search for a patient across all hospital tenants. Use this capability only when operationally necessary (e.g., support escalation). Every cross-tenant search is logged with the searching superadmin's identity, timestamp, and reason.

**Support Inbox**

The superadmin dashboard includes a platform-wide support inbox. Hospital admins and staff can submit support requests that appear in this inbox. Respond to and close tickets from this view.

**Platform Billing**

The platform billing view shows subscription status and billing records for all tenants. This is used by the platform operations team to manage subscription renewals, usage-based billing, and plan upgrades.

---

### Module D: Branding Management

Hospitals with the Branding module active can customize the visual appearance of their MediFleet instance. Superadmins manage the branding configuration at the tenant level.

**Logo and Background Images**

- Accepted format: Base64-encoded image strings.
- Maximum file size: **1.2 MB** per image (after base64 encoding). Images exceeding this limit will be rejected.
- Recommended formats: PNG for logos (transparent background), JPEG for background images.

**Brand Colors**

- **brand_primary:** The primary brand color used for buttons, active navigation items, and key UI elements. Must be a valid hex color code (e.g., `#1A73E8`).
- **brand_accent:** The secondary accent color used for highlights and secondary actions. Must also be a valid hex color code.

Test color combinations for accessibility contrast ratios. Light text on dark backgrounds (or vice versa) should meet WCAG AA standards.

**Print Templates**

The branding module includes customizable print templates for prescriptions, invoices, and patient summary documents. Templates use the hospital's logo, brand colors, and contact details.

---

### Assessment: Superadmin

Attempt each scenario independently. Answers are provided in Section 4.3.

**Question S-1**
You provision a new hospital tenant. At the end of the provisioning process, a temporary password is displayed. What must you do immediately, and what happens if you navigate away from this screen without copying it?

**Question S-2**
A hospital administrator calls to say their billing module suddenly shows the 402 screen for all billing staff, starting this morning. You check the tenant record and see that `"billing": false` in the feature_flags. You set it back to `true`. The administrator calls back 30 seconds later and says the 402 is still showing. Is there a system error?

**Question S-3**
A hospital's subscription plan includes a maximum of 50 active staff accounts. The hospital's administrator has been creating accounts and now has 48 active accounts. They ask you if they can add 10 more. How do you verify whether this is possible?

**Question S-4**
A hospital wants to upload a high-resolution logo that is 1.8 MB as a base64 string. What will happen when you attempt to save it, and what should you advise the hospital's administrator?

**Question S-5**
You use the cross-tenant patient search to find a patient record at a specific hospital. Aside from finding the record, what else does this action generate in the system?

*Answers are provided in Section 4.3.*

---

# Part 3: Cross-Cutting Topics

---

## 3.1 KDPA Compliance for All Clinical Staff

**Who must complete this section:** All clinical staff — Doctors, Nurses, Pharmacists, Laboratory Technicians, Radiologists.

### What Is the Kenya Data Protection Act (KDPA) 2019?

The KDPA (Kenya Data Protection Act 2019) governs how personal and health data is collected, stored, used, and shared. Health data is classified as sensitive personal data under the Act and receives the highest level of protection. Non-compliance can result in individual criminal liability, institutional fines, and reputational harm to your facility.

### Consent Workflow

Before accessing a patient's medical history — particularly sensitive records — MediFleet requires you to confirm that patient consent has been obtained.

1. When you attempt to access the medical history section, the system prompts: "Confirm that patient consent has been obtained for accessing this record."
2. Verbally confirm with the patient that they agree to you viewing their historical information.
3. Acknowledge consent in the system.
4. Proceed.

Never acknowledge consent in the system if you have not actually obtained it from the patient. False consent acknowledgement is a KDPA violation and a professional misconduct issue.

### Sensitive Data Restrictions

The following three categories are flagged `is_sensitive = True` and are subject to additional access restrictions:

- **Mental health records**
- **Obstetric / gynaecological records**
- **HIV-related records**

Access to sensitive records is limited to authorized personnel only. If you attempt to access a sensitive record without the appropriate authorization, the system will deny access. Do not attempt to access sensitive records outside the scope of your clinical role.

### DataAccessLog

Every time you view a patient's record, the system automatically creates a **DataAccessLog** entry recording:

- Which user accessed the record
- Which patient's record was accessed
- The timestamp of access
- The reason/context (if captured)

You cannot suppress or delete DataAccessLog entries. This log is available to administrators and auditors.

### Data Subject Access Request (DSAR)

A patient has the right under KDPA to request a copy of all data held about them (a Data Subject Access Request, or DSAR). If a patient submits a DSAR:

1. Direct them to your facility's Privacy Officer or System Administrator.
2. Do not attempt to compile or share data yourself without formal authorization.
3. The facility must respond to a DSAR within the timelines prescribed by the Act.

### Right to Erasure

Under KDPA, a patient may request erasure of their personal data. In MediFleet, **erasure is implemented as pseudonymization** — not as hard deletion. This means:

- Identifying information (name, ID number, contact details) is replaced with anonymous tokens.
- Clinical records (diagnoses, test results, treatment history) are preserved for medical and legal purposes but are no longer linkable to the individual.
- Hard deletion of clinical records is not permitted under healthcare records retention laws.

### Breach Notification

If a data breach occurs (unauthorized access, loss of data, ransomware, etc.):

1. Immediately notify your facility's Data Protection Officer (DPO) or system administrator.
2. The facility is legally required to notify the **Office of the Data Protection Commissioner (ODPC)** within **72 hours** of becoming aware of the breach (KDPA Section 43).
3. Affected individuals must also be notified where the breach is likely to result in high risk to their rights.

Do not delay reporting a suspected breach. Time is of the essence.

---

## 3.2 Data Security for All Staff

### Never Share Credentials

Your login credentials (email and password) are personal and non-transferable. You must never:

- Share your password with a colleague, even temporarily.
- Allow another person to use your logged-in session.
- Use a colleague's credentials to perform actions on their behalf.

All actions performed under your credentials are attributed to you in the audit log. You are accountable for everything done under your account.

### Automatic Session Management

MediFleet manages your session automatically using two tokens:

- **Access Token** — valid for 15 minutes. Refreshed automatically in the background when you are active.
- **Refresh Token** — valid for 7 days. Used to issue new access tokens. Rotated on each use.

You do not need to manually manage tokens. However, if you are inactive for an extended period, you may be prompted to re-authenticate.

### Refresh Token Reuse Detected

If you see the message **"Refresh token reuse detected"** when attempting to use the system:

1. **Stop immediately.** This message means your refresh token has already been used — which may indicate your session has been hijacked by an unauthorized person.
2. Log out of all sessions.
3. Change your password immediately.
4. Report the incident to your system administrator as a potential security breach.

This is not a normal error message — treat it as a security incident every time.

### CSRF Tokens

MediFleet uses CSRF (Cross-Site Request Forgery) double-submit cookie protection on all state-changing requests. This protection operates automatically in the background — you do not need to take any action. Do not attempt to disable or work around browser security features, as these protections are part of the system's security posture.

---

## 3.3 Internal Messaging

MediFleet includes an integrated messaging system for communication between staff.

**Channel Types**

| Type | Description |
|---|---|
| Direct Message (DM) | One-to-one conversation between two staff members |
| Group | A named conversation with multiple selected participants |
| Department Channel | Automatically created when a department is created; all department members are included |

**Accessing Messages**

Navigate to the **Messages** section from your sidebar. Your inbox shows all channels you belong to.

**Unread Count**

The unread message count displayed next to each channel is calculated as the number of messages received since your `last_read_at` timestamp for that channel. Opening a channel marks it as read.

**Real-Time Delivery**

Messages are delivered in real time via the WebSocket connection established at login. You do not need to refresh the page — new messages appear instantly.

**Professionalism Note**

The messaging system is for professional clinical and operational communication. All messages are subject to audit and may be reviewed by administrators.

---

## 3.4 Notification Management

**The Bell Icon**

The notification bell in the top navigation bar displays a count of unread notifications. Click it to open the notification panel.

**Navigating from Notifications**

Clicking an individual notification takes you directly to the relevant resource (e.g., clicking a lab result notification opens that patient's lab result). The notification is marked as read when clicked.

**Marking Notifications as Read**

- **Individual:** Click the notification.
- **Bulk:** Use the **Mark All as Read** control in the notification panel to clear all unread notifications at once.

**What Generates Notifications**

- Lab results completed for your patient
- Radiology reports completed for your patient
- Queue updates
- New direct messages
- Appointment reminders
- System alerts relevant to your role

---

## 3.5 Settings and Branding

**Who Can Change Settings**

Most system settings are restricted to the Admin role. Individual staff may change their own personal preferences (theme, notification preferences) from their profile settings page. Role-specific configuration (M-Pesa credentials, module settings, pricing) requires Admin access.

**Sensitive Settings Masking**

Sensitive configuration values (such as M-Pesa Consumer Secret and Passkey) are masked in the settings display — you see asterisks rather than the actual value. This prevents inadvertent exposure of credentials on screen. Click the reveal icon (if authorized) to view the actual value; minimize screen exposure time when doing so.

**Branding Customization**

Facilities with the Branding module active can customize their MediFleet appearance. This includes logo, background images, brand primary and accent colors, and print templates. Branding configuration is managed by the Admin role. See Section 2.10 Module D for technical specifications.

---

# Part 4: Training Program Administration

---

## 4.1 Trainer Guide

### Recommended Training Sequence and Duration

| Role | Recommended Training Duration | Notes |
|---|---|---|
| Receptionist | 4 hours | Focus heavily on patient registration accuracy and queue acuity judgement |
| Doctor | 6 hours | Allow extended time for SOAP note practice and KDPA consent workflows |
| Nurse | 4 hours | Prioritize FEFO and bed management hands-on exercises |
| Pharmacist | 4 hours | Emphasize FEFO, idempotency, and STAT/shortage scenarios |
| Laboratory Technician | 5 hours | Include catalog management and reagent logging practice |
| Radiologist | 3 hours | Include report template creation and contrast protocol review |
| Billing Officer | 4 hours | Dedicate time to M-Pesa flow and cheque bounce scenarios |
| Admin | 6 hours | Cover RBAC thoroughly; run permission override scenarios |
| Patient Portal User | 1 hour | Self-guided; provide printed quick-start card |
| Superadmin | 4 hours | Conducted by platform team only; include tenant provisioning dry-run |

### Demo Tenant Setup

Training should always be conducted on a **dedicated demo tenant** — never on the production environment. Before each training session:

1. Ensure the demo tenant is active in the superadmin dashboard.
2. Verify all relevant modules are enabled on the demo tenant.
3. Pre-populate the demo tenant with realistic but fictional patient data.
4. Create demo user accounts for each role to be trained.
5. Reset the demo tenant data between training cohorts to prevent confusion.

### Running a Training Session

1. Begin every session with Part 1 (Platform Orientation), regardless of role.
2. Use a projector or shared screen to walk through each module step by step.
3. After the trainer demonstrates each procedure, have the trainee replicate it independently on their own login.
4. Present the assessment scenarios verbally or in writing and allow the trainee to reason through their answer before checking the Answer Key.
5. Record training completion and assessment performance on the competency signoff checklist.
6. Issue the competency signoff only when all required tasks are demonstrated unaided.

---

## 4.2 Competency Signoff Checklists

### Receptionist Competency Checklist

The trainee must demonstrate each of the following unaided before signoff:

- [ ] Successfully log in, including navigating the hospital selection screen
- [ ] Register a new patient with all required fields completed correctly
- [ ] Locate a patient using at least two different search methods (name, OP number)
- [ ] Add a patient to the queue with the correct acuity level for a given scenario
- [ ] Route a patient to the correct department
- [ ] Book an appointment with a specific doctor on a specified date
- [ ] Update an appointment status from Scheduled to Confirmed
- [ ] Correctly identify and navigate a 402 Module Unavailable screen

### Doctor Competency Checklist

- [ ] Log in and navigate to the clinical queue
- [ ] Claim an unassigned patient from the queue
- [ ] Enter all eight vitals fields, including BP in correct format, and confirm BMI auto-calculates
- [ ] Complete a full SOAP note including all required fields
- [ ] Select the correct ICD-10 code using the search field
- [ ] Order a lab test at STAT priority and explain when STAT is appropriate
- [ ] Order a radiology examination and identify any contrast/prep flags
- [ ] Write a prescription in correct clinical format
- [ ] Create a referral with appropriate urgency level
- [ ] Navigate the medical history section and demonstrate the consent acknowledgement workflow
- [ ] Explain the sensitive data categories and their access restrictions

### Nurse Competency Checklist

- [ ] Log in and navigate to the ward board
- [ ] Correctly identify all four bed status colors and their meanings
- [ ] Admit a patient to an available bed (and demonstrate they cannot select an occupied/maintenance/cleaning bed)
- [ ] Log supply usage for a consumable item using FEFO batch selection
- [ ] Log usage of a reusable item and explain why stock does not decrease
- [ ] Complete a patient discharge with all required fields, including discharge notes
- [ ] Confirm bed returns to Cleaning status after discharge and transition to Available after cleaning

### Pharmacist Competency Checklist

- [ ] Log in and navigate to the pharmacy queue
- [ ] Locate a pending prescription in the queue
- [ ] Select the correct FEFO batch for dispensing
- [ ] Complete a prescription dispense and explain the idempotency key function
- [ ] Process an OTC sale without a patient record
- [ ] Explain what a reorder threshold alert means and the correct action
- [ ] Initiate a stock transfer request from the Main Store

### Laboratory Technician Competency Checklist

- [ ] Log in and navigate to the lab worklist
- [ ] Correctly sort and prioritize the worklist (STAT first, then Urgent, then Routine)
- [ ] Identify whether a test requires a barcode and complete specimen collection accordingly
- [ ] Enter results for a multi-parameter test
- [ ] Identify and explain an out-of-range result flag
- [ ] Log reagent consumption using FEFO batch selection
- [ ] Complete a test and confirm doctor notification
- [ ] Add a new test to the catalog with at least two parameters

### Radiologist Competency Checklist

- [ ] Log in and navigate to the radiology worklist
- [ ] Identify and act on contrast and preparation flags before proceeding
- [ ] Complete a radiology examination report with all required fields
- [ ] Explain the source of pre-populated text in the Findings field
- [ ] Add a new examination type to the catalog with a default report template

### Billing Officer Competency Checklist

- [ ] Log in and navigate to the billing queue
- [ ] Correctly identify all five invoice statuses and their meanings
- [ ] Record a cash payment and explain the idempotency key function
- [ ] Record a partial payment and identify the resulting invoice status
- [ ] Initiate an M-Pesa STK push with a phone number in 07XXXXXXXX format
- [ ] Record a cheque receipt and advance it through the deposited → cleared lifecycle
- [ ] Handle a bounced cheque including mandatory bounce_reason entry

### Admin Competency Checklist

- [ ] Log in and navigate to the admin dashboard
- [ ] Create a new staff account with all required fields
- [ ] Explain why must_change_password is set to True by default
- [ ] Deactivate and reactivate a staff account
- [ ] Explain the effective permissions formula
- [ ] Add an explicit permission grant to a specific user
- [ ] Add an explicit permission revoke to a specific user
- [ ] Create a new department and explain the auto-created messaging channel
- [ ] Configure and explain M-Pesa credentials (account reference 12-char limit)
- [ ] Update a lab test base price using the Pricing tab
- [ ] Filter and read an audit log entry including old_value and new_value

### Patient Portal Competency Checklist

- [ ] Successfully log in using OP number, date of birth, and last 4 phone digits
- [ ] Locate and view appointment history
- [ ] Locate and view invoice history
- [ ] Explain why certain medical history entries are not visible
- [ ] Describe the 60-minute session timeout

### Superadmin Competency Checklist

- [ ] Log in using the bearer token mechanism
- [ ] Provision a new demo tenant and capture the one-time temporary password
- [ ] Enable and disable a module via the feature_flags JSON
- [ ] Explain the 60-second cache propagation delay
- [ ] Activate and deactivate a tenant
- [ ] Explain the platform-level visibility capabilities and cross-tenant search logging
- [ ] Demonstrate the branding image upload and explain the 1.2 MB limit
- [ ] Apply valid hex color codes for brand_primary and brand_accent

---

## 4.3 Assessment Answer Key

### Orientation Assessment Answers

**O-1**
The lockout lasts 15 minutes from the time of the fifth failed attempt. If 20 minutes have passed and the account is still locked, either the 15-minute window has not fully elapsed (check exact time), or the administrator has manually locked the account for a different reason. The correct action is to wait until the full 15-minute lockout has passed, then try again carefully. If still locked after waiting, contact the system administrator.

**O-2**
Two possible explanations: (1) The colleague has a different role that includes permissions to access the Radiology module, while your role does not. (2) Your hospital may have the Radiology module active, but your role's sidebar permissions do not include it — or alternatively, the module may have been recently enabled but your account's role does not include it in its navigation scope. Both role and module subscription can independently affect sidebar visibility.

**O-3**
You must clear the ActivePatientBar before beginning work on Patient B. Failing to do so means any actions you take (ordering tests, entering notes, logging medications) could be inadvertently attached to Patient A's record. Click the X on the ActivePatientBar to clear the active patient context, then search for and set Patient B.

**O-4**
The 402 screen means the Pharmacy module has not been activated for your hospital's subscription. It does not indicate a system error or a problem with your account credentials. The correct escalation path is to contact your system administrator, who can check the module configuration. If the module should be active, the administrator escalates to the MediFleet platform team (Superadmin).

**O-5**
You should complete any critical data entry in your current form before interacting with the notification, to avoid losing work. When you click the notification, the system will navigate you directly to the relevant resource (e.g., a completed lab result, a new message) and mark that notification as read. If the notification is not time-sensitive, you may also use "Mark All as Read" and address it after completing your current task.

---

### Receptionist Assessment Answers

**R-1**
With three patients sharing the name "James Mwangi," you must use additional identifiers to confirm the correct patient. Ask the patient for their OP number (if they have a card or previous receipt), their date of birth, their National ID number, and their registered phone number. Cross-reference these against the three records in the search results. Only proceed once you have a definitive match on at least two independent identifiers.

**R-2**
The system will assign **OP-2026-0087** — the format is OP-YEAR-NNNN where NNNN is a sequential counter within that calendar year.

**R-3**
Assign acuity level **1 (Emergency)**. Chest pain with rapid breathing are potential symptoms of a cardiac or respiratory emergency, both life-threatening. The Emergency acuity ensures this patient appears at the top of the clinical queue immediately, ahead of Urgent and Standard patients.

**R-4**
Do not book the appointment. The doctor's block has not been entered into the scheduling system — this is an administrative gap, not a patient-facing problem. Inform the patient that the 14:30 slot is unavailable (explain briefly without disclosing internal scheduling issues). Contact the doctor or their administrative support to get the schedule block entered in the system. Then offer the patient an alternative time or a different available appointment.

**R-5**
The appointment should have been left as **Scheduled** (or updated to **Confirmed** if the patient had confirmed attendance) until the patient either arrived or definitively cancelled. "No-Show" is the correct status only after the appointment time has passed and the patient did not attend without cancellation. "Cancelled" should only be used when the patient explicitly cancels. For a patient expressing uncertainty about attendance, the appointment remains Scheduled.

**R-6**
The Primary Phone Number field is mandatory and has not been completed or has been entered in an invalid format. You need to obtain the patient's mobile phone number. Without it, the registration cannot be saved.

**R-7**
The field in MediFleet is the **OP number** (Outpatient number). The format is OP-YEAR-NNNN, for example OP-2025-0187. This number is printed on their previous receipts, appointment cards, or any printed correspondence from the facility.

**R-8**
The first Urgent patient will be seen before the second Urgent patient. Both are the same acuity level (2), so the secondary sort criterion applies: **time of arrival** (join time). The patient who joined the queue first — 10 minutes before the second Urgent patient — is seen first. Within the same acuity level, the queue is strictly first-in, first-served.

---

### Doctor Assessment Answers

**D-1**
The Emergency (level 1) patient immediately jumps to the top of the queue. The waiting Standard (level 3) patient's position within the Standard group is unchanged — they remain the next Standard patient to be seen. However, all Emergency and Urgent patients ahead of them (including the new Emergency patient) must be seen first. The level-3 patient's wait time continues to increase.

**D-2**
BMI is calculated automatically by the system from the Weight and Height values you have entered. You should not enter BMI manually. If the BMI field remains blank after entering both weight and height, check that both values are in the correct units (kg and cm respectively) and are numeric. If the field still does not populate, this may be a display delay — save and reopen the form, or contact technical support if the issue persists.

**D-3**
Review the allergy banner carefully before prescribing. If the allergy involves the drug class you intend to prescribe (penicillin in this case), do not proceed with that medication. Select an alternative antibiotic from a different class. If clinically there is no alternative, document your clinical reasoning fully in the encounter notes, confirm the specific allergy type and severity with the patient, and follow your institution's allergy challenge protocol. Patient safety takes precedence.

**D-4**
The record must reach the **Billed** status. Until the doctor advances the record from Draft to Billed, the prescription notes remain within the clinical encounter and are not visible in the pharmacy queue. Once Billed is reached, the prescription transmits to Pharmacy.

**D-5**
The system enforces sensitive data access restrictions via the `is_sensitive = True` flag on the record. Mental health records are classified as sensitive and are restricted to authorized personnel. Before you can view the record yourself, you must obtain the patient's verbal consent and acknowledge it in the system's consent prompt. Once you have acknowledged consent, you gain access. The patient's request not to share with the nurse means you should not discuss or share the content — the nurse does not have access to the sensitive record through the system unless they have explicit authorization.

**D-6**
You should: (1) Inform the patient that contrast dye will be used and check for any contraindications, allergies to contrast agents, or relevant conditions (e.g., renal impairment, prior contrast reactions). Document any findings in the radiology order's clinical notes. (2) Communicate any contraindication findings to the radiologist who will be performing the examination — include this in the order notes so the radiologist can take appropriate action (e.g., pre-medication, switching to non-contrast protocol, or contraindication cancellation).

**D-7**
Select **Emergency** urgency. The patient needs to be seen today — this is the definition of an emergency referral requiring immediate transfer. An "Urgent" referral (24–48 hours) would not meet this clinical need.

**D-8**
Use the ICD-10 code search field built into the form to look up and select codes. Do not enter codes from memory. This reduces transcription errors, ensures you select the correct specificity level, and confirms the code exists and is current in the system's catalog. If "J18.9" is the correct code for pneumonia (unspecified), searching for it in the field will surface it — but the search also helps catch cases where you may have slightly misremembered a code.

**D-9**
Record clinical reasoning, differential diagnoses, and staff-to-staff communications in the **Internal Notes** field. This field is not visible to billing staff or non-clinical roles. Never put sensitive clinical reasoning in the Assessment or Plan fields if you are concerned about it appearing on patient-facing or billing documents.

**D-10**
Order all four tests: FBC, LFTs, and malaria rapid test as **Routine** (non-urgent); blood culture as **STAT** (highest priority — genuinely time-critical, especially for a febrile patient where sepsis must be excluded). Explain to the lab team via the clinical notes field why the blood culture is STAT. Reserve STAT designation for tests where the result will immediately change acute clinical management. Do not mark all tests STAT — this dilutes the urgency signal for genuinely critical tests.

---

### Nurse Assessment Answers

**N-1**
Only **Bed 3D (green/Available)** can be used for admission. Bed 3A (orange/Occupied) already has a patient. Bed 3B (red/Maintenance) is out of service. Bed 3C (yellow/Cleaning) is awaiting cleaning after a prior patient. The system will not permit admission to any bed that is not in Available status.

**N-2**
Select **Batch B (expires August 2026)** first — it has the earliest expiry date. The governing principle is **FEFO (First-Expire-First-Out)**: always use stock that expires soonest to minimize waste and ensure supply rotation. Batch A (Jan 2027) is used next, and Batch C (March 2028) is used last.

**N-3**
Do not proceed with the discharge until the attending doctor has entered a formal discharge order in the patient's clinical record in the system. Verbal orders are insufficient — a verbal instruction cannot be audited, and acting on it creates clinical and legal risk. Politely inform the doctor that you will proceed once the discharge order is documented in the system.

**N-4**
No, you cannot admit the new patient to Bed 5C while it shows yellow (Cleaning). The bed must first be physically cleaned and then have its status updated to **Available (green)** using the Mark Clean action. Only then can a new patient be admitted to it.

**N-5**
No, this is not a system error. The blood pressure cuff is flagged as a reusable item in the catalog. The system intentionally does not deduct stock for reusable items — it records the usage for clinical documentation purposes but recognizes the item is returned and sterilized for re-use. This behavior is correct.

**N-6**
Do not fabricate or guess follow-up details. The correct action is to pause the discharge, contact the attending doctor via messaging or in person, and ask them to document the follow-up plan in the clinical record. Once you have the confirmed information, return to the discharge screen and complete the discharge notes accurately. Discharge notes are a clinical document — accuracy is essential.

---

### Pharmacist Assessment Answers

**P-1**
Apply FEFO: dispense from **Batch Y first** (expires February 2026 — soonest expiry). Batch Y has 50 tablets, but 60 are required. After dispensing all 50 from Batch Y, dispense the remaining 10 tablets from **Batch X** (expires June 2026 — next soonest). Do not use Batch Z (December 2026) until the earlier-expiry batches are exhausted.

**P-2**
The idempotency key has protected against a double-dispense. The message means the transaction was successfully processed on your first click — the medication has already been dispensed and the invoice updated. Do not submit again. Check the dispense history to confirm the transaction was recorded correctly, and proceed normally.

**P-3**
Use the **OTC Sale** workflow. Click OTC Sale from the pharmacy screen. Leave the patient field blank (anonymous walk-in sale). Search for and select the antacid item in the catalog. Select the appropriate batch (FEFO). Enter the quantity. Confirm the sale. Generate a receipt if required.

**P-4**
MediFleet automatically updates the patient's invoice when a dispense is completed. The pharmacist does not need to manually add medication charges to the bill — this is handled by the system as part of the dispense workflow. The billing officer can see the charge as soon as the pharmacist confirms the dispense.

**P-5**
This is not necessarily a supply crisis — 15 capsules may still be enough for current needs. However, the reorder threshold alert means stock has reached or fallen below the minimum level set in the catalog for this item, indicating it is time to initiate a replenishment. The correct action is to notify the inventory manager or administrator and initiate a stock transfer request from the Main Store. Do not wait until stock reaches zero.

**P-6**
Initiate a **Stock Transfer Request** from the Main Store. Navigate to Stock Transfers, click Request Transfer, select Amoxicillin 500mg and the quantity needed, and submit the request. The Main Store manager will review and fulfill the transfer. Communicate the urgency to your administrator if the item is needed immediately for an active prescription.

---

### Lab Technician Assessment Answers

**L-1**
Process in this order:
1. **STAT blood culture** (highest priority — process immediately)
2. **Urgent malaria rapid test** (second priority)
3. **Routine urine microscopy** (third, within Routine group — ordered at the same time as lipid profile, so first in alphabetical or order-received basis)
4. **Routine lipid profile** (last)

**L-2**
You must: (1) Generate or affix a barcode label to the specimen container for this specific test. (2) Enter the specimen ID (barcode value) into the system when marking the specimen as collected. Both actions must be completed before the system will allow you to mark the specimen as collected.

**L-3**
A result of 6.2 g/dL against a reference range of 12.0–17.5 g/dL indicates the patient has a significantly low haemoglobin — a potentially critical finding. The red flag indicates the result is outside the normal range. You should: complete the test entry, add a technician note documenting the finding, complete the test to trigger the doctor notification, and — given the severity of the value — consider directly notifying the ordering doctor immediately rather than waiting for them to notice the notification.

**L-4**
By using the newer box instead of the already-opened earlier-expiry box, you violated the **FEFO (First-Expire-First-Out)** principle. The box that was already open (with an earlier expiry) should have been used first. Going forward, always select the batch with the earliest expiry date at the top of the batch list. If you are managing physical reagent storage, also ensure physical placement reflects FEFO (older stock in front).

**L-5**
Select **Choice** as the value type. The result can only be one of a defined set of options ("Reactive" or "Non-Reactive"). Choice type allows you to define a pick list, ensuring consistent result entry and preventing free-text variation.

**L-6**
The test status is "In Progress," meaning the results have not yet been entered and the test has not been completed. The system only sends the result notification to the doctor when the test status transitions to **Completed** (when you click Complete Test). The doctor has not been notified because the test was never completed in the system. Open the test, enter the results, and click Complete Test.

---

### Radiologist Assessment Answers

**Rad-1**
Do not proceed with the contrast examination. A history of severe allergic reaction to contrast is a significant contraindication. Stop and contact the ordering doctor immediately. Document the contraindication in the examination record. The doctor must review the clinical indication and determine whether to: proceed with a non-contrast alternative, arrange pre-medication under specialist supervision, or cancel the order. Patient safety is the priority — never administer contrast to a patient with a documented severe reaction without a formal clinical decision by the responsible physician.

**Rad-2**
The pre-populated text is a **default report template** defined in the radiology catalog for this examination type. When a new examination type is added to the catalog, the administrator can enter a structured template that automatically appears in the Findings field for all reports of that type. This is a deliberate feature designed to guide the radiologist through a systematic reporting structure. The colleague's suggestion that it is an error is incorrect.

**Rad-3**
Upon clicking Complete Examination, the system: (1) Changes the examination status from Pending to Completed. (2) Sends a real-time notification via WebSocket to the ordering doctor, alerting them that the radiology report for their patient is ready. The report becomes immediately available on the patient's clinical record for authorized staff to view.

**Rad-4**
If the default report template is left blank, radiologists who open the examination will encounter an empty Findings field with no structured guidance. They will need to write the entire report from scratch each time, which increases reporting time and risks inconsistent reporting structure across different radiologists. It is strongly recommended to always add a default report template when creating a new examination type.

---

### Billing Officer Assessment Answers

**B-1**
The invoice status updates to **Partially Paid**. The system records the KES 2,000 payment and shows the remaining balance of KES 2,500 outstanding. The invoice remains open for further payment recording.

**B-2**
The idempotency key has prevented a double-payment transaction. The first click successfully processed the payment — the second click was rejected because the system recognized the same transaction was already completed. Do not attempt to submit again. Check the payment history on the invoice to confirm the first payment was recorded correctly. Proceed as normal.

**B-3**
The system will transmit the number in the international format **254712345678** (replacing the leading 0 with the Kenya country code 254). You do not need to change the format before entering it — enter it as 0712345678 (or however the patient naturally provides it) and the system normalizes it automatically before sending to the M-Pesa API.

**B-4**
Ask the patient if they received a prompt on their phone and whether they completed the payment. If they have not yet responded to the prompt, ask them to do so now. If 5 or more minutes have passed with no callback update, the STK push may have timed out or the patient may not have completed it. You can retry the STK push or offer an alternative payment method (cash, card). Do not manually change the invoice status from Pending M-Pesa while waiting.

**B-5**
When you click **Mark Cleared** on the cheque, the system automatically posts a payment against the corresponding invoice. The invoice status updates to **Paid** (assuming the cheque amount covers the full balance, or **Partially Paid** if it does not). The Clearing action is the trigger — you do not need to separately record the payment through the normal payment workflow.

**B-6**
The **bounce_reason** field is mandatory when marking a cheque as bounced. The system will not save without it. This field is required for audit and recovery purposes — it documents the bank's stated reason for returning the cheque (e.g., "Refer to Drawer," "Insufficient Funds," "Payment Stopped"), which is essential information for following up with the patient or organization and for dispute resolution.

---

### Admin Assessment Answers

**A-1**
Yes, this is the correct and expected behavior. The system sets `must_change_password = True` by default when a new account is created. This forces the staff member to set their own personal password on first login, ensuring that the administrator (who set the temporary password) cannot access the account, and that the staff member takes ownership of their credentials.

**A-2**
Use the **UserPermissionsEditor** on the doctor's staff account to add an **Explicit Grant** for the specific billing read permission (e.g., `billing:read`). This grants the additional permission to this individual doctor only, without modifying the DOCTOR role definition. All other doctors remain unaffected. The effective permissions formula ensures this grant is added on top of their role: (Role Permissions ∪ {billing:read}) − Revokes.

**A-3**
Navigate to the receptionist's staff account → Permissions tab → UserPermissionsEditor. In the **Explicit Revokes** section, add `patients:write`. Click Save. This removes the write permission from this specific receptionist only. Other receptionists are not affected — they retain the full role permissions. Only this individual receptionist's effective access is reduced: (Role Permissions ∪ Grants) − {patients:write}.

**A-4**
Navigate to the **Audit Logs** tab. Apply the following filters: (1) User = "Sarah Kamau" (2) Date range = last 30 days. Optionally, filter by Action Type = Payment-related actions (e.g., "Payment Recorded," "Invoice Updated"). Review the resulting entries, examining the old_value and new_value fields to understand what changed.

**A-5**
The two most likely causes: (1) The staff member has not yet been added as a member of the Physiotherapy department. The auto-created channel is accessible only to department members — creating the department does not automatically add existing staff. The administrator needs to go to the department and add the staff member. (2) The staff member may need to refresh their browser or log out and back in for the new channel to appear in their sidebar if it was added after their current session started.

**A-6**
The Account Reference field has a maximum of **12 characters**. "KenyaGeneralHospitalNairobi" exceeds this limit significantly. The account reference must be shortened to 12 characters or fewer (e.g., "KGH-NAIROBI" or "KGHNBI"). This is the reference that appears on the customer's M-Pesa statement when they complete a payment, so choose something recognizable but within the character limit.

**A-7**
Yes. Deactivating an account suspends login access but does not delete any data associated with the account. All patient records, clinical notes, and other content created by the former staff member are fully preserved and accessible to authorized users. The records are simply attributed to the deactivated user account in the audit trail.

**A-8**
This audit log entry shows that a user's role was changed from NURSE to DOCTOR. This is significant from a security perspective because it represents a privilege escalation — the DOCTOR role has significantly more clinical permissions than the NURSE role, including the ability to create clinical encounters, write prescriptions, and order tests. Any unauthorized or unexplained role change should be investigated immediately to determine who made the change, why, and whether the change is legitimate. The audit log captures who performed the change and when.

---

### Patient Portal Assessment Answers

**Pat-1**
After multiple failed login attempts, the account will be locked temporarily (similar to the staff lockout mechanism). You will see a lockout message. The correct action is to visit the reception desk in person — staff can look up your registered phone number (the last 4 digits of which are required for portal login) and provide you with the information you need. Do not continue guessing, as this may extend the lockout.

**Pat-2**
This is not a system error. It is intentional behavior mandated by KDPA privacy protections. Mental health records are classified as sensitive (`is_sensitive = True`) and are restricted from displaying in the patient portal to protect your most private health information. If you need to access these records or discuss them, please contact your care team directly.

**Pat-3**
The patient portal has a **60-minute automatic session timeout**. If you do not log out, the system will automatically terminate your session after 60 minutes of inactivity. Anyone who opens the browser after the session has expired will see the login screen, not your records. This protection exists specifically for shared or public computer scenarios. However, best practice is always to log out manually when you finish viewing your records.

---

### Superadmin Assessment Answers

**S-1**
You must copy the temporary password immediately. The temporary password is displayed **once only** during provisioning — there is no way to retrieve it again after you navigate away from the provisioning completion screen. If you navigate away without copying it, the password is permanently inaccessible and you will need to use the password reset mechanism to generate a new one for the initial admin account. Copy the password immediately and transmit it to the hospital administrator through a secure channel.

**S-2**
There is no system error. This is the expected behavior due to the **60-second cache propagation delay** for feature flag changes. After updating a tenant's feature_flags, the change takes up to 60 seconds to propagate to all active sessions. The administrator called back only 30 seconds after the change. Advise them to wait another 30 seconds and then refresh their browser. If the 402 screen persists after 60 seconds have passed, then further investigation is warranted.

**S-3**
Check the `plan_limits` object on the tenant record in the superadmin dashboard. If the plan limit for active staff accounts is 50, the hospital can currently add only 2 more (to reach 50). Adding 10 more would require either upgrading their subscription plan to one with a higher limit, or requesting a plan limit adjustment from the platform team. Communicate this clearly to the hospital administrator.

**S-4**
The system will reject the upload. Base64-encoded images are subject to a **1.2 MB maximum size cap**. An image that is 1.8 MB after base64 encoding will not be accepted. Advise the hospital administrator to compress the logo image (reduce resolution, optimize for web, or export at a lower file size) until it is under 1.2 MB, then re-encode it as base64 and retry the upload.

**S-5**
In addition to returning the search results, the system generates an **audit log entry** recording: the searching superadmin's identity, the timestamp of the search, the search terms used, and the specific tenant/patient record accessed. Cross-tenant searches by superadmins are fully logged to ensure accountability and prevent unauthorized use of platform-wide visibility.

---

*End of MediFleet Training Program Documentation*

*Version 1.0 — 2026-05-16*
*MediFleet Platform Team*
