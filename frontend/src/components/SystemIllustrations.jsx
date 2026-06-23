import React from 'react';
import {
    Stethoscope, Bed, TestTube, Pill, Smartphone, Bell, CheckCircle2,
    Activity, Clock, AlertCircle, ArrowRight,
} from 'lucide-react';

/*
   SystemIllustrations — faithful, scaled-down recreations of real MediFleet
   surfaces, built from the same palette and utility classes the live app
   uses (card / badge / brand-gradient). They are static, non-interactive
   previews so a visitor sees what the workspace actually looks like before
   they ever sign in. Shared by the Landing product-preview section and the
   Demo page chapter rail so both stay visually identical.

   Each mock is a self-contained function so a page can drop in just the one
   it needs, or render the full set via <SystemMockGrid />.
*/

/* Static mock data — hoisted to module scope so it is built once, not
   rebuilt on every render (which would break memoized children). */
const QUEUE_ROWS = [
    { name: 'A. Mwangi', op: 'OP-2026-0142', wait: '4 min', tone: 'rose', tag: 'Urgent' },
    { name: 'J. Otieno', op: 'OP-2026-0138', wait: '11 min', tone: 'amber', tag: 'Waiting' },
    { name: 'F. Wanjiru', op: 'OP-2026-0131', wait: '18 min', tone: 'teal', tag: 'In room' },
];

const WARD_BEDS = ['busy', 'busy', 'free', 'busy', 'clean', 'free', 'busy', 'busy', 'free', 'busy', 'busy', 'clean'];
const WARD_CLS = {
    busy:  'bg-brand-500/90 text-white',
    free:  'bg-accent-50 text-accent-700 ring-1 ring-inset ring-accent-200',
    clean: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
};
const WARD_LABEL = { busy: 'Occupied', free: 'Available', clean: 'Cleaning' };

const LAB_TESTS = [
    { name: 'Haemoglobin', value: '13.8', unit: 'g/dL', flag: 'normal' },
    { name: 'White cell count', value: '11.4', unit: '10⁹/L', flag: 'high' },
    { name: 'Platelets', value: '248', unit: '10⁹/L', flag: 'normal' },
    { name: 'Potassium', value: '2.9', unit: 'mmol/L', flag: 'low' },
];
const LAB_FLAG_CLS = {
    normal: 'text-accent-700 bg-accent-50 ring-accent-100',
    high:   'text-rose-700 bg-rose-50 ring-rose-100',
    low:    'text-amber-700 bg-amber-50 ring-amber-100',
};
const LAB_FLAG_TEXT = { normal: 'In range', high: 'High', low: 'Low' };

const PHARMACY_ITEMS = [
    { drug: 'Amoxicillin 500mg', qty: '21 caps', batch: 'B-7741' },
    { drug: 'Paracetamol 1g', qty: '10 tabs', batch: 'B-5520' },
    { drug: 'ORS sachets', qty: '6 units', batch: 'B-9013' },
];

const NOTIFICATIONS = [
    { tone: 'rose', text: 'Critical value flagged on FBC for OP-2026-0142', ago: 'just now', icon: AlertCircle },
    { tone: 'accent', text: 'Discharge approved for bed 4, maternity', ago: '6m ago', icon: CheckCircle2 },
    { tone: 'brand', text: 'Low stock: Amoxicillin 500mg below reorder level', ago: '22m ago', icon: Bell },
];
const NOTIFICATION_TONE_CLS = { rose: 'text-rose-600', accent: 'text-accent-600', brand: 'text-brand-600' };

function Frame({ title, badge, badgeTone = 'brand', children }) {
    const tone =
        badgeTone === 'accent' ? 'bg-accent-50 text-accent-700 ring-accent-100'
      : badgeTone === 'teal'   ? 'bg-teal-50 text-teal-700 ring-teal-100'
      : badgeTone === 'amber'  ? 'bg-amber-50 text-amber-700 ring-amber-100'
                               : 'bg-brand-50 text-brand-700 ring-brand-100';
    return (
        <div className="relative bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            <div className="px-4 py-2.5 border-b border-ink-200/70 bg-ink-50/60 flex items-center justify-between">
                <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">{title}</span>
                {badge && (
                    <span className={`text-2xs font-semibold uppercase tracking-[0.1em] px-2 py-0.5 rounded-md ring-1 ring-inset ${tone}`}>
                        {badge}
                    </span>
                )}
            </div>
            <div className="p-4">{children}</div>
        </div>
    );
}

