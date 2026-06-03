import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    LifeBuoy, Search, Filter, Send, RefreshCw, Activity, MessageSquare,
    Building2, Calendar, CheckCircle2, AlertCircle, Clock, ShieldCheck,
    Mail, Globe, Headphones, Wallet, Wrench,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Platform support inbox.                                                   */
/*                                                                            */
/*  Light shadcn-aligned surface. The status pill colours stay in the         */
/*  semantic hue family (blue=open, amber=in-flight, accent=resolved, ink=    */
/*  closed) but on light backgrounds (50/100 tints) so contrast meets WCAG.   */
/*  Layout collapses to a single column under lg so the page is usable on a   */
/*  tablet held in portrait.                                                  */
/* ────────────────────────────────────────────────────────────────────────── */

const STATUS_META = {
    'Open':                 { color: 'bg-blue-50 text-blue-800 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20',     icon: AlertCircle },
    'In Progress':          { color: 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',  icon: Activity    },
    'Waiting on Customer':  { color: 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',  icon: Clock       },
    'Resolved':             { color: 'bg-accent-50 text-accent-800 ring-accent-200 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/20', icon: CheckCircle2 },
    'Closed':               { color: 'bg-ink-100 text-ink-700 ring-ink-200 dark:bg-ink-800/40 dark:text-ink-300 dark:ring-ink-700',       icon: CheckCircle2 },
};

const CATEGORIES = ['Billing', 'Bug', 'Feature', 'Account', 'Onboarding', 'Other'];
const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];
const STATUSES = Object.keys(STATUS_META);

// Desks group categories so the team can work one queue at a time. Mirrors the
// outbound sender mapping (Billing→finance, Bug/Feature→technical, else support).
const DESKS = {
    Support:   { cats: ['Account', 'Onboarding', 'Other'], icon: Headphones },
    Finance:   { cats: ['Billing'],                         icon: Wallet },
    Technical: { cats: ['Bug', 'Feature'],                  icon: Wrench },
};

export default function SupportInbox() {
    const [tickets, setTickets] = useState([]);
    const [summary, setSummary] = useState({});
    const [active, setActive] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('Open');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('');
    const [deskFilter, setDeskFilter] = useState('');   // '' = all desks

    // Desk grouping is applied client-side over the fetched list.
    const visibleTickets = deskFilter
        ? tickets.filter(t => DESKS[deskFilter].cats.includes(t.category))
        : tickets;

    const [reply, setReply] = useState('');
    const [sendingReply, setSendingReply] = useState(false);

    useEffect(() => { fetchAll(); }, []);  // initial
    useEffect(() => {
        const t = setTimeout(fetchTickets, 300);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search, statusFilter, categoryFilter, priorityFilter]);

    const fetchAll = async () => {
        await Promise.all([fetchTickets(), fetchSummary()]);
    };

    const fetchSummary = async () => {
        try {
            const res = await apiClient.get('/public/superadmin/tickets/summary');
            setSummary(res.data || {});
        } catch {
            // Summary is decorative — silently degrade if it fails.
        }
    };

    const fetchTickets = async () => {
        setIsLoading(true);
        try {
            const params = new URLSearchParams();
            if (search) params.set('search', search);
            if (statusFilter) params.set('status', statusFilter);
            if (categoryFilter) params.set('category', categoryFilter);
            if (priorityFilter) params.set('priority', priorityFilter);
            const res = await apiClient.get(`/public/superadmin/tickets/?${params.toString()}`);
            setTickets(res.data || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load tickets.');
        } finally {
            setIsLoading(false);
        }
    };

    const openTicket = async (id) => {
        try {
            const res = await apiClient.get(`/public/superadmin/tickets/${id}`);
            setActive(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load ticket.');
        }
    };

    const sendReply = async () => {
        if (!reply.trim() || !active) return;
        setSendingReply(true);
        try {
            const res = await apiClient.post(`/public/superadmin/tickets/${active.ticket_id}/reply`, { body: reply });
            setActive(res.data);
            setReply('');
            fetchTickets();
            fetchSummary();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to send reply.');
        } finally {
            setSendingReply(false);
        }
    };

    const setStatus = async (status) => {
        if (!active) return;
        try {
            await apiClient.patch(`/public/superadmin/tickets/${active.ticket_id}/status`, { status });
            const refreshed = await apiClient.get(`/public/superadmin/tickets/${active.ticket_id}`);
            setActive(refreshed.data);
            fetchTickets();
            fetchSummary();
            toast.success(`Status → ${status}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to update status.');
        }
    };

    return (
        <div className="space-y-5 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={LifeBuoy}
                title="Support Inbox"
                subtitle="Tickets raised by tenant admins across the fleet."
                tone="brand"
                actions={
                    <button
                        type="button"
                        onClick={fetchAll}
                        className="btn-secondary cursor-pointer"
                    >
                        <RefreshCw size={14} aria-hidden="true" /> Refresh
                    </button>
                }
            />

            {/* KPI row — filterable */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {STATUSES.map(s => {
                    const count = summary[s] || 0;
                    const isActive = statusFilter === s;
                    return (
                        <button
                            key={s}
                            type="button"
                            onClick={() => setStatusFilter(s)}
                            aria-pressed={isActive}
                            className={`text-left rounded-2xl p-4 border transition-colors cursor-pointer ${
                                isActive
                                    ? 'bg-brand-50 border-brand-200 dark:bg-brand-500/10 dark:border-brand-500/20 ring-2 ring-brand-500/20'
                                    : 'card hover:bg-ink-50 dark:hover:bg-ink-800/50'
                            }`}
                        >
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400">{s}</p>
                            <p className="text-2xl font-semibold text-ink-900 dark:text-white mt-1 tracking-tight">{count}</p>
                        </button>
                    );
                })}
            </div>

            {/* Desk tabs — Support / Finance / Technical */}
            <div className="flex gap-2 flex-wrap" role="tablist" aria-label="Support desks">
                {['', ...Object.keys(DESKS)].map(d => {
                    const Icon = d ? DESKS[d].icon : LifeBuoy;
                    const count = d
                        ? tickets.filter(t => DESKS[d].cats.includes(t.category)).length
                        : tickets.length;
                    const selected = deskFilter === d;
                    return (
                        <button
                            key={d || 'all'}
                            type="button"
                            role="tab"
                            aria-selected={selected}
                            onClick={() => setDeskFilter(d)}
                            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium ring-1 ring-inset transition-colors cursor-pointer ${
                                selected
                                    ? 'bg-brand-600 text-white ring-brand-600'
                                    : 'bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 ring-ink-200 dark:ring-ink-800 hover:bg-ink-50 dark:hover:bg-ink-800/50'
                            }`}
                        >
                            <Icon size={15} aria-hidden="true" />
                            {d || 'All desks'}
                            <span className={`text-2xs font-semibold rounded-full px-1.5 py-0.5 ${selected ? 'bg-white/20' : 'bg-ink-100 text-ink-600 dark:bg-ink-800/60 dark:text-ink-400'}`}>{count}</span>
                        </button>
                    );
                })}
            </div>

            {/* Filters */}
            <div className="card p-3 flex flex-col sm:flex-row flex-wrap gap-3 sm:items-center">
                <div className="relative flex-1 min-w-0 sm:min-w-[16rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="ticket-search" className="sr-only">Search tickets</label>
                    <input
                        id="ticket-search"
                        type="search"
                        className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-4 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                        placeholder="Search subject…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                    />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="cat-filter" className="sr-only">Filter by category</label>
                    <select
                        id="cat-filter"
                        className="w-full sm:w-auto bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-8 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                        value={categoryFilter}
                        onChange={e => setCategoryFilter(e.target.value)}
                    >
                        <option value="">All categories</option>
                        {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                    </select>
                </div>
                <label htmlFor="prio-filter" className="sr-only">Filter by priority</label>
                <select
                    id="prio-filter"
                    className="w-full sm:w-auto bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                    value={priorityFilter}
                    onChange={e => setPriorityFilter(e.target.value)}
                >
                    <option value="">All priorities</option>
                    {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                </select>
                <button
                    type="button"
                    onClick={() => setStatusFilter('')}
                    className="text-2xs text-ink-600 dark:text-ink-400 hover:text-brand-700 uppercase tracking-wider cursor-pointer"
                >
                    Clear status
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                {/* List */}
                <div className="lg:col-span-5 card overflow-hidden flex flex-col" style={{ maxHeight: 'calc(100vh - 24rem)', minHeight: '24rem' }}>
                    {isLoading ? (
                        <div className="flex-1 flex items-center justify-center text-ink-600 dark:text-ink-400 p-10">
                            <Activity className="animate-spin mr-2 text-brand-600" size={18} aria-hidden="true" /> Loading…
                        </div>
                    ) : visibleTickets.length === 0 ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-500 dark:text-ink-400 p-10 text-center">
                            <LifeBuoy size={36} className="mb-3 text-ink-400" aria-hidden="true" />
                            <p className="text-sm">No tickets match the filters.</p>
                        </div>
                    ) : (
                        <ul className="overflow-y-auto custom-scrollbar divide-y divide-ink-100 dark:divide-ink-800">
                            {visibleTickets.map(t => {
                                const meta = STATUS_META[t.status] || {};
                                const isActiveTicket = active?.ticket_id === t.ticket_id;
                                return (
                                    <li key={t.ticket_id}>
                                        <button
                                            type="button"
                                            onClick={() => openTicket(t.ticket_id)}
                                            aria-current={isActiveTicket ? 'true' : undefined}
                                            className={`w-full p-4 text-left transition-colors cursor-pointer ${
                                                isActiveTicket ? 'bg-brand-50 dark:bg-brand-500/10' : 'hover:bg-ink-50 dark:hover:bg-ink-800/50'
                                            }`}
                                        >
                                            <div className="flex justify-between items-start gap-2 mb-1">
                                                <h3 className="font-semibold text-sm text-ink-900 dark:text-white line-clamp-1 flex-1">{t.subject}</h3>
                                                <span className={`px-2 py-0.5 rounded-full text-2xs font-semibold ring-1 ring-inset shrink-0 ${meta.color}`}>{t.status}</span>
                                            </div>
                                            <div className="flex items-center gap-2 text-xs text-ink-600 dark:text-ink-400 mt-1">
                                                <Building2 size={11} aria-hidden="true" />
                                                <span className={`truncate ${t.tenant_name ? '' : 'italic text-ink-400'}`}>{t.tenant_name || 'Unassigned'}</span>
                                            </div>
                                            <div className="flex items-center gap-3 text-2xs text-ink-500 dark:text-ink-400 mt-1 flex-wrap">
                                                <span className="font-mono">#{t.ticket_id}</span>
                                                <span>{t.category}</span>
                                                <span>{t.priority}</span>
                                                {(t.origin === 'email' || t.origin === 'web') && (
                                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-teal-50 text-teal-700 ring-1 ring-inset ring-teal-100 dark:bg-teal-500/10 dark:text-teal-300 dark:ring-teal-500/20">
                                                        {t.origin === 'email' ? <Mail size={9} aria-hidden="true" /> : <Globe size={9} aria-hidden="true" />}
                                                        {t.origin === 'email' ? 'Email' : 'Web'}
                                                    </span>
                                                )}
                                                <span className="ml-auto flex items-center gap-1 shrink-0"><Calendar size={10} aria-hidden="true" /> {new Date(t.created_at).toLocaleDateString()}</span>
                                            </div>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>

                {/* Thread */}
                <div className="lg:col-span-7 card overflow-hidden flex flex-col" style={{ maxHeight: 'calc(100vh - 24rem)', minHeight: '24rem' }}>
                    {!active ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-500 dark:text-ink-400 p-10 text-center">
                            <MessageSquare size={36} className="mb-3 text-ink-400" aria-hidden="true" />
                            <p className="text-sm">Select a ticket to view the thread.</p>
                        </div>
                    ) : (
                        <>
                            <div className="p-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40">
                                <div className="flex justify-between items-start gap-3 mb-2">
                                    <div className="min-w-0">
                                        <h2 className="text-base font-semibold text-ink-900 dark:text-white truncate">{active.subject}</h2>
                                        <div className="flex items-center gap-2 sm:gap-3 text-xs text-ink-600 dark:text-ink-400 mt-1 flex-wrap">
                                            <span className="flex items-center gap-1"><Building2 size={11} aria-hidden="true" /> {active.tenant_name || 'Unassigned'}</span>
                                            <span className="font-mono">#{active.ticket_id}</span>
                                            <span>{active.category}</span>
                                            <span>P: {active.priority}</span>
                                            {(active.origin === 'email' || active.origin === 'web') && (
                                                <span className="inline-flex items-center gap-1 text-teal-700 dark:text-teal-300">
                                                    {active.origin === 'email' ? <Mail size={11} aria-hidden="true" /> : <Globe size={11} aria-hidden="true" />}
                                                    {active.origin === 'email' ? 'Email' : 'Web'}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1 truncate">Raised by {active.submitter_name} &lt;{active.submitter_email}&gt;</p>
                                    </div>
                                </div>
                                <div className="flex flex-wrap gap-1.5 pt-1">
                                    {STATUSES.map(s => (
                                        <button
                                            key={s}
                                            type="button"
                                            onClick={() => setStatus(s)}
                                            disabled={s === active.status}
                                            className={`text-2xs font-semibold px-2.5 py-1 rounded-lg ring-1 ring-inset transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
                                                s === active.status
                                                    ? STATUS_META[s].color
                                                    : 'bg-white dark:bg-ink-900 text-ink-700 dark:text-ink-200 ring-ink-200 dark:ring-ink-800 hover:bg-ink-50 dark:hover:bg-ink-800/50 hover:text-ink-900 dark:hover:text-white'
                                            }`}
                                            aria-pressed={s === active.status}
                                        >
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar bg-ink-50/40 dark:bg-ink-800/40">
                                {(active.messages || []).map(m => {
                                    const isPlatform = m.author_kind === 'platform';
                                    return (
                                        <div key={m.message_id} className={`flex ${isPlatform ? 'justify-end' : 'justify-start'}`}>
                                            <div className={`max-w-[85%] sm:max-w-[80%] rounded-2xl p-3 border ${
                                                isPlatform
                                                    ? 'bg-brand-50 border-brand-200 dark:bg-brand-500/10 dark:border-brand-500/20'
                                                    : 'bg-white border-ink-200 dark:bg-ink-900 dark:border-ink-800'
                                            }`}>
                                                <div className="flex items-baseline justify-between gap-3 mb-1">
                                                    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200 flex items-center gap-1.5">
                                                        {isPlatform && <ShieldCheck size={11} className="text-brand-700" aria-hidden="true" />}
                                                        {isPlatform ? 'MediFleet' : m.author_name}
                                                    </span>
                                                    <span className="text-2xs text-ink-500 dark:text-ink-400 shrink-0">{new Date(m.created_at).toLocaleString()}</span>
                                                </div>
                                                <p className="text-sm text-ink-900 dark:text-white whitespace-pre-wrap leading-relaxed">{m.body}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {active.status !== 'Closed' && (
                                <div className="p-3 border-t border-ink-200 dark:border-ink-800 flex gap-2 bg-white dark:bg-ink-900">
                                    <label htmlFor="reply-body" className="sr-only">Reply</label>
                                    <textarea
                                        id="reply-body"
                                        rows="2"
                                        className="flex-1 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 resize-none"
                                        placeholder="Reply to the tenant…"
                                        value={reply}
                                        onChange={e => setReply(e.target.value)}
                                    />
                                    <button
                                        type="button"
                                        onClick={sendReply}
                                        disabled={sendingReply || !reply.trim()}
                                        aria-label="Send reply"
                                        className="btn-primary self-end disabled:opacity-50 cursor-pointer"
                                    >
                                        {sendingReply ? <Activity size={16} className="animate-spin" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
                                    </button>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
