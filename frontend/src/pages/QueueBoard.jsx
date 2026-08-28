import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, RefreshCw, Clock, ArrowRight, Users, ListChecks,
    CheckCircle2, MapPin, ChevronDown, ChevronRight, CreditCard,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import PageHeader from '../components/PageHeader';
import { SkeletonTable } from '../components/ui/Skeleton';
import { departmentLabel } from '../utils/departments';

const LIVE_REFRESH_MS = 15000; // re-pull the live board every 15s

/* ─── Pure display helpers (module scope — not rebuilt per render) ─────────── */

const fmtClock = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const fmtDuration = (seconds) => {
    if (seconds == null || seconds < 0) return '—';
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m`;
    return `${s}s`;
};

const secondsSince = (iso, nowMs) => {
    if (!iso) return null;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? null : Math.max(0, Math.floor((nowMs - t) / 1000));
};

// Waiting-time urgency + acuity share one colour scale.
const acuityBadge = (level) => {
    if (level === 1) return 'badge-danger';
    if (level === 2) return 'badge-warn';
    return 'badge-neutral';
};
const acuityLabel = (level) => (level === 1 ? 'Emergency' : level === 2 ? 'Urgent' : 'Standard');

const statusBadge = (status) => {
    if (status === 'Completed') return 'badge-success';
    if (status === 'Cancelled') return 'badge-neutral';
    if (status === 'In Progress' || status === 'In Consultation') return 'badge-info';
    return 'badge-warn'; // Waiting
};

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function QueueBoard() {
    const [tab, setTab] = useState('live'); // 'live' | 'day'

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Operations"
                icon={ListChecks}
                title="Queue Board"
                subtitle="See everyone on the floor in real time, and replay each patient's journey through the rooms for any day."
            />

            <div className="card p-2 flex items-center shrink-0">
                <div role="tablist" aria-label="Queue board mode" className="segmented max-w-md">
                    <button type="button" role="tab" aria-selected={tab === 'live'} onClick={() => setTab('live')}
                        className={`segmented-option ${tab === 'live' ? 'segmented-option-active' : ''}`}>
                        <Activity size={16} className={tab === 'live' ? 'text-brand-600' : 'text-ink-400'} /> Live queue
                    </button>
                    <button type="button" role="tab" aria-selected={tab === 'day'} onClick={() => setTab('day')}
                        className={`segmented-option ${tab === 'day' ? 'segmented-option-active' : ''}`}>
                        <MapPin size={16} className={tab === 'day' ? 'text-accent-600' : 'text-ink-400'} /> Day &middot; Footprints
                    </button>
                </div>
            </div>

            {tab === 'live' ? <LiveQueue /> : <DayFootprints />}
        </div>
    );
}


/* ─── Live queue ──────────────────────────────────────────────────────────── */

function LiveQueue() {
    const [rows, setRows] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [lastUpdated, setLastUpdated] = useState(null);
    const [dept, setDept] = useState('All');
    // A 1s ticker so the waiting-time column counts up live between refreshes.
    const [nowMs, setNowMs] = useState(() => Date.now());

    const load = useCallback(async (quiet = false) => {
        if (!quiet) setIsLoading(true);
        try {
            const res = await apiClient.get('/queue/live');
            setRows(res.data || []);
            setLastUpdated(Date.now());
        } catch (err) {
            if (!quiet) toast.error(err.response?.data?.detail || 'Could not load the live queue.');
        } finally {
            // Unconditional reset — a quiet refresh never set it true, so this is
            // a no-op there (React bails on an unchanged value).
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
        const poll = setInterval(() => load(true), LIVE_REFRESH_MS);
        const tick = setInterval(() => setNowMs(Date.now()), 1000);
        return () => { clearInterval(poll); clearInterval(tick); };
    }, [load]);

    const departments = ['All', ...Array.from(new Set(rows.map((r) => r.to_department))).sort()];
    const visible = dept === 'All' ? rows : rows.filter((r) => r.to_department === dept);

    return (
        <div className="flex-1 min-h-0 card overflow-hidden flex flex-col">
            {/* Toolbar */}
            <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 p-3 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/30">
                <div role="group" aria-label="Filter by department" className="flex flex-wrap items-center gap-1.5">
                    {departments.map((d) => (
                        <button type="button" key={d} onClick={() => setDept(d)}
                            aria-pressed={dept === d}
                            className={`chip ${dept === d ? 'chip-active' : ''}`}>
                            {d === 'All' ? 'All' : departmentLabel(d)}{d !== 'All' && <span className="chip-count">{rows.filter((r) => r.to_department === d).length}</span>}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-2xs text-ink-500 dark:text-ink-400 flex items-center gap-1">
                        <span className="inline-block size-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
                        {visible.length} on queue{lastUpdated ? ` · updated ${fmtClock(new Date(lastUpdated).toISOString())}` : ''}
                    </span>
                    <button type="button" onClick={() => load()} className="btn-ghost text-xs" title="Refresh now">
                        <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> Refresh
                    </button>
                </div>
            </div>

            {/* Table */}
            <div className="flex-1 overflow-auto custom-scrollbar">
                <table className="table-clean min-w-[860px]">
                    <thead>
                        <tr>
                            <th>Q.No</th>
                            <th>Patient</th>
                            <th>Scheme</th>
                            <th>From &rarr; To (room)</th>
                            <th>Joined</th>
                            <th>Waiting</th>
                            <th>Priority</th>
                            <th>Staff</th>
                        </tr>
                    </thead>
                    <tbody>
                        {isLoading ? (
                            <tr><td colSpan={8}>
                                <SkeletonTable rows={6} cols={8} label="Loading the floor" />
                            </td></tr>
                        ) : visible.length === 0 ? (
                            <tr><td colSpan={8} className="px-4 py-12 text-center text-ink-500">
                                <Users size={32} className="mx-auto mb-2 text-ink-300" />
                                <p className="text-sm font-medium">No patients waiting{dept !== 'All' ? ` in ${departmentLabel(dept)}` : ''}.</p>
                            </td></tr>
                        ) : visible.map((r) => {
                            const waited = secondsSince(r.joined_at, nowMs);
                            const longWait = waited != null && waited > 30 * 60; // >30 min
                            return (
                                <tr key={r.queue_id}>
                                    <td className="font-mono text-ink-500 dark:text-ink-400">#{r.queue_id}</td>
                                    <td>
                                        <span className="font-medium text-ink-900 dark:text-ink-100">{r.patient_name}</span>
                                        <span className="block text-2xs font-mono text-ink-400">{r.outpatient_no || '—'}</span>
                                    </td>
                                    <td>
                                        <span className="inline-flex items-center gap-1 text-xs text-ink-600 dark:text-ink-300">
                                            <CreditCard size={12} className="text-ink-400" /> {r.scheme}
                                        </span>
                                    </td>
                                    <td>
                                        <span className="inline-flex items-center gap-1.5 text-xs">
                                            <span className="text-ink-500 dark:text-ink-400">{r.from_department ? departmentLabel(r.from_department) : 'Arrival'}</span>
                                            <ArrowRight size={12} className="text-ink-400 shrink-0" />
                                            <span className="font-medium text-ink-800 dark:text-ink-200">{departmentLabel(r.to_department)}</span>
                                        </span>
                                    </td>
                                    <td className="text-ink-600 dark:text-ink-300 whitespace-nowrap">{fmtClock(r.joined_at)}</td>
                                    <td className={`whitespace-nowrap font-medium ${longWait ? 'text-rose-600 dark:text-rose-400' : 'text-ink-700 dark:text-ink-200'}`}>
                                        <Clock size={11} className="inline mr-1 -mt-0.5" />{fmtDuration(waited)}
                                    </td>
                                    <td><span className={`${acuityBadge(r.acuity_level)} text-2xs`}>{acuityLabel(r.acuity_level)}</span></td>
                                    <td className="text-ink-600 dark:text-ink-400">{r.assigned_to || <span className="text-ink-400 italic">Unclaimed</span>}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}


/* ─── Day / footprints ────────────────────────────────────────────────────── */

function DayFootprints() {
    const [day, setDay] = useState(() => todayISO());
    const [data, setData] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [dealtOnly, setDealtOnly] = useState(false);
    const [expanded, setExpanded] = useState({});

    const load = useCallback(async (d) => {
        setIsLoading(true);
        try {
            const res = await apiClient.get('/queue/day', { params: { date: d } });
            setData(res.data || null);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not load the day report.');
            setData(null);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { load(day); }, [day, load]);

    const patients = (data?.patients || []).filter((p) => (dealtOnly ? p.dealt_with : true));
    const toggle = (id) => setExpanded((e) => ({ ...e, [id]: !e[id] }));

    return (
        <div className="flex-1 min-h-0 card overflow-hidden flex flex-col">
            {/* Toolbar */}
            <div className="shrink-0 flex flex-wrap items-center justify-between gap-3 p-3 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/30">
                <div className="flex items-center gap-2">
                    <label htmlFor="qb-day" className="label mb-0">Day</label>
                    <input id="qb-day" type="date" value={day} max={todayISO()} onChange={(e) => setDay(e.target.value)} className="input w-auto" />
                    <label className="flex items-center gap-1.5 text-xs text-ink-600 dark:text-ink-300 cursor-pointer ml-2">
                        <input type="checkbox" checked={dealtOnly} onChange={(e) => setDealtOnly(e.target.checked)} className="size-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500" />
                        Dealt-with only
                    </label>
                </div>
                {data && (
                    <div className="flex items-center gap-3 text-2xs text-ink-500 dark:text-ink-400">
                        <span className="inline-flex items-center gap-1"><Users size={12} /> {data.total_patients} seen</span>
                        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400"><CheckCircle2 size={12} /> {data.dealt_with} dealt with</span>
                        <span className="inline-flex items-center gap-1"><Activity size={12} /> {data.still_active} still active</span>
                    </div>
                )}
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto custom-scrollbar p-3 sm:p-4 space-y-2">
                {isLoading ? (
                    <div className="py-6"><SkeletonTable rows={4} cols={4} label="Loading the day" /></div>
                ) : patients.length === 0 ? (
                    <div className="py-12 text-center text-ink-500">
                        <MapPin size={32} className="mx-auto mb-2 text-ink-300" />
                        <p className="text-sm font-medium">No patients {dealtOnly ? 'dealt with' : 'seen'} on this day.</p>
                    </div>
                ) : patients.map((p) => {
                    const open = !!expanded[p.patient_id];
                    return (
                        <div key={p.patient_id} className="card-flush border border-ink-200 dark:border-ink-800 rounded-xl overflow-hidden">
                            <button type="button" onClick={() => toggle(p.patient_id)}
                                className="w-full flex items-center gap-3 p-3 text-left hover:bg-ink-50/60 dark:hover:bg-ink-800/40">
                                {open ? <ChevronDown size={16} className="text-ink-400 shrink-0" /> : <ChevronRight size={16} className="text-ink-400 shrink-0" />}
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-ink-900 dark:text-ink-100 truncate">{p.patient_name}</span>
                                        <span className="text-2xs font-mono text-ink-400">{p.outpatient_no || '—'}</span>
                                        {p.dealt_with && <span className="badge-success text-2xs">Dealt with</span>}
                                        {p.still_active && <span className="badge-warn text-2xs">On queue</span>}
                                    </div>
                                    {/* Compact trail preview */}
                                    <div className="flex flex-wrap items-center gap-1 mt-1 text-2xs text-ink-500 dark:text-ink-400">
                                        {p.departments.map((d, i) => (
                                            <React.Fragment key={d}>
                                                {i > 0 && <ArrowRight size={9} className="text-ink-300" />}
                                                <span>{departmentLabel(d)}</span>
                                            </React.Fragment>
                                        ))}
                                    </div>
                                </div>
                                <div className="text-right text-2xs text-ink-500 dark:text-ink-400 shrink-0">
                                    <div>{p.stops} stop{p.stops === 1 ? '' : 's'}</div>
                                    <div>{fmtClock(p.first_seen)} – {fmtClock(p.last_seen)}</div>
                                </div>
                            </button>

                            {open && (
                                <div className="border-t border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/30 p-3">
                                    <ol className="space-y-2">
                                        {p.footprint.map((s, i) => (
                                            <li key={s.queue_id} className="flex items-start gap-3">
                                                <span className="mt-0.5 shrink-0 size-5 rounded-full bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-300 text-2xs font-bold flex items-center justify-center">{i + 1}</span>
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="font-medium text-sm text-ink-800 dark:text-ink-200">{departmentLabel(s.department)}</span>
                                                        <span className={`${statusBadge(s.status)} text-2xs`}>{s.status}</span>
                                                        {s.handled_by && <span className="text-2xs text-ink-500 dark:text-ink-400">by {s.handled_by}</span>}
                                                    </div>
                                                    <div className="text-2xs text-ink-500 dark:text-ink-400 mt-0.5">
                                                        {fmtClock(s.joined_at)} {s.completed_at ? `→ ${fmtClock(s.completed_at)}` : '→ …'} &middot; {fmtDuration(s.duration_seconds)}
                                                    </div>
                                                </div>
                                            </li>
                                        ))}
                                    </ol>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
