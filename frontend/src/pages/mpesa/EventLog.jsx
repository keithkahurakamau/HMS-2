import React, { useCallback, useEffect, useState } from 'react';
import { ListChecks, ChevronLeft, ChevronRight, X, Eye } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import { SkeletonTable } from '../../components/ui/Skeleton';
import ErrorState from '../../components/ui/ErrorState';
import { listEvents, OUTCOMES, FLOWS, flowLabel, outcomeBadgeClass } from '../../api/mpesaEvents';
import EventDetailDrawer from './EventDetailDrawer';

const PAGE_SIZE = 25;

/**
 * EventLog: the hospital-facing view of the Daraja event log. Every M-Pesa
 * interaction, whatever its outcome, is here: a cashier who needs to answer
 * "what happened to this payment" starts on this page, not in a log
 * aggregator only an engineer can read.
 *
 * Filters and search are server-side (see api/mpesaEvents.js /
 * backend/app/routes/mpesa_events.py): this table is append-only and grows
 * with transaction volume, so nothing here loads the full history client-side.
 */
export default function EventLog() {
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const [outcome, setOutcome] = useState('');
    const [flow, setFlow] = useState('');
    const [search, setSearch] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

    const [selectedId, setSelectedId] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await listEvents({
                outcome: outcome || undefined,
                flow: flow || undefined,
                search: search || undefined,
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
                page,
                page_size: PAGE_SIZE,
            });
            setItems(Array.isArray(data.items) ? data.items : []);
            setTotal(data.total || 0);
        } catch (err) {
            setError(err?.response?.data?.detail || 'Could not load the M-Pesa event log.');
        } finally {
            setLoading(false);
        }
    }, [outcome, flow, search, dateFrom, dateTo, page]);

    useEffect(() => { load(); }, [load]);

    const setOutcomeFilter = (value) => { setOutcome(value); setPage(1); };
    const clearFilters = () => {
        setOutcome(''); setFlow(''); setSearch(''); setDateFrom(''); setDateTo(''); setPage(1);
    };
    const hasFilters = outcome || flow || search || dateFrom || dateTo;

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const rangeEnd = Math.min(page * PAGE_SIZE, total);

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="M-Pesa"
                icon={ListChecks}
                title="Event log"
                subtitle="Every Daraja interaction, whatever its outcome: a push, a callback, a quarantined amount, a refund result."
                tone="brand"
            />

            <div className="card p-3 space-y-3">
                <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by outcome">
                    <button type="button" onClick={() => setOutcomeFilter('')} aria-pressed={outcome === ''}
                        className={`chip ${outcome === '' ? 'chip-active' : ''}`}>
                        All outcomes
                    </button>
                    {OUTCOMES.map((o) => (
                        <button key={o} type="button" onClick={() => setOutcomeFilter(o)} aria-pressed={outcome === o}
                            className={`chip ${outcome === o ? 'chip-active' : ''}`}>
                            {o}
                        </button>
                    ))}
                </div>

                <div className="flex flex-wrap items-end gap-3">
                    <label className="block">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Flow</span>
                        <select
                            aria-label="Filter by flow"
                            className="input w-auto"
                            value={flow}
                            onChange={(e) => { setFlow(e.target.value); setPage(1); }}
                        >
                            <option value="">All flows</option>
                            {FLOWS.map((f) => <option key={f} value={f}>{flowLabel(f)}</option>)}
                        </select>
                    </label>
                    <label className="block flex-1 min-w-[12rem]">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Receipt or phone</span>
                        <input
                            aria-label="Search by receipt or phone"
                            className="input w-full"
                            value={search}
                            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                            placeholder="e.g. QGR7... or 2547..."
                        />
                    </label>
                    <label className="block">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">From</span>
                        <input aria-label="From date" type="date" className="input w-auto"
                            value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
                    </label>
                    <label className="block">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">To</span>
                        <input aria-label="To date" type="date" className="input w-auto"
                            value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
                    </label>
                    {hasFilters && (
                        <button type="button" onClick={clearFilters} className="btn btn-ghost btn-xs">
                            <X size={12} aria-hidden="true" /> Clear filters
                        </button>
                    )}
                </div>
            </div>

            {loading && <SkeletonTable rows={8} cols={7} label="Loading M-Pesa events" />}
            {!loading && error && <ErrorState title="Could not load the event log" message={error} onRetry={load} />}

            {!loading && !error && items.length === 0 && (
                <div className="empty">
                    <p className="text-sm text-ink-500 dark:text-ink-400">
                        {hasFilters ? 'No events match these filters.' : 'No M-Pesa events recorded yet.'}
                    </p>
                </div>
            )}

            {!loading && !error && items.length > 0 && (
                <div className="card-flush overflow-hidden overflow-x-auto">
                    <table className="table-clean min-w-[920px]">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Flow</th>
                                <th>Direction</th>
                                <th>Outcome</th>
                                <th>Result</th>
                                <th className="num">Duration</th>
                                <th>Receipt</th>
                                <th>Phone</th>
                                <th>Detail</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((row) => (
                                <tr key={row.id}>
                                    <td className="text-xs tnum whitespace-nowrap">
                                        {row.created_at ? new Date(row.created_at).toLocaleString() : '-'}
                                    </td>
                                    <td className="text-xs">{flowLabel(row.flow)}</td>
                                    <td className="text-xs capitalize">{row.direction}</td>
                                    <td><span className={outcomeBadgeClass(row.outcome)}>{row.outcome}</span></td>
                                    <td className="text-xs text-ink-600 dark:text-ink-300 max-w-[16rem] truncate" title={row.daraja_result_desc || ''}>
                                        {row.daraja_result_desc || (row.daraja_result_code ? `Code ${row.daraja_result_code}` : '-')}
                                    </td>
                                    <td className="num tnum text-xs">{row.duration_ms != null ? `${row.duration_ms} ms` : '-'}</td>
                                    <td className="text-xs tnum">{row.receipt_number || '-'}</td>
                                    <td className="text-xs tnum">{row.phone_masked || '-'}</td>
                                    <td>
                                        <button type="button" className="btn btn-secondary btn-xs" onClick={() => setSelectedId(row.id)}>
                                            <Eye size={12} aria-hidden="true" /> View
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {!loading && !error && total > 0 && (
                <div className="flex items-center justify-end gap-2">
                    <span className="text-xs text-ink-500 dark:text-ink-400 tnum">
                        {rangeStart}-{rangeEnd} of {total}
                    </span>
                    <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1} aria-label="Previous page"
                        className="p-1.5 rounded-lg border border-ink-200 dark:border-ink-800 text-ink-600 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 disabled:opacity-40 disabled:cursor-not-allowed">
                        <ChevronLeft size={15} />
                    </button>
                    <button type="button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages} aria-label="Next page"
                        className="p-1.5 rounded-lg border border-ink-200 dark:border-ink-800 text-ink-600 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 disabled:opacity-40 disabled:cursor-not-allowed">
                        <ChevronRight size={15} />
                    </button>
                </div>
            )}

            {selectedId != null && (
                <EventDetailDrawer eventId={selectedId} onClose={() => setSelectedId(null)} />
            )}
        </div>
    );
}
