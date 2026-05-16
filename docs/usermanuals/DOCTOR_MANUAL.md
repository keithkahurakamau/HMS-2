# MediFleet Hospital Management System
## Doctor User Manual

**Role**: Doctor  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/clinical`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Clinical Queue — Viewing and Claiming Patients
4. Creating an Encounter (Clinical Record)
5. Vitals Entry
6. SOAP Note — Complete Walkthrough
7. Ordering Laboratory Tests
8. Ordering Radiology Examinations
9. Writing Prescriptions
10. Follow-Up Appointments
11. Referrals
12. Medical History — Viewing and Adding Entries
13. Patient Portal Context
14. Common Errors
15. Keyboard Tips

---

## 1. Quick Start

As a Doctor, your primary workspace is the **Clinical Module** at `/app/clinical`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/clinical`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Open the Clinical Queue to see patients waiting for you.
2. Claim a patient from the queue.
3. Review the allergies banner before touching the patient record.
4. Record vitals, write a SOAP note, and add diagnoses with ICD-10 codes.
5. Order labs and/or radiology as needed.
6. Write prescriptions for pharmacy to fulfill.
7. Schedule a follow-up appointment or create a referral.
8. Review or update the patient's medical history.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `clinical:read` | View clinical records, SOAP notes, and encounter history |
| `clinical:write` | Create and edit encounters, SOAP notes, diagnoses, and plans |
| `lab_orders:write` | Order laboratory tests |
| `radiology_orders:write` | Order radiology examinations |
| `prescriptions:write` | Write prescriptions |
| `appointments:write` | Schedule follow-up appointments |
| `referrals:write` | Create and manage referrals |
| `medical_history:read` | View patient medical history |
| `medical_history:write` | Add entries to patient medical history |
| `patients:read` | View basic patient demographic data |
| `messaging:write` | Send messages to colleagues |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Clinical Queue — Viewing and Claiming Patients

The Clinical Queue is the list of patients waiting to be seen. Patients are sorted by acuity (most urgent first) and then by arrival time within the same acuity level.

### Acuity Sort Order

| Priority | Acuity Code | Label | Action Required |
|----------|-------------|-------|-----------------|
| 1st | 1 | Emergency | See immediately |
| 2nd | 2 | Urgent | See as soon as possible |
| 3rd | 3 | Standard | Routine — see in order |

### Procedure: Review the Queue

1. Navigate to `/app/clinical`. The queue panel is displayed prominently.
2. Each queue entry shows: **Patient Name**, **OP Number**, **Acuity Level**, **Chief Complaint**, and **Wait Time**.
3. Review the list before claiming any patient.

### Procedure: Claim a Patient

1. Click on the patient row in the queue to open their summary.
2. Review the **Allergies Banner** at the top of the patient summary. This banner lists all documented allergies. Never dismiss it before reading it.
3. Click **Claim Patient** (or "Start Consultation"). This marks the patient as "With Doctor" and removes them from the general queue.
4. The system opens the patient's encounter creation screen automatically.

### Allergies Banner

- The allergies banner appears in a highlighted bar (typically red or orange) at the top of any patient clinical view.
- It displays the **allergen name**, **reaction type**, and **severity** for each documented allergy.
- If no allergies are documented, the banner states "No Known Allergies — Please Confirm with Patient."
- Always verbally confirm allergies with the patient before prescribing.

---

## 4. Creating an Encounter (Clinical Record)

An **Encounter** is the record of a single clinical visit. Each time a patient is seen, a new encounter is created. Encounters progress through statuses: **Draft → Billed → Pharmacy → Completed**.

### Procedure: Start a New Encounter

1. After claiming the patient (Section 3), the new encounter form opens automatically.
2. The encounter is pre-linked to the patient's profile and the current date and time.
3. The initial status is **Draft** — the encounter is private and editable at this stage.
4. Complete Vitals (Section 5) and the SOAP Note (Section 6) before finalizing.

