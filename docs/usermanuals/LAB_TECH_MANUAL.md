# MediFleet Hospital Management System
## Laboratory Technician User Manual

**Role**: Laboratory Technician  
**System**: MediFleet HMS  
**Version**: 2.0  
**Date**: 2026-05-16  
**Landing Page After Login**: `/app/laboratory`

---

## Table of Contents

1. Quick Start
2. Permissions Reference
3. Lab Worklist — Priority and Queue Management
4. Specimen Collection
5. Entering Test Results
6. Reagent and Consumable Logging
7. Lab Catalog Management — Tests
8. Lab Catalog Management — Parameters and Bill of Materials
9. Common Errors
10. Keyboard Tips

---

## 1. Quick Start

As a Laboratory Technician, your primary workspace is the **Laboratory Module** at `/app/laboratory`. This screen opens immediately after login.

**First-time login**: You will be forced to set a new password before reaching `/app/laboratory`. See the INDEX manual for password requirements.

Your typical daily workflow:

1. Open the Lab Worklist and review incoming orders sorted by priority (STAT first).
2. Identify specimens that require barcode labels before collection.
3. Collect or receive specimens, mark them as collected, and update the specimen ID.
4. Process specimens in priority order, entering results for each parameter.
5. Flag out-of-range values for clinician review.
6. Log reagent and consumable usage for each test batch.
7. Maintain the lab catalog by adding or updating tests and parameters.

---

## 2. Permissions Reference

| Permission Code | What It Allows |
|-----------------|----------------|
| `laboratory:read` | View the lab worklist, orders, and results |
| `laboratory:write` | Update specimen status, enter results, and complete orders |
| `lab_catalog:read` | View lab test catalog and parameters |
| `lab_catalog:write` | Add, edit, and deactivate lab tests and parameters |
| `inventory:read` | View reagent and consumable stock |
| `inventory:write` | Log reagent and consumable usage |
| `clinical:read` | View clinical notes relevant to lab orders |
| `messaging:write` | Send results notifications or queries to clinical staff |

If any of these actions are unavailable, contact your Admin to verify your permissions.

---

## 3. Lab Worklist — Priority and Queue Management

The **Lab Worklist** displays all pending and in-progress laboratory orders. Orders are sorted by priority, then by time of order within the same priority level.

### Priority Sort Order

| Priority | Description | Processing Expectation |
|----------|-------------|----------------------|
| STAT | Critical — process immediately before all others | Minutes; interrupt current work if needed |
| Urgent | High priority — process before Routine | Within hours of receipt |
| Routine | Standard queue | Normal processing order |

**Always process STAT orders first, regardless of what you are currently working on.**

### Reading the Worklist

Each worklist entry shows:

| Column | Description |
|--------|-------------|
| Order ID | Unique identifier for the order |
| Patient Name | Patient's full name |
| OP Number | Patient's unique identifier (format: OP-YEAR-NNNN) |
| Test Name | Name of the ordered test |
| Priority | STAT / Urgent / Routine |
| Requires Barcode | Yes/No — indicates if a barcode label must be printed before collection |
| Status | Current state of the order (Pending / In Progress / Completed / Rejected) |
| Ordered By | Doctor who placed the order |
| Order Time | When the order was placed |

### Reading Clinical Notes on an Order

Some orders include **clinical notes** from the ordering doctor. These may contain important information such as:

- Patient is on anticoagulation therapy (handle blood samples carefully)
- Patient has contrast allergy (relevant for certain tests)
- Previous results for comparison
- Specific clinical question to answer

### Procedure: Read Clinical Notes Before Processing

1. Click on the order entry in the worklist.
2. Locate the **Clinical Notes** field in the order detail panel.
3. Read all notes before collecting the specimen or beginning the test.
4. If notes raise a clinical question you cannot resolve, message the ordering doctor before proceeding.

---

## 4. Specimen Collection

### Barcode Labels

Orders with **Requires Barcode = Yes** need a printed barcode label affixed to the specimen container before or immediately after collection. This label links the physical specimen to the digital order.

### Procedure: Print a Barcode Label

1. Click on the order entry.
2. If **Requires Barcode = Yes**, a **Print Label** button is visible.
3. Ensure your label printer is connected and loaded with labels.
4. Click **Print Label**.
5. Affix the label to the specimen container before collection.

### Lab Order Status Flow

```
Pending → In Progress → Completed
                      → Rejected (if specimen invalid or test cannot be performed)
```

### Procedure: Mark Specimen as Collected and Update Status to In Progress

1. Locate the order in the worklist with status **Pending**.
2. Click the order to open its detail view.
3. Click **Mark Collected / Start Processing**.
4. The system prompts you to enter or confirm the **Specimen ID**:
   - If your facility auto-generates specimen IDs: the system may pre-fill this field. Confirm it is correct.
   - If your facility uses manual specimen IDs: type the specimen ID from the label or collection tube into the field.
