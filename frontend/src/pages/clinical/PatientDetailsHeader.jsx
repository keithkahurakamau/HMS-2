import React, { useState } from 'react';
import {
    ChevronDown, ChevronUp, User, Users, Clock, AlertTriangle, UserMinus,
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
    showSearch = true, queueLabel = 'Consultation queue',
}) {
    // Queue starts collapsed while charting (maximise the workspace) and open
    // when idle (so the doctor can pick the next patient). The shell remounts
    // this via `key` on patient change, so this initialiser re-runs correctly.
    const [open, setOpen] = useState(() => !activePatient);
    const hasAllergy = activePatient?.allergies && activePatient.allergies.toLowerCase() !== 'none';

    return (
        <div className="card-flush border border-ink-200 dark:border-ink-800 rounded-2xl overflow-hidden">
            {/* Top row: patient summary (always visible, incl. allergies) + search + view-all */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3 border-b border-ink-100 dark:border-ink-800">
                <button type="button" onClick={() => setOpen((o) => !o)}
                    className="flex items-center gap-2 text-sm font-semibold text-ink-900 dark:text-white shrink-0"
                    aria-expanded={open} title={open ? `Hide ${queueLabel.toLowerCase()}` : `Show ${queueLabel.toLowerCase()}`}>
                    <User size={16} className="text-brand-500" />
                    <span className="max-w-[13rem] truncate">{activePatient ? activePatient.patient_name : 'No patient selected'}</span>
                    {open ? <ChevronUp size={15} className="text-ink-400" /> : <ChevronDown size={15} className="text-ink-400" />}
                </button>
                {activePatient && (
                    <div className="flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400 min-w-0">
                        {activePatient.outpatient_no && <span className="font-mono truncate">{activePatient.outpatient_no}</span>}
                        <span className="text-ink-300 dark:text-ink-600">·</span>
                        <span className="whitespace-nowrap">{activePatient.age ?? '—'} / {activePatient.gender ?? '—'}</span>
                        {hasAllergy && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 dark:bg-rose-500/10 ring-1 ring-rose-200 dark:ring-rose-500/20 text-rose-700 dark:text-rose-300 px-2 py-0.5 font-medium max-w-[16rem] truncate">
                                <AlertTriangle size={11} className="shrink-0" /> {activePatient.allergies}
                            </span>
                        )}
                    </div>
                )}
                {showSearch ? (
                    <div className="flex-1 min-w-[200px]">
                        <PatientSearch onSelect={onSelectPatient} placeholder="Search patient by name, ID, OP No or phone…" />
                    </div>
                ) : <div className="flex-1" />}
                {onViewAllPatients && (
                    <button type="button" onClick={onViewAllPatients} className="btn-ghost text-xs whitespace-nowrap shrink-0">
                        <Users size={14} /> View all patients
                    </button>
                )}
            </div>

            {/* Consultation queue table (collapsible) */}
            {open && (
                <div className="p-3">
                    <div className="flex items-center justify-between mb-2">
                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 flex items-center gap-2">
                            <Clock size={13} /> {queueLabel}
                        </h4>
                        <span className="text-2xs text-ink-500 dark:text-ink-400">{queue.length} waiting</span>
                    </div>
                    {isLoadingQueue ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400">Loading queue…</p>
                    ) : queue.length === 0 ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400 italic">No patients waiting.</p>
                    ) : (
                        <div className="overflow-auto max-h-56 custom-scrollbar">
                            <table className="table-inline">
                                <thead>
                                    <tr className="text-2xs uppercase tracking-wider text-ink-500 dark:text-ink-400 text-left">
                                        <th>Q.No</th>
                                        <th>OPD</th>
                                        <th>Name</th>
                                        <th>From</th>
                                        <th>Mins</th>
                                        <th className="sr-only">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                                    {queue.map((item, i) => {
                                        const mins = minutesWaiting(item.joined_at);
                                        const active = activePatient?.queue_id === item.queue_id;
                                        return (
                                            <tr key={item.queue_id}
                                                className={active ? 'bg-brand-50 dark:bg-brand-500/10' : ''}>
                                                <td className="text-ink-500 dark:text-ink-400">{i + 1}</td>
                                                <td className="text-ink-600 dark:text-ink-300">{item.outpatient_no || '—'}</td>
                                                <td>
                                                    <button type="button" onClick={() => onSelectPatient(item)}
                                                        className="font-medium text-ink-800 dark:text-ink-200 hover:text-brand-600 dark:hover:text-brand-400 text-left flex items-center gap-2">
                                                        {item.patient_name}
                                                        {item.priority && item.priority !== 'Normal' && (
                                                            <span className={`${priorityBadge(item.priority)} text-2xs`}>{item.priority}</span>
                                                        )}
                                                    </button>
                                                </td>
                                                <td className="text-ink-600 dark:text-ink-300">{item.triage_time || '—'}</td>
                                                <td className="text-ink-600 dark:text-ink-300">{mins == null ? '—' : mins}</td>
                                                <td className="num">
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