### Consultation Fee

- A **consultation fee** is automatically added to the patient's invoice when you submit the encounter.
- The fee amount is set by your Admin in the billing configuration.
- You do not need to enter the fee manually.

---

## 5. Vitals Entry

Vitals are recorded as part of every encounter. They are displayed in the top section of the encounter form.

### Vitals Fields and Expected Formats

| Vital Sign | Field Name | Format / Unit | Example |
|------------|------------|---------------|---------|
| Blood Pressure | BP | "Systolic/Diastolic" mmHg | `120/80` |
| Heart Rate | HR | Beats per minute (bpm) | `72` |
| Respiratory Rate | RR | Breaths per minute | `16` |
| Temperature | Temp | Degrees Celsius (°C) | `37.2` |
| Oxygen Saturation | SpO2 | Percentage (%) | `98` |
| Weight | Weight | Kilograms (kg) | `70` |
| Height | Height | Centimeters (cm) | `175` |
| Body Mass Index | BMI | Auto-calculated | *(auto-filled)* |

### Procedure: Record Vitals

1. In the encounter form, locate the **Vitals** section.
2. Enter Blood Pressure in the format `Systolic/Diastolic` — for example `120/80`. Do not add units or spaces.
3. Enter Heart Rate as a whole number in bpm.
4. Enter Respiratory Rate as a whole number (breaths per minute).
5. Enter Temperature in Celsius to one decimal place.
6. Enter SpO2 as a percentage without the % symbol (e.g. `98`).
7. Enter Weight in kilograms.
8. Enter Height in centimeters.
9. The system **automatically calculates BMI** from weight and height. You do not need to enter BMI manually. It appears after you fill both fields.
10. Click **Save Vitals** to record them.

### BMI Auto-Calculation

BMI is computed as: **Weight (kg) / (Height (m))²**

The result is displayed next to the height and weight fields and is stored with the encounter record.

---

## 6. SOAP Note — Complete Walkthrough

The SOAP note is the structured clinical narrative of the encounter. It is divided into four sections: Subjective, Objective, Assessment, and Plan.

### 6.1 Subjective Section

The Subjective section captures information as reported by the patient.

| Field | Description |
|-------|-------------|
| Chief Complaint (CC) | The patient's primary reason for visiting, in their own words. E.g. "Chest pain for 2 days." |
| History of Present Illness (HPI) | Detailed narrative of the current complaint: onset, location, duration, character, aggravating/relieving factors, associated symptoms. |
| Review of Systems (ROS) | Systematic enquiry of other body systems beyond the chief complaint. |

**Procedure: Complete the Subjective Section**

1. In the encounter form, click the **Subjective** tab or scroll to the Subjective section.
2. Type the patient's **Chief Complaint** in the CC field — use the patient's own words where possible.
3. Expand the **HPI** field and write a detailed narrative.
4. Fill in the **ROS** field — you may use checkboxes (if provided) or free text.
5. The system auto-saves as you type.

### 6.2 Objective Section

The Objective section contains clinician-observed findings.

| Field | Description |
|-------|-------------|
| Physical Examination (PE) | Your systematic examination findings: general appearance, head/neck, chest, abdomen, extremities, neurological, etc. |

**Procedure: Complete the Objective Section**

1. Click the **Objective** tab.
2. In the **Physical Examination** field, document your examination findings system by system.
3. Reference any already-entered vitals here by linking them (they appear in the sidebar for convenience).

### 6.3 Assessment Section

The Assessment section documents your clinical conclusions.

| Field | Description |
|-------|-------------|
| Diagnosis | Primary and secondary diagnoses in clinical language. |
| ICD-10 Code | International Classification of Diseases code for each diagnosis. |

**Procedure: Add a Diagnosis with ICD-10 Code**

