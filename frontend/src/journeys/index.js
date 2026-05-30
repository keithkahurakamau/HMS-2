/**
 * Module journey step definitions.
 *
 * Each key maps to an array of steps. A step is:
 *   {
 *     selector?:  string,          // CSS selector to spotlight
 *     title:      string,
 *     body:       string,
 *     placement?: 'top' | 'bottom' | 'left' | 'right' | 'center',
 *     tip?:       string,          // optional brand-tinted callout shown
 *                                  // beneath the body — use for power-user
 *                                  // shortcuts or "did you know" notes
 *   }
 *
 * If `selector` doesn't resolve at runtime we silently fall back to a
 * centred card — so a tour never breaks when a target moves; it just
 * loses its arrow.
 *
 * Authoring philosophy: every step talks about what the USER does next,
 * not what the widget IS. A new staff member should be able to follow
 * these tours and run their full shift without training — orient, then
 * walk them through the actual workflow, button by button.
 */
export const JOURNEYS = {

    /* ──────────────────────────────────────────────────────────────
       Dashboard / Home — orient a fresh user to the shell
       ────────────────────────────────────────────────────────────── */
    dashboard: [
        { title: 'Welcome — let me show you how the shift runs',
          body: "Across every module the layout is the same: sidebar on the left for navigation, top bar for context and alerts, work area in the middle. Once you know where these live you can run the whole hospital from here without anyone training you.",
          placement: 'center' },
        { selector: '[data-tour="sidebar-nav"]',
          title: 'Step 1 — pick what you want to do',
          body: "The sidebar is your menu. Receptionists usually start with Patient Registry, doctors with Clinical Desk, pharmacists with Pharmacy. Tap any module to jump straight to it.",
          placement: 'right',
          tip: 'Anything your role isn\'t allowed to use is hidden — if you can see a link, you can use it.' },
        { selector: '[data-tour="topbar-help"]',
          title: 'Step 2 — if you ever feel lost, click "?"',
          body: "This help icon replays the walk-through for whatever page you're on. Hit it any time you forget where a button is — no need to ask a colleague or look up a manual.",
          placement: 'bottom' },
        { selector: '[data-tour="topbar-notifications"]',
          title: 'Step 3 — keep an eye on the bell',
          body: "Critical lab results, prescriptions waiting to be dispensed, appointments arriving — the bell flashes when something needs your attention. Click it to see the queue.",
          placement: 'bottom' },
        { selector: '[data-tour="active-patient-bar"]',
          title: 'Step 4 — your "patient in front of you"',
          body: "Whichever patient you've opened anywhere in the system stays pinned to this bar. Walk from Reception to Clinical to Pharmacy — every page already knows who you mean.",
          placement: 'bottom',
          tip: 'Click the bar to clear the active patient when you\'re done with them.' },
        { selector: '[data-tour="topbar-signout"]',
          title: 'Step 5 — sign out when you leave the workstation',
          body: "Sessions stay open until you sign out, so on a shared computer always click here when your shift ends. The next person signs in fresh under their own name.",
          placement: 'bottom' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Admin Dashboard — the Admin's first-day walkthrough
       ────────────────────────────────────────────────────────────── */
    admin: [
        { title: 'Admin walk-through — set up your hospital in 5 minutes',
          body: "We'll go through the order Admins follow on day one: add your staff, give them roles, then review the audit log so you can confirm every change is tracked.",
          placement: 'center' },
        { selector: '[data-tour="admin-tabs"]',
          title: 'Step 1 — switch between the four admin tools',
          body: "Users (staff accounts), Roles & Permissions (who can do what), Audit Log (who did what), Service Pricing (what you charge). Start with Users.",
          placement: 'bottom' },
        { selector: '[data-tour="admin-users"]',
          title: 'Step 2 — invite your staff',
          body: "Click Add user, type their name, email, and pick a role from the dropdown. They get a sign-in link and can start working immediately. Deactivate anyone who leaves so their cookie stops working.",
          placement: 'top',
          tip: 'Every staff edit you make is logged with your user ID and timestamp — useful when you need to prove who changed what.' },
        { selector: '[data-tour="admin-roles"]',
          title: 'Step 3 — assign roles (or build your own)',
          body: 'Built-in roles cover most hospitals. If you need a "Senior Nurse" who can discharge patients, click "New role", pick the permissions you want, save — done. Assign it under Users.',
          placement: 'top' },
        { selector: '[data-tour="admin-permission-override"]',
          title: 'Step 4 — give one person a one-off permission',
          body: 'Don\'t want to create a whole new role just for one nurse who can take cash? Open her user, click "Add override", grant just the cashier permission. Easier than redesigning your roles.',
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Patient Registry — Receptionist's full registration flow
       ────────────────────────────────────────────────────────────── */
    patients: [
        { title: 'Receptionist walk-through — register and route a patient',
          body: "This is where every patient starts their visit. We'll go through the exact sequence you'll do every day: check if they're already registered, register them if not, then route them to whichever department they need.",
          placement: 'center' },
        { selector: '[data-tour="patients-stats"]',
          title: 'Step 1 — glance at the strip when you arrive',
          body: 'Before opening the directory: how many active patients, how many registered today, how many flagged for allergies. Useful when a manager asks "how busy are we?" — you answer without leaving this screen.',
          placement: 'bottom' },
        { selector: '[data-tour="patient-search"]',
          title: 'Step 2 — search first, register second',
          body: "When a patient arrives, type their phone, ID, or surname here. If they come up — open them. If they don't — only then register them. This stops you from creating duplicates.",
          placement: 'bottom',
          tip: 'You can paste an OP number directly — even a partial one matches.' },
        { selector: '[data-tour="patients-filter-chips"]',
          title: 'Step 3 — narrow by sex if needed',
          body: 'If a patient\'s name is common, filter by Male or Female to shorten the list. Click "All" to clear.',
          placement: 'bottom' },
        { selector: '[data-tour="register-patient"]',
          title: 'Step 4 — register a new walk-in',
          body: 'No match in search? Click "Register patient". Fill in name, sex, date of birth, contact, next-of-kin, blood group, allergies. The form scrolls — finish every section.',
          placement: 'left',
          tip: 'The "Treatment consent" checkbox at the bottom is REQUIRED — without it the doctor cannot save any clinical notes for this patient later.' },
        { selector: '[data-tour="patient-row-route-chips"]',
          title: 'Step 5 — send them where they\'re going',
          body: "Once registered (or found), use these chips to put the patient into the right queue: Clinical (to see a doctor), Lab (for tests), Radiology (for imaging), Pharmacy (for refills), Wards (admission), or Billing (cashier).",
          placement: 'left',
          tip: 'A picker opens so you choose which doctor / pharmacist / nurse — that staff member sees the patient in their queue immediately.' },
        { selector: '[data-tour="patient-row-more"]',
          title: 'Step 6 — for anything else, open the ⋮ menu',
          body: "Edit patient details, view full medical history, print a patient card with their OP number, deactivate the file, or run a KDPA Section 26 access report — all under the three-dots menu.",
          placement: 'left' },
        { title: 'You\'re done',
          body: 'That\'s the receptionist\'s whole flow. Search → register if new → route. Repeat all day. Click "?" in the top bar if you ever want this walk-through again.',
          placement: 'center' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Clinical Desk — the Doctor's full consultation workflow
       ────────────────────────────────────────────────────────────── */
    clinical: [
        { title: 'Doctor walk-through — run a consultation end-to-end',
          body: "We'll walk through one full encounter the way you'll do every patient: pick them from your queue, record consent, fill vitals + SOAP, decide the diagnosis, then route them to Pharmacy / Billing / Wards. By the end you'll have the muscle memory for the whole shift.",
          placement: 'center' },
        { selector: '[data-tour="clinical-queue"]',
          title: 'Step 1 — pick the next patient',
          body: "Your queue lives at the top of the page. Reception routes patients to you and they appear here in order. Click any card to open their workspace.",
          placement: 'bottom',
          tip: 'Critical-priority patients show a pulsing red dot — see them first.' },
        { selector: '[data-tour="clinical-consent"]',
          title: 'Step 2 — record consent BEFORE you chart',
          body: 'Click "Record consent" right after opening the patient. Pick Verbal if they agreed face-to-face, Written if you have a signed form, Implied (Emergency) only if they can\'t communicate. Without active consent the system blocks every clinical save (KDPA Section 30).',
          placement: 'bottom',
          tip: 'Reception captures consent at registration, so most encounters won\'t need this step — but if you get a "no active consent" error, this is the fix.' },
        { selector: '[data-tour="clinical-vitals"]',
          title: 'Step 3 — fill vitals',
          body: "Blood pressure, heart rate, respiratory rate, temperature, SpO₂. Enter weight + height and BMI computes automatically. You can skip a field if it wasn't measured — none of these are forced.",
          placement: 'top' },
        { selector: '[data-tour="clinical-diagnoses"]',
          title: 'Step 4 — chief complaint, history, examination, diagnosis',
          body: 'Type the patient\'s chief complaint (one line — "headache for 3 days"), then the history of present illness (the story), then your physical examination findings. Pick or type an ICD-10 code for the diagnosis.',
          placement: 'top',
          tip: 'The ICD-10 dropdown filters as you type — start with a body system ("resp", "card") to narrow it.' },
        { selector: '[data-tour="clinical-prescriptions"]',
          title: 'Step 5 — write the prescription',
          body: 'This box is what Pharmacy sees. Write what the patient should take, in plain language ("Amoxicillin 500mg TDS for 5 days"). Pharmacy picks the actual batches.',
          placement: 'top',
          tip: 'Leave this blank if there\'s no prescription — but then don\'t use "Forward to pharmacy" below.' },
        { selector: '[data-tour="clinical-save-draft"]',
          title: 'Step 6a — "Save draft" if you\'re interrupted',
          body: 'Patient stepped out for an X-ray? Got pulled into an emergency? Click Save draft. The encounter stays in your workspace, the patient stays in your queue marked "In Consultation", and you pick up exactly where you left off.',
          placement: 'top' },
        { selector: '[data-tour="clinical-send-billing"]',
          title: 'Step 6b — "Send to billing" when consultation is done',
          body: "Use this when the patient only needs to pay the consultation fee and leave (no meds, no admission). The cashier sees them in the Billing queue with a pending invoice. The consultation fee posts automatically — leave the fee checkbox ON unless the patient is exempt.",
          placement: 'top',
          tip: 'You\'ll get a friendly error if you uncheck the fee AND haven\'t added any other charges — otherwise the cashier wouldn\'t know to call the patient.' },
        { selector: '[data-tour="clinical-forward-pharmacy"]',
          title: 'Step 6c — "Forward to pharmacy" for prescriptions',
          body: "Patient leaves the room and walks to Pharmacy with a prescription. The pharmacist sees them in their queue with your prescription text waiting. Requires the Medications field filled — otherwise the button refuses.",
          placement: 'top' },
        { selector: '[data-tour="clinical-finalize"]',
          title: 'Step 6d — "Finalise & sign" to close the encounter',
          body: "Use this when the encounter is fully done — no meds, no billing, no follow-up. The record locks, the queue clears, your workspace resets. Requires at least a chief complaint or a diagnosis (no blank sign-offs allowed).",
          placement: 'top' },
        { title: 'That\'s every consultation',
          body: 'Pick from queue → consent → vitals → SOAP → diagnosis → prescription → route. Repeat. The "?" icon in the top bar replays this any time you want.',
          placement: 'center' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Medical History — Doctor / Nurse longitudinal chart
       ────────────────────────────────────────────────────────────── */
    medical_history: [
        { title: 'Walk-through — read and update a patient\'s long-term chart',
          body: "Clinical Desk is for what’s happening today. Medical History is for everything that has ever happened: surgeries, allergies, chronic conditions, immunisations, social context. We’ll walk through how to find a chart and add to it.",
          placement: 'center' },
        { selector: '[data-tour="mh-search"]',
          title: 'Step 1 — open a patient',
          body: "Type a name or OP number. The chart loads with every section pre-expanded so you can scan the whole timeline in one scroll.",
          placement: 'bottom' },
        { selector: '[data-tour="consent-card"]',
          title: 'Step 2 — verify consent first',
          body: 'Green banner = active Treatment consent, you can chart freely. Red banner = no active consent, every save will be blocked. If red, click "+ Record consent" right there to fix it.',
          placement: 'right',
          tip: 'Recording consent here is the same form as in Clinical Desk — same data lands in the same place.' },
        { selector: '[data-tour="mh-entry-section"]',
          title: 'Step 3 — scan the relevant section',
          body: "Each section (Surgical, Family, Social, Immunisations, Allergies, etc.) shows how many entries it has on its tag. Collapse sections you don't care about.",
          placement: 'top' },
        { selector: '[data-tour="mh-add-entry"]',
          title: 'Step 4 — add a new entry',
          body: "Click + on any section. Title, description, optional event date, severity, status (Active / Resolved / Managed / Remission). Saves into the timeline so the next clinician sees it.",
          placement: 'left' },
        { selector: '[data-tour="mh-print"]',
          title: 'Step 5 — print for a referral',
          body: "Sending the patient to a specialist outside the system? Print the summary. Includes the consent log so the receiving clinician can see scope.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Laboratory — Lab Technician's order-to-result flow
       ────────────────────────────────────────────────────────────── */
    laboratory: [
        { title: 'Lab technician walk-through',
          body: "We'll go through the order an actual lab tech runs: see what's pending, collect the specimen, enter results. Plus how to set up tests in the catalogue when your hospital adds new ones.",
          placement: 'center' },
        { selector: '[data-tour="lab-queue"]',
          title: 'Step 1 — see what doctors have ordered',
          body: "Every lab request from any doctor lands here with its current state. Priority (STAT / Urgent / Routine) sorts the queue.",
          placement: 'right' },
        { selector: '[data-tour="lab-collect"]',
          title: 'Step 2 — mark the specimen collected',
          body: 'When you draw blood or receive a sample, open the order and click "Collect". Prints the barcode label and starts the turnaround clock so SLA is tracked.',
          placement: 'top' },
        { selector: '[data-tour="lab-complete"]',
          title: 'Step 3 — enter the result',
          body: "Once analyzed, click Complete. The result form is generated FROM the test's parameter schema — WBC, RBC, HGB for a CBC, glucose for an FBS, etc. Out-of-range values turn red automatically.",
          placement: 'top',
          tip: 'Critical values auto-DM the ordering doctor so they don\'t miss it.' },
        { selector: '[data-tour="lab-catalog"]',
          title: 'Setup — manage the test menu',
          body: "Adding a new test you offer? Catalog tab. Set its name, specimen type, base price, turnaround hours.",
          placement: 'top' },
        { selector: '[data-tour="lab-parameters"]',
          title: 'Setup — parameters per test',
          body: "Each test needs its parameters defined (units + reference range) so the result form knows what to ask. Without parameters, you can't enter results — set this up before you offer the test.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Radiology — Radiographer / Radiologist flow
       ────────────────────────────────────────────────────────────── */
    radiology: [
        { title: 'Radiology walk-through',
          body: "Process imaging requests in priority order, take the image, report findings, sign off.",
          placement: 'center' },
        { selector: '[data-tour="radio-queue"]',
          title: 'Step 1 — pick a study',
          body: "STAT first, Urgent next, Routine sorted by request time. Each row shows modality (X-ray / CT / MRI / US) and body part.",
          placement: 'right' },
        { selector: '[data-tour="radio-result"]',
          title: 'Step 2 — report your findings',
          body: 'Capture findings and impression. If "require radiologist sign-off" is on in Settings, the report can\'t release until a senior radiologist attests — useful for trainee output.',
          placement: 'top' },
        { selector: '[data-tour="radio-catalog"]',
          title: 'Setup — manage your imaging menu',
          body: "List every exam you offer with its modality, body part, and base price. Doctors pick from this list when ordering.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Pharmacy — Pharmacist's dispense + receipt flow
       ────────────────────────────────────────────────────────────── */
    pharmacy: [
        { title: 'Pharmacist walk-through',
          body: "We'll walk one prescription from the dispense queue all the way to a printed receipt. Then you'll know every screen you need.",
          placement: 'center' },
        { selector: '[data-tour="pharmacy-inventory"]',
          title: 'Step 1 — orient yourself on stock',
          body: "Inventory tab shows live stock for every drug and every batch. Low-stock items flag automatically so you know what to re-order.",
          placement: 'right' },
        { selector: '[data-tour="pharmacy-dispense-queue"]',
          title: 'Step 2 — pick the next prescription',
          body: "Prescriptions from doctors land in this queue with the patient's name, prescription text, and any allergies highlighted. Click to open.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-batch-picker"]',
          title: 'Step 3 — pick a batch',
          body: "Each drug has multiple batches with different expiry dates. The list is sorted FEFO (First Expiry First Out) — take the top one unless you have a specific reason.",
          placement: 'top',
          tip: 'The system locks the batch row while you dispense so two pharmacists can\'t double-claim the last pack.' },
        { selector: '[data-tour="pharmacy-pay-cash"]',
          title: 'Step 4a — patient pays cash',
          body: "Type the amount received, the system records change due. Posts straight to the till for end-of-day reconciliation.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-pay-card"]',
          title: 'Step 4b — patient pays by card',
          body: "Run the card on your POS terminal, type the slip reference in here to reconcile.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-pay-mpesa"]',
          title: 'Step 4c — M-Pesa STK push',
          body: "Type the patient's phone number, click Send. They get a prompt on their phone — they enter their PIN, the callback hits us, the payment posts automatically. No counting cash, no slips to lose.",
          placement: 'top',
          tip: 'If the callback never arrives (their phone was off, they declined), the transaction times out after 90s and you can retry or switch to cash.' },
        { selector: '[data-tour="pharmacy-receipt"]',
          title: 'Step 5 — print the receipt',
          body: "One click. Includes hospital branding, item list, batch numbers, your name. The same receipt the patient sees in their portal.",
          placement: 'left' },
        { selector: '[data-tour="pharmacy-transactions"]',
          title: 'End of shift — reconcile',
          body: "Transactions log lists every dispense, payment, return for the shift. Filter by date, export to CSV, hand to accounting.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Inventory — Pharmacy / Lab manager
       ────────────────────────────────────────────────────────────── */
    inventory: [
        { title: 'Inventory walk-through',
          body: "Set up your stores, add items, receive stock in batches, react to low-stock alerts. The whole supply-chain workflow.",
          placement: 'center' },
        { selector: '[data-tour="inventory-locations"]',
          title: 'Step 1 — locations are stock pools',
          body: "Main Store, Pharmacy, Lab, Wards each hold their own stock. To move stock between them, use the Transfer flow — quantity logs into both sides.",
          placement: 'bottom' },
        { selector: '[data-tour="inventory-items"]',
          title: 'Step 2 — add items to the catalogue',
          body: "An item is a product (drug or consumable). Set its generic name, dosage form, unit cost, minimum stock level. Reusable items (e.g. nebulizer masks) get a usage log instead of being decremented.",
          placement: 'top' },
        { selector: '[data-tour="inventory-batches"]',
          title: 'Step 3 — receive stock in batches',
          body: "Every shipment is a batch with its own batch number, expiry, and unit cost. Pharmacy dispenses pull from the soonest-expiring batch first.",
          placement: 'top' },
        { selector: '[data-tour="inventory-alerts"]',
          title: 'Step 4 — react to low-stock alerts',
          body: "Items below their minimum threshold show here. Click an alert to open the re-order flow.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Wards — Nurse's admission-to-discharge flow
       ────────────────────────────────────────────────────────────── */
    wards: [
        { title: 'Ward nurse walk-through',
          body: "Admit a patient, log shift consumption, discharge them. The Bed Board is your single source of truth — green = free, blue = occupied, amber = cleaning, red = maintenance.",
          placement: 'center' },
        { selector: '[data-tour="bed-board"]',
          title: 'Step 1 — see every bed at a glance',
          body: "Live view of every ward, every bed. Click any bed to see who's in it, when they were admitted, who the admitting doctor is.",
          placement: 'bottom',
          tip: 'The system locks the bed row while you admit, so two nurses can\'t accidentally put two patients in the same bed.' },
        { selector: '[data-tour="ward-admit"]',
          title: 'Step 2 — admit a patient',
          body: 'Click a green bed → "Admit". Pick the patient, the admitting doctor, the primary diagnosis. The bed flips to blue, an Admission record opens.',
          placement: 'top' },
        { selector: '[data-tour="ward-consume"]',
          title: 'Step 3 — log what your shift used',
          body: "Syringes, gloves, IV fluids — log them from the Wards location's stock at end of shift. Inventory decrements automatically and the cost lands on the patient's invoice.",
          placement: 'top' },
        { selector: '[data-tour="ward-discharge"]',
          title: 'Step 4 — discharge',
          body: "Write the discharge notes, click Discharge. The admission closes, the bed flips to amber (cleaning) so housekeeping turns it before the next patient.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Appointments — Receptionist booking flow
       ────────────────────────────────────────────────────────────── */
    appointments: [
        { title: 'Appointments walk-through',
          body: "Book follow-ups, check the day's schedule, mark arrivals. Slot duration comes from Settings (default 30 min).",
          placement: 'center' },
        { selector: '[data-tour="appt-calendar"]',
          title: 'Step 1 — see the doctor\'s calendar',
          body: "Per-doctor calendar shows what's already booked. Empty slots are click-to-book.",
          placement: 'top' },
        { selector: '[data-tour="appt-new"]',
          title: 'Step 2 — book new',
          body: "Pick patient → doctor → date/time. Slot availability is checked server-side so two receptionists booking the same moment can't double-book.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Billing — Cashier's flow
       ────────────────────────────────────────────────────────────── */
    billing: [
        { title: 'Cashier walk-through',
          body: "Open the queue, find your patient, take payment, print the receipt. Cash, card, M-Pesa, or cheque — all work the same way.",
          placement: 'center' },
        { selector: '[data-tour="billing-queue"]',
          title: 'Step 1 — open the pending queue',
          body: "Every patient with an unpaid invoice is here. Search by name or OP number.",
          placement: 'right' },
        { selector: '[data-tour="billing-consultation"]',
          title: 'Quick-add — consultation fee',
          body: "If the doctor forgot to charge the consultation fee, one click adds it to the patient's invoice.",
          placement: 'top' },
        { selector: '[data-tour="billing-pay"]',
          title: 'Step 2 — take the payment',
          body: "Click Pay on the patient's row. Pick the method (Cash / Card / M-Pesa / Cheque). Each method has its own flow — M-Pesa pushes the STK prompt to the patient's phone, cash records change due.",
          placement: 'left' },
        { selector: '[data-tour="billing-mpesa"]',
          title: 'End of shift — M-Pesa reconciliation',
          body: "Every M-Pesa payment is logged here with receipt number and payer phone. Reconcile against your bank settlement statement at close.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Cheque Register — Finance team, bidirectional flow
       ────────────────────────────────────────────────────────────── */
    cheques: [
        { title: 'Cheque register walk-through — both directions',
          body: "Cheques you RECEIVE (insurer paying you, employer paying for an employee's care) AND cheques you ISSUE (paying a supplier, refunding a patient) live in one ledger. Different lifecycles, same screen.",
          placement: 'center' },
        { selector: '[data-tour="cheque-direction-tabs"]',
          title: 'Step 1 — pick Incoming or Outgoing',
          body: "The whole page swaps based on direction — KPI tiles, status options, table columns, even the New-cheque form change to match.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-kpis"]',
          title: 'Step 2 — scan the status tiles',
          body: "Incoming: Received → In-transit → Cleared → Bounced. Outgoing: Issued → In-transit → Cleared → Returned. Each tile shows the count and the running total.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-search"]',
          title: 'Step 3 — find a specific cheque',
          body: "Search by cheque number, counterparty (drawer for incoming, payee for outgoing), or bank.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-new"]',
          title: 'Step 4 — record a new cheque',
          body: "Incoming asks who wrote it to you; outgoing asks who you wrote it to. Different forms, same button.",
          placement: 'left',
          tip: 'Link incoming cheques to an Invoice or Patient — that auto-applies the payment when the cheque clears.' },
        { selector: '[data-tour="cheque-row-actions"]',
          title: 'Step 5 — work the lifecycle',
          body: "Incoming: Deposit → Clear / Bounce. Outgoing: Dispatch → Clear / Return / Stop. Cancel any time before a terminal state. Each transition logs who, when, and (where required) why.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Messages — quick orientation
       ────────────────────────────────────────────────────────────── */
    messages: [
        { title: 'Internal messaging — how staff talk',
          body: "Direct messages for 1:1, groups for ad-hoc huddles, department channels for standing teams. Everything is real-time and audit-logged.",
          placement: 'center' },
        { selector: '[data-tour="msg-list"]',
          title: 'Step 1 — your inbox',
          body: "Threads sorted by last activity. Unread badge per thread shows how many you've missed.",
          placement: 'right' },
        { selector: '[data-tour="msg-new-direct"]',
          title: 'Step 2 — direct message',
          body: "Pick any staff member from the directory. Private to the two of you, logged centrally.",
          placement: 'top' },
        { selector: '[data-tour="msg-new-group"]',
          title: 'Step 3 — group huddle',
          body: "Spin up a group for a case discussion. Add as many staff as you need.",
          placement: 'top' },
        { selector: '[data-tour="msg-departments"]',
          title: 'Step 4 — department channels',
          body: "Persistent channels for each department (ICU, Pharmacy, OBGYN). Membership tracks the directory — join Pharmacy and you're auto-added.",
          placement: 'top' },
    ],

    notifications: [
        { title: 'Notifications inbox',
          body: "Anything the system needs to surface — critical lab values, dispense backlog, expired consents — lands here with a deep link to the source.",
          placement: 'center' },
        { selector: '[data-tour="notif-list"]',
          title: 'Step 1 — read top-down',
          body: "Unread items have a coloured dot. Click to jump to whatever the notification is about; it marks read automatically.",
          placement: 'right' },
        { selector: '[data-tour="notif-read-all"]',
          title: 'Step 2 — bulk-clear unread state',
          body: "End of shift, hit Mark all read. Doesn't delete — the history is preserved.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Settings — Admin configuration tour
       ────────────────────────────────────────────────────────────── */
    settings: [
        { title: 'Settings walk-through',
          body: "Every per-tenant configuration lives here. We'll show you where to find the common ones and how to roll out a change.",
          placement: 'center' },
        { selector: '[data-tour="settings-categories"]',
          title: 'Step 1 — find the category',
          body: "Branding, working hours, billing, lab/radiology defaults, notifications, privacy. Tabs lazy-load so the page stays quick.",
          placement: 'bottom' },
        { selector: '[data-tour="settings-list"]',
          title: 'Step 2 — change the value',
          body: "Each setting picks the right widget for its type — text input, number spinner, toggle, JSON editor. Sensitive values mask until you click the eye.",
          placement: 'top' },
        { selector: '[data-tour="settings-custom"]',
          title: 'Step 3 — add a custom setting',
          body: "Hospital has a quirky requirement? Add a custom key with its data type and default. Becomes available to whichever module reads its category.",
          placement: 'top' },
        { selector: '[data-tour="settings-save"]',
          title: 'Step 4 — save in bulk',
          body: "Make all your changes, then save once. The button counts unsaved changes so you don't accidentally walk away with dirty state.",
          placement: 'left' },
        { selector: '[data-tour="restart-tours"]',
          title: 'Step 5 — replay all tours for new staff',
          body: 'Onboarding someone at a shared workstation? Reset every module\'s "tour-complete" flag here — next visit fires the walk-through fresh.',
          placement: 'left' },
    ],

    branding: [
        { title: 'Branding studio',
          body: "Your hospital's logo + colours + print templates. Applied everywhere — sign-in, sidebar, headers, printed documents.",
          placement: 'center' },
        { selector: '[data-tour="branding-logo"]',
          title: 'Step 1 — upload your logo',
          body: "Square PNG or SVG, transparent background recommended. Auto-applies to the sidebar and every printed document.",
          placement: 'top' },
        { selector: '[data-tour="branding-colors"]',
          title: 'Step 2 — pick brand colours',
          body: "Primary and accent. Hex codes only; the server validates so you can't smuggle in CSS.",
          placement: 'top' },
        { selector: '[data-tour="branding-templates"]',
          title: 'Step 3 — customise print templates',
          body: "Invoices, receipts, prescriptions, lab reports, patient cards. Your hospital name, address, and tagline pull from Settings → Branding automatically.",
          placement: 'top' },
    ],

    accounting: [
        { title: 'Accounting walk-through',
          body: "Full managerial accounting — chart of accounts, journals, fiscal periods, statements, bank reconciliation. Auto-posting wires every cleared payment into the GL.",
          placement: 'center' },
        { selector: '[data-tour="acc-coa"]',
          title: 'Step 1 — chart of accounts',
          body: "Five-tier hierarchy (Assets / Liabilities / Equity / Income / Expenses). Set this up first — every other screen needs accounts to post into.",
          placement: 'top' },
        { selector: '[data-tour="acc-ledger-mappings"]',
          title: 'Step 2 — wire operations to the GL',
          body: "Events like \"invoice paid\" or \"cheque cleared\" need an account to post to. Set these mappings once and auto-posting handles every transaction from then on.",
          placement: 'top',
          tip: 'A missing mapping silently strands entries — the page flags them so you can fix.' },
        { selector: '[data-tour="acc-journal"]',
          title: 'Step 3 — manual journal entries',
          body: "Year-end adjustments, depreciation, accruals. Server enforces debits = credits, your user ID is stamped on every line.",
          placement: 'top' },
        { selector: '[data-tour="acc-statements"]',
          title: 'Step 4 — financial statements',
          body: "Balance sheet, P&L, cash flow, trial balance — all computed live off the GL with date-range filters.",
          placement: 'top' },
        { selector: '[data-tour="acc-bank-recon"]',
          title: 'Step 5 — bank reconciliation',
          body: "Import the bank statement, match transactions, post unmatched lines. The system flags anything in your books not on the statement.",
          placement: 'top' },
        { selector: '[data-tour="acc-debtors"]',
          title: 'Step 6 — debtors and insurance claims',
          body: "Submit a claim, track ageing buckets, settle when paid, reject the rejected portion. Every transition auto-posts to AR.",
          placement: 'top' },
    ],

    payhero: [
        { title: 'M-Pesa Payments — collect at the till & pharmacy',
          body: "This is where you connect your hospital's own Safaricom shortcode so patients can pay by M-Pesa. Let me walk you through the whole setup — it takes about two minutes.",
          placement: 'center' },
        { selector: '[data-tour="mpesa-flow"]',
          title: 'First, understand where the money goes',
          body: "Every shilling a patient pays settles into YOUR hospital's own bank account, on your own schedule. MediFleet never holds or touches your money — it only triggers the M-Pesa prompt and shows you the result live.",
          placement: 'bottom',
          tip: "The only money MediFleet ever charges you is your monthly subscription — never a cut of patient payments." },
        { selector: '[data-tour="mpesa-shortcode"]',
          title: 'Step 1 — enter your Safaricom shortcode',
          body: "Type the PayBill or Buy-Goods Till your hospital already owns, and pick its type (PayBill needs an account number; a Till doesn't). This is the only number you need — there's nothing to copy from any payment provider.",
          placement: 'right' },
        { selector: '[data-tour="mpesa-settlement"]',
          title: 'Step 2 — choose your settlement bank',
          body: "Pick the bank and enter the account number + name where your M-Pesa proceeds should land. This is your hospital's account — the money settles straight to you.",
          placement: 'right' },
        { selector: '[data-tour="mpesa-editor"]',
          title: 'Step 3 — save',
          body: "Click Save settings. Your details are stored and sent to MediFleet, who finishes activating M-Pesa for your till on the platform side.",
          placement: 'top' },
        { selector: '[data-tour="mpesa-status"]',
          title: 'Step 4 — watch the status',
          body: "This card tells you whether M-Pesa is live yet. While it says 'awaiting activation', collection stays disabled. Once MediFleet activates your till it flips to live and you can take payments at the till and pharmacy.",
          placement: 'left' },
        { selector: '[data-tour="mpesa-test"]',
          title: 'Step 5 — send a KES 1 test',
          body: "Once you're live, enter your own phone number and send a real KES 1 prompt. Approve it on your phone to confirm the whole chain works end-to-end before you take a real patient payment.",
          placement: 'left',
          tip: "The test unlocks only after MediFleet activates your till — until then the button stays disabled." },
    ],

    /* ──────────────────────────────────────────────────────────────
       Superadmin — per-hospital Pay Hero provisioning (operator side)
       ────────────────────────────────────────────────────────────── */
    payhero_provisioning: [
        { title: 'M-Pesa Provisioning — wire a hospital',
          body: "This is the operator side: here you connect each hospital's Pay Hero account so they can collect M-Pesa. Hospitals never see this screen — they only see whether their M-Pesa is live.",
          placement: 'center' },
        { selector: '[data-tour="prov-guide"]',
          title: 'The model — you never touch hospital money',
          body: "Each hospital owns its OWN Pay Hero account. Patient money flows into the hospital's account and settles to the hospital's bank. You only trigger the push and relay status. The only money you collect is subscriptions, on the separate Subscription Billing screen.",
          placement: 'bottom' },
        { selector: '[data-tour="prov-hospital"]',
          title: 'Step 1 — pick the hospital',
          body: "Choose which hospital you're wiring. Its saved config (if any) loads below.",
          placement: 'bottom' },
        { selector: '[data-tour="prov-payhero"]',
          title: 'Step 2 — paste their Pay Hero wiring',
          body: "From the hospital's own Pay Hero account, paste the Channel ID, API username/password, and webhook signing secret. Saving a channel id is what flips their M-Pesa to live.",
          placement: 'right',
          tip: "Each hospital signs its callbacks with its own webhook secret — leave it blank only if they share the platform default account." },
        { selector: '[data-tour="prov-test"]',
          title: 'Step 3 — send a KES 1 test',
          body: "After saving, send a real KES 1 STK push using the hospital's wiring to confirm money actually moves and the callback settles. The result shows here.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Superadmin — Subscription Billing (the operator's OWN money)
       ────────────────────────────────────────────────────────────── */
    platform_subscriptions: [
        { title: 'Subscription Billing — the one rail where you get paid',
          body: "Hospitals' patient payments never touch you. This screen is the only place MediFleet receives money: you charge each tenant their subscription into your OWN Pay Hero account. Let me show you how to set it up and collect.",
          placement: 'center' },
        { selector: '[data-tour="sub-guide"]',
          title: 'How it works',
          body: "You configure MediFleet's own Pay Hero account once. Then, each cycle, you charge a tenant's billing phone by M-Pesa — the money lands in your account and settles to your bank. Watch it complete live below.",
          placement: 'bottom' },
        { selector: '[data-tour="sub-health"]',
          title: 'Readiness check',
          body: "This banner tells you whether your billing account is ready. If anything's missing — channel id, credentials, webhook secret, settlement bank, or PUBLIC_BASE_URL — it lists exactly what to fix. Charging stays locked until it's green.",
          placement: 'bottom' },
        { selector: '[data-tour="sub-config"]',
          title: 'Step 1 — provision your account',
          body: "Paste MediFleet's OWN Pay Hero channel id, API username/password, and webhook secret, then pick the settlement bank where YOU get paid. Save. Leave the password/secret blank to keep what's already stored.",
          placement: 'right',
          tip: "These are your account's values — completely separate from the hospital accounts you wire on the M-Pesa Provisioning screen." },
        { selector: '[data-tour="sub-charge"]',
          title: 'Step 2 — charge a tenant',
          body: "Pick a tenant, set their billing phone (you can save it as their default), enter the amount + a period label, and Charge. Use the Test button first to send a real KES 1 push and confirm the chain works.",
          placement: 'left' },
        { selector: '[data-tour="sub-activity"]',
          title: 'Step 3 — watch it settle live',
          body: "Every charge appears here and flips from Pending → Success the instant the tenant approves and the callback settles — no refresh needed. The M-Pesa receipt number is your proof of payment.",
          placement: 'top' },
    ],

    support: [
        { title: 'Support tickets',
          body: "Raise a ticket and the MediFleet platform team responds. Bug? Feature request? Just a question? Pick a category.",
          placement: 'center' },
        { selector: '[data-tour="support-new"]',
          title: 'Step 1 — open a ticket',
          body: "Subject, category, priority, body. Attach screenshots if you've got them.",
          placement: 'left' },
        { selector: '[data-tour="support-list"]',
          title: 'Step 2 — track responses',
          body: "Your tickets, their status (Open / In Progress / Resolved), the team's last reply.",
          placement: 'right' },
    ],

    privacy: [
        { title: 'Privacy & KDPA',
          body: "Section 26 access logs (who saw what), Section 30 consent records (what they allowed), Section 40 erasure requests, Section 43 breach notification with a 72-hour countdown.",
          placement: 'center' },
    ],

    referrals: [
        { title: 'Referrals',
          body: "Out-bound referrals to specialists with status tracking; inbound queue for receiving facilities.",
          placement: 'center' },
    ],

    analytics: [
        { title: 'Analytics',
          body: "Aggregated dashboards across encounters, pharmacy turnover, lab throughput, billing performance, per-doctor productivity. Filter by date-range to slice the period you care about.",
          placement: 'center' },
    ],
};

/* ── Per-user progress (localStorage) ────────────────────────────── */

export function journeyStorageKey(userId) {
    return `hms_journey_progress_${userId || 'anon'}`;
}

export function readProgress(userId) {
    try {
        const raw = localStorage.getItem(journeyStorageKey(userId));
        if (!raw) return new Set();
        const parsed = JSON.parse(raw);
        return new Set(Array.isArray(parsed) ? parsed : []);
    } catch {
        return new Set();
    }
}

export function writeProgress(userId, set) {
    try {
        localStorage.setItem(journeyStorageKey(userId), JSON.stringify([...set]));
    } catch { /* private mode / quota — silently degrade */ }
}
