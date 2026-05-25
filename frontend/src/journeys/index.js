/**
 * Module journey step definitions.
 *
 * Each key maps to an array of steps. A step is:
 *   {
 *     selector?: string,    // CSS selector to spotlight; omit for centred card
 *     title:     string,
 *     body:      string,
 *     placement?: 'top' | 'bottom' | 'left' | 'right' | 'center',
 *   }
 *
 * If `selector` doesn't resolve at runtime we silently fall back to a
 * centred card — so a tour never breaks when a target moves; it just
 * loses its arrow.
 *
 * Adding a new module: pick a stable selector on the target element (we
 * prefer `data-tour="<key>"` attributes already sprinkled through the
 * SPA so refactors don't break tours), write 2-4 short steps, drop them
 * here. The infra picks it up automatically as long as the module page
 * calls `useModuleJourney('<key>')`.
 */
export const JOURNEYS = {
    /* ─────────── Always-on workspace ─────────── */

    dashboard: [
        { title: 'Welcome to MediFleet',
          body: "This is your home base. Every signed-in staff member lands here first — and your view adapts to your role.",
          placement: 'center' },
        { selector: '[data-tour="role-redirect"]',
          title: 'Role-based start page',
          body: "Doctors land on Clinical Desk, nurses on Wards, pharmacists on Pharmacy. The platform picks the right place for you.",
          placement: 'bottom' },
        { selector: '[data-tour="sidebar-nav"]',
          title: 'Module navigation',
          body: "Every module you have access to is in the sidebar. Modules you haven't subscribed to are hidden — no clutter.",
          placement: 'right' },
        { selector: '[data-tour="active-patient-bar"]',
          title: 'Active patient strip',
          body: "Pick a patient anywhere in the app and this bar follows you across modules — so you never lose context.",
          placement: 'bottom' },
    ],

    patients: [
        { title: 'Patient Registry',
          body: "Search, register, and manage every patient who walks through your front desk. KDPA consent is captured at registration so clinical writes pass the gate from day one.",
          placement: 'center' },
        { selector: '[data-tour="patient-search"]',
          title: 'Universal search',
          body: "Search by name, OP number, ID, or phone — one input handles everything. Recent matches surface first.",
          placement: 'bottom' },
        { selector: '[data-tour="register-patient"]',
          title: 'Register a new patient',
          body: "Demographics, clinical baselines, contact, employer, next-of-kin — plus the Treatment-consent checkbox at the bottom.",
          placement: 'left' },
        { selector: '[data-tour="patient-row-actions"]',
          title: 'Row actions',
          body: "Open any row's ⋮ menu to view history, edit details, print the patient card, export a KDPA Section 26 report, deactivate, or erase.",
          placement: 'left' },
    ],

    appointments: [
        { title: 'Appointments',
          body: "Book, reschedule, and cancel appointments. Doctor schedules respect each provider's working hours.",
          placement: 'center' },
        { selector: '[data-tour="appointments-calendar"]',
          title: 'Calendar view',
          body: "Per-doctor calendar with slot-availability lookups so you never double-book.",
          placement: 'top' },
    ],

    messages: [
        { title: 'Internal messaging',
          body: "Direct, group, and department conversations — fan-out is real-time via WebSocket + Redis pub/sub.",
          placement: 'center' },
        { selector: '[data-tour="conversation-list"]',
          title: 'Your conversations',
          body: "Unread badges across tabs. Click a thread to open it; click + to start a new direct or group conversation.",
          placement: 'right' },
    ],

    notifications: [
        { title: 'Notifications inbox',
          body: "System events and clinical alerts land here with deep-links into the originating record.",
          placement: 'center' },
    ],

    support: [
        { title: 'In-app support',
          body: "Raise a ticket and the MediFleet platform team will respond — with full ticket lifecycle + audit.",
          placement: 'center' },
    ],

    settings: [
        { title: 'Hospital settings',
          body: "Branding, working hours, billing, lab, radiology, notifications, and privacy controls live here.",
          placement: 'center' },
        { selector: '[data-tour="settings-categories"]',
          title: 'Setting categories',
          body: "Each tab covers one slice of hospital configuration. Sensitive values are masked until you click the eye.",
          placement: 'bottom' },
        { selector: '[data-tour="restart-tours"]',
          title: 'Re-run any tour',
          body: "Want to see a module's intro again? Click here and the next time you visit that module the tour will start fresh.",
          placement: 'left' },
    ],

    /* ─────────── Optional add-on modules ─────────── */

    clinical: [
        { title: 'Clinical Desk',
          body: "Encounters, vitals, diagnoses, prescriptions, referrals — captured in one continuous flow with a KDPA Section 30 consent gate on every write.",
          placement: 'center' },
        { selector: '[data-tour="clinical-queue"]',
          title: 'Your queue',
          body: "Patients routed to you from the front desk appear here, ordered by triage acuity then arrival time.",
          placement: 'right' },
        { selector: '[data-tour="encounter-form"]',
          title: 'Encounter capture',
          body: "Vitals, complaint, diagnoses (ICD-style), prescriptions, and referrals in one form. Auto-saves as you type.",
          placement: 'top' },
    ],

    laboratory: [
        { title: 'Laboratory',
          body: "Lab catalogue with per-test parameter definitions, barcoded specimen IDs, and critical-value alerts.",
          placement: 'center' },
        { selector: '[data-tour="lab-queue"]',
          title: 'Order queue',
          body: "New orders land here. Collect → process → result, each step audit-logged.",
          placement: 'right' },
        { selector: '[data-tour="lab-catalog"]',
          title: 'Test catalog',
          body: "Add new tests with their reference ranges, units, and required parameters. Barcoding is per-test.",
          placement: 'left' },
    ],

    radiology: [
        { title: 'Radiology',
          body: "Imaging orders with priority routing, radiologist sign-off requirements, and contrast tracking.",
          placement: 'center' },
        { selector: '[data-tour="radiology-queue"]',
          title: 'Imaging queue',
          body: "Routine / Urgent / STAT triage. Sign-off is required on every report before release.",
          placement: 'right' },
    ],

    pharmacy: [
        { title: 'Pharmacy',
          body: "Post-dispense and OTC payment flows, batch + expiry tracking, low-stock alerts.",
          placement: 'center' },
        { selector: '[data-tour="pharmacy-inventory"]',
          title: 'Stock visibility',
          body: "Every batch, every expiry. Low-stock items raise an alert that pings the right team automatically.",
          placement: 'right' },
        { selector: '[data-tour="dispense-flow"]',
          title: 'Dispense flow',
          body: "Pick a prescription → confirm batch → process payment (Cash / Card / M-Pesa STK) → print receipt.",
          placement: 'top' },
    ],

    inventory: [
        { title: 'Inventory',
          body: "Stores, suppliers, batches, reusable-asset tracking, and per-location stock visibility.",
          placement: 'center' },
        { selector: '[data-tour="inventory-items"]',
          title: 'Item catalogue',
          body: "Add items with batch + expiry. Reusable assets get their own usage log.",
          placement: 'top' },
    ],

    wards: [
        { title: 'Wards & In-Patient',
          body: "Real-time bed map, admission/discharge orchestration, per-shift consumption logging.",
          placement: 'center' },
        { selector: '[data-tour="bed-board"]',
          title: 'Bed board',
          body: "Live view of every ward. Locked-row admissions defeat double-booking at the SQL level.",
          placement: 'bottom' },
    ],

    billing: [
        { title: 'Billing',
          body: "Encounter-grained invoicing, partial-payment support, consultation-fee shortcuts.",
          placement: 'center' },
        { selector: '[data-tour="billing-queue"]',
          title: 'Pending invoices',
          body: "Every patient with an open invoice surfaces here. Eager-loaded so the queue stays snappy.",
          placement: 'right' },
        { selector: '[data-tour="payment-modal"]',
          title: 'Process payment',
          body: "Cash, Card, M-Pesa STK Push, or Pay Hero. Every payment is idempotency-keyed.",
          placement: 'left' },
    ],

    cheques: [
        { title: 'Cheque register',
          body: "Receipt → deposit → clear → bounce or cancel. Each transition auto-posts to the GL.",
          placement: 'center' },
    ],

    medical_history: [
        { title: 'Medical History',
          body: "Longitudinal chart across nine entry types — surgical, family, social, immunizations, allergies, mental health, more.",
          placement: 'center' },
        { selector: '[data-tour="consent-card"]',
          title: 'Consent panel',
          body: "Active treatment consent shows here. Record a new consent or print the audit trail.",
          placement: 'right' },
    ],

    payhero: [
        { title: 'Pay Hero (M-Pesa)',
          body: "Mobile-money collections — STK push, webhook-validated callbacks, per-tenant credentials.",
          placement: 'center' },
    ],

    analytics: [
        { title: 'Analytics',
          body: "Aggregated dashboards across encounters, pharmacy turnover, lab throughput, and billing performance.",
          placement: 'center' },
    ],

    branding: [
        { title: 'Branding',
          body: "Upload your logo, set brand colours, choose how printed documents look. Per-tenant theming applied across the SPA.",
          placement: 'center' },
    ],

    privacy: [
        { title: 'Privacy & KDPA',
          body: "Consent records, DSAR exports, Section 40 erasure, and Section 43 breach notification with a 72-hour countdown.",
          placement: 'center' },
    ],

    referrals: [
        { title: 'Referrals',
          body: "Out-bound referrals to specialists with status tracking and an inbound queue for receiving facilities.",
          placement: 'center' },
    ],

    accounting: [
        { title: 'Managerial Accounting',
          body: "Chart of accounts, journals, fiscal periods, debtor lifecycle, bank reconciliation, IFRS-shaped statements.",
          placement: 'center' },
        { selector: '[data-tour="acc-statements"]',
          title: 'Financial statements',
          body: "Balance sheet, P&L, cash flow, trial balance — all computed live off the GL.",
          placement: 'top' },
    ],

    admin: [
        { title: 'Admin Dashboard',
          body: "Staff directory, roles, permissions, audit log, service pricing — everything an Admin needs in one place.",
          placement: 'center' },
        { selector: '[data-tour="admin-users"]',
          title: 'Staff & roles',
          body: "Invite staff, assign roles, override permissions per user. Every change is audit-logged.",
          placement: 'bottom' },
    ],
};

/**
 * Generates a per-user localStorage key for the journey progress so two
 * accounts sharing one browser don't see each other's tour state.
 */
export function journeyStorageKey(userId) {
    return `hms_journey_progress_${userId || 'anon'}`;
}

/**
 * Returns the set of module keys this user has completed (Set<string>).
 * Reads from localStorage; tolerates corrupted JSON by returning empty.
 */
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