1. Click the **Assessment** tab.
2. In the **Diagnosis** field, type the diagnosis name.
3. In the **ICD-10** search field, begin typing the condition name or the ICD-10 code (e.g. type `J06` for upper respiratory infection, or type "hypertension" to search by name).
4. Select the matching code from the dropdown.
5. To add a **secondary diagnosis**, click **+ Add Diagnosis** and repeat steps 2–4.
6. You may add as many diagnoses as clinically warranted.

### 6.4 Plan Section

The Plan section documents what will happen next for this patient.

| Field | Description |
|-------|-------------|
| Treatment Plan | Medications, therapies, procedures, and other management steps. |
| Prescription | Medications ordered for pharmacy to dispense (link to Prescription module). |
| Follow-Up | Next appointment date and instructions. |
| Internal Notes | Notes visible only to clinical staff, not printed on patient-facing documents. |

**Procedure: Complete the Plan Section**

1. Click the **Plan** tab.
2. Enter the **Treatment Plan** — describe all therapeutic interventions.
3. Add prescriptions using the Prescriptions module (Section 8).
4. Enter follow-up instructions in the **Follow-Up** field.
5. Add any **Internal Notes** for clinical staff communication. These notes do not appear on patient printouts.

### Finalizing the Encounter

1. After completing all SOAP sections, review the full note.
2. Click **Submit Encounter** (or **Finalize**).
3. The encounter status changes from **Draft** to **Billed** — the consultation fee is automatically posted to the patient's invoice.
4. The encounter is now visible to pharmacy, billing, and nursing staff as appropriate.

---

## 7. Ordering Laboratory Tests

Lab orders are attached to the current encounter and routed to the Laboratory module for processing.

### Lab Priority Levels

| Priority | Description | Expected Turnaround |
|----------|-------------|---------------------|
| STAT | Critical — process immediately | Minutes |
| Urgent | High priority — process before routine | Within hours |
| Routine | Standard processing order | Normal queue |

### Procedure: Order a Single Lab Test

1. In the encounter form, click the **Lab Orders** tab or the **+ Order Lab** button.
2. A test catalog dialog opens. Browse by category or use the search field.
3. Click the test name to select it.
4. Set the **Priority** (Routine, Urgent, or STAT).
5. Add any **clinical notes** for the lab technician (e.g. "Patient is on anticoagulation — handle sample carefully").
6. Click **Add to Order**.
7. When you have added all required tests, click **Submit Lab Orders**.

### Procedure: Batch Order Multiple Lab Tests

1. Follow steps 1–3 above for the first test.
2. Continue selecting additional tests from the catalog — each is added to a batch list at the bottom of the dialog.
3. Review the batch list to confirm all tests are correct.
4. Set priority for each test individually if they differ.
5. Click **Submit All Orders** to send the entire batch to the lab worklist at once.

### Reading Lab Results in Clinical Context

- Completed lab results appear in the patient's record under the **Lab Results** tab.
- Out-of-range values are highlighted (typically in red for high and blue/green for low).
- You can view historical results for the same tests to track trends.

---

## 8. Ordering Radiology Examinations

Radiology orders are sent to the Radiology module and assigned to a radiologist.

### Procedure: Order a Radiology Examination

1. In the encounter form, click the **Radiology Orders** tab or **+ Order Radiology**.
2. A radiology catalog dialog opens. Search by exam name, body part, or modality.

   Available modalities include:
   - **X-Ray**
   - **CT** (Computed Tomography)
   - **MRI** (Magnetic Resonance Imaging)
   - **Ultrasound**
   - **Mammography**

3. Select the appropriate examination from the catalog.
4. Review the flags displayed for the selected exam:
   - **Requires Prep**: If marked, inform the patient of preparation instructions (e.g. fasting, bowel preparation).
   - **Requires Contrast**: If marked, document any contrast allergies before ordering.
5. Add a **clinical indication** in the notes field — this helps the radiologist understand the clinical question.
6. Click **Submit Radiology Order**.

