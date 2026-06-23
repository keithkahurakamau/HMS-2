import React, { useState } from 'react';
import {
    Activity, HeartPulse, Droplet, Thermometer, CalendarDays, Pill,
    Clock, MapPin, Check, RefreshCw, ChevronRight, TrendingUp, TrendingDown,
} from 'lucide-react';

/*
 * InteractiveDashboard
 * --------------------
 * A fully interactive mock of the MediFleet patient portal. It is not wired
 * to the API; it runs on local state so a visitor can click around and feel
 * the product before signing in. Three tabs:
 *   - Overview      : live-style health metrics with trend sparklines
 *   - Appointments  : upcoming visits, confirm / reschedule affordances
 *   - Prescriptions : active meds with a working "request refill" flow
 *
 * Built on the premium landing language (lp-card / lp-chip). Self-contained
 * and reusable: drop <InteractiveDashboard /> anywhere.
 */

const TABS = [
    { key: 'overview', label: 'Overview', icon: Activity },
    { key: 'appointments', label: 'Appointments', icon: CalendarDays },
    { key: 'prescriptions', label: 'Prescriptions', icon: Pill },
];

const METRICS = [
    { key: 'hr', label: 'Heart rate', value: '72', unit: 'bpm', icon: HeartPulse, trend: 'down', delta: '-3', spark: [14, 12, 16, 11, 13, 9, 10], tint: '#00d4d4' },
    { key: 'bp', label: 'Blood pressure', value: '118/76', unit: 'mmHg', icon: Activity, trend: 'flat', delta: 'stable', spark: [12, 13, 12, 14, 12, 13, 12], tint: '#008080' },
    { key: 'spo2', label: 'Oxygen', value: '98', unit: '%', icon: Droplet, trend: 'up', delta: '+1', spark: [9, 10, 11, 10, 12, 13, 14], tint: '#00d4d4' },
    { key: 'temp', label: 'Temperature', value: '36.6', unit: '°C', icon: Thermometer, trend: 'flat', delta: 'normal', spark: [11, 12, 11, 12, 11, 12, 11], tint: '#008080' },
];

const APPOINTMENTS = [
    { id: 1, doctor: 'Dr. Achieng Otieno', dept: 'Cardiology', date: 'Mon, 14 Jul', time: '09:30', room: 'Block B, Room 4' },
    { id: 2, doctor: 'Dr. Singh Mehta', dept: 'General medicine', date: 'Thu, 24 Jul', time: '11:00', room: 'Block A, Room 2' },
];

const INITIAL_RX = [
    { id: 1, name: 'Atorvastatin 20mg', schedule: 'Once daily, evening', left: 6 },
    { id: 2, name: 'Metformin 500mg', schedule: 'Twice daily, with meals', left: 12 },
    { id: 3, name: 'Vitamin D3 1000IU', schedule: 'Once daily', left: 2 },
];