/* Clinical desk waiting queue */
export function ClinicalQueueMock() {
    return (
        <Frame title="Clinical desk" badge="Live queue" badgeTone="brand">
            <div className="flex items-center gap-2 mb-3">
                <span className="size-8 rounded-lg bg-brand-50 ring-1 ring-brand-100 text-brand-700 flex items-center justify-center">
                    <Stethoscope size={16} />
                </span>
                <div>
                    <p className="text-sm font-semibold text-ink-900 leading-none">12 patients waiting</p>
                    <p className="text-2xs text-ink-500 mt-1">Average wait 9 minutes</p>
                </div>
            </div>
            <ul className="space-y-1.5">
                {QUEUE_ROWS.map((r) => {
                    const dot = r.tone === 'rose' ? 'bg-rose-500' : r.tone === 'amber' ? 'bg-amber-500' : 'bg-teal-500';
                    return (
                        <li key={r.op} className="flex items-center justify-between p-2 rounded-lg bg-ink-50/70 border border-ink-100">
                            <div className="flex items-center gap-2 min-w-0">
                                <span className={`size-2 rounded-full ${dot}`} />
                                <span className="text-xs font-medium text-ink-800 truncate">{r.name}</span>
                                <span className="text-2xs text-ink-400 font-mono hidden sm:inline">{r.op}</span>
                            </div>
                            <span className="text-2xs font-semibold text-ink-500 inline-flex items-center gap-1 shrink-0">
                                <Clock size={11} /> {r.wait}
                            </span>
                        </li>
                    );
                })}
            </ul>
        </Frame>
    );
}

/* Wards bed map */
export function WardMapMock() {
    return (
        <Frame title="Wards" badge="Bed map" badgeTone="teal">
            <div className="flex items-center gap-2 mb-3">
                <span className="size-8 rounded-lg bg-teal-50 ring-1 ring-teal-100 text-teal-700 flex items-center justify-center">
                    <Bed size={16} />
                </span>
                <div>
                    <p className="text-sm font-semibold text-ink-900 leading-none">Maternity wing</p>
                    <p className="text-2xs text-ink-500 mt-1">8 occupied, 3 available, 1 cleaning</p>
                </div>
            </div>
            <div className="grid grid-cols-6 gap-1.5">
                {WARD_BEDS.map((b, i) => (
                    <div key={`bed-${i + 1}`} className={`aspect-square rounded-md flex items-center justify-center text-2xs font-bold ${WARD_CLS[b]}`}>
                        {i + 1}
                    </div>
                ))}
            </div>
            <div className="mt-3 flex items-center gap-3 text-2xs text-ink-500">
                {Object.entries(WARD_LABEL).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1">
                        <span className={`size-2 rounded-sm ${k === 'busy' ? 'bg-brand-500' : k === 'free' ? 'bg-accent-300' : 'bg-amber-300'}`} />
                        {v}
                    </span>
                ))}
            </div>
        </Frame>
    );
}

/* Lab results with reference ranges */
export function LabResultsMock() {
    return (
        <Frame title="Laboratory" badge="Result entry" badgeTone="accent">
            <div className="flex items-center gap-2 mb-3">
                <span className="size-8 rounded-lg bg-accent-50 ring-1 ring-accent-100 text-accent-700 flex items-center justify-center">
                    <TestTube size={16} />
                </span>
                <div>
                    <p className="text-sm font-semibold text-ink-900 leading-none">Full blood count</p>
                    <p className="text-2xs text-ink-500 mt-1 font-mono">SPEC-2026-00481</p>
                </div>
            </div>
            <ul className="space-y-1.5">
                {LAB_TESTS.map((t) => (
                    <li key={t.name} className="flex items-center justify-between text-xs">
                        <span className="text-ink-700 truncate">{t.name}</span>
                        <span className="flex items-center gap-2 shrink-0">
                            <span className="font-semibold text-ink-900 tabular-nums">{t.value}<span className="text-ink-400 font-normal ml-0.5">{t.unit}</span></span>
                            <span className={`text-2xs font-semibold px-1.5 py-0.5 rounded ring-1 ring-inset ${LAB_FLAG_CLS[t.flag]}`}>{LAB_FLAG_TEXT[t.flag]}</span>
                        </span>
                    </li>
                ))}
            </ul>
        </Frame>
    );
}