### Viewing Radiology Reports

- Completed radiology reports appear under the **Radiology Results** tab of the encounter.
- Reports include: Findings, Conclusion/Impression, and any image URLs.
- If contrast was used, that will be documented by the radiologist.

---

## 9. Writing Prescriptions

Prescriptions written in the encounter are visible to the Pharmacist for fulfillment.

### Procedure: Add a Prescription

1. In the Plan section of the SOAP note, click **+ Add Prescription** or navigate to the Prescriptions tab.
2. Search for the medication by generic name or brand name.
3. Select the medication from the results list.
4. Enter the following fields:

   | Field | Description |
   |-------|-------------|
   | Dose | Amount per administration (e.g. `500mg`) |
   | Route | How it is administered (e.g. Oral, IV, Topical) |
   | Frequency | How often (e.g. Twice daily, Every 8 hours) |
   | Duration | How long to take it (e.g. 7 days) |
   | Instructions | Special instructions (e.g. "Take with food", "Avoid sunlight") |
   | Quantity | Total units to dispense |

5. Click **Add Medication**.
6. Repeat for additional medications.
7. Click **Save Prescription** when all medications are entered.

### How Pharmacy Reads Prescriptions

- The pharmacist sees all prescriptions linked to the encounter in the Pharmacy module.
- They fulfill orders using First-Expire-First-Out (FEFO) batch selection.
- Once fulfilled, the prescription status updates and the invoice reflects the dispensed items.
- If the pharmacist has a query, they may send you a direct message through the messaging system.

---

## 10. Follow-Up Appointments

### Procedure: Schedule a Follow-Up

1. In the **Plan** section of the SOAP note, click **Schedule Follow-Up**.
2. A mini-appointment dialog appears.
3. Select the **date** for the follow-up.
4. Select the **doctor** (defaults to yourself; change if referring to a colleague).
5. Select the **appointment type** (e.g. Follow-Up, Review Results).
6. Add follow-up instructions for the patient in the notes field.
7. Click **Book Appointment**.
8. The appointment is created with status **Scheduled** and linked to this encounter.
9. The Receptionist can confirm the appointment when the patient checks in next time.

---

## 11. Referrals

Referrals send the patient to another provider — either internal (another department) or external (another facility).

### Referral Urgency Levels

| Urgency | Description |
|---------|-------------|
| Routine | Non-urgent; can be seen in normal scheduling |
| Urgent | Should be seen within a short time frame |
| Emergency | Immediate transfer required |

### Referral Status Lifecycle

| Status | Meaning |
|--------|---------|
| Pending | Referral created but not yet sent |
| Sent | Referral transmitted to receiving provider |
| Accepted | Receiving provider has accepted the patient |
| Completed | Patient has been seen by the receiving provider |
| Cancelled | Referral withdrawn |

### Procedure: Create a Referral

1. In the encounter form, click the **Referrals** tab or **+ New Referral**.
2. Select the **Referral Type**: Internal (within the same facility) or External (another institution).
3. For internal referrals: select the **destination department** from the dropdown.
4. For external referrals: enter the **receiving facility name** and **specialist name**.
5. Set the **Urgency Level** (Routine, Urgent, or Emergency).
6. Write the **Referral Reason** — include a clinical summary, diagnosis, and specific question for the receiving provider.
7. Attach any relevant documents if available (lab results, radiology reports).
8. Click **Submit Referral**. Status becomes **Pending**.

### Procedure: Track a Referral

1. Open the patient's record and navigate to the **Referrals** tab.
2. All referrals are listed with their current status.
3. When the receiving provider accepts and completes the referral, the status updates accordingly.
4. You will receive an in-system notification when a referral status changes.

---

## 12. Medical History — Viewing and Adding Entries

The Medical History module stores structured health background information. Access requires patient consent under the KDPA (Kenya Data Protection Act).

### KDPA Consent Requirement