/* Tiny inline sparkline (no chart library, pure SVG). */
function Sparkline({ points, tint }) {
    const max = Math.max(...points);
    const min = Math.min(...points);
    const range = max - min || 1;
    const step = 100 / (points.length - 1);
    const d = points
        .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * step} ${24 - ((p - min) / range) * 20}`)
        .join(' ');
    return (
        <svg viewBox="0 0 100 24" className="w-full h-6" preserveAspectRatio="none" aria-hidden="true">
            <path d={d} fill="none" stroke={tint} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

export default function InteractiveDashboard({ className = '' }) {
    const [tab, setTab] = useState('overview');
    const [confirmed, setConfirmed] = useState({});
    const [rx, setRx] = useState(INITIAL_RX);
    const [refilling, setRefilling] = useState(null);

    const requestRefill = (id) => {
        setRefilling(id);
        // Simulated async refill so the button shows a real interaction cycle.
        window.setTimeout(() => {
            setRx((prev) => prev.map((m) => (m.id === id ? { ...m, left: m.left + 30, refilled: true } : m)));
            setRefilling(null);
        }, 900);
    };

    return (
        <div className={`lp-glass-dark rounded-[1.6rem] p-3 sm:p-4 ${className}`}>
            {/* Window chrome */}
            <div className="flex items-center justify-between px-2 pt-1 pb-3">
                <div className="flex items-center gap-1.5">
                    <span className="size-2.5 rounded-full bg-[#00ffff]/70" />
                    <span className="size-2.5 rounded-full bg-[#b2f0f0]/50" />
                    <span className="size-2.5 rounded-full bg-[#008080]/70" />
                </div>
                <span className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-[#b2f0f0]/70">
                    Patient portal preview
                </span>
            </div>

            <div className="rounded-[1.2rem] bg-white/95 overflow-hidden shadow-2xl">
                {/* Patient header */}
                <div className="px-4 sm:px-5 py-4 bg-gradient-to-r from-[#012626] to-[#015050] text-white flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <span className="size-10 rounded-xl bg-[#00ffff]/20 ring-1 ring-[#00ffff]/40 flex items-center justify-center">
                            <HeartPulse size={20} className="text-[#7dfdfd]" />
                        </span>
                        <div>
                            <p className="text-sm font-semibold leading-none">Amara Njoki</p>
                            <p className="text-[0.7rem] text-[#b2f0f0]/80 mt-1 font-mono">OP-2026-0142</p>
                        </div>
                    </div>
                    <span className="hidden sm:inline-flex items-center gap-1.5 text-[0.65rem] font-semibold px-2.5 py-1 rounded-full bg-[#00ffff]/15 text-[#7dfdfd] ring-1 ring-[#00ffff]/30">
                        <span className="size-1.5 rounded-full bg-[#00ffff] animate-pulse" /> Verified
                    </span>
                </div>

                {/* Tabs */}
                <div className="flex gap-1 p-1.5 bg-[#f2fdfd] border-b border-[#b2f0f0]/60">
                    {TABS.map((t) => {
                        const Icon = t.icon;
                        const active = tab === t.key;
                        return (
                            <button
                                key={t.key}
                                type="button"
                                onClick={() => setTab(t.key)}
                                aria-pressed={active}
                                className={`flex-1 inline-flex items-center justify-center gap-1.5 text-xs font-semibold py-2 rounded-lg transition-all duration-200 ease-in-out cursor-pointer ${
                                    active
                                        ? 'bg-[#008080] text-white shadow-md shadow-[#008080]/30'
                                        : 'text-[#015050] hover:bg-[#b2f0f0]/50'
                                }`}
                            >
                                <Icon size={14} /> <span className="hidden xs:inline sm:inline">{t.label}</span>
                            </button>
                        );
                    })}
                </div>

                {/* Panel body */}
                <div className="p-4 sm:p-5 min-h-[19rem]">
                    {tab === 'overview' && (
                        <div className="animate-fade-in">
                            <div className="grid grid-cols-2 gap-3">
                                {METRICS.map((m) => {
                                    const Icon = m.icon;
                                    const TrendIcon = m.trend === 'up' ? TrendingUp : m.trend === 'down' ? TrendingDown : Activity;
                                    return (
                                        <div
                                            key={m.key}
                                            className="group rounded-xl border border-[#b2f0f0] bg-white p-3 transition-all duration-200 ease-in-out hover:-translate-y-1 hover:border-[#00d4d4] hover:shadow-lg hover:shadow-[#008080]/10"
                                        >
                                            <div className="flex items-center justify-between">
                                                <span className="size-7 rounded-lg bg-[#e6fbfb] text-[#008080] flex items-center justify-center group-hover:bg-[#00ffff]/20 transition-colors">
                                                    <Icon size={15} />
                                                </span>
                                                <span className="inline-flex items-center gap-0.5 text-[0.62rem] font-semibold text-[#475569]">
                                                    <TrendIcon size={11} /> {m.delta}
                                                </span>
                                            </div>
                                            <p className="mt-2 text-[0.65rem] font-semibold uppercase tracking-wide text-[#64748b]">{m.label}</p>
                                            <p className="text-lg font-bold text-[#012626] leading-tight tabular-nums">
                                                {m.value}<span className="text-[0.65rem] font-medium text-[#94a3b8] ml-1">{m.unit}</span>
                                            </p>
                                            <Sparkline points={m.spark} tint={m.tint} />
                                        </div>
                                    );
                                })}
                            </div>
                            <div className="mt-3 flex items-center justify-between rounded-xl bg-gradient-to-r from-[#e6fbfb] to-[#b2f0f0]/40 px-3 py-2.5 ring-1 ring-[#b2f0f0]">
                                <span className="text-xs font-semibold text-[#015050] inline-flex items-center gap-1.5">
                                    <Check size={14} className="text-[#008080]" /> All vitals within range
                                </span>
                                <span className="text-[0.65rem] font-medium text-[#64748b]">Updated 2 min ago</span>
                            </div>
                        </div>
                    )}

                    {tab === 'appointments' && (
                        <div className="animate-fade-in space-y-3">
                            {APPOINTMENTS.map((a) => {
                                const isConfirmed = confirmed[a.id];
                                return (
                                    <div key={a.id} className="rounded-xl border border-[#b2f0f0] bg-white p-3.5 transition-all duration-200 ease-in-out hover:border-[#00d4d4] hover:shadow-md">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="min-w-0">
                                                <p className="text-sm font-semibold text-[#012626] truncate">{a.doctor}</p>
                                                <p className="text-[0.7rem] text-[#008080] font-medium">{a.dept}</p>
                                                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.7rem] text-[#475569]">
                                                    <span className="inline-flex items-center gap-1"><CalendarDays size={12} /> {a.date}</span>
                                                    <span className="inline-flex items-center gap-1"><Clock size={12} /> {a.time}</span>
                                                    <span className="inline-flex items-center gap-1"><MapPin size={12} /> {a.room}</span>
                                                </div>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => setConfirmed((c) => ({ ...c, [a.id]: !c[a.id] }))}
                                                className={`shrink-0 text-[0.7rem] font-bold px-3 py-1.5 rounded-lg transition-all duration-200 ease-in-out cursor-pointer ${
                                                    isConfirmed
                                                        ? 'bg-[#008080] text-white'
                                                        : 'bg-[#e6fbfb] text-[#008080] hover:bg-[#00ffff]/25'
                                                }`}
                                            >
                                                {isConfirmed ? (
                                                    <span className="inline-flex items-center gap-1"><Check size={12} /> Confirmed</span>
                                                ) : 'Confirm'}
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                            <button type="button" className="w-full text-xs font-semibold text-[#008080] inline-flex items-center justify-center gap-1 py-2 rounded-lg hover:bg-[#e6fbfb] transition-colors duration-200 cursor-pointer">
                                View full schedule <ChevronRight size={13} />
                            </button>
                        </div>
                    )}

                    {tab === 'prescriptions' && (
                        <div className="animate-fade-in space-y-3">
                            {rx.map((m) => {
                                const low = m.left <= 3;
                                const isRefilling = refilling === m.id;
                                return (
                                    <div key={m.id} className="rounded-xl border border-[#b2f0f0] bg-white p-3.5 transition-all duration-200 ease-in-out hover:border-[#00d4d4] hover:shadow-md">
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="flex items-center gap-2.5 min-w-0">
                                                <span className="size-8 rounded-lg bg-[#e6fbfb] text-[#008080] flex items-center justify-center shrink-0">
                                                    <Pill size={15} />
                                                </span>
                                                <div className="min-w-0">
                                                    <p className="text-sm font-semibold text-[#012626] truncate">{m.name}</p>
                                                    <p className="text-[0.7rem] text-[#475569] truncate">{m.schedule}</p>
                                                </div>
                                            </div>
                                            <div className="text-right shrink-0">
                                                <p className={`text-[0.7rem] font-bold ${low ? 'text-rose-600' : 'text-[#008080]'}`}>
                                                    {m.left} left
                                                </p>
                                                <button
                                                    type="button"
                                                    onClick={() => requestRefill(m.id)}
                                                    disabled={isRefilling || m.refilled}
                                                    className={`mt-1 text-[0.65rem] font-bold px-2.5 py-1 rounded-md transition-all duration-200 ease-in-out cursor-pointer disabled:cursor-default ${
                                                        m.refilled
                                                            ? 'bg-[#008080] text-white'
                                                            : 'bg-[#e6fbfb] text-[#008080] hover:bg-[#00ffff]/25'
                                                    }`}
                                                >
                                                    {isRefilling ? (
                                                        <span className="inline-flex items-center gap-1"><RefreshCw size={11} className="animate-spin" /> Sending</span>
                                                    ) : m.refilled ? (
                                                        <span className="inline-flex items-center gap-1"><Check size={11} /> Requested</span>
                                                    ) : 'Refill'}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