/* Pharmacy dispense ticket */
export function PharmacyMock() {
    return (
        <Frame title="Pharmacy" badge="Dispense" badgeTone="accent">
            <div className="flex items-center gap-2 mb-3">
                <span className="size-8 rounded-lg bg-accent-50 ring-1 ring-accent-100 text-accent-700 flex items-center justify-center">
                    <Pill size={16} />
                </span>
                <div>
                    <p className="text-sm font-semibold text-ink-900 leading-none">Prescription RX-2026-0337</p>
                    <p className="text-2xs text-ink-500 mt-1">Stock checked, batches reserved</p>
                </div>
            </div>
            <ul className="space-y-1.5">
                {PHARMACY_ITEMS.map((i) => (
                    <li key={i.drug} className="flex items-center justify-between p-2 rounded-lg bg-ink-50/70 border border-ink-100">
                        <div className="min-w-0">
                            <p className="text-xs font-medium text-ink-800 truncate">{i.drug}</p>
                            <p className="text-2xs text-ink-400 font-mono">{i.batch}</p>
                        </div>
                        <span className="text-2xs font-semibold text-ink-600 shrink-0">{i.qty}</span>
                    </li>
                ))}
            </ul>
            <div className="mt-3 flex items-center justify-between rounded-lg bg-accent-50 ring-1 ring-accent-100 px-3 py-2">
                <span className="text-xs font-semibold text-accent-700 inline-flex items-center gap-1.5">
                    <CheckCircle2 size={13} /> Ready to dispense
                </span>
                <span className="text-xs font-semibold text-accent-700">KES 1,240</span>
            </div>
        </Frame>
    );
}

/* Billing with M-Pesa STK */
export function BillingMock() {
    return (
        <Frame title="Billing" badge="M-Pesa STK" badgeTone="brand">
            <div className="flex items-center gap-2 mb-3">
                <span className="size-8 rounded-lg bg-brand-50 ring-1 ring-brand-100 text-brand-700 flex items-center justify-center">
                    <Smartphone size={16} />
                </span>
                <div>
                    <p className="text-sm font-semibold text-ink-900 leading-none">Invoice INV-2026-1190</p>
                    <p className="text-2xs text-ink-500 mt-1">Consultation, lab, pharmacy</p>
                </div>
            </div>
            <div className="rounded-xl bg-gradient-to-br from-brand-50 via-teal-50 to-accent-50 ring-1 ring-ink-100 p-3">
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500">Balance due</p>
                <p className="text-2xl font-semibold text-ink-900 tabular-nums mt-0.5">KES 3,450</p>
                <div className="mt-2 flex items-center gap-2 text-2xs font-semibold text-brand-700">
                    <Activity size={12} className="animate-pulse-soft" /> STK push sent to 0712 *** 458
                </div>
            </div>
            <div className="mt-2.5 flex items-center justify-between text-2xs text-ink-500">
                <span>Awaiting confirmation</span>
                <span className="inline-flex items-center gap-1 font-semibold text-ink-600">Receipt auto-posts to GL <ArrowRight size={11} /></span>
            </div>
        </Frame>
    );
}

/* Notification stack */
export function NotificationsMock() {
    return (
        <Frame title="Notifications" badge="Real-time" badgeTone="amber">
            <ul className="space-y-2.5">
                {NOTIFICATIONS.map((n) => {
                    const Icon = n.icon;
                    return (
                        <li key={n.text} className="flex items-start gap-2">
                            <span className={`mt-0.5 shrink-0 ${NOTIFICATION_TONE_CLS[n.tone]}`}><Icon size={14} /></span>
                            <div className="min-w-0">
                                <p className="text-xs text-ink-800 leading-snug">{n.text}</p>
                                <p className="text-2xs text-ink-400 mt-0.5">{n.ago}</p>
                            </div>
                        </li>
                    );
                })}
            </ul>
        </Frame>
    );
}

const ALL = [ClinicalQueueMock, WardMapMock, LabResultsMock, PharmacyMock, BillingMock, NotificationsMock];

/* Convenience grid used by the Landing product-preview section. */
export function SystemMockGrid({ className = '' }) {
    return (
        <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 ${className}`}>
            {ALL.map((Mock, i) => (
                <div key={Mock.name} className="animate-slide-up" style={{ animationDelay: `${i * 70}ms`, animationFillMode: 'both' }}>
                    <Mock />
                </div>
            ))}
        </div>
    );
}

export default SystemMockGrid;
