import React, { createContext, useCallback, useContext, useEffect, useMemo, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { apiClient } from '../api/client';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Active patient context.                                                   */
/*                                                                            */
/*  When a clinician opens a patient — from the directory, the clinical       */
/*  queue, or any other "select patient" affordance — the patient becomes     */
/*  the *active* context. The active context:                                 */
/*                                                                            */
/*    1. Renders as a persistent bar at the top of every workspace page,      */
/*       so the clinician always knows which patient they're acting on.       */
/*    2. Survives soft navigations across modules (Clinical → Pharmacy →      */
/*       Lab → …) so the user doesn't have to re-pick the patient.            */
/*    3. Survives reloads via sessionStorage — closing the tab still ends     */
/*       the session, which keeps the audit window tight.                     */
/*    4. Posts an entry to /api/patients/{id}/access on every navigation,     */
/*       feeding the KDPA S.26 audit trail with both the module visited      */
/*       AND the timestamp.                                                   */
/* ────────────────────────────────────────────────────────────────────────── */

const PatientContext = createContext(null);

// Only an opaque ID + the open timestamp ever cross into sessionStorage.
// The full record (name, DOB, allergies, blood group, …) is PHI under KDPA
// S.26 and MUST stay in volatile React state — never persisted in clear
// text. On reload we re-fetch from /api/patients/{id} which goes through
// the authenticated tenant DB; if the cookie is gone or the tenant header
// no longer matches, the fetch fails and the context clears itself, which
// is exactly the right behavior. (CodeQL alert #7: js/clear-text-storage)
const SESSION_KEY = 'hms_active_patient_ref';

// Map the URL prefix to a human-readable module label for the access log.
// Anything not in the map is dropped to a generic "Workspace" — better
// than logging the raw URL into a privacy table.
const PATH_TO_MODULE = [
    ['/app/admin',              'Command Center'],
    ['/app/patients',           'Patient Registry'],
    ['/app/medical-history',    'Medical History'],
    ['/app/clinical',           'Clinical Desk'],
    ['/app/laboratory',         'Laboratory'],
    ['/app/radiology',          'Radiology'],
    ['/app/pharmacy',           'Pharmacy'],
    ['/app/wards',              'Wards'],
    ['/app/appointments',       'Appointments'],
    ['/app/inventory',          'Inventory'],
    ['/app/billing',            'Billing'],
    ['/app/messages',           'Messaging'],
    ['/app/cheques',            'Cheque Register'],
    ['/app/support',            'Support'],
    ['/app/settings',           'Settings'],
    ['/app/branding',           'Branding'],
];

const moduleForPath = (pathname) => {
    if (!pathname) return null;
    for (const [prefix, label] of PATH_TO_MODULE) {
        if (pathname.startsWith(prefix)) return label;
    }
    return null;
};

const loadRefFromSession = () => {
    try {
        const raw = sessionStorage.getItem(SESSION_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        const id = Number(parsed?.patient_id);
        if (!Number.isInteger(id) || id <= 0) return null;
        return { patient_id: id, opened_at: parsed?.opened_at ?? null };
    } catch { return null; }
};

const persistRefToSession = (patientId, openedAt) => {
    try {
        if (patientId) {
            sessionStorage.setItem(
                SESSION_KEY,
                JSON.stringify({ patient_id: patientId, opened_at: openedAt }),
            );
        } else {
            sessionStorage.removeItem(SESSION_KEY);
        }
    } catch { /* private mode, full storage — silently degrade */ }
};

export const PatientProvider = ({ children }) => {
    const [activePatient, setActivePatientState] = useState(null);
    const location = useLocation();
    // Coalesce: don't double-log the same (patient, module) pair within a
    // short window — React routing fires twice in StrictMode and several
    // pages remount on filter changes.
    const lastLog = useRef({ patientId: null, module: null, at: 0 });

    const setActivePatient = useCallback((patient) => {
        // Normalize the shape so every caller — Patients page, Clinical
        // queue, etc. — produces the same context. Required fields:
        //   patient_id, outpatient_no, surname, other_names.
        // Optional: sex, date_of_birth, allergies, blood_group.
        if (!patient) {
            setActivePatientState(null);
            persistRefToSession(null);
            return;
        }
        const patientId = patient.patient_id ?? patient.id ?? null;
        const openedAt = new Date().toISOString();
        const normalised = {
            patient_id:    patientId,
            outpatient_no: patient.outpatient_no ?? patient.opd ?? '',
            surname:       patient.surname ?? '',
            other_names:   patient.other_names ?? '',
            patient_name:  patient.patient_name
                            || [patient.other_names, patient.surname].filter(Boolean).join(' '),
            sex:           patient.sex ?? null,
            age:           patient.age ?? null,
            gender:        patient.gender ?? null,
            date_of_birth: patient.date_of_birth ?? null,
            allergies:     patient.allergies ?? null,
            blood_group:   patient.blood_group ?? null,
            queue_id:      patient.queue_id ?? null,
            opened_at:     openedAt,
        };
        setActivePatientState(normalised);
        // Only the opaque ID + timestamp survive a reload; PHI never touches
        // sessionStorage (see SESSION_KEY comment above).
        persistRefToSession(patientId, openedAt);
    }, []);

    const clearActivePatient = useCallback(() => {
        setActivePatientState(null);
        persistRefToSession(null);
    }, []);

    // Rehydrate the full record on mount when sessionStorage holds an ID
    // from a previous tab session. Fire-and-forget: if the fetch fails
    // (cookie expired, tenant header missing, patient deleted), we clear
    // the stale reference instead of leaving the UI stuck on a phantom.
    useEffect(() => {
        const ref = loadRefFromSession();
        if (!ref) return;
        let cancelled = false;
        apiClient
            .get(`/patients/${ref.patient_id}`)
            .then((res) => {
                if (cancelled) return;
                const p = res?.data;
                if (!p?.patient_id) {
                    persistRefToSession(null);
                    return;
                }
                setActivePatientState({
                    patient_id:    p.patient_id,
                    outpatient_no: p.outpatient_no ?? '',
                    surname:       p.surname ?? '',
                    other_names:   p.other_names ?? '',
                    patient_name:  [p.other_names, p.surname].filter(Boolean).join(' '),
                    sex:           p.sex ?? null,
                    age:           p.age ?? null,
                    gender:        p.gender ?? null,
                    date_of_birth: p.date_of_birth ?? null,
                    allergies:     p.allergies ?? null,
                    blood_group:   p.blood_group ?? null,
                    queue_id:      null,
                    opened_at:     ref.opened_at ?? new Date().toISOString(),
                });
            })
            .catch(() => {
                if (!cancelled) persistRefToSession(null);
            });
        return () => { cancelled = true; };
    }, []);

    // ── Audit trail: log every cross-module navigation while a patient
    // is active. Fires on URL change. Fire-and-forget — a failed log
    // must not block the user's workflow.
    useEffect(() => {
        if (!activePatient || !activePatient.patient_id) return;
        const module = moduleForPath(location.pathname);
        if (!module) return;
        const now = Date.now();
        const same =
            lastLog.current.patientId === activePatient.patient_id
            && lastLog.current.module === module
            && (now - lastLog.current.at) < 4000;
        if (same) return;
        lastLog.current = { patientId: activePatient.patient_id, module, at: now };
        apiClient
            .post(`/patients/${activePatient.patient_id}/access`, { module })
            .catch(() => { /* non-critical, swallow */ });
    }, [activePatient, location.pathname]);

    const value = useMemo(() => ({
        activePatient,
        setActivePatient,
        clearActivePatient,
    }), [activePatient, setActivePatient, clearActivePatient]);

    return <PatientContext.Provider value={value}>{children}</PatientContext.Provider>;
};

export const useActivePatient = () => {
    const ctx = useContext(PatientContext);
    if (!ctx) throw new Error('useActivePatient must be used within PatientProvider');
    return ctx;
};
