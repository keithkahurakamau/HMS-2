import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    LifeBuoy, Search, Filter, Send, RefreshCw, Activity, MessageSquare,
    Building2, Calendar, CheckCircle2, AlertCircle, Clock, X,
} from 'lucide-react';

const STATUS_META = {
    'Open':                 { color: 'bg-blue-500/20 text-blue-300 ring-blue-500/30',     icon: AlertCircle },
    'In Progress':          { color: 'bg-amber-500/20 text-amber-300 ring-amber-500/30',  icon: Activity    },
    'Waiting on Customer':  { color: 'bg-amber-500/20 text-amber-300 ring-amber-500/30',  icon: Clock       },
    'Resolved':             { color: 'bg-accent-500/20 text-accent-300 ring-accent-500/30', icon: CheckCircle2 },
    'Closed':               { color: 'bg-white/10 text-ink-400 ring-white/20',            icon: CheckCircle2 },
};

const CATEGORIES = ['Billing', 'Bug', 'Feature', 'Account', 'Onboarding', 'Other'];
const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];
const STATUSES = Object.keys(STATUS_META);

export default function SupportInbox() {
    const [tickets, setTickets] = useState([]);
    const [summary, setSummary] = useState({});
    const [active, setActive] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('Open');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('');

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
            const res = await apiClient.patch(`/public/superadmin/tickets/${active.ticket_id}/status`, { status });
            const refreshed = await apiClient.get(`/public/superadmin/tickets/${active.ticket_id}`);
            setActive(refreshed.data);
            void res;
            fetchTickets();
            fetchSummary();
            toast.success(`Status → ${status}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to update status.');
        }
    };

    return (
        <div className="space-y-5 animate-fade-in">
            <div className="flex justify-between items-start flex-wrap gap-3">
                <div>
                    <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-amber-400">Console</span>
                    <h1 className="text-2xl font-semibold text-white tracking-tight mt-1 flex items-center gap-2">
                        <LifeBuoy size={22} className="text-amber-400" /> Support Inbox
                    </h1>
                    <p className="text-sm text-ink-400 mt-1">Tickets raised by tenant admins across the fleet.</p>
                </div>
                <button onClick={fetchAll} className="px-3 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg text-sm font-semibold ring-1 ring-white/10 flex items-center gap-2">
                    <RefreshCw size={14} /> Refresh
                </button>
            </div>

            {/* KPI row */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {STATUSES.map(s => {
                    const count = summary[s] || 0;
                    return (
                        <button key={s} onClick={() => setStatusFilter(s)}
                                className={`text-left rounded-2xl p-4 ring-1 transition-colors ${statusFilter === s ? 'bg-white/[0.08] ring-amber-500/40' : 'bg-white/[0.04] ring-white/10 hover:bg-white/[0.06]'}`}>
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">{s}</p>
                            <p className="text-2xl font-semibold text-white mt-1">{count}</p>
                        </button>
                    );
                })}
            </div>

            {/* Filters */}
            <div className="bg-white/[0.04] ring-1 ring-white/10 rounded-2xl p-3 flex flex-wrap gap-3 items-center">
                <div className="relative flex-1 min-w-[16rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                    <input className="w-full bg-ink-900/60 ring-1 ring-white/10 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-ink-500 focus:outline-none focus:ring-amber-500/30"
                           placeholder="Search subject…" value={search} onChange={e => setSearch(e.target.value)} />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                    <select className="bg-ink-900/60 ring-1 ring-white/10 rounded-lg pl-9 pr-8 py-2 text-sm text-white focus:outline-none"
                            value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
                        <option value="">All categories</option>
                        {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                    </select>
                </div>
                <select className="bg-ink-900/60 ring-1 ring-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none"
                        value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}>
                    <option value="">All priorities</option>
                    {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                </select>
                <button onClick={() => setStatusFilter('')} className="text-2xs text-ink-400 hover:text-amber-300 uppercase tracking-wider">Clear status</button>
            </div>

            <div className="grid grid-cols-12 gap-4">
                {/* List */}
                <div className="col-span-12 lg:col-span-5 bg-white/[0.04] ring-1 ring-white/10 rounded-2xl overflow-hidden flex flex-col" style={{maxHeight: 'calc(100vh - 24rem)'}}>
                    {isLoading ? (
                        <div className="flex-1 flex items-center justify-center text-ink-400 p-10">
                            <Activity className="animate-spin mr-2 text-amber-400" size={18} /> Loading…
                        </div>
                    ) : tickets.length === 0 ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-500 p-10 text-center">
                            <LifeBuoy size={36} className="mb-3 text-ink-600" />
                            <p className="text-sm">No tickets match the filters.</p>
                        </div>
                    ) : (
                        <div className="overflow-y-auto custom-scrollbar divide-y divide-white/5">
                            {tickets.map(t => {
                                const meta = STATUS_META[t.status] || {};
                                const isActive = active?.ticket_id === t.ticket_id;
                                return (
                                    <button key={t.ticket_id} onClick={() => openTicket(t.ticket_id)}
                                            className={`w-full p-4 text-left transition-colors ${isActive ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'}`}>
                                        <div className="flex justify-between items-start gap-2 mb-1">
                                            <h3 className="font-semibold text-sm text-white line-clamp-1 flex-1">{t.subject}</h3>
                                            <span className={`px-2 py-0.5 rounded-full text-2xs font-semibold ring-1 ${meta.color}`}>{t.status}</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-ink-400 mt-1">
                                            <Building2 size={11} /> <span className="truncate">{t.tenant_name}</span>
                                        </div>
                                        <div className="flex items-center gap-3 text-2xs text-ink-500 mt-1">
                                            <span className="font-mono">#{t.ticket_id}</span>
                                            <span>{t.category}</span>
                                            <span>{t.priority}</span>
                                            <span className="ml-auto flex items-center gap-1"><Calendar size={10} /> {new Date(t.created_at).toLocaleDateString()}</span>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Thread */}
                <div className="col-span-12 lg:col-span-7 bg-white/[0.04] ring-1 ring-white/10 rounded-2xl overflow-hidden flex flex-col" style={{maxHeight: 'calc(100vh - 24rem)'}}>
                    {!active ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-ink-500 p-10 text-center">
                            <MessageSquare size={36} className="mb-3 text-ink-600" />
                            <p className="text-sm">Select a ticket to view the thread.</p>
                        </div>
                    ) : (
                        <>
                            <div className="p-4 border-b border-white/5 bg-white/[0.02]">
                                <div className="flex justify-between items-start gap-3 mb-2">
                                    <div className="min-w-0">
                                        <h2 className="text-base font-semibold text-white">{active.subject}</h2>
                                        <div className="flex items-center gap-3 text-xs text-ink-400 mt-1">
                                            <Building2 size={11} /> <span>{active.tenant_name}</span>
                                            <span className="font-mono">#{active.ticket_id}</span>
                                            <span>{active.category}</span>
                                            <span>P: {active.priority}</span>
                                        </div>
                                        <p className="text-2xs text-ink-500 mt-1">Raised by {active.submitter_name} &lt;{active.submitter_email}&gt;</p>
                                    </div>
                                </div>
                                <div className="flex flex-wrap gap-1.5 pt-1">
                                    {STATUSES.map(s => (
                                        <button key={s} onClick={() => setStatus(s)} disabled={s === active.status}
                                                className={`text-2xs font-semibold px-2.5 py-1 rounded-lg ring-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                                                    s === active.status
                                                        ? STATUS_META[s].color
                                                        : 'bg-white/5 text-ink-400 ring-white/10 hover:bg-white/10 hover:text-white'
                                                }`}>
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                                {(active.messages || []).map(m => {
                                    const isPlatform = m.author_kind === 'platform';
                                    return (
                                        <div key={m.message_id} className={`flex ${isPlatform ? 'justify-end' : 'justify-start'}`}>
                                            <div className={`max-w-[80%] rounded-2xl p-3 ${isPlatform ? 'bg-amber-500/15 ring-1 ring-amber-500/30' : 'bg-white/[0.05] ring-1 ring-white/10'}`}>
                                                <div className="flex items-baseline justify-between gap-3 mb-1">
                                                    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-300">
                                                        {isPlatform ? '🟡 MediFleet' : m.author_name}
                                                    </span>
                                                    <span className="text-2xs text-ink-500">{new Date(m.created_at).toLocaleString()}</span>
                                                </div>
                                                <p className="text-sm text-ink-100 whitespace-pre-wrap leading-relaxed">{m.body}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {active.status !== 'Closed' && (
                                <div className="p-3 border-t border-white/5 flex gap-2">
                                    <textarea rows="2" className="flex-1 bg-ink-900/60 ring-1 ring-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-ink-500 focus:outline-none resize-none"
                                              placeholder="Reply to the tenant…" value={reply}
                                              onChange={e => setReply(e.target.value)} />
                                    <button onClick={sendReply} disabled={sendingReply || !reply.trim()}
                                            className="self-end px-4 py-2 bg-gradient-to-b from-amber-500 to-amber-600 text-white rounded-lg font-semibold text-sm shadow-glow disabled:opacity-50">
                                        {sendingReply ? <Activity size={16} className="animate-spin" /> : <Send size={16} />}
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
