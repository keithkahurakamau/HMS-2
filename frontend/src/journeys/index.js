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
 * Adding a new module: pick a stable selector on the target element
 * (we prefer `data-tour="<key>"` attributes already sprinkled through
 * the SPA so refactors don't break tours), write your steps, drop them
 * here. The infra picks it up automatically as long as the module page
 * has a route entry in MainLayout's ROUTE_TO_JOURNEY table.
 */
export const JOURNEYS = {

    /* ──────────────────────────────────────────────────────────────
       Dashboard / Home
       ────────────────────────────────────────────────────────────── */
    dashboard: [
        { title: 'Welcome to MediFleet',
          body: "This is your home base. The platform is multi-tenant, role-driven, and audit-logged from day one. Let's walk through the chrome you'll see on every page.",
          placement: 'center' },
        { selector: '[data-tour="sidebar-nav"]',
          title: 'Module navigation',
          body: "Every module your role can access is in the sidebar. Anything your tenant hasn't subscribed to is hidden — no empty pages, no broken links.",
          placement: 'right',
          tip: 'Hover any item to see its full label; click the brand logo at the top to bounce back to your role landing page.' },
        { selector: '[data-tour="topbar-help"]',
          title: 'Replay this page\'s tour anytime',
          body: "This help icon in the top bar restarts the tour for whichever page you're on. Use it to onboard new staff or refresh yourself on a feature you haven't touched in months.",
          placement: 'bottom' },
        { selector: '[data-tour="topbar-notifications"]',
          title: 'Real-time notifications',
          body: "Clinical alerts, system events, and cross-module updates surface here in real time via WebSocket. The badge counts unread items; click to open the inbox.",
          placement: 'bottom' },
        { selector: '[data-tour="active-patient-bar"]',
          title: 'Active patient context',
          body: "Pick a patient anywhere — directory, queue, lab, ward — and they latch onto this bar. As you move between modules, the bar follows you so you never lose context.",
          placement: 'bottom',
          tip: 'PHI never persists in browser storage. Only the patient ID survives a tab reload — the rest re-fetches from the authenticated API.' },
        { selector: '[data-tour="topbar-signout"]',
          title: 'Sign out',
          body: "Your session is HttpOnly-cookie-based, so closing the tab doesn't kill it. Use Sign Out when leaving a shared workstation to revoke the cookie cleanly.",
          placement: 'bottom' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Admin Dashboard
       ────────────────────────────────────────────────────────────── */
    admin: [
        { title: 'Command Center',
          body: "Everything an Admin needs in one place — staff, roles, permissions, audit log, service pricing. Each card opens its own tab below.",
          placement: 'center' },
        { selector: '[data-tour="admin-tabs"]',
          title: 'Section tabs',
          body: "Switch between Users, Roles & Permissions, Audit Log, and Service Pricing. Each tab loads its own data lazily, so the page stays snappy on first paint.",
          placement: 'bottom' },
        { selector: '[data-tour="admin-users"]',
          title: 'Staff directory',
          body: "Invite new staff, assign roles, deactivate stale accounts. Each row shows the staff member's role, specialization, and active status at a glance.",
          placement: 'top',
          tip: 'Every staff change writes to the audit log with your user ID, the field changed, and the before/after value.' },
        { selector: '[data-tour="admin-roles"]',
          title: 'Roles & permissions',
          body: "MediFleet ships with seven built-in roles (Admin, Doctor, Nurse, Pharmacist, Lab Tech, Radiologist, Receptionist). You can also create custom roles with hand-picked permission codes.",
          placement: 'top' },
        { selector: '[data-tour="admin-permission-override"]',
          title: 'Per-user permission overrides',
          body: "Need to grant one nurse the ability to discharge patients without giving every nurse the same power? Override at the individual user level here. The override layers on top of the user's role.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Patient Registry
       ────────────────────────────────────────────────────────────── */
    patients: [
        { title: 'Patient Registry',
          body: "Where every patient who walks through your front desk gets registered, searched, and routed. KDPA-compliant consent is captured at registration so clinical writes pass the gate from minute one.",
          placement: 'center' },
        { selector: '[data-tour="patients-stats"]',
          title: 'At-a-glance stats',
          body: "Active patient count, registrations today, sex split, and an allergy-flagged count so a front-desk lead can size the workload before opening the directory.",
          placement: 'bottom' },
        { selector: '[data-tour="patient-search"]',
          title: 'Universal search',
          body: "One input searches OP Number, surname, other names, ID number, and phone simultaneously. Type a few characters and matches surface live.",
          placement: 'bottom',
          tip: 'Search is case-insensitive and uses a substring match — typing "256" finds OP Numbers ending in 256 just as well as those starting with it.' },
        { selector: '[data-tour="patients-filter-chips"]',
          title: 'Sex filter',
          body: "Quick chips to narrow the directory by patient sex. Combine with the search box to find, e.g., all male patients named Ochieng.",
          placement: 'bottom' },
        { selector: '[data-tour="register-patient"]',
          title: 'Register a new patient',
          body: "Opens a focused modal that captures demographics, clinical baselines (blood group, allergies, chronic conditions), ID, contact, employment, next-of-kin, and the all-important Treatment-consent checkbox.",
          placement: 'left',
          tip: 'The consent checkbox defaults to checked + Verbal so walk-in registrations finish fast; you can change the method or uncheck if the patient hasn\'t actually agreed yet.' },
        { selector: '[data-tour="patient-row-route-chips"]',
          title: 'Route the patient',
          body: "Send a registered patient straight to Clinical Desk, Laboratory, Radiology, Pharmacy, Wards, or Billing without leaving this page. Each chip opens a picker so you choose the receiving staff member.",
          placement: 'left' },
        { selector: '[data-tour="patient-row-more"]',
          title: 'Row actions',
          body: "The ⋮ menu carries every action available for that patient: view full history, edit details, print the patient card, export a KDPA Section 26 access report, deactivate, or erase (KDPA Section 40).",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Clinical Desk
       ────────────────────────────────────────────────────────────── */
    clinical: [
        { title: 'Clinical Desk',
          body: "Where doctors capture every encounter. Vitals, diagnoses, prescriptions, referrals — all in one form, with a KDPA Section 30 consent gate enforced on every write.",
          placement: 'center' },
        { selector: '[data-tour="clinical-queue"]',
          title: 'Your queue',
          body: "Patients routed to you from the front desk land here, ordered by triage acuity (Critical first) then arrival time. Each row shows the patient's vitals snapshot and the reason they were routed.",
          placement: 'right' },
        { selector: '[data-tour="clinical-vitals"]',
          title: 'Vitals capture',
          body: "BP, pulse, temp, SpO₂, respiratory rate, height, weight, BMI — all in one row. BMI auto-calculates from height + weight. Any value outside the normal range gets flagged in red.",
          placement: 'top' },
        { selector: '[data-tour="clinical-diagnoses"]',
          title: 'Diagnoses',
          body: "Free-text or pick from your custom catalog. Each diagnosis carries a status (Confirmed / Suspected / Ruled out) so a follow-up doctor sees the clinical reasoning.",
          placement: 'top' },
        { selector: '[data-tour="clinical-prescriptions"]',
          title: 'Prescriptions',
          body: "Pick a drug from inventory, set dosage and instructions. The dispense queue in Pharmacy receives the order in real time. Return-prescription flow handles undispensed reversals.",
          placement: 'top',
          tip: 'Pharmacy uses SELECT FOR UPDATE on batch decrements, so two clinicians prescribing the last unit of a batch can\'t double-dispense.' },
        { selector: '[data-tour="clinical-submit"]',
          title: 'Save encounter',
          body: "Hits the KDPA consent gate first. If the patient has no active Treatment consent, a recoverable error tells you to record one from Medical History. Otherwise the encounter saves, the queue advances, and the patient routes to wherever the next action lives (lab / pharmacy / wards / billing).",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Medical History
       ────────────────────────────────────────────────────────────── */
    medical_history: [
        { title: 'Medical History',
          body: "The longitudinal chart — surgical history, family history, social history, immunizations, allergies, chronic conditions, past medical events, obstetric, mental health. Every read is logged per KDPA Section 26.",
          placement: 'center' },
        { selector: '[data-tour="mh-search"]',
          title: 'Patient picker',
          body: "Search by name or OP number. The chart loads with every entry type pre-expanded so you can scroll through the whole history without clicking each section open.",
          placement: 'bottom' },
        { selector: '[data-tour="consent-card"]',
          title: 'Consent panel',
          body: "Shows every consent record on file for this patient. Active Treatment consent gets a green banner; missing consent is a loud red warning so you know a clinical write will be blocked.",
          placement: 'right',
          tip: 'Click "+ Record consent" to capture consent right here without leaving the chart.' },
        { selector: '[data-tour="mh-entry-section"]',
          title: 'Entry sections',
          body: "Each section can be expanded or collapsed independently. The badge next to the label shows how many entries are on file.",
          placement: 'top' },
        { selector: '[data-tour="mh-add-entry"]',
          title: 'Add an entry',
          body: "Adds a new entry to any section. Free-text title and description, optional event date, severity (Mild → Life-threatening), and a status (Active / Resolved / Managed / Remission).",
          placement: 'left' },
        { selector: '[data-tour="mh-print"]',
          title: 'Print summary',
          body: "Produces a printable medical-history summary suitable for sharing with referring specialists. Includes the consent log so the recipient can see scope.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Laboratory
       ────────────────────────────────────────────────────────────── */
    laboratory: [
        { title: 'Laboratory',
          body: "Test catalogue with per-test parameter definitions, barcoded specimens, and critical-value alerts that auto-DM the ordering doctor.",
          placement: 'center' },
        { selector: '[data-tour="lab-queue"]',
          title: 'Order queue',
          body: "Every lab order with its current state (Ordered / Collected / Processing / Resulted / Reported). Click a row to enter results.",
          placement: 'right' },
        { selector: '[data-tour="lab-collect"]',
          title: 'Specimen collection',
          body: "Marks the order as Collected, prints the barcode label, and starts the turnaround clock. Default turnaround comes from Settings → Laboratory.",
          placement: 'top' },
        { selector: '[data-tour="lab-complete"]',
          title: 'Enter results',
          body: "Each test catalogue entry defines its own parameter schema (units, reference range, critical flags). The result form renders dynamically from that schema — no schema, no guessing.",
          placement: 'top',
          tip: 'Out-of-range values automatically notify the ordering doctor if "Notify critical values" is on in Settings.' },
        { selector: '[data-tour="lab-catalog"]',
          title: 'Test catalog',
          body: "Manage the menu of tests your lab offers. Each test has a default specimen type, base price, turnaround hours, and parameters.",
          placement: 'top' },
        { selector: '[data-tour="lab-parameters"]',
          title: 'Parameters per test',
          body: "For a panel like CBC, you'll define WBC, RBC, HGB, etc., each with their own units and ranges. Result entry then uses these parameters automatically.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Radiology
       ────────────────────────────────────────────────────────────── */
    radiology: [
        { title: 'Radiology',
          body: "Imaging orders, sign-off-gated reports, contrast usage tracking. Priority routing (Routine / Urgent / STAT) feeds your queue order.",
          placement: 'center' },
        { selector: '[data-tour="radio-queue"]',
          title: 'Imaging queue',
          body: "STAT requests rise to the top; Urgent next; Routine sorted by request time. Each row shows modality, body part, and contrast indicator.",
          placement: 'right' },
        { selector: '[data-tour="radio-result"]',
          title: 'Report a study',
          body: "Capture findings and impression. If 'Require radiologist sign-off' is on in Settings, the report can't be released without a senior radiologist's attestation.",
          placement: 'top' },
        { selector: '[data-tour="radio-catalog"]',
          title: 'Exam catalog',
          body: "Manage every imaging exam you offer with its modality, body part, and base price.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Pharmacy
       ────────────────────────────────────────────────────────────── */
    pharmacy: [
        { title: 'Pharmacy',
          body: "Stock-aware dispensing with batch + expiry tracking. Cash, Card, or M-Pesa STK payment integrated; receipts auto-generated.",
          placement: 'center' },
        { selector: '[data-tour="pharmacy-inventory"]',
          title: 'Live inventory',
          body: "Every drug, every batch, every expiry. Low-stock items auto-flag and ping the inventory team. Reusable assets (e.g. nebulizer masks) have their own usage log.",
          placement: 'right' },
        { selector: '[data-tour="pharmacy-dispense-queue"]',
          title: 'Dispense queue',
          body: "Prescriptions from Clinical Desk land here. Click a row to start the dispense flow.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-batch-picker"]',
          title: 'Pick a batch',
          body: "Shows every batch with available stock, expiry date, and unit cost. FEFO (First Expiry, First Out) sort by default so you don't sit on soon-to-expire stock.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-pay-cash"]',
          title: 'Cash payment',
          body: "Records the cash receipt and posts straight to the cash drawer for the till's daily reconciliation.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-pay-card"]',
          title: 'Card payment',
          body: "Card transactions are recorded against the till; the actual capture happens at the POS terminal, you just reconcile the slip reference here.",
          placement: 'top' },
        { selector: '[data-tour="pharmacy-pay-mpesa"]',
          title: 'M-Pesa STK push',
          body: "Sends a Pay Hero STK push to the patient's phone. They confirm with their PIN, the callback lands on our webhook, the payment posts automatically. No manual reconciliation.",
          placement: 'top',
          tip: 'Webhook callbacks are HMAC-signed and CIDR-locked, so a malicious party can\'t fake a "paid" notification.' },
        { selector: '[data-tour="pharmacy-receipt"]',
          title: 'Print receipt',
          body: "Prints a customer receipt with the hospital branding, item list, batch numbers, and the dispenser's name. Same template the patient sees in their portal.",
          placement: 'left' },
        { selector: '[data-tour="pharmacy-transactions"]',
          title: 'Transactions log',
          body: "Every dispense, every payment, every return — append-only, audit-friendly, exportable to CSV for accounting reconciliation.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Inventory
       ────────────────────────────────────────────────────────────── */
    inventory: [
        { title: 'Inventory Hub',
          body: "Stores, suppliers, batches, transfers between locations, low-stock alerts. Locations come pre-seeded (Main Store, Pharmacy, Laboratory, Wards) but you can add more.",
          placement: 'center' },
        { selector: '[data-tour="inventory-locations"]',
          title: 'Locations',
          body: "Each location is its own stock pool. Transfers between locations are logged with a from/to/quantity record so reconciliation is mechanical.",
          placement: 'bottom' },
        { selector: '[data-tour="inventory-items"]',
          title: 'Item catalogue',
          body: "Add items with name, generic, dosage form, strength, requires-prescription flag, unit cost, and minimum stock level. Reusable items use a separate usage log instead of being decremented.",
          placement: 'top' },
        { selector: '[data-tour="inventory-batches"]',
          title: 'Batches',
          body: "Receive new stock in batches with batch number, expiry date, and unit cost. Pharmacy dispenses pull from the earliest-expiring batch by default.",
          placement: 'top' },
        { selector: '[data-tour="inventory-alerts"]',
          title: 'Low-stock alerts',
          body: "Items below their minimum threshold raise an alert here. Click an alert to open the procurement flow.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Wards & Admissions
       ────────────────────────────────────────────────────────────── */
    wards: [
        { title: 'Wards & Admissions',
          body: "Real-time bed map, admission/discharge orchestration, per-shift consumption logging, bed-cleaning hand-off.",
          placement: 'center' },
        { selector: '[data-tour="bed-board"]',
          title: 'Bed board',
          body: "Live view of every bed across every ward. Green = Available, blue = Occupied, amber = Cleaning, red = Maintenance. Click any bed to admit a patient or end an admission.",
          placement: 'bottom',
          tip: 'Admissions use SELECT FOR UPDATE on the bed row, so two clerks trying to admit different patients to the same bed at the same second can\'t both succeed.' },
        { selector: '[data-tour="ward-admit"]',
          title: 'Admit a patient',
          body: "Pick the patient, the bed, the admitting doctor, and the primary diagnosis. Creates an AdmissionRecord and flips the bed to Occupied in one transaction.",
          placement: 'top' },
        { selector: '[data-tour="ward-consume"]',
          title: 'Log ward consumption',
          body: "Each shift logs what they used (syringes, gloves, IV fluids). Items decrement from the Wards location's stock.",
          placement: 'top' },
        { selector: '[data-tour="ward-discharge"]',
          title: 'Discharge',
          body: "Captures the discharge notes, ends the admission, flips the bed to Cleaning so housekeeping knows to turn it before the next admission.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Appointments
       ────────────────────────────────────────────────────────────── */
    appointments: [
        { title: 'Appointments',
          body: "Doctor schedules, slot availability, status workflow (Booked → Arrived → Seen / No-show / Cancelled).",
          placement: 'center' },
        { selector: '[data-tour="appt-calendar"]',
          title: 'Calendar view',
          body: "Per-doctor calendar. Slot duration comes from Settings → Working hours (default 30 min). Drag a patient onto a slot to book.",
          placement: 'top' },
        { selector: '[data-tour="appt-new"]',
          title: 'New appointment',
          body: "Pick the patient, the doctor, the date/time. Slot availability is checked server-side so two receptionists can't double-book.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Billing
       ────────────────────────────────────────────────────────────── */
    billing: [
        { title: 'Billing & Finance',
          body: "Encounter-grained invoicing with idempotency-keyed payments. Cash, Card, M-Pesa STK, or Cheque. Partial payments supported.",
          placement: 'center' },
        { selector: '[data-tour="billing-queue"]',
          title: 'Pending invoices',
          body: "Every patient with an open invoice. The queue is eager-loaded so opening it on a busy day doesn't N+1 the database.",
          placement: 'right' },
        { selector: '[data-tour="billing-consultation"]',
          title: 'Consultation fee',
          body: 'One-click "Add consultation fee" charges the configured fee for the patient\'s first encounter today.',
          placement: 'top' },
        { selector: '[data-tour="billing-pay"]',
          title: 'Process payment',
          body: "Opens the payment modal with method picker (Cash / Card / M-Pesa / Cheque). Each method has its own follow-up flow.",
          placement: 'left' },
        { selector: '[data-tour="billing-mpesa"]',
          title: 'M-Pesa transactions',
          body: "Every M-Pesa payment lands here with the receipt number, the phone number that paid, and a link back to the originating invoice. Use this view to reconcile against your Pay Hero dashboard.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Cheque Register — INCOMING + OUTGOING
       ────────────────────────────────────────────────────────────── */
    cheques: [
        { title: 'Cheque Register — bidirectional',
          body: "Track every cheque your hospital RECEIVES (from insurers, employers, patients) AND every cheque you ISSUE (to suppliers, staff, refunds). Two flows, one ledger, separate lifecycles.",
          placement: 'center' },
        { selector: '[data-tour="cheque-direction-tabs"]',
          title: 'Direction tabs',
          body: "Switch between Incoming and Outgoing. The whole page swaps — KPI tiles, status filter, table columns, row actions, and the New-cheque modal — to match the active flow.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-kpis"]',
          title: 'Status KPIs',
          body: "Incoming shows Received → In-transit → Cleared → Bounced. Outgoing shows Issued → In-transit → Cleared → Returned. Each tile carries the count and the running total in your currency.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-search"]',
          title: 'Search',
          body: "Finds a cheque by its number, the counterparty name (drawer for incoming, payee for outgoing), or the bank name.",
          placement: 'bottom' },
        { selector: '[data-tour="cheque-new"]',
          title: 'New cheque',
          body: "Opens the create modal with its own direction toggle. Incoming asks for drawer + drawer type; outgoing asks for payee + payee type + date issued.",
          placement: 'left',
          tip: 'Incoming cheques can be linked to an Invoice or a Patient; outgoing cheques don\'t carry those links — they post against Accounts Payable.' },
        { selector: '[data-tour="cheque-row-actions"]',
          title: 'Row actions',
          body: "The buttons on each row enforce the lifecycle. Incoming: Deposit → Clear / Bounce. Outgoing: Dispatch → Clear / Return / Stop. Cancel is available any time before a terminal state.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Messages
       ────────────────────────────────────────────────────────────── */
    messages: [
        { title: 'Internal Messaging',
          body: "Direct, group, and department conversations. Real-time fan-out via WebSocket + Redis pub/sub, so escalations land instantly even across worker processes.",
          placement: 'center' },
        { selector: '[data-tour="msg-list"]',
          title: 'Conversation list',
          body: "Unread badges next to each thread. The list is sorted by last activity so the threads needing your attention float to the top.",
          placement: 'right' },
        { selector: '[data-tour="msg-new-direct"]',
          title: 'Start a direct message',
          body: "Pick any staff member from the directory. The conversation is private to the two of you.",
          placement: 'top' },
        { selector: '[data-tour="msg-new-group"]',
          title: 'Group chat',
          body: "Spin up an ad-hoc group for a case discussion or a shift huddle.",
          placement: 'top' },
        { selector: '[data-tour="msg-departments"]',
          title: 'Department channels',
          body: "Persistent channels for each department (ICU, Pharmacy, OBGYN, etc.). Membership tracks the staff directory automatically — when someone joins Pharmacy, they're added to the channel.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Notifications
       ────────────────────────────────────────────────────────────── */
    notifications: [
        { title: 'Notifications inbox',
          body: "System and clinical alerts with deep links into the originating record.",
          placement: 'center' },
        { selector: '[data-tour="notif-list"]',
          title: 'Inbox',
          body: "Unread items have a coloured dot. Click to open the source record (lab result, appointment reminder, etc.); the notification marks read.",
          placement: 'right' },
        { selector: '[data-tour="notif-read-all"]',
          title: 'Mark all read',
          body: "Bulk-clears the unread state. Doesn't delete anything — the audit history of every notification you've received stays intact.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Settings
       ────────────────────────────────────────────────────────────── */
    settings: [
        { title: 'Hospital Settings',
          body: "Per-tenant key/value configuration store covering branding, working hours, billing, lab/radiology defaults, notifications, and privacy.",
          placement: 'center' },
        { selector: '[data-tour="settings-categories"]',
          title: 'Categories',
          body: "Branding, working hours, billing, laboratory, radiology, notifications, privacy. Each tab loads its own slice of settings.",
          placement: 'bottom' },
        { selector: '[data-tour="settings-list"]',
          title: 'Setting widgets',
          body: "Each setting renders the right widget for its data type: text input for strings, number spinner for numbers, toggle for booleans, code editor for JSON. Sensitive values are masked until you click the eye.",
          placement: 'top' },
        { selector: '[data-tour="settings-custom"]',
          title: 'Custom settings',
          body: "Need a setting that doesn't exist out-of-the-box? Add it here with a category, key, label, description, data type, and default value. Becomes available to the modules that read its category.",
          placement: 'top' },
        { selector: '[data-tour="settings-save"]',
          title: 'Save changes',
          body: "Bulk-saves every dirty setting in one PUT. The count of unsaved changes is shown on the button so you don't lose track.",
          placement: 'left' },
        { selector: '[data-tour="restart-tours"]',
          title: 'Replay tours',
          body: "Resets every module's tour-complete flag so the next time you visit each module, the tour fires fresh. Useful for onboarding a new team member at a shared workstation.",
          placement: 'left' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Branding
       ────────────────────────────────────────────────────────────── */
    branding: [
        { title: 'Branding Studio',
          body: "Upload your hospital's logo, background, and brand colours. Applied everywhere — sign-in page, sidebar, headers, printed documents.",
          placement: 'center' },
        { selector: '[data-tour="branding-logo"]',
          title: 'Logo upload',
          body: "Drop a square PNG or SVG (transparent background recommended). Auto-applies to the sidebar brand block and every printed document.",
          placement: 'top' },
        { selector: '[data-tour="branding-colors"]',
          title: 'Brand colours',
          body: "Pick a primary and accent colour. We validate hex codes server-side and never let you smuggle CSS in — every value is allow-listed before it touches the CSSOM.",
          placement: 'top' },
        { selector: '[data-tour="branding-templates"]',
          title: 'Print templates',
          body: "Customize how invoices, receipts, prescriptions, lab reports, and patient cards print. Your hospital name, address, and tagline pull from Settings → Branding automatically.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Accounting (Managerial)
       ────────────────────────────────────────────────────────────── */
    accounting: [
        { title: 'Managerial Accounting',
          body: "Chart of accounts, journals, fiscal periods, debtor lifecycle, bank reconciliation, IFRS-shaped financial statements. Auto-posting wires every cleared bill, dispense, and cheque directly into the GL.",
          placement: 'center' },
        { selector: '[data-tour="acc-coa"]',
          title: 'Chart of accounts',
          body: "Five-tier hierarchy (Assets / Liabilities / Equity / Income / Expenses). Each leaf account is the destination for auto-posted journal entries.",
          placement: 'top' },
        { selector: '[data-tour="acc-ledger-mappings"]',
          title: 'Ledger mappings',
          body: "This is the link between operational events (billing.invoice.paid, cheques.deposit.cleared, etc.) and the GL accounts that should be debited and credited. Set them once; auto-posting handles the rest.",
          placement: 'top',
          tip: 'A misconfigured mapping silently lands entries in the wrong account. We surface a "missing mapping" notice when an event fires without a mapping.' },
        { selector: '[data-tour="acc-journal"]',
          title: 'Manual journal entries',
          body: "Year-end adjustments, depreciation, accruals. Each entry is balanced server-side (debits must equal credits) and stamped with your user ID.",
          placement: 'top' },
        { selector: '[data-tour="acc-statements"]',
          title: 'Financial statements',
          body: "Balance sheet, P&L, cash flow, trial balance, daily collections — all computed live off the GL with date-range filters.",
          placement: 'top' },
        { selector: '[data-tour="acc-bank-recon"]',
          title: 'Bank reconciliation',
          body: "Import a bank statement, match transactions to your books, post any unmatched lines to the right GL account.",
          placement: 'top' },
        { selector: '[data-tour="acc-debtors"]',
          title: 'Debtors lifecycle',
          body: "Insurance claims and credit accounts. Submit a claim, track ageing, settle when paid, reject the rejected portion. Each transition auto-posts to AR.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Pay Hero (M-Pesa) settings
       ────────────────────────────────────────────────────────────── */
    payhero: [
        { title: 'Pay Hero (M-Pesa) settings',
          body: "Per-tenant Pay Hero aggregator credentials. STK push triggers, webhook validation, per-till reconciliation.",
          placement: 'center' },
        { selector: '[data-tour="payhero-config"]',
          title: 'Aggregator credentials',
          body: "Channel ID, username, password — encrypted at rest with the Fernet ENCRYPTION_KEY and never returned to the SPA in plaintext.",
          placement: 'top' },
        { selector: '[data-tour="payhero-test"]',
          title: 'Test STK push',
          body: "Sends a 1-shilling STK push to a phone number you choose, end-to-end. Confirms the webhook callback lands correctly and the receipt posts.",
          placement: 'top' },
        { selector: '[data-tour="payhero-unmatched"]',
          title: 'Unmatched callbacks',
          body: "If a callback arrives that doesn't match a known invoice (rare; usually wrong reference field), it lands here for manual assignment.",
          placement: 'top' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Support
       ────────────────────────────────────────────────────────────── */
    support: [
        { title: 'In-app Support',
          body: "Raise a ticket and the MediFleet platform team will respond. Full lifecycle (Open / In Progress / Resolved / Closed), priority, audit trail.",
          placement: 'center' },
        { selector: '[data-tour="support-new"]',
          title: 'New ticket',
          body: "Subject, category (Bug / Feature / Question / Other), priority, body. Attachments coming soon.",
          placement: 'left' },
        { selector: '[data-tour="support-list"]',
          title: 'Your tickets',
          body: "Every ticket you've raised, with its status and the platform team's last reply.",
          placement: 'right' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Privacy / KDPA — placeholder, single intro card
       ────────────────────────────────────────────────────────────── */
    privacy: [
        { title: 'Privacy & KDPA',
          body: "Section 26 access logs, Section 30 consent records, Section 40 erasure requests, Section 43 breach notification (72-hour countdown).",
          placement: 'center' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Referrals
       ────────────────────────────────────────────────────────────── */
    referrals: [
        { title: 'Referrals',
          body: "Out-bound referrals to specialists with status tracking and an inbound queue for receiving facilities.",
          placement: 'center' },
    ],

    /* ──────────────────────────────────────────────────────────────
       Analytics
       ────────────────────────────────────────────────────────────── */
    analytics: [
        { title: 'Analytics',
          body: "Aggregated dashboards across encounters, pharmacy turnover, lab throughput, billing performance, per-doctor productivity.",
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
