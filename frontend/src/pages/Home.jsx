import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Stethoscope, HeartPulse, Users, TestTube, Radio, Pill, Bed, Receipt,
    CalendarDays, CalendarClock, ClipboardList, Package, Banknote, BookOpen,
    MessageSquare, Bell, ArrowRight, Activity, CheckCircle2, AlertCircle,
    LayoutDashboard, Smartphone,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useModules } from '../context/ModuleContext';
import { useBranding } from '../context/BrandingContext';

// Quick-action tiles. Each declares the permission and module that gate it —
// same philosophy as the sidebar, so a user only ever sees actions they can
// actually open. `perm: null` means account-level (everyone).
const ACTIONS = [
    { label: 'Command Center', desc: 'Hospital overview & admin', to: '/app/admin',        icon: LayoutDashboard, perm: 'users:manage',     module: 'dashboard',       tone: 'brand' },
    { label: 'Clinical Desk',  desc: 'See waiting patients',     to: '/app/clinical',     icon: Stethoscope,     perm: 'clinical:read',    module: 'clinical',        tone: 'sky' },
    { label: 'Triage',         desc: 'Capture vitals & acuity',  to: '/app/triage',       icon: HeartPulse,      perm: 'triage:read',      module: 'clinical',        tone: 'rose' },
    { label: 'Patients',       desc: 'Register & search',        to: '/app/patients',     icon: Users,           perm: 'patients:read',    module: 'patients',        tone: 'brand' },
    { label: 'Laboratory',     desc: 'Process the lab queue',    to: '/app/laboratory',   icon: TestTube,        perm: 'laboratory:read',  module: 'laboratory',      tone: 'violet' },
    { label: 'Radiology',      desc: 'Imaging worklist',         to: '/app/radiology',    icon: Radio,           perm: 'radiology:read',   module: 'radiology',       tone: 'indigo' },
    { label: 'Pharmacy',       desc: 'Dispense prescriptions',   to: '/app/pharmacy',     icon: Pill,            perm: 'pharmacy:read',    module: 'pharmacy',        tone: 'emerald' },
    { label: 'Wards',          desc: 'Beds & admissions',        to: '/app/wards',        icon: Bed,             perm: 'wards:read',       module: 'wards',           tone: 'teal' },
    { label: 'Billing',        desc: 'Invoices & payments',      to: '/app/billing',      icon: Receipt,         perm: 'billing:read',     module: 'billing',         tone: 'amber' },
    { label: 'Inventory',      desc: 'Stock & suppliers',        to: '/app/inventory',    icon: Package,         perm: 'inventory:read',   module: 'inventory',       tone: 'sky' },
    { label: 'Accounting',     desc: 'Ledgers & reports',        to: '/app/accounting',   icon: BookOpen,        perm: 'accounting:view',  module: 'accounting',      tone: 'violet' },
    { label: 'Cheques',        desc: 'Cheque register',          to: '/app/cheques',      icon: Banknote,        perm: 'cheques:read',     module: 'cheques',         tone: 'amber' },
    { label: 'Appointments',   desc: 'Book & manage',            to: '/app/appointments', icon: CalendarDays,    perm: 'appointments:read',module: 'appointments',    tone: 'brand' },
    { label: 'Calendar',       desc: 'Schedule & events',        to: '/app/calendar',     icon: CalendarClock,   perm: null,               module: 'appointments',    tone: 'teal' },
    { label: 'Medical History',desc: 'Longitudinal charts',      to: '/app/medical-history',icon: ClipboardList, perm: 'history:read',     module: 'medical_history', tone: 'indigo' },
    { label: 'M-Pesa',         desc: 'Mobile-money settings',    to: '/app/mpesa-settings',icon: Smartphone,     perm: 'payhero:manage',   module: 'payhero',         tone: 'emerald' },
    { label: 'Messages',       desc: 'Team messaging',           to: '/app/messages',     icon: MessageSquare,   perm: null,               module: 'messaging',       tone: 'sky' },
];

const TONE = {
    brand:   'bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 ring-brand-100 dark:ring-brand-500/20',
    sky:     'bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300 ring-sky-100 dark:ring-sky-500/20',
    rose:    'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 ring-rose-100 dark:ring-rose-500/20',
    violet:  'bg-violet-50 dark:bg-violet-500/10 text-violet-700 dark:text-violet-300 ring-violet-100 dark:ring-violet-500/20',
    indigo:  'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 ring-indigo-100 dark:ring-indigo-500/20',
    emerald: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 ring-emerald-100 dark:ring-emerald-500/20',
    teal:    'bg-teal-50 dark:bg-teal-500/10 text-teal-700 dark:text-teal-300 ring-teal-100 dark:ring-teal-500/20',
    amber:   'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 ring-amber-100 dark:ring-amber-500/20',
};

const NOTIF_TONE = {
    critical: 'text-rose-600 dark:text-rose-400',
    warning:  'text-amber-600 dark:text-amber-400',
    success:  'text-accent-600 dark:text-accent-400',
    info:     'text-sky-600 dark:text-sky-400',
};

