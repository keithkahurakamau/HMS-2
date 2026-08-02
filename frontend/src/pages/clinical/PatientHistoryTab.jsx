import React, { useState, useEffect } from 'react';
import {
    History, Scissors, Cigarette, Dna, Receipt, Syringe, Printer,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';

const CATEGORIES = [
    { icon: History, label: 'Medical Hx', entry_type: null },
    { icon: Scissors, label: 'Surgical Hx', entry_type: 'SURGICAL_HISTORY' },
    { icon: Cigarette, label: 'Social Hx', entry_type: 'SOCIAL_HISTORY' },
    { icon: Dna, label: 'Family Hx', entry_type: 'FAMILY_HISTORY' },
    { icon: Receipt, label: 'Economic Hx', entry_type: 'ECONOMIC_HISTORY' },
    { icon: Syringe, label: 'Immunizations', entry_type: 'IMMUNIZATION' },
];

const fmt = (v) => (v ? new Date(v).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—');

/**
 * Patient History tab — the six history categories (each opens the read-only
 * history popup, pre-focused) plus this patient's previous visits pulled from
 * GET /clinical/records/{id}. `onOpenHistory(entry_type)` and `onPrintAllVisits`
 * are wired by the shell.
 */
export default function PatientHistoryTab({ patientId, onOpenHistory, onPrintAllVisits }) {
    const [visits, setVisits] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!patientId) { setVisits([]); setLoading(false); return; }
        setLoading(true);
        apiClient.get(`/clinical/records/${patientId}`)
            .then((r) => setVisits(r.data || []))
            .catch(() => toast.error('Could not load previous visits.'))
            .finally(() => setLoading(false));
    }, [patientId]);

    return (
        <div className="space-y-6">
            <div className="card-flush p-6 border-l-4 border-l-brand-500">
                <h3 className="section-eyebrow flex items-center gap-2 mb-4"><History size={16} className="text-brand-500" /> History</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
                    {CATEGORIES.map(({ icon: Icon, label, entry_type }) => (
                        <button type="button" key={label} onClick={() => onOpenHistory(entry_type)}
                            className="flex items-center gap-1.5 px-3 py-2 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 text-ink-600 dark:text-ink-400 rounded-lg text-xs font-medium hover:border-brand-300 dark:hover:border-brand-500/40 hover:text-brand-700 dark:hover:text-brand-300 transition-colors">
                            <Icon size={13} /> {label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="card-flush p-6 border-l-4 border-l-ink-700">
                <div className="flex items-center justify-between mb-4 border-b border-ink-100 dark:border-ink-800 pb-3">
                    <h3 className="section-eyebrow flex items-center gap-2"><History size={16} className="text-ink-600 dark:text-ink-400" /> Previous visits</h3>
                    {onPrintAllVisits && (
                        <button type="button" onClick={onPrintAllVisits} className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 flex items-center gap-1"><Printer size={13} /> Print all</button>
                    )}
                </div>
                {loading ? (
                    <p className="text-sm text-ink-500 dark:text-ink-400">Loading…</p>
                ) : visits.length === 0 ? (
                    <p className="text-sm text-ink-500 dark:text-ink-400 italic">No recorded visits for this patient.</p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="text-2xs uppercase tracking-wider text-ink-500 dark:text-ink-400 text-left border-b border-ink-100 dark:border-ink-800">
                                    <th className="py-2 pr-3 font-medium">Date</th>
                                    <th className="py-2 pr-3 font-medium">Chief complaint</th>
                                    <th className="py-2 pr-3 font-medium">ICD-10</th>
                                    <th className="py-2 pr-3 font-medium">BP</th>
                                    <th className="py-2 font-medium">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                                {visits.map((v) => (
                                    <tr key={v.record_id}>
                                        <td className="py-2 pr-3 text-ink-600 dark:text-ink-300 whitespace-nowrap">{fmt(v.created_at)}</td>
                                        <td className="py-2 pr-3 text-ink-800 dark:text-ink-200">{v.chief_complaint || '—'}</td>
                                        <td className="py-2 pr-3 text-ink-600 dark:text-ink-300">{v.icd10_code || '—'}</td>
                                        <td className="py-2 pr-3 text-ink-600 dark:text-ink-300">{v.blood_pressure || '—'}</td>
                                        <td className="py-2"><span className="badge-neutral text-2xs">{v.record_status}</span></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}
