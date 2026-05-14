import React from 'react';
import { useNavigate } from 'react-router-dom';
import { X, User, AlertTriangle, Droplet, History, Stethoscope, FlaskConical } from 'lucide-react';
import { useActivePatient } from '../context/PatientContext';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Active patient bar — renders above the main outlet whenever a patient    */
/*  has been opened. Provides a constant "who am I working on" affordance     */
/*  plus shortcuts to the chart and clinical queue.                           */
/*                                                                            */
/*  Keep this bar SHORT — it spans every page, every device. Anything that    */
/*  doesn't help the clinician immediately identify the patient and reach    */
/*  their most-common destinations belongs on the chart itself, not here.    */
/* ────────────────────────────────────────────────────────────────────────── */

const initialsOf = (p) => {
    if (!p) return '?';
    const s = (p.surname || '?').trim()[0] || '?';
    const o = (p.other_names || '').trim()[0] || '';
    return (s + o).toUpperCase();
};

export default function ActivePatientBar() {
    const { activePatient, clearActivePatient } = useActivePatient();
    const navigate = useNavigate();

    if (!activePatient || !activePatient.patient_id) return null;

    const hasAllergies =
        typeof activePatient.allergies === 'string'
        && activePatient.allergies.trim()
        && activePatient.allergies.trim().toLowerCase() !== 'none';

    const fullName = activePatient.patient_name
        || [activePatient.other_names, activePatient.surname].filter(Boolean).join(' ')
        || 'Active patient';

    return (
        <div
            role="region"
            aria-label="Active patient"
            className="sticky top-0 z-20 -mx-4 sm:-mx-6 lg:-mx-8 mb-4 px-4 sm:px-6 lg:px-8 py-2.5 bg-brand-50/95 border-b border-brand-200 backdrop-blur-md shadow-soft"
        >
            <div className="flex items-center gap-3 min-w-0">
                {/* Avatar */}
                <div className="shrink-0 w-9 h-9 rounded-full bg-white border border-brand-200 flex items-center justify-center text-xs font-semibold text-brand-700" aria-hidden="true">
                    {initialsOf(activePatient)}
                </div>

                {/* Identity */}
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Active patient</span>
                        <span className="font-mono text-2xs text-brand-700/80">{activePatient.outpatient_no}</span>
                    </div>
                    <div className="flex items-center gap-2 text-sm font-medium text-ink-900 truncate">
                        <span className="truncate">{fullName}</span>
                        <span className="text-ink-500 text-xs hidden sm:inline">
                            {activePatient.sex || activePatient.gender || ''}
                            {(activePatient.age !== null && activePatient.age !== undefined) ? `, ${activePatient.age}y` : ''}
                        </span>
                        {hasAllergies && (
                            <span className="badge-warn inline-flex items-center gap-1 shrink-0" title={activePatient.allergies}>
                                <AlertTriangle size={10} aria-hidden="true" /> Allergies
                            </span>
                        )}
                        {activePatient.blood_group && activePatient.blood_group !== 'Unknown' && (
                            <span className="hidden md:inline-flex items-center gap-1 text-xs text-ink-600">
                                <Droplet size={11} className="text-rose-500" aria-hidden="true" />
                                {activePatient.blood_group}
                            </span>
                        )}
                    </div>
                </div>

                {/* Quick actions */}
                <div className="flex items-center gap-1 shrink-0">
                    <button
                        type="button"
                        onClick={() => navigate(`/app/medical-history?patient_id=${activePatient.patient_id}`)}
                        className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-brand-800 hover:bg-brand-100 transition-colors cursor-pointer"
                        title="Open full chart"
                    >
                        <History size={13} aria-hidden="true" /> Chart
                    </button>
                    <button
                        type="button"
                        onClick={() => navigate('/app/clinical')}
                        className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-brand-800 hover:bg-brand-100 transition-colors cursor-pointer"
                        title="Go to Clinical Desk"
                    >
                        <Stethoscope size={13} aria-hidden="true" /> Clinical
                    </button>
                    <button
                        type="button"
                        onClick={() => navigate('/app/laboratory')}
                        className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-brand-800 hover:bg-brand-100 transition-colors cursor-pointer"
                        title="Go to Laboratory"
                    >
                        <FlaskConical size={13} aria-hidden="true" /> Lab
                    </button>
                    <button
                        type="button"
                        onClick={clearActivePatient}
                        aria-label="Clear active patient"
                        className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-brand-700 hover:bg-brand-100 transition-colors cursor-pointer"
                        title="Close active patient"
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </div>
            </div>
        </div>
    );
}
