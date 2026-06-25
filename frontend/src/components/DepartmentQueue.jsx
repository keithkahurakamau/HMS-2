import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { Users, Clock, X, UserMinus } from 'lucide-react';

/**
 * DepartmentQueue — patients routed to a department via the generic
 * PatientQueue, with per-row remove (checkout) and cancel actions.
 *
 * Two render modes:
 *   • default — a standalone card with its own header + empty state.
 *   • inline  — bare rows meant to sit at the TOP of a module's native
 *     worklist (Pharmacy/Lab/Radiology), so routed patients appear in the
 *     same queue as the real work items, each tagged "Routed". Renders
 *     nothing when there are no routed patients (no redundant empty box).
 *
 * Props:
 *   department  {string}    required — filters the queue endpoint
 *   title       {string?}   heading override (default mode only)
 *   inline      {boolean?}  render as inline rows inside a parent list
 *   onChange    {function?} called after a successful remove or cancel
 */
export default function DepartmentQueue({ department, title, inline = false, onChange }) {
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

    const renderRow = (r) => (
        <li key={r.queue_id} className="flex items-center justify-between gap-3 p-3 rounded-lg border border-brand-100 dark:border-ink-800 bg-white dark:bg-ink-900">
            <div className="min-w-0">
                <p className="font-semibold text-sm text-ink-900 dark:text-white truncate flex items-center gap-2">
                    {r.patient_name || `Patient #${r.patient_id}`}
                    <span className="badge-brand text-2xs shrink-0">Routed</span>
                </p>
                <p className="text-xs text-ink-500 flex items-center gap-1">
                    <Clock size={10} /> Acuity {r.acuity_level} &middot; {r.status}
                </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
                <button type="button" onClick={() => remove(r.queue_id)}
                    className="btn-secondary px-2 py-1 text-xs flex items-center gap-1">
                    <UserMinus size={13} /> Remove
                </button>
                <button type="button" onClick={() => cancel(r.queue_id)}
                    className="btn-secondary px-2 py-1 text-xs flex items-center gap-1 text-rose-600">
                    <X size={13} /> Cancel
                </button>
            </div>
        </li>
    );

    // Inline: a tagged strip at the top of the module's native worklist.
    // Nothing to show when no patient was routed here — stay out of the way.
    if (inline) {
        if (loading || rows.length === 0) return null;
        return (
            <div className="mb-4 rounded-xl border border-brand-200 dark:border-brand-500/20 bg-brand-50/40 dark:bg-brand-500/5 p-3">
                <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300 mb-2 flex items-center gap-1.5">
                    <Users size={12} /> Routed from triage &middot; {rows.length}
                </p>
                <ul className="space-y-2">
                    {rows.map(renderRow)}
                </ul>
            </div>
        );
    }

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
                        {rows.map(renderRow)}
                    </ul>
                )}
            </div>
        </div>
    );
}
