import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    LifeBuoy, Plus, X, Send, Activity, RefreshCw,
    MessageSquare, Calendar, CheckCircle2, AlertCircle, Clock, ShieldCheck,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

const STATUS_ICONS = {
    'Open':                 AlertCircle,
    'In Progress':          Activity,
    'Waiting on Customer':  Clock,
    'Resolved':             CheckCircle2,
    'Closed':               CheckCircle2,
};

const STATUS_DOT_COLOR = {
    'Open':                'bg-blue-500',
    'In Progress':         'bg-amber-500',
    'Waiting on Customer': 'bg-amber-500',
    'Resolved':            'bg-accent-500',
    'Closed':              'bg-ink-400',
};

const formatRelative = (iso) => {
    if (!iso) return '—';
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
};

/* ────────────────────────────────────────────────────────────────────────── */
/*  Tenant-side support inbox.                                                */
/*  Hospital admin raises tickets to the MediFleet platform team and tracks   */
/*  responses. Tickets live in the master DB but the staff cookie auths us    */
/*  in.                                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

const STATUS_META = {
    'Open':                 { badge: 'badge-info',    icon: AlertCircle    },
    'In Progress':          { badge: 'badge-warn',    icon: Activity       },
    'Waiting on Customer':  { badge: 'badge-warn',    icon: Clock          },
    'Resolved':             { badge: 'badge-success', icon: CheckCircle2   },
    'Closed':               { badge: 'badge-neutral', icon: CheckCircle2   },
};

const CATEGORIES = ['Billing', 'Bug', 'Feature', 'Account', 'Onboarding', 'Other'];
const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];

export default function Support() {
    const [tickets, setTickets] = useState([]);
    const [activeTicket, setActiveTicket] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState('');

    const [isNewOpen, setIsNewOpen] = useState(false);
    const [draft, setDraft] = useState({ subject: '', body: '', category: 'Other', priority: 'Normal' });
    const [submitting, setSubmitting] = useState(false);

    const [reply, setReply] = useState('');
    const [sendingReply, setSendingReply] = useState(false);

    useEffect(() => { fetchTickets(); }, []);  // initial load — filter is client-side now

    // ModuleGuard hands us a prefill payload via router state when the user
    // clicks "Contact MediFleet Support to upgrade". Open the new-ticket
    // composer with the request already drafted so the operator only has to
    // press Send.
    const location = useLocation();
    const navigate = useNavigate();
    useEffect(() => {
        const prefill = location.state?.prefill;
        if (!prefill) return;
        setDraft({
            subject:  prefill.subject  || '',
            body:     prefill.body     || '',
            category: prefill.category || 'Account',
            priority: prefill.priority || 'Normal',
        });
        setIsNewOpen(true);
        // Strip the state so a back-forward navigation doesn't re-open the
        // composer with stale prefill data.
        navigate(location.pathname, { replace: true, state: null });
    }, [location.state, location.pathname, navigate]);

    const fetchTickets = async () => {
        setIsLoading(true);
        try {
            // Pull the full history once; client-side filter lets us show
            // accurate counts per status across the whole inbox.
            const res = await apiClient.get('/support/');
            setTickets(res.data || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load tickets.');
        } finally {
            setIsLoading(false);
        }
    };

    const openTicket = async (id) => {
        try {
            const res = await apiClient.get(`/support/${id}`);
            setActiveTicket(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load ticket.');
        }
    };

    const submitNew = async (e) => {
        e.preventDefault();
        if (!draft.subject.trim() || !draft.body.trim()) return toast.error('Subject and details are required.');
        setSubmitting(true);
        try {
            const res = await apiClient.post('/support/', draft);
            toast.success('Ticket raised — the MediFleet team will respond shortly.');
            setIsNewOpen(false);
            setDraft({ subject: '', body: '', category: 'Other', priority: 'Normal' });
            await fetchTickets();
            setActiveTicket(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not raise ticket.');
        } finally {
            setSubmitting(false);
        }
    };

    const sendReply = async () => {
        if (!reply.trim() || !activeTicket) return;
        setSendingReply(true);
        try {
            const res = await apiClient.post(`/support/${activeTicket.ticket_id}/reply`, { body: reply });
            setActiveTicket(res.data);
            setReply('');
            fetchTickets();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to send reply.');
        } finally {
            setSendingReply(false);
        }
    };

    const closeTicket = async () => {
        if (!activeTicket) return;
        if (!window.confirm('Mark this ticket as closed?')) return;
        try {
            const res = await apiClient.post(`/support/${activeTicket.ticket_id}/close`);
            setActiveTicket(res.data);
            fetchTickets();
            toast.success('Ticket closed.');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to close ticket.');
        }
    };

    // Per-status counts for the filter chips. Computed off the unfiltered
    // history so the "All / Open / In Progress / …" totals stay accurate.
    const statusCounts = useMemo(() => {
        const counts = { Open: 0, 'In Progress': 0, 'Waiting on Customer': 0, Resolved: 0, Closed: 0 };
        for (const t of tickets) {
            if (counts[t.status] !== undefined) counts[t.status] += 1;
        }
        return counts;
    }, [tickets]);

    // History view — newest activity first. Apply the status filter here
    // rather than on the server so the filter chips above can show counts.
    const sortedTickets = useMemo(() => {
        const filtered = statusFilter ? tickets.filter(t => t.status === statusFilter) : tickets;
        return [...filtered].sort((a, b) => {
            const at = new Date(a.updated_at || a.created_at || 0).getTime();
            const bt = new Date(b.updated_at || b.created_at || 0).getTime();
            return bt - at;
        });
    }, [tickets, statusFilter]);

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Help"
                icon={LifeBuoy}
                title="MediFleet Support"
                subtitle="Raise tickets to the MediFleet platform team. Bug reports, billing, feature requests, anything."
                actions={
                    <>
                        <button onClick={fetchTickets} className="btn-secondary cursor-pointer"><RefreshCw size={15} /> Refresh</button>
                        <button onClick={() => setIsNewOpen(true)} className="btn-primary cursor-pointer"><Plus size={15} /> New ticket</button>
                    </>
                }
            />

            {/* History filter chips — show count per status across the whole inbox */}
            <div className="card p-2 flex flex-wrap gap-1" role="tablist" aria-label="Filter tickets by status">
                <button
                    type="button"
                    onClick={() => setStatusFilter('')}
                    role="tab"
                    aria-selected={!statusFilter}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                        !statusFilter ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-200' : 'text-ink-700 hover:bg-ink-50'
                    }`}
                >
                    All
                    <span className={`text-2xs font-semibold tabular-nums ${!statusFilter ? 'text-brand-700' : 'text-ink-500'}`}>{tickets.length}</span>
                </button>
                {Object.keys(STATUS_META).map(s => {
                    const isActive = statusFilter === s;
                    const count = statusCounts[s] || 0;
                    return (
                        <button
                            key={s}
                            type="button"
                            onClick={() => setStatusFilter(s)}
                            role="tab"
                            aria-selected={isActive}
                            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                                isActive ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-200' : 'text-ink-700 hover:bg-ink-50'
                            }`}
                        >
                            <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT_COLOR[s]}`} aria-hidden="true" />
                            {s}
                            <span className={`text-2xs font-semibold tabular-nums ${isActive ? 'text-brand-700' : 'text-ink-500'}`}>{count}</span>
                        </button>
                    );
                })}
            </div>

            <div className="grid grid-cols-12 gap-4">
                {/* List */}
                <div className="col-span-12 lg:col-span-5 card overflow-hidden flex flex-col" style={{maxHeight: 'calc(100vh - 18rem)'}}>
                    {isLoading ? (
                        <div className="flex-1 flex items-center justify-center text-ink-400 p-10">
                            <Activity className="animate-spin mr-2 text-brand-500" size={18} /> Loading…
                        </div>
                    ) : sortedTickets.length === 0 ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-400 p-10 text-center">
                            <LifeBuoy size={36} className="mb-3 text-ink-300" />
                            <p className="text-sm">No tickets yet. Click "New ticket" to raise one.</p>
                        </div>
                    ) : (
                        <ul className="overflow-y-auto custom-scrollbar divide-y divide-ink-100">
                            {sortedTickets.map(t => {
                                const meta = STATUS_META[t.status] || {};
                                const active = activeTicket?.ticket_id === t.ticket_id;
                                const lastUpdate = t.updated_at || t.created_at;
                                return (
                                    <li key={t.ticket_id}>
                                        <button
                                            type="button"
                                            onClick={() => openTicket(t.ticket_id)}
                                            aria-current={active ? 'true' : undefined}
                                            className={`w-full p-4 text-left transition-colors cursor-pointer flex gap-3 items-start ${
                                                active ? 'bg-brand-50/60' : 'hover:bg-ink-50/60'
                                            }`}
                                        >
                                            <span
                                                className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${STATUS_DOT_COLOR[t.status] || 'bg-ink-400'}`}
                                                aria-hidden="true"
                                            />
                                            <div className="min-w-0 flex-1">
                                                <div className="flex justify-between items-start gap-2 mb-1">
                                                    <h3 className="font-semibold text-sm text-ink-900 line-clamp-1 flex-1">{t.subject}</h3>
                                                    <span className={`${meta.badge} shrink-0`}>{t.status}</span>
                                                </div>
                                                <div className="flex items-center gap-2 sm:gap-3 text-xs text-ink-500 mt-1 flex-wrap">
                                                    <span className="font-mono">#{t.ticket_id}</span>
                                                    <span>{t.category}</span>
                                                    <span>{t.priority}</span>
                                                    <span className="ml-auto flex items-center gap-1 shrink-0" title={new Date(lastUpdate).toLocaleString()}>
                                                        <Calendar size={11} aria-hidden="true" /> {formatRelative(lastUpdate)}
                                                    </span>
                                                </div>
                                            </div>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>

                {/* Thread */}
                <div className="col-span-12 lg:col-span-7 card overflow-hidden flex flex-col" style={{maxHeight: 'calc(100vh - 18rem)'}}>
                    {!activeTicket ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-400 p-10 text-center">
                            <MessageSquare size={36} className="mb-3 text-ink-300" />
                            <p className="text-sm">Select a ticket to view the conversation.</p>
                        </div>
                    ) : (
                        <>
                            <div className="p-4 border-b border-ink-100 bg-ink-50/60">
                                <div className="flex justify-between items-start gap-3 mb-1">
                                    <div className="min-w-0">
                                        <h2 className="text-base font-semibold text-ink-900 truncate">{activeTicket.subject}</h2>
                                        <div className="flex items-center gap-2 sm:gap-3 text-xs text-ink-500 mt-1 flex-wrap">
                                            <span className="font-mono">#{activeTicket.ticket_id}</span>
                                            <span>{activeTicket.category}</span>
                                            <span>Priority: {activeTicket.priority}</span>
                                            {activeTicket.created_at && (
                                                <span title={new Date(activeTicket.created_at).toLocaleString()}>
                                                    Opened {formatRelative(activeTicket.created_at)}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <span className={`${STATUS_META[activeTicket.status]?.badge} shrink-0 inline-flex items-center gap-1`}>
                                        {(() => {
                                            const Ico = STATUS_ICONS[activeTicket.status] || AlertCircle;
                                            return <Ico size={11} aria-hidden="true" />;
                                        })()}
                                        {activeTicket.status}
                                    </span>
                                </div>
                                {activeTicket.status !== 'Closed' && (
                                    <button
                                        type="button"
                                        onClick={closeTicket}
                                        className="text-xs text-rose-600 hover:text-rose-700 hover:underline mt-1 cursor-pointer"
                                    >
                                        Mark as closed
                                    </button>
                                )}
                            </div>

                            <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                                {(activeTicket.messages || []).map(m => {
                                    const isPlatform = m.author_kind === 'platform';
                                    return (
                                        <div key={m.message_id} className={`flex ${isPlatform ? 'justify-start' : 'justify-end'}`}>
                                            <div className={`max-w-[85%] sm:max-w-[75%] rounded-2xl p-3 border ${
                                                isPlatform ? 'bg-amber-50 border-amber-200' : 'bg-brand-50 border-brand-200'
                                            }`}>
                                                <div className="flex items-baseline justify-between gap-3 mb-1">
                                                    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 inline-flex items-center gap-1.5">
                                                        {isPlatform && <ShieldCheck size={11} className="text-amber-700" aria-hidden="true" />}
                                                        {isPlatform ? 'MediFleet Team' : m.author_name}
                                                    </span>
                                                    <span className="text-2xs text-ink-500 shrink-0" title={new Date(m.created_at).toLocaleString()}>
                                                        {formatRelative(m.created_at)}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-ink-900 whitespace-pre-wrap leading-relaxed">{m.body}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {activeTicket.status !== 'Closed' && (
                                <div className="p-3 border-t border-ink-100 bg-white flex gap-2">
                                    <textarea rows="2" className="input flex-1 resize-none" placeholder="Reply to MediFleet support…"
                                              value={reply} onChange={e => setReply(e.target.value)} />
                                    <button onClick={sendReply} disabled={sendingReply || !reply.trim()} className="btn-primary self-end disabled:opacity-50">
                                        {sendingReply ? <Activity size={16} className="animate-spin" /> : <Send size={16} />}
                                    </button>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* New ticket modal */}
            {isNewOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsNewOpen(false)} />
                    <div className="relative w-full max-w-xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex justify-between items-center p-5 border-b border-ink-100">
                            <h2 className="text-xl font-semibold flex items-center gap-2"><LifeBuoy size={20} className="text-brand-600" /> Raise a ticket</h2>
                            <button onClick={() => setIsNewOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full">
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={submitNew} className="flex-1 overflow-y-auto p-5 bg-ink-50/60 space-y-4">
                            <div>
                                <label className="label">Subject *</label>
                                <input required className="input" value={draft.subject} maxLength="200"
                                       onChange={e => setDraft({ ...draft, subject: e.target.value })}
                                       placeholder="Short summary of the issue" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="label">Category</label>
                                    <select className="input" value={draft.category}
                                            onChange={e => setDraft({ ...draft, category: e.target.value })}>
                                        {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="label">Priority</label>
                                    <select className="input" value={draft.priority}
                                            onChange={e => setDraft({ ...draft, priority: e.target.value })}>
                                        {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="label">What's going on? *</label>
                                <textarea required rows="8" className="input resize-none" value={draft.body}
                                          onChange={e => setDraft({ ...draft, body: e.target.value })}
                                          placeholder="Describe the issue, what you expected, and what happened. Include steps, screenshots URLs, or error messages." />
                            </div>
                            <div className="flex justify-end gap-2 pt-3 border-t border-ink-100">
                                <button type="button" onClick={() => setIsNewOpen(false)} className="btn-secondary">Cancel</button>
                                <button type="submit" disabled={submitting} className="btn-primary">
                                    {submitting ? <Activity size={15} className="animate-spin" /> : <Send size={15} />} Submit
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
