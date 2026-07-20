import React, { useState, useEffect } from 'react';
import { X, Activity, TrendingUp } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';

const COLUMNS = [
    { key: 'blood_pressure', label: 'BP' },
    { key: 'heart_rate', label: 'HR' },
    { key: 'respiratory_rate', label: 'Resp' },
    { key: 'temperature', label: 'Temp °C' },
    { key: 'spo2', label: 'SpO₂ %' },
    { key: 'weight_kg', label: 'Wt kg' },
    { key: 'bmi', label: 'BMI' },
];

/**
 * Read-only vitals history for the active patient, backing the "View trends"
 * button on the Clinical Desk. Rows come from
 * GET /clinical/patients/{id}/vitals-history oldest-first, so reading down
 * the table follows the trend forward in time.
 */
export default function VitalsTrendsModal({ patient, onClose }) {
    const [rows, setRows] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get(`/clinical/patients/${patient.patient_id}/vitals-history`);
                setRows(res.data || []);
            } catch (e) {
                toast.error(e.response?.data?.detail || 'Failed to load vitals history.');
            } finally {
                setIsLoading(false);
            }
        })();
    }, [patient.patient_id]);

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="vitals-trends-title"
        >
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-elevated w-full max-w-3xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700 flex items-center gap-1.5">
                            <TrendingUp size={12} aria-hidden="true" /> Vitals trends
                        </p>
                        <h2 id="vitals-trends-title" className="text-base sm:text-lg font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-100 dark:hover:bg-ink-800/50 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {isLoading ? (
                        <div className="text-center py-10 text-ink-500 dark:text-ink-400">
                            <Activity className="animate-spin inline mr-2 text-brand-600" size={18} aria-hidden="true" /> Loading vitals history…
                        </div>
                    ) : rows.length === 0 ? (
                        <p className="text-center py-10 text-sm text-ink-500 dark:text-ink-400">
                            No past vitals recorded for this patient yet.
                        </p>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 border-b border-ink-200 dark:border-ink-800 bg-ink-50/60 dark:bg-ink-800/40">
                                        <th scope="col" className="px-4 py-2.5">Date</th>
                                        {COLUMNS.map((c) => (
                                            <th scope="col" key={c.key} className="px-3 py-2.5 whitespace-nowrap">{c.label}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                                    {rows.map((r) => (
                                        <tr key={r.record_id} className="text-ink-800 dark:text-ink-200">
                                            <td className="px-4 py-2 whitespace-nowrap text-xs text-ink-500 dark:text-ink-400">
                                                {r.recorded_at
                                                    ? new Date(r.recorded_at).toLocaleDateString([], { dateStyle: 'medium' })
                                                    : '—'}
                                            </td>
                                            {COLUMNS.map((c) => (
                                                <td key={c.key} className="px-3 py-2 whitespace-nowrap font-mono text-xs">
                                                    {r[c.key] ?? '—'}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            <p className="px-4 py-2.5 text-2xs text-ink-500 dark:text-ink-400">
                                Oldest reading first — read down the table to follow the trend.
                            </p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