const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
};

const todayBounds = () => {
    const now = new Date();
    const d = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    return { from: `${d}T00:00:00`, to: `${d}T23:59:59` };
};

export default function Home() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const { hasModule, loading: modulesLoading } = useModules();
    const { branding } = useBranding();

    const [notifications, setNotifications] = useState([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [todayAppts, setTodayAppts] = useState([]);
    const [todayEvents, setTodayEvents] = useState([]);
    // "now" lives in state (refreshed on each load) so the relative-time
    // formatter stays a pure function of props/state during render.
    const [now, setNow] = useState(() => Date.now());

    // Memoise so the array identity is stable across renders (it's a dep of
    // the actions memo + the data loader).
    const perms = useMemo(() => user?.permissions || [], [user?.permissions]);
    const firstName = (user?.full_name || '').split(' ')[0] || 'there';
    // Derived (not state): which roles get the appointments overlay.
    const canSeeAppts = perms.includes('appointments:read') || perms.includes('patients:write');

    // Quick actions the user can actually open (permission + module-entitled).
    const actions = useMemo(() => ACTIONS.filter((a) => {
        if (a.module && !modulesLoading && !hasModule(a.module)) return false;
        if (a.perm && !perms.includes(a.perm)) return false;
        return true;
    }), [perms, hasModule, modulesLoading]);

    const load = useCallback(async () => {
        setNow(Date.now());
        const { from, to } = todayBounds();
        const [notifRes, evtRes] = await Promise.all([
            apiClient.get('/notifications/', { params: { limit: 6 } }).catch(() => ({ data: {} })),
            apiClient.get('/calendar/events', { params: { date_from: from, date_to: to } }).catch(() => ({ data: [] })),
        ]);
        setNotifications(notifRes.data?.notifications || []);
        setUnreadCount(notifRes.data?.unread_count || 0);
        setTodayEvents(evtRes.data || []);

        // Appointments are permission-gated; only fetch if the role has access.
        if (perms.includes('appointments:read') || perms.includes('patients:write')) {
            try {
                const params = { date_from: from, date_to: to };
                if (user?.role === 'Doctor' && user?.user_id) params.doctor_id = user.user_id;
                const r = await apiClient.get('/appointments/', { params });
                setTodayAppts((r.data || []).filter((a) => a.status !== 'Cancelled'));
            } catch { /* leave empty on 402/403 */ }
        }
    }, [perms, user]);

    useEffect(() => { load(); }, [load]);

    const markRead = async (id) => {
        try {
            await apiClient.patch(`/notifications/${id}/read`);
            setNotifications((prev) => prev.map((n) => n.notification_id === id ? { ...n, is_read: true } : n));
            setUnreadCount((c) => Math.max(0, c - 1));
        } catch { /* non-fatal */ }
    };

    const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    const fmtAgo = (iso) => {
        if (!iso) return '';
        const mins = Math.round((now - new Date(iso).getTime()) / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.round(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        return `${Math.round(hrs / 24)}d ago`;
    };

    return (
        <div className="space-y-6 pb-8">
            {/* Greeting banner */}
            <div className="rounded-2xl bg-gradient-to-br from-brand-600 via-brand-700 to-teal-700 text-white p-6 sm:p-8 shadow-elevated">
                <p className="text-2xs font-semibold uppercase tracking-[0.18em] text-brand-200">
                    {new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}
                </p>
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight mt-1">
                    {greeting()}, {firstName}.
                </h1>
                <p className="text-sm text-brand-100/90 mt-1.5">
                    {user?.role} · {branding?.tenant_name || localStorage.getItem('hms_tenant_name') || 'MediFleet'}
                </p>
                <div className="flex flex-wrap gap-2 mt-4">
                    <button type="button" onClick={() => navigate('/app/calendar')}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 text-sm font-medium backdrop-blur-sm transition-colors">
                        <CalendarClock size={15} /> My calendar
                    </button>
                    {unreadCount > 0 && (
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/15 text-sm font-medium backdrop-blur-sm">
                            <Bell size={15} /> {unreadCount} unread notification{unreadCount === 1 ? '' : 's'}
                        </span>
                    )}
                </div>
            </div>

            {/* Quick actions */}
            <section>
                <h2 className="section-eyebrow mb-3">Quick actions</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                    {actions.map((a) => {
                        const Icon = a.icon;
                        return (
                            <Link key={a.to} to={a.to}
                                className="group card p-4 hover:-translate-y-0.5 hover:shadow-elevated transition-all">
                                <div className={`size-10 rounded-xl flex items-center justify-center ring-1 ${TONE[a.tone]}`}>
                                    <Icon size={19} />
                                </div>
                                <div className="mt-3 flex items-center justify-between">
                                    <div className="min-w-0">
                                        <p className="text-sm font-semibold text-ink-900 dark:text-white truncate">{a.label}</p>
                                        <p className="text-2xs text-ink-500 dark:text-ink-400 truncate">{a.desc}</p>
                                    </div>
                                    <ArrowRight size={15} className="text-ink-300 group-hover:text-brand-500 group-hover:translate-x-0.5 transition-all shrink-0" />
                                </div>
                            </Link>
                        );
                    })}
                </div>
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Today's schedule */}
                <div className="lg:col-span-2 card p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="section-eyebrow">Today</h2>
                        <Link to="/app/calendar" className="text-xs text-brand-700 dark:text-brand-300 hover:underline inline-flex items-center gap-1">
                            Open calendar <ArrowRight size={12} />
                        </Link>
                    </div>

                    {canSeeAppts && (
                        <div className="mb-4">
                            <p className="text-2xs font-semibold uppercase tracking-wider text-ink-400 mb-2">Appointments</p>
                            {todayAppts.length === 0 ? (
                                <p className="text-sm text-ink-500 dark:text-ink-400">No appointments today.</p>
                            ) : (
                                <ul className="space-y-1.5">
                                    {todayAppts.slice(0, 6).map((a) => (
                                        <li key={a.appointment_id} className="flex items-center gap-2 text-sm">
                                            <span className="font-mono text-2xs text-ink-400 w-12 shrink-0">{fmtTime(a.appointment_date)}</span>
                                            <Stethoscope size={13} className="text-sky-500 shrink-0" />
                                            <span className="text-ink-800 dark:text-ink-200 truncate flex-1">{a.patient_name}</span>
                                            <span className="text-2xs text-ink-400 truncate hidden sm:block">{a.doctor_name}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    )}

                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-wider text-ink-400 mb-2">My events</p>
                        {todayEvents.length === 0 ? (
                            <p className="text-sm text-ink-500 dark:text-ink-400">
                                No personal events today.{' '}
                                <Link to="/app/calendar" className="text-brand-700 dark:text-brand-300 hover:underline">Add one</Link>.
                            </p>
                        ) : (
                            <ul className="space-y-1.5">
                                {todayEvents.map((e) => (
                                    <li key={e.event_id} className="flex items-center gap-2 text-sm">
                                        <span className="font-mono text-2xs text-ink-400 w-12 shrink-0">{e.all_day ? 'All day' : fmtTime(e.start_at)}</span>
                                        <span className="size-2 rounded-full bg-teal-500 shrink-0" />
                                        <span className="text-ink-800 dark:text-ink-200 truncate flex-1">{e.title}</span>
                                        <span className="text-2xs text-ink-400 capitalize">{e.category}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>

                {/* Notifications */}
                <div className="card p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="section-eyebrow">Notifications</h2>
                        {unreadCount > 0 && <span className="badge-warn">{unreadCount}</span>}
                    </div>
                    {notifications.length === 0 ? (
                        <div className="text-center py-8 text-ink-400">
                            <Bell size={20} className="mx-auto mb-2 opacity-50" />
                            <p className="text-sm">You're all caught up.</p>
                        </div>
                    ) : (
                        <ul className="space-y-2.5">
                            {notifications.map((n) => {
                                const body = (
                                    <>
                                        <div className="flex items-start gap-2">
                                            <span className={`mt-1 shrink-0 ${NOTIF_TONE[n.category] || NOTIF_TONE.info}`}>
                                                {n.category === 'success' ? <CheckCircle2 size={14} />
                                                    : n.category === 'critical' || n.category === 'warning' ? <AlertCircle size={14} />
                                                    : <Bell size={14} />}
                                            </span>
                                            <div className="min-w-0 flex-1">
                                                <p className={`text-sm leading-tight truncate ${n.is_read ? 'text-ink-500 dark:text-ink-400' : 'font-semibold text-ink-900 dark:text-white'}`}>{n.title}</p>
                                                {n.body && <p className="text-2xs text-ink-500 dark:text-ink-400 truncate mt-0.5">{n.body}</p>}
                                                <p className="text-2xs text-ink-400 mt-0.5">{fmtAgo(n.created_at)}</p>
                                            </div>
                                            {!n.is_read && <span className="size-2 rounded-full bg-brand-500 mt-1.5 shrink-0" />}
                                        </div>
                                    </>
                                );
                                return (
                                    <li key={n.notification_id}>
                                        {n.link ? (
                                            <Link to={n.link} onClick={() => markRead(n.notification_id)}
                                                className="block p-2 -mx-2 rounded-lg hover:bg-ink-50 dark:hover:bg-ink-800/50 transition-colors">
                                                {body}
                                            </Link>
                                        ) : (
                                            <button type="button" onClick={() => markRead(n.notification_id)}
                                                className="block w-full text-left p-2 -mx-2 rounded-lg hover:bg-ink-50 dark:hover:bg-ink-800/50 transition-colors">
                                                {body}
                                            </button>
                                        )}
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </div>
        </div>
    );
}