5. Confirm the **specimen type** (e.g. Venous Blood, Urine, Swab) — this is pre-filled from the order; verify it matches what was collected.
6. Enter the **collection date and time** (defaults to now; adjust if collection occurred earlier).
7. Click **Save**. The order status changes from **Pending** to **In Progress**.

### Procedure: Reject a Specimen

If the specimen is unsuitable for testing (e.g. haemolysed, insufficient volume, wrong tube, mislabelled):

1. Open the order entry.
2. Click **Reject Specimen**.
3. Enter a **rejection reason** from the dropdown or free-text field. Common reasons:
   - Specimen haemolysed
   - Insufficient volume
   - Wrong tube type
   - Mislabelled specimen
   - Clotted specimen
4. Click **Confirm Rejection**. The status changes to **Rejected**.
5. The ordering doctor is notified of the rejection.
6. Message the doctor or nursing staff to arrange recollection.

---

## 5. Entering Test Results

Once a specimen has been processed, you enter the results into the system. The results form is auto-populated from the test catalog, ensuring all required parameters are present.

### Procedure: Enter Results for a Test

1. Locate the order in the worklist with status **In Progress**.
2. Click on the order to open the results entry form.
3. The **Parameters** section is automatically populated based on the test definition in the catalog. Each parameter shows:
   - Parameter name (e.g. Haemoglobin, White Cell Count)
   - Unit (e.g. g/dL, x10⁹/L)
   - Reference range (e.g. 12.0–16.0 g/dL)
   - Value type (numeric, text, or select from choices)
4. Enter the result for each parameter:
   - For **numeric** parameters: type the numeric value.
   - For **text** parameters: type the descriptive result.
   - For **choice** parameters: select the appropriate option from the dropdown (e.g. Positive / Negative, Reactive / Non-Reactive).
5. The system **automatically highlights out-of-range values**:
   - Values **above** the reference range are highlighted (typically in red).
   - Values **below** the reference range are highlighted (typically in blue or green).
6. Review all highlighted values carefully. Out-of-range values will be visible to the doctor in the same highlighted format.
7. Enter your **Technician Notes** — any comments about the specimen quality, methodology used, or result interpretation caveats.
8. Log reagent and consumable usage (Section 6) before completing.
9. Click **Complete Test**. The order status changes from **In Progress** to **Completed**.
10. The results immediately become visible to the ordering doctor and any nursing staff with results access.

### Reference Ranges

- Reference ranges are set per parameter in the Lab Catalog (see Section 7).
- If you believe a reference range is incorrect for your facility, do not alter individual results — contact your Admin or update the catalog parameter (Section 8).

---

## 6. Reagent and Consumable Logging

Every test performed consumes reagents and consumables. These must be logged for inventory accuracy and billing purposes.

### Item Types

| Type | Description |
|------|-------------|
| Consumable (Reagent) | Single-use chemical reagents or test kits. Quantity is deducted from stock. |
| Reusable Item | Lab equipment used during processing (e.g. calibration materials, reusable instrument parts). Logged but not deducted. |

### Understanding FEFO in the Lab

Like pharmacy, laboratory reagents are tracked in batches by expiry date. The system sorts batches FEFO (First-Expire-First-Out) — always use the batch at the top of the list.

### Procedure: Log Reagent Usage

1. In the results entry form, locate the **Reagents / Consumables** section.
2. Click **+ Add Reagent**.
3. Search for the reagent or consumable by name.
4. Select it from the catalog results.
5. The system displays available batches sorted by expiry date (FEFO order).
6. Select the **first batch** in the list (earliest expiry).
7. Enter the **batch number** (typically pre-filled from the selected batch; verify it matches the physical batch on the bench).
8. Enter the **quantity used** (number of units consumed for this test run).
9. Click **Add**.
10. Repeat for additional reagents if the test requires multiple reagents.

### Logging Reusable Items

1. Follow steps 2–4 above to find the reusable item.
2. The system identifies it as **Reusable**.
3. Log the quantity used — this is recorded for audit purposes but does not reduce stock levels.
4. Click **Add**.

---

## 7. Lab Catalog Management — Tests

The Lab Catalog defines all tests available to be ordered by doctors. Each test has a name, associated parameters, a base price, and an active/inactive status.

### Procedure: Add a New Test to the Catalog

1. Navigate to the **Lab Catalog** tab in the Laboratory module.
2. Click **+ New Test**.
3. Complete the test fields:

   | Field | Description |
   |-------|-------------|
   | Test Name | Descriptive name (e.g. "Full Blood Count", "Urine Microscopy") |
   | Department | Lab department (e.g. Haematology, Microbiology, Chemistry) |
   | Sample Type | What specimen is required (e.g. EDTA Blood, Urine, Swab) |
   | Requires Barcode | Toggle on if specimen container must be barcoded |
   | Default Priority | Pre-set priority for orders (Routine, Urgent, STAT) |
   | Base Price | Cost of the test for billing purposes (set in consultation with Admin) |
   | Description | Brief description of the test and its clinical utility |

