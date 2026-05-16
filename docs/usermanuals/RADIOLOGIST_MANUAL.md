# MediFleet Hospital Management System
## Radiologist User Manual

**Role**: Radiologist  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/radiology`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Radiology Worklist
4. Completing an Examination
5. Radiology Catalog Management
6. Common Errors
7. Keyboard Tips

---

## 1. Quick Start

As a Radiologist, your primary workspace is the **Radiology Module** at `/app/radiology`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/radiology`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Open the Radiology Worklist to see all pending examination requests.
2. Review each request for modality, preparation flags, and contrast requirements.
3. Perform the examination and enter your findings and impression.
4. Mark the examination as Completed — the report becomes visible to the ordering doctor.
5. Maintain the Radiology Catalog to ensure accurate exam definitions and pricing.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `radiology:read` | View the worklist, pending requests, and completed reports |
| `radiology:write` | Enter findings, complete examinations, and update reports |
| `radiology_catalog:read` | View the radiology exam catalog |
| `radiology_catalog:write` | Add, edit, and manage radiology exam definitions |
| `clinical:read` | View clinical notes and indications on radiology orders |
| `patients:read` | View basic patient demographic data |
| `messaging:write` | Communicate with clinical staff |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Radiology Worklist

The **Radiology Worklist** displays all pending and in-progress radiology examination requests ordered by doctors.

### Reading the Worklist

Each worklist entry shows:

| Column | Description |
|--------|-------------|
| Order ID | Unique identifier for the radiology order |
| Patient Name | Patient's full name |
| OP Number | Patient's unique identifier (OP-YEAR-NNNN) |
| Exam Name | Name of the examination ordered (e.g. "Chest X-Ray PA", "CT Abdomen with Contrast") |
| Modality | Type of imaging: X-Ray, CT, MRI, Ultrasound, or Mammography |
| Body Part | Anatomical region being imaged |
| Ordered By | Doctor who placed the order |
| Order Date/Time | When the request was submitted |
| Requires Prep | Whether patient preparation is needed before the exam |
| Requires Contrast | Whether contrast media is needed |
| Status | Pending or Completed |

### Modality Types

| Modality | Description |
|----------|-------------|
| X-Ray | Conventional radiography; fastest turnaround |
| CT | Computed Tomography; detailed cross-sectional imaging |
| MRI | Magnetic Resonance Imaging; soft tissue detail; no ionizing radiation |
| Ultrasound | Real-time imaging using sound waves; used for soft tissues, pregnancy, vascular |
| Mammography | Specialized X-Ray for breast tissue |

### Preparation and Contrast Flags

- **Requires Prep = Yes**: The patient must have completed preparation before the exam. Examples:
  - Fasting for abdominal CT or ultrasound
  - Bowel preparation for pelvic MRI
  - Full bladder for pelvic ultrasound
  - Before performing the exam, confirm with the patient (or clinical staff) that preparation has been completed.

- **Requires Contrast = Yes**: The exam involves contrast media (e.g. iodinated contrast for CT, gadolinium for MRI). Before proceeding:
  - Check for **contrast allergy** in the patient's allergy history.
  - Check **renal function** results if available (contrast is nephrotoxic in patients with renal impairment).
  - If you have concerns, message the ordering doctor before proceeding.

### Procedure: Review a Pending Request

1. Open the Radiology Worklist from `/app/radiology`.
2. Review entries sorted by order date (oldest first) for standard workflow, or filter by modality if managing a specific imaging room.
3. Click on a pending order to open the full request detail.
4. Read the **Clinical Indication** — this is the doctor's note explaining why the examination is needed and what clinical question it should answer.
5. Note the **Requires Prep** and **Requires Contrast** flags.
6. Confirm with the patient that all preparation is complete (for prep-required exams).
7. Verify the patient's identity: ask for their name and OP Number and confirm it matches the order.

---

## 4. Completing an Examination

After performing the examination, you enter your report in the system. The report includes Findings and a Conclusion/Impression.

