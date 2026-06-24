import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { Users, Clock, X, UserMinus } from 'lucide-react';

/**
 * DepartmentQueue — shows patients routed to a department via the generic
 * PatientQueue, with per-row remove (checkout) and cancel actions. Dropped
 * into module pages (Reception, Lab, Pharmacy, Radiology, Wards) so triage
 * dispositions actually surface where the patient was sent.
 *
 * Props:
 *   department  {string}   required — filters the queue endpoint
 *   title       {string?}  optional heading override
 *   onChange    {function?} called after a successful remove or cancel
 */
export default function DepartmentQueue({ department, title, onChange }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchRows = useCallback(async () => {
        setLoading(true);
        try {
            const res = await apiClient.get(`/queue/?department=${department}`);
            setRows(res.data || []);
        } catch {
            // queue read is best-effort; leave empty on failure
        } finally {
            setLoading(false);
        }
    }, [department]);

    useEffect(() => { fetchRows(); }, [fetchRows]);

    const remove = async (queueId) => {
        try {
            await apiClient.patch(`/queue/${queueId}/checkout`);
            toast.success('Removed from queue.');
            fetchRows();
            onChange?.();
        } catch {
            toast.error('Could not remove from queue.');
        }
    };

    const cancel = async (queueId) => {
        const reason = window.prompt('Cancel reason (optional):') ?? null;
        try {
            await apiClient.patch(`/queue/${queueId}/cancel`, { reason });
            toast.success('Patient cancelled.');
            fetchRows();
            onChange?.();
        } catch {
            toast.error('Could not cancel.');
        }
    };

    return (
        <div className="card">
            <div className="p-4 flex items-center gap-3 border-b border-ink-100 dark:border-ink-800">
                <Users className="text-brand-600" size={18} />
                <h2 className="font-semibold text-ink-900 dark:text-white text-base">
                    {title || `Patients routed to ${department}`}
                </h2>
                <span className="badge-brand">{rows.length} Waiting</span>
            </div>
            <div className="p-4">
                {loading ? (
                    <p className="text-sm text-ink-400 text-center py-4">Loading&hellip;</p>
                ) : rows.length === 0 ? (
                    <p className="text-sm text-ink-400 text-center py-4">No patients routed here.</p>
                ) : (
                    <ul className="space-y-2">
                        {rows.map((r) => (
                            <li key={r.queue_id} className="flex items-center justify-between gap-3 p-3 rounded-xl border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900">
                                <div className="min-w-0">
                                    <p className="font-semibold text-sm text-ink-900 dark:text-white truncate">
                                        {r.patient_name || `Patient #${r.patient_id}`}
                                    </p>
                                    <p className="text-xs text-ink-500 flex items-center gap-1">
                                        <Clock size={10} /> Acuity {r.acuity_level} &middot; {r.status}
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <button
                                        type="button"
                                        onClick={() => remove(r.queue_id)}
                                        className="btn-secondary px-2 py-1 text-xs flex items-center gap-1"
                                    >
                                        <UserMinus size={13} /> Remove
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => cancel(r.queue_id)}
                                        className="btn-secondary px-2 py-1 text-xs flex items-center gap-1 text-rose-600"
                                    >
                                        <X size={13} /> Cancel
                                    </button>
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}