4. Click **Save Test**. The test is now active and visible in the doctor's order catalog.
5. You must add **parameters** to the test before it can produce results — see Section 8.

### Procedure: Deactivate a Test

If a test is no longer offered or has been replaced:

1. Locate the test in the catalog list.
2. Click the test to open its detail view.
3. Click **Deactivate Test**.
4. Confirm the action. The test status changes to **Inactive**.
5. Inactive tests do not appear in the doctor's ordering catalog.
6. Existing completed results for this test remain accessible in patient records.

---

## 8. Lab Catalog Management — Parameters and Bill of Materials

### Parameters

Each test consists of one or more **parameters** — the individual measurable values that make up the test result.

#### Parameter Fields

| Field | Description |
|-------|-------------|
| Key | Unique identifier for the parameter within the test (e.g. `hgb`, `wbc`) — no spaces, lowercase |
| Name | Display name shown to users (e.g. "Haemoglobin", "White Blood Cells") |
| Unit | Unit of measurement (e.g. `g/dL`, `x10⁹/L`, `mmol/L`, `%`) |
| Value Type | How the result is entered: `numeric` (a number), `text` (free text), or `choice` (from a list) |
| Choices | If value_type is `choice`: the list of valid options (e.g. "Positive, Negative") |
| Reference Low | The lower bound of the normal range (numeric parameters only) |
| Reference High | The upper bound of the normal range (numeric parameters only) |
| Sort Order | Display order in the results form |

### Procedure: Add Parameters to a Test

1. Open the test in the Lab Catalog.
2. Under the **Parameters** section, click **+ Add Parameter**.
3. Fill in all parameter fields (see table above).
4. For **choice** parameters, enter each valid option separated by commas.
5. For **numeric** parameters, enter the **Reference Low** and **Reference High** values — these are used to flag out-of-range results automatically.
6. For **text** parameters, leave reference range fields empty.
7. Click **Save Parameter**.
8. Repeat for each measurable value in the test.
9. Use the drag handles (if available) to reorder parameters to match your reporting format.

### Procedure: Edit a Parameter

1. Open the test, find the parameter in the list.
2. Click **Edit** on the parameter row.
3. Update the fields as needed.
4. Click **Save**. The change applies to all future results entries for this test.
5. Historical results are not retroactively changed.

### Bill of Materials (BOM)

The **Bill of Materials** defines which reagents and consumables are expected to be used for each test. This acts as a guide for technicians and supports automatic cost calculation.

### Procedure: Add a Bill of Materials Entry

1. Open the test in the Lab Catalog.
2. Navigate to the **Bill of Materials** tab.
3. Click **+ Add BOM Item**.
4. Search for the reagent or consumable from the inventory catalog.
5. Enter the **quantity** expected to be consumed per test run.
6. Click **Save BOM Item**.
7. Repeat for each reagent or consumable used in the test.

### Procedure: Update BOM After Protocol Change

If your laboratory changes its testing protocol and uses different quantities or reagents:

1. Open the test's BOM tab.
2. Click **Edit** on the relevant BOM item.
3. Update the quantity or replace the item.
4. Click **Save**. The updated BOM applies to future tests.

---

## 9. Common Errors

| Error Message | Cause | What to Do |
|---------------|-------|------------|
| "Order already completed" | Attempting to enter results on a completed order | View the existing results; contact Admin if correction is needed |
| "Specimen ID required" | Trying to start processing without entering a specimen ID | Enter the specimen ID from the collection tube label |
| "Parameter not found" | A parameter was deleted from the catalog after the order was placed | Contact Admin to restore the parameter or manually add a technician note |
| "Reference range invalid" | Low reference value is higher than high reference value in catalog | Edit the parameter in the catalog to correct the values |
| "Reagent batch expired" | Selected reagent batch is past its expiry date | Use the next available batch; report expired stock to Admin |
| "Insufficient reagent stock" | Not enough reagent stock to log the required quantity | Request a stock transfer from Main Store; log what is available |
| "Test inactive" | Doctor tried to order a deactivated test | Reactivate the test in the catalog if it should still be available |
| "Access denied" / 403 | Missing permission | Contact your Admin to verify your permissions |
| "Module not available" / 402 | Laboratory module not in subscription | Contact Admin or platform support |
| "Session expired" | Token could not be refreshed | Log in again |

---

## 10. Keyboard Tips

| Shortcut / Tip | Action |
|----------------|--------|
| `Tab` | Move between result entry fields in the parameters form |
| `Escape` | Close dialogs without saving |
| Type in test search | Real-time search; effective with 3+ characters |
| Click priority column header | Sort worklist by priority (ensures STAT appears first) |
| Browser `F5` or `Ctrl+R` | Refresh worklist if new orders do not appear |
| Tab through parameters | Fastest way to enter numeric results sequentially |

---

*MediFleet HMS — Laboratory Technician Manual*  
*For technical issues, contact your Admin or raise a support ticket.*  
*Confidential — For Authorized Staff Only*