### Report Structure

| Section | Description |
|---------|-------------|
| Findings | A systematic, detailed description of what was observed in the images. The default findings template provides a starting structure. |
| Conclusion / Impression | Your radiological interpretation: the clinical meaning of the findings, differential diagnoses, and recommendations for further imaging if needed. |
| Image URL | Link to the image storage location (PACS system URL or image file URL) |
| Contrast Used | If the exam required contrast: confirm whether it was administered and the type/volume used |

### Procedure: Complete an Examination and Submit a Report

1. Click on the pending radiology order in the worklist.
2. Click **Start / Open Exam** to begin. The status remains Pending until you submit.
3. Review the order details one final time:
   - Patient name and OP Number
   - Exam name and modality
   - Clinical indication from the referring doctor
4. The **Findings** section is pre-filled with the **default findings template** configured for this exam type in the catalog. The template provides standard headings for the modality and body part — this ensures a consistent, complete report structure.
5. Edit the **Findings** section to reflect the actual examination:
   - Replace or fill in all template placeholders.
   - Document findings systematically (e.g. for a chest X-Ray: heart, lungs, pleura, mediastinum, bones, soft tissues).
   - Include both positive findings (abnormalities) and relevant negative findings.
   - Be specific about size, location, density/signal characteristics, and any comparison with prior studies.
6. The **Conclusion / Impression** section is pre-filled with the **default impression template** if one is configured. Edit it to express your definitive radiological interpretation:
   - State your primary impression clearly.
   - List differential diagnoses where appropriate.
   - Add recommendations (e.g. "Recommend follow-up CT in 3 months", "Suggest clinical correlation").
7. In the **Image URL** field, paste or enter the URL to the study images (from your PACS or image archive system). This allows the ordering doctor to access images directly from the patient's record.
8. If the exam required contrast:
   - Tick the **Contrast Used** checkbox.
   - Enter the **contrast agent type** (e.g. Iohexol 300mg/mL) and **volume administered** (e.g. 80mL IV).
9. Review the complete report before submitting.
10. Click **Submit Report** (or **Mark Complete**).
11. The order status changes from **Pending** to **Completed**.
12. The report is immediately visible to the ordering doctor under the **Radiology Results** tab of the patient's clinical encounter.

### When to Contact the Referring Doctor

Message the ordering doctor immediately if:

- You identify an unexpected critical finding (e.g. tension pneumothorax, aortic dissection, intracranial haemorrhage).
- The exam cannot be completed as requested (e.g. patient could not tolerate the position, equipment malfunction).
- Contrast was not administered due to allergy or renal concern and you need guidance on how to proceed.

### Procedure: Message the Ordering Doctor

1. Click the **Messages** icon in the navigation bar.
2. Click **+ New Message** and search for the doctor's name.
3. Write a specific, actionable message including the patient's **OP Number**, the exam name, and your finding or concern.
4. Click **Send**.

---

## 5. Radiology Catalog Management

The **Radiology Catalog** defines all examination types available for doctors to order. Each entry defines the exam's name, modality, body part, preparation requirements, contrast requirements, default report templates, and base price.

### Catalog Fields Reference

| Field | Description |
|-------|-------------|
| Exam Name | Full descriptive name of the examination (e.g. "Chest X-Ray PA", "MRI Brain with Gadolinium") |
| Modality | Select from: X-Ray, CT, MRI, Ultrasound, Mammography |
| Body Part | Anatomical region (e.g. Chest, Abdomen, Brain, Pelvis, Right Knee) |
| Requires Prep | Toggle on if patient preparation is required before the exam |
| Requires Contrast | Toggle on if contrast media is used |
| Default Findings Template | The standard structured text that pre-populates the Findings field when a report is opened. Should include all relevant anatomical sections for the modality and body part. |
| Default Impression Template | Standard text that pre-populates the Conclusion/Impression field. Should prompt for primary impression and recommendations. |
| Base Price | Cost of the examination for billing purposes |
| Active | Whether this exam can currently be ordered |

