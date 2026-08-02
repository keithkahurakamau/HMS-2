import React, { useState } from 'react';
import {
    ChevronDown, ChevronUp, User, Search, Users, Clock, AlertTriangle, UserMinus,
} from 'lucide-react';
import PatientSearch from '../../components/PatientSearch';
import { minutesWaiting } from '../../utils/clinicalForms';

const priorityBadge = (priority) => {
    if (priority === 'Critical') return 'badge-danger';
    if (priority === 'High') return 'badge-warn';
    return 'badge-neutral';
};

/** DoctorV2 patient-details + consultation-queue header.
 *
 *  Collapsible demographics for the patient being charted, a compact queue
 *  table (Q.No · OPD · Name · From · Mins waiting), a patient typeahead, and a
 *  "View all patients" shortcut. Purely presentational — every action is a
 *  callback the shell wires up.
 */
export default function PatientDetailsHeader({
    activePatient, queue = [], isLoadingQueue = false,
    onSelectPatient, onRemoveFromQueue, onViewAllPatients,
}) {
    const [open, setOpen] = useState(true);

    return (
        <div className="card-flush border border-ink-200 dark:border-ink-800 rounded-2xl overflow-hidden">
            {/* Top row: active patient + search + view-all */}
            <div className="flex flex-wrap items-center gap-3 p-3 border-b border-ink-100 dark:border-ink-800">
                <button type="button" onClick={() => setOpen((o) => !o)}
                    className="flex items-center gap-2 text-sm font-semibold text-ink-900 dark:text-white"
                    aria-expanded={open}>
                    <User size={16} className="text-brand-500" />
                    {activePatient ? activePatient.patient_name : 'No patient selected'}
                    {open ? <ChevronUp size={15} className="text-ink-400" /> : <ChevronDown size={15} className="text-ink-400" />}
                </button>
                <div className="flex-1 min-w-[220px]">
                    <PatientSearch onSelect={onSelectPatient} placeholder="Search patient by name, ID, OP No or phone…" />
                </div>
                <button type="button" onClick={onViewAllPatients} className="btn-ghost text-xs whitespace-nowrap">
                    <Users size={14} /> View all patients
                </button>
            </div>

            {/* Collapsible demographics for the charted patient */}
            {open && activePatient && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 border-b border-ink-100 dark:border-ink-800 bg-ink-50/60 dark:bg-ink-800/30">
                    <Field label="OP Number" value={activePatient.outpatient_no} />
                    <Field label="Age / Sex" value={`${activePatient.age ?? '—'} / ${activePatient.gender ?? '—'}`} />
                    <Field label="Allergies" value={activePatient.allergies || 'None'}
                        danger={activePatient.allergies && activePatient.allergies !== 'None'} />
                    <Field label="Priority" value={activePatient.priority || 'Normal'} />
                </div>
            )}

            {/* Consultation queue table */}
            {open && (
                <div className="p-3">
                    <div className="flex items-center justify-between mb-2">
                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 flex items-center gap-2">
                            <Clock size={13} /> Consultation queue
                        </h4>
                        <span className="text-2xs text-ink-500 dark:text-ink-400">{queue.length} waiting</span>
                    </div>
                    {isLoadingQueue ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400">Loading queue…</p>
                    ) : queue.length === 0 ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400 italic">No patients waiting.</p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-2xs uppercase tracking-wider text-ink-500 dark:text-ink-400 text-left">
                                        <th className="py-1.5 pr-3 font-medium">Q.No</th>
                                        <th className="py-1.5 pr-3 font-medium">OPD</th>
                                        <th className="py-1.5 pr-3 font-medium">Name</th>
                                        <th className="py-1.5 pr-3 font-medium">From</th>
                                        <th className="py-1.5 pr-3 font-medium">Mins</th>
                                        <th className="py-1.5 font-medium sr-only">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                                    {queue.map((item, i) => {
                                        const mins = minutesWaiting(item.joined_at);
                                        const active = activePatient?.queue_id === item.queue_id;
                                        return (
                                            <tr key={item.queue_id}
                                                className={active ? 'bg-brand-50 dark:bg-brand-500/10' : ''}>
                                                <td className="py-1.5 pr-3 text-ink-500 dark:text-ink-400">{i + 1}</td>
                                                <td className="py-1.5 pr-3 text-ink-600 dark:text-ink-300">{item.outpatient_no || '—'}</td>
                                                <td className="py-1.5 pr-3">
                                                    <button type="button" onClick={() => onSelectPatient(item)}
                                                        className="font-medium text-ink-800 dark:text-ink-200 hover:text-brand-600 dark:hover:text-brand-400 text-left flex items-center gap-2">
                                                        {item.patient_name}
                                                        {item.priority && item.priority !== 'Normal' && (
                                                            <span className={`${priorityBadge(item.priority)} text-2xs`}>{item.priority}</span>
                                                        )}
                                                    </button>
                                                </td>
                                                <td className="py-1.5 pr-3 text-ink-600 dark:text-ink-300">{item.triage_time || '—'}</td>
                                                <td className="py-1.5 pr-3 text-ink-600 dark:text-ink-300">{mins == null ? '—' : mins}</td>
                                                <td className="py-1.5 text-right">
                                                    {onRemoveFromQueue && (
                                                        <button type="button" onClick={() => onRemoveFromQueue(item)}
                                                            aria-label={`Remove ${item.patient_name} from queue`}
                                                            className="p-1 rounded-lg text-ink-400 hover:text-rose-600 hover:bg-ink-100 dark:hover:bg-ink-800">
                                                            <UserMinus size={15} />
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function Field({ label, value, danger = false }) {
    return (
        <div>
            <div className="text-2xs uppercase tracking-wider text-ink-500 dark:text-ink-400">{label}</div>
            <div className={`text-sm font-medium flex items-center gap-1 ${danger ? 'text-rose-600 dark:text-rose-400' : 'text-ink-800 dark:text-ink-200'}`}>
                {danger && <AlertTriangle size={13} />}{value ?? '—'}
            </div>
        </div>
    );
}