- Before accessing the medical history of any patient, you must confirm **consent has been recorded** in the system.
- If consent has not been given, the system will block access and prompt you to record consent first.
- Every view of medical history is logged automatically in the **DataAccessLog** for audit purposes.

### History Entry Types

| Entry Type | Description |
|------------|-------------|
| `SURGICAL_HISTORY` | Past surgeries and procedures |
| `FAMILY_HISTORY` | Health conditions in blood relatives |
| `SOCIAL_HISTORY` | Lifestyle factors: smoking, alcohol, occupation, living situation |
| `IMMUNIZATION` | Vaccine history |
| `ALLERGY` | Documented allergies (also displayed in the Allergies Banner) |
| `CHRONIC_CONDITION` | Ongoing diagnosed conditions (e.g. diabetes, hypertension) |
| `PAST_MEDICAL_EVENT` | Significant past illnesses or hospitalizations |
| `OBSTETRIC_HISTORY` | Pregnancy and birth history (where applicable) |
| `MENTAL_HEALTH` | Mental health diagnoses and treatment history |

### Sensitive Records

- Entries with the **is_sensitive** flag are restricted to authorized users only.
- Mental health entries are frequently marked sensitive.
- If a record you expect to see is hidden, you may lack the appropriate permission. Contact your Admin.

### Procedure: View Medical History

1. Open the patient's record.
2. Navigate to the **Medical History** tab.
3. If consent is not yet recorded, the system will display a consent prompt. Record consent from the patient verbally and tick the consent checkbox in the system.
4. The history entries are displayed grouped by type.
5. Each view is automatically logged.

### Procedure: Add a Medical History Entry

1. In the Medical History tab, click **+ Add Entry**.
2. Select the **Entry Type** from the dropdown (see table above).
3. Fill in the entry details (description, date of event, severity, etc.).
4. If the information is highly sensitive, tick the **Mark as Sensitive** checkbox. This restricts future access to authorized users.
5. Click **Save Entry**.

---

## 13. Patient Portal Context

Patients can view certain information via the Patient Portal at `/patient`. Understanding what they can see helps manage their expectations:

- Patients can view their **upcoming and past appointments**.
- Patients can view their **invoice statuses and amounts**.
- Patients can view **non-sensitive medical history entries**.
- Patients **cannot** see sensitive-flagged entries, internal notes, or draft encounters.
- The portal is **entirely read-only** — patients cannot request changes or book appointments through it.
- The portal uses three-factor authentication (OP Number + Date of Birth + last 4 digits of phone).

---

## 14. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "No queue entries found" | No patients waiting in your assigned queue | Check that you are viewing the correct department queue |
| "ICD-10 code not found" | Searched term does not match the catalog | Try alternate spellings or browse the ICD-10 tree |
| "Encounter already submitted" | Attempting to edit a finalized encounter | Contact Admin if a correction is needed; finalized encounters are locked |
| "Consent not recorded" | Medical history accessed without patient consent | Record consent from the patient and check the consent box |
| "Sensitive record — access denied" | Record is flagged is_sensitive and you lack the permission | Contact Admin to grant appropriate access or involve a senior clinician |
| "Lab test catalog is empty" | No tests configured in the catalog | Contact your Admin or Lab Technician to set up the lab catalog |
| "Referral destination required" | External referral submitted without facility name | Fill in the receiving facility name field |
| "Module not available" / 402 | Subscription does not include this module | Contact your Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 15. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between form fields in encounter forms |
| `Escape` | Close dialogs without saving |
| Type in ICD-10 search | Real-time search; fastest with 3+ characters |
| Click column headers in queue | Sort queue by that column |
| Browser `F5` or `Ctrl+R` | Refresh queue if new patients do not appear |
| Save frequently | The system auto-saves most fields, but click Save explicitly after vital entry |

---

*MediFleet HMS — Doctor Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Clinical Staff Only*