### Procedure: Add a New Exam to the Catalog

1. Navigate to the **Radiology Catalog** tab in the Radiology module.
2. Click **+ New Exam**.
3. Enter the **Exam Name** — be precise and consistent. Examples:
   - "Chest X-Ray PA" (not just "Chest X-Ray")
   - "CT Abdomen and Pelvis with Contrast"
   - "Ultrasound Pelvis — Obstetric"
4. Select the **Modality** from the dropdown (X-Ray, CT, MRI, Ultrasound, Mammography).
5. Enter the **Body Part**.
6. Set the **Requires Prep** toggle as appropriate.
7. Set the **Requires Contrast** toggle as appropriate.
8. Write the **Default Findings Template**. This should be a complete structured prompt that guides the reporting radiologist. Example for Chest X-Ray PA:

   ```
   Technical quality: [adequate/limited - specify reason]
   
   Heart: Size [normal/enlarged]. Cardiothoracic ratio [X].
   
   Lungs: Lung fields [clear/describe findings]. Lung volumes [normal/reduced/hyperinflated].
   Pleura: No pleural effusion/pneumothorax [or describe findings].
   
   Mediastinum: Mediastinal width [normal/widened]. Trachea [central/deviated].
   
   Bones and soft tissues: No acute bony abnormality [or describe].
   
   Other findings: [include if applicable]
   ```

9. Write the **Default Impression Template**. Example:

   ```
   1. [Primary impression — state the main finding or normal study]
   2. [Secondary finding if applicable]
   
   Recommendation: [Clinical correlation advised / Follow-up imaging recommended / No further imaging required]
   ```

10. Enter the **Base Price** — coordinate with your Admin on standard pricing.
11. Click **Save Exam**. The exam is now available in the doctor's radiology ordering catalog.

### Procedure: Edit an Existing Exam

1. Locate the exam in the catalog list.
2. Click the exam to open its detail.
3. Click **Edit**.
4. Modify the relevant fields (e.g. update the findings template, correct the base price, change a prep or contrast flag).
5. Click **Save**. Changes apply to all future orders for this exam.
6. Existing completed reports for previous orders are not affected.

### Procedure: Deactivate an Exam

If an exam is no longer offered (equipment taken offline, exam replaced by a different protocol):

1. Open the exam in the catalog.
2. Click **Deactivate**.
3. Confirm the action. The exam disappears from the doctor's ordering catalog.
4. Historical reports for deactivated exams remain accessible in patient records.

### Procedure: Reactivate an Exam

1. In the catalog list, enable the **Show Inactive** toggle to see deactivated exams.
2. Click the deactivated exam.
3. Click **Activate**.
4. The exam becomes available for ordering again.

---

## 6. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Order not found" | The order ID has been changed or cancelled | Refresh the worklist; if the order was cancelled, the referring doctor will be shown a notification |
| "Findings template missing" | The exam does not have a default findings template configured | Enter your findings manually; update the catalog template to avoid this for future exams |
| "Image URL invalid" | The URL entered does not resolve or is in an invalid format | Verify the URL in your PACS or image archive; paste it directly from the browser |
| "Contrast field required" | Exam marked Requires Contrast but contrast details not filled | Complete the contrast type and volume fields before submitting |
| "Report already submitted" | Attempting to edit a completed report | Contact Admin if a correction is needed; completed reports are locked |
| "Access denied" / 403 | Missing permission for the action | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Radiology module not in subscription | Contact Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 7. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between fields in the report form |
| `Escape` | Close dialogs without saving |
| Click column headers in worklist | Sort by that column (e.g. click Modality to group by modality) |
| Browser `F5` or `Ctrl+R` | Refresh worklist if new orders are not appearing |
| Copy/paste image URL | Paste directly from PACS browser address bar into the Image URL field |
| Save draft frequently | Click Save (not Submit) to save a partial report without completing it |

---

*MediFleet HMS — Radiologist Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Clinical Staff Only*
