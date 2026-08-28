import React, { useMemo, useState } from 'react';
import { X, Users, UserMinus, AlertTriangle, Search, Trash2, Activity } from 'lucide-react';
import { minutesWaiting } from '../utils/clinicalForms';
import { departmentLabel } from '../utils/departments';

/**
 * Everyone currently waiting in one department's queue, behind the
 * "View all patients" button.
 *
 * The inline queue strip on each workspace is deliberately short (it shares
 * space with the chart), so a busy clinic could not see past the first few
 * rows. This lists the whole queue, searchable, and offers the two actions
 * that were otherwise buried: remove one patient, or clear the queue.
 *
 * Presentational — removal is delegated to the page, which already owns the
 * queue refresh and the workspace it may need to clear.
 */

const priorityBadge = (priority) => {
    if (priority === 'Critical') return 'badge-danger';
    if (priority === 'High') return 'badge-warn';
    return 'badge-neutral';
};

export default function QueuePatientsModal({
    queue = [],
    department,
    onClose,
    onSelectPatient,
    onRemoveFromQueue,
    onClearQueue,
    isClearing = false,
}) {
    const [search, setSearch] = useState('');
    const [confirmingClear, setConfirmingClear] = useState(false);

    const label = department ? departmentLabel(department) : 'Queue';

    const visible = useMemo(() => {
        const needle = search.trim().toLowerCase();
        if (!needle) return queue;
        return queue.filter((q) =>
            (q.patient_name || '').toLowerCase().includes(needle)
            || (q.outpatient_no || '').toLowerCase().includes(needle));
    }, [queue, search]);

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="queue-patients-title"
        >
            <div className="card w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="px-5 py-3.5 border-b border-ink-100 dark:border-ink-800 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                        <span className="text-brand-600"><Users size={17} /></span>
                        <h2 id="queue-patients-title" className="text-sm font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                            {label} — all patients waiting
                        </h2>
                        <span className="badge-neutral shrink-0">{queue.length}</span>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close"
                        className="p-1.5 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 dark:hover:bg-ink-800 transition-colors cursor-pointer">
                        <X size={18} />
                    </button>
                </div>

                {/* Search */}
                {queue.length > 0 && (
                    <div className="px-5 pt-4">
                        <div className="relative">
                            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                            <input
                                type="search"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Filter by name or OP number…"
                                aria-label="Filter queued patients"
                                className="input pl-9"
                            />
                        </div>
                    </div>
                )}

                {/* List */}
                <div className="flex-1 overflow-auto px-5 py-4 custom-scrollbar">
                    {queue.length === 0 ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400 italic py-6 text-center">
                            No patients are waiting in this queue.
                        </p>
                    ) : visible.length === 0 ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400 italic py-6 text-center">
                            No patient matches “{search}”.
                        </p>
                    ) : (
                        <table className="table-inline">
                            <thead>
                                <tr className="text-2xs uppercase tracking-wider text-ink-500 dark:text-ink-400 text-left">
                                    <th>Q.No</th>
                                    <th>OP number</th>
                                    <th>Patient</th>
                                    <th>From</th>
                                    <th>Waiting</th>
                                    <th className="num">Remove</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                                {visible.map((item) => {
                                    const mins = minutesWaiting(item.joined_at);
                                    // Position in the real queue, not the filtered view — a
                                    // filtered row must still show its true place in line.
                                    const position = queue.indexOf(item) + 1;
                                    return (
                                        <tr key={item.queue_id}>
                                            <td className="text-ink-500 dark:text-ink-400 tabular-nums">{position}</td>
                                            <td className="font-mono text-xs text-ink-600 dark:text-ink-300">{item.outpatient_no || '—'}</td>
                                            <td>
                                                <button type="button"
                                                    onClick={() => { onSelectPatient?.(item); onClose(); }}
                                                    className="font-medium text-ink-800 dark:text-ink-200 hover:text-brand-600 dark:hover:text-brand-400 text-left flex items-center gap-2">
                                                    {item.patient_name}
                                                    {item.priority && item.priority !== 'Normal' && (
                                                        <span className={`${priorityBadge(item.priority)} text-2xs`}>{item.priority}</span>
                                                    )}
                                                </button>
                                            </td>
                                            <td className="text-ink-600 dark:text-ink-300">{item.triage_time || '—'}</td>
                                            <td className="text-ink-600 dark:text-ink-300 tabular-nums">
                                                {mins == null ? '—' : `${mins} min`}
                                            </td>
                                            <td className="num">
                                                {onRemoveFromQueue && (
                                                    <button type="button" onClick={() => onRemoveFromQueue(item)}
                                                        aria-label={`Remove ${item.patient_name} from queue`}
                                                        className="p-1.5 rounded-lg text-ink-400 hover:text-rose-600 hover:bg-ink-100 dark:hover:bg-ink-800 transition-colors cursor-pointer">
                                                        <UserMinus size={15} />
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* Footer — bulk clear */}
                <div className="px-5 py-3.5 border-t border-ink-100 dark:border-ink-800 bg-ink-50/50 dark:bg-ink-800/30">
                    {confirmingClear ? (
                        // Two-step rather than window.confirm: removing everyone waiting is
                        // not undoable from the UI, so the count is restated before it runs.
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <p className="text-xs text-ink-700 dark:text-ink-300 flex items-start gap-1.5">
                                <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-500" />
                                Remove all {queue.length} patient{queue.length === 1 ? '' : 's'} from the {label.toLowerCase()} queue?
                                They stop appearing as waiting; their records are untouched.
                            </p>
                            <div className="flex items-center gap-2 shrink-0">
                                <button type="button" onClick={() => setConfirmingClear(false)}
                                    disabled={isClearing} className="btn-secondary cursor-pointer">
                                    Cancel
                                </button>
                                <button type="button" onClick={onClearQueue}
                                    disabled={isClearing} className="btn-danger cursor-pointer disabled:cursor-wait">
                                    {isClearing ? <Activity size={14} className="animate-spin" /> : <Trash2 size={14} />}
                                    Yes, remove all
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-between gap-3">
                            <p className="text-2xs text-ink-500 dark:text-ink-400">
                                Click a name to open that patient.
                            </p>
                            {onClearQueue && queue.length > 0 && (
                                <button type="button" onClick={() => setConfirmingClear(true)}
                                    className="btn-danger-ghost cursor-pointer">
                                    <Trash2 size={14} /> Remove all from queue
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
