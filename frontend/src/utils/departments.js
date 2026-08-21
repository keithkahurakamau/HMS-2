/**
 * Canonical queue/analytics department names (the backend source of truth) →
 * the single display label shown to users everywhere a department/room appears
 * (Queue Board, routing chips, triage dispositions, module strips).
 *
 * The backend keeps the canonical names ("Consultation", …) because analytics
 * rollups and per-module queue filters key off them; this map is purely the
 * presentation layer so users never see the same place under two names
 * (e.g. "Consultation" vs "Clinical Desk").
 */
export const DEPARTMENT_LABELS = {
    Reception: 'Reception',
    Triage: 'Triage',
    Consultation: 'Clinical Desk',
    Laboratory: 'Laboratory',
    Radiology: 'Radiology',
    Pharmacy: 'Pharmacy',
    Billing: 'Billing',
    Wards: 'Wards',
    Maternity: 'Maternity',
    Dialysis: 'Dialysis',
    Theatre: 'Theatre',
};

/** Friendly, app-wide display label for a canonical department name. */
export const departmentLabel = (canonical) => DEPARTMENT_LABELS[canonical] || canonical || '—';
