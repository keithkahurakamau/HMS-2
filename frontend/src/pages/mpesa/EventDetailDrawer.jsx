import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ArrowRightLeft } from 'lucide-react';
import { getEvent, flowLabel, outcomeBadgeClass } from '../../api/mpesaEvents';
import { formatKes } from '../../api/mpesa';
import { SkeletonTable } from '../../components/ui/Skeleton';
import ErrorState from '../../components/ui/ErrorState';

// Same focus-management pattern as
// frontend/src/pages/superadmin/receivables/TenantDrawer.jsx: focus in on
// open, a live-queried Tab trap, restore to the trigger on close. Copied
// rather than shared because the two drawers have nothing else in common
// and this project's dialog pattern is not yet extracted into a hook.
const FOCUSABLE_SELECTOR = [
    'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
    'input:not([disabled])', 'select:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(', ');

function formatDateTime(iso) {
    if (!iso) return '-';
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

export default function EventDetailDrawer({ eventId, onClose }) {
    const [event, setEvent] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const dialogRef = useRef(null);
    const closeButtonRef = useRef(null);
    const previouslyFocusedRef = useRef(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getEvent(eventId);
            setEvent(data);
        } catch (err) {
            setError(err?.response?.data?.detail || 'Could not load this event.');
        } finally {
            setLoading(false);
        }
    }, [eventId]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => {
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    useEffect(() => {
        previouslyFocusedRef.current = document.activeElement;
        closeButtonRef.current?.focus();
        return () => {
            const toRestore = previouslyFocusedRef.current;
            if (toRestore && typeof toRestore.focus === 'function' && document.contains(toRestore)) {
                toRestore.focus();
            }
        };
    }, []);

    const handleTrapKeyDown = (event2) => {
        if (event2.key !== 'Tab' || !dialogRef.current) return;
        const focusables = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const isInside = dialogRef.current.contains(document.activeElement);
        if (event2.shiftKey) {
            if (!isInside || document.activeElement === first) { event2.preventDefault(); last.focus(); }
        } else if (!isInside || document.activeElement === last) {
            event2.preventDefault(); first.focus();
        }
    };

    return createPortal(
        <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/50 backdrop-blur-sm" onClick={onClose} role="presentation">
            <div
                ref={dialogRef}
                className="overlay-surface h-full w-full max-w-xl flex flex-col rounded-none border-l"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={handleTrapKeyDown}
                role="dialog"
                aria-modal="true"
                aria-label={event ? `M-Pesa event ${event.id}` : 'M-Pesa event detail'}
            >
                <div className="flex items-center justify-between p-4 border-b border-ink-200 dark:border-ink-800 shrink-0">
                    <h2 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2 min-w-0">
                        <ArrowRightLeft size={16} className="text-brand-500 shrink-0" aria-hidden="true" />
                        <span className="truncate">{event ? `${flowLabel(event.flow)} · #${event.id}` : 'Loading event…'}</span>
                    </h2>
                    <button
                        ref={closeButtonRef}
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-1.5 rounded-lg text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800 cursor-pointer"
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-6">
                    {loading && <SkeletonTable rows={5} cols={2} label="Loading event detail" />}
                    {!loading && error && <ErrorState title="Could not load this event" message={error} onRetry={load} />}
                    {!loading && !error && event && <EventDetailBody event={event} />}
                </div>
            </div>
        </div>,
        document.body,
    );
}

function EventDetailBody({ event }) {
    return (
        <>
            <div className="flex items-center gap-2 flex-wrap">
                <span className={outcomeBadgeClass(event.outcome)}>{event.outcome}</span>
                <span className="badge-neutral">{event.direction}</span>
                {event.http_status != null && <span className="text-xs text-ink-500 dark:text-ink-400 tnum">HTTP {event.http_status}</span>}
            </div>

            {event.outcome === 'quarantined' && (
                <section className="card p-4 border-2 border-amber-300 dark:border-amber-500/40 bg-amber-50/60 dark:bg-amber-500/10">
                    <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-3">
                        Amount claimed vs. amount requested
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500 dark:text-ink-400">Requested</p>
                            <p className="tnum text-lg font-semibold text-ink-900 dark:text-white mt-1">
                                {event.requested_amount != null ? formatKes(event.requested_amount) : 'Unknown'}
                            </p>
                        </div>
                        <div>
                            <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500 dark:text-ink-400">Claimed</p>
                            <p className="tnum text-lg font-semibold text-rose-700 dark:text-rose-400 mt-1">
                                {event.claimed_amount != null ? formatKes(event.claimed_amount) : 'Unknown'}
                            </p>
                        </div>
                    </div>
                </section>
            )}

            <section className="card p-4 space-y-2">
                <h3 className="text-sm font-semibold text-ink-900 dark:text-white mb-1">Overview</h3>
                <DetailRow label="Time" value={formatDateTime(event.created_at)} />
                <DetailRow label="Result code" value={event.daraja_result_code} mono />
                <DetailRow label="Result description" value={event.daraja_result_desc} />
                <DetailRow label="Duration" value={event.duration_ms != null ? `${event.duration_ms} ms` : null} mono />
                <DetailRow label="Checkout request ID" value={event.checkout_request_id} mono />
                <DetailRow label="Conversation ID" value={event.conversation_id} mono />
                <DetailRow label="Receipt number" value={event.receipt_number} mono />
                {/* Full value, unlike the list view: this is the one place a
                    cashier is allowed to see the complete phone number. */}
                <DetailRow label="Phone number" value={event.phone_number} mono />
                {event.error_detail && <DetailRow label="Error detail" value={event.error_detail} />}
            </section>

            <PayloadSection title="Request payload" payload={event.request_payload} />
            <PayloadSection title="Response payload" payload={event.response_payload} />
        </>
    );
}

function DetailRow({ label, value, mono = false }) {
    if (value == null || value === '') return null;
    return (
        <div className="flex items-start justify-between gap-3 text-xs py-0.5">
            <span className="text-ink-500 dark:text-ink-400 shrink-0">{label}</span>
            <span className={`text-right text-ink-800 dark:text-ink-200 break-all ${mono ? 'tnum' : ''}`}>{value}</span>
        </div>
    );
}

function PayloadSection({ title, payload }) {
    return (
        <section className="space-y-1.5">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white">{title}</h3>
            {!payload ? (
                <p className="text-xs text-ink-500 dark:text-ink-400">Not recorded.</p>
            ) : (
                <pre className="tnum text-[11px] leading-relaxed bg-ink-50 dark:bg-ink-900/60 border border-ink-200 dark:border-ink-800 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all">
                    {JSON.stringify(payload, null, 2)}
                </pre>
            )}
        </section>
    );
}
