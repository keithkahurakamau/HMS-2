import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
    ArrowRight, ShieldCheck, Stethoscope, HeartPulse, Lock, Activity,
    Users, Building2, Sparkles, CheckCircle2, ChevronRight, BarChart3,
    Pill, TestTube, Bed, Receipt, MessageSquare, Globe2, Workflow,
} from 'lucide-react';
import Logo from '../components/Logo';

export default function Landing() {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen bg-ink-50 text-ink-900 font-sans">
            {/* ============== Floating navbar ============== */}
            <header className="fixed top-4 inset-x-4 z-50">
                <div className="max-w-7xl mx-auto bg-white/85 backdrop-blur-xl border border-ink-200/70 rounded-2xl shadow-soft px-4 sm:px-6 py-3 flex items-center justify-between">
                    <Link to="/" className="flex items-center cursor-pointer" aria-label="MediFleet home">
                        <Logo variant="full" size={32} label="MediFleet" />
                    </Link>
                    <nav className="hidden md:flex items-center gap-1">
                        <a href="#features" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors">Features</a>
                        <a href="#modules" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors">Modules</a>
                        <a href="#how" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors">How it works</a>
                        <a href="#trust" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors">Compliance</a>
                    </nav>
                    <div className="flex items-center gap-2">
                        <Link to="/portal" className="hidden sm:inline-flex btn-secondary text-xs cursor-pointer">
                            Find your hospital
                        </Link>
                        <button onClick={() => navigate('/portal')} className="btn-primary text-xs cursor-pointer">
                            Sign in <ArrowRight size={14} />
                        </button>
                    </div>
                </div>
            </header>

            {/* ============== Hero ============== */}
            <section className="relative pt-36 pb-20 sm:pt-44 sm:pb-28 overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute inset-0 bg-aurora" />
                    <div className="absolute inset-0 bg-grid-faint bg-grid-faint opacity-50" />
                    <div className="absolute -top-32 -right-24 w-[40rem] h-[40rem] bg-brand-300/20 rounded-full blur-[120px]" />
                    <div className="absolute -bottom-40 -left-24 w-[36rem] h-[36rem] bg-accent-300/20 rounded-full blur-[120px]" />
                </div>

                <div className="relative max-w-7xl mx-auto px-6 grid lg:grid-cols-12 gap-10 items-center">
                    <div className="lg:col-span-7 animate-slide-up">
                        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/80 ring-1 ring-brand-200 text-2xs font-semibold uppercase tracking-[0.16em] text-brand-700">
                            <Sparkles size={12} className="text-teal-500" />
                            Multi-tenant clinical cloud · est. 2024
                        </span>
                        <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tightest leading-[1.05]">
                            Care that{' '}
                            <span className="text-gradient-brand">flows</span>{' '}
                            across every shift, ward, and clinic.
                        </h1>
                        <p className="mt-6 text-lg text-ink-600 leading-relaxed max-w-xl">
                            MediFleet unifies registration, clinical desk, pharmacy, lab, radiology,
                            wards, and billing into one secure workspace — so your team spends time
                            on patients, not paperwork.
                        </p>
                        <div className="mt-8 flex flex-wrap items-center gap-3">
                            <button onClick={() => navigate('/portal')} className="btn-primary text-base px-5 py-3 cursor-pointer group">
                                Open your hospital
                                <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
                            </button>
                            <button onClick={() => navigate('/portal?next=/patient')} className="btn-secondary text-base px-5 py-3 cursor-pointer">
                                <HeartPulse size={16} /> Patient portal
                            </button>
                            <Link to="/superadmin/login" className="text-sm font-semibold text-ink-500 hover:text-brand-700 transition-colors px-3 py-3 cursor-pointer">
                                Platform console &rarr;
                            </Link>
                        </div>
                        <div className="mt-10 flex items-center gap-6 text-xs text-ink-500">
                            <Trust icon={<Lock size={14} className="text-brand-600" />} label="HttpOnly JWT · CSRF" />
                            <Trust icon={<ShieldCheck size={14} className="text-teal-600" />} label="KDPA aligned" />
                            <Trust icon={<Globe2 size={14} className="text-accent-600" />} label="Database per tenant" />
                        </div>
                    </div>

                    {/* ── Hero composition ── */}
                    <div className="lg:col-span-5 relative">
                        <HeroComposition />
                    </div>
                </div>
            </section>

            {/* ============== Stat strip ============== */}
            <section className="relative">
                <div className="max-w-7xl mx-auto px-6 -mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Modules" value="14+" hint="Clinical, ops & finance" />
                    <Stat label="Tenant isolation" value="100%" hint="Per-DB separation" />
                    <Stat label="Auth lockout" value="5 / 15m" hint="Brute-force aware" />
                    <Stat label="Audit retention" value="∞" hint="Append-only by design" />
                </div>
            </section>

            {/* ============== Features ============== */}
            <section id="features" className="py-24">
                <div className="max-w-7xl mx-auto px-6">
                    <SectionHeader
                        eyebrow="What you get"
                        title="A clinical workspace that respects every role"
                        subtitle="Every module is built on the same audit, RBAC, and tenant-isolation primitives, so you don't trade safety for speed."
                    />
                    <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                        <FeatureCard
                            tone="brand" icon={<Stethoscope size={20} />}
                            title="Clinical desk"
                            body="Encounters, vitals, prescriptions, referrals — captured in one continuous flow with consent gates baked in."
                        />
                        <FeatureCard
                            tone="teal" icon={<TestTube size={20} />}
                            title="Lab & radiology"
                            body="Order, collect, result, and report — with traceable specimen IDs and sample lifecycle tracking."
                        />
                        <FeatureCard
                            tone="accent" icon={<Pill size={20} />}
                            title="Pharmacy & inventory"
                            body="Stock-aware dispensing, batch & expiry tracking, low-stock alerts that ping the right team automatically."
                        />
                        <FeatureCard
                            tone="brand" icon={<Bed size={20} />}
                            title="Wards & admissions"
                            body="Real-time bed map, admission/discharge orchestration, and per-shift handover notes."
                        />
                        <FeatureCard
                            tone="teal" icon={<Receipt size={20} />}
                            title="Billing & cheques"
                            body="Encounter-grained invoicing, M-Pesa STK push, and a full cheque register with lifecycle states."
                        />
                        <FeatureCard
                            tone="accent" icon={<MessageSquare size={20} />}
                            title="Internal messaging"
                            body="Real-time WebSocket fan-out across departments — escalate, ping, and resolve without leaving the app."
                        />
                    </div>
                </div>
            </section>

            {/* ============== Modules grid ============== */}
            <section id="modules" className="py-24 bg-gradient-to-b from-white to-brand-50/40">
                <div className="max-w-7xl mx-auto px-6">
                    <SectionHeader
                        eyebrow="Modules"
                        title="One workspace, every department"
                        subtitle="Pick the modules each role needs and lock them down with permission-driven access."
                    />
                    <div className="mt-12 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                        {[
                            ['Patient registry', Users, 'brand'],
                            ['Medical history', Activity, 'teal'],
                            ['Clinical desk', Stethoscope, 'accent'],
                            ['Laboratory', TestTube, 'brand'],
                            ['Radiology', Workflow, 'teal'],
                            ['Pharmacy', Pill, 'accent'],
                            ['Wards', Bed, 'brand'],
                            ['Appointments', BarChart3, 'teal'],
                            ['Billing', Receipt, 'accent'],
                            ['Messages', MessageSquare, 'brand'],
                        ].map(([name, Icon, tone]) => (
                            <div key={name} className="group bg-white border border-ink-200/70 rounded-2xl px-4 py-5 shadow-soft hover:shadow-elevated hover:border-brand-200 transition-all cursor-pointer">
                                <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${
                                    tone === 'brand' ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-100'
                                  : tone === 'teal'  ? 'bg-teal-50 text-teal-700 ring-1 ring-teal-100'
                                                     : 'bg-accent-50 text-accent-700 ring-1 ring-accent-100'
                                }`}>
                                    <Icon size={18} />
                                </div>
                                <p className="text-sm font-semibold text-ink-900 group-hover:text-brand-700 transition-colors">{name}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ============== How it works ============== */}
            <section id="how" className="py-24">
                <div className="max-w-7xl mx-auto px-6">
                    <SectionHeader
                        eyebrow="How it works"
                        title="From sign-up to first encounter in minutes"
                        subtitle="The platform team provisions your hospital, then your Admin invites the team and starts seeing patients the same day."
                    />
                    <div className="mt-12 grid md:grid-cols-3 gap-5">
                        <Step n={1} title="Provision your hospital">
                            The MediFleet platform team spins up a dedicated database, applies the schema, seeds RBAC roles, and creates your Admin account.
                        </Step>
                        <Step n={2} title="Brand your workspace">
                            Upload your logo, set a background image for your sign-in screen, pick brand colours, and choose how printed documents look.
                        </Step>
                        <Step n={3} title="Invite your team">
                            Add staff, assign roles, and grant permission overrides as needed. Every action is audit-logged from the first minute.
                        </Step>
                    </div>
                </div>
            </section>

            {/* ============== Trust / Compliance ============== */}
            <section id="trust" className="py-24 bg-gradient-to-b from-brand-50/40 to-white">
                <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <span className="section-eyebrow">Compliance</span>
                        <h2 className="mt-2 text-3xl sm:text-4xl font-semibold tracking-tight">
                            Built for clinical environments — not retrofitted into one.
                        </h2>
                        <p className="mt-4 text-ink-600 leading-relaxed">
                            Every endpoint enforces tenant isolation at the JWT layer.
                            Every clinical write goes through a consent gate. Every audit
                            row is append-only by trigger — even with database superuser access.
                        </p>
                        <ul className="mt-6 space-y-3">
                            <Bullet>KDPA Section 26 — append-only access logs</Bullet>
                            <Bullet>KDPA Section 30 — consent-gated clinical writes</Bullet>
                            <Bullet>KDPA Section 40 — subject erasure endpoint</Bullet>
                            <Bullet>KDPA Section 43 — 72-hour breach countdown</Bullet>
                            <Bullet>HttpOnly JWT cookies, CSRF double-submit, refresh-token reuse detection</Bullet>
                        </ul>
                    </div>
                    <div>
                        <ComplianceCard />
                    </div>
                </div>
            </section>

            {/* ============== CTA ============== */}
            <section className="py-24">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="relative overflow-hidden rounded-3xl bg-brand-gradient p-10 sm:p-16 shadow-elevated">
                        <div className="absolute inset-0 bg-aurora opacity-60 pointer-events-none" />
                        <div className="absolute -top-24 -right-24 w-96 h-96 rounded-full bg-white/10 blur-3xl pointer-events-none" />
                        <div className="relative flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
                            <div>
                                <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white max-w-xl">
                                    Ready to run a calmer hospital?
                                </h2>
                                <p className="mt-3 text-white/80 max-w-lg">
                                    Sign in to your tenant or talk to the platform team about provisioning a new workspace.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-3">
                                <button onClick={() => navigate('/portal')} className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-white text-brand-700 font-semibold text-sm hover:bg-ink-50 transition-all shadow-soft cursor-pointer">
                                    Open your hospital <ArrowRight size={16} />
                                </button>
                                <Link to="/superadmin/login" className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-white/10 text-white font-semibold text-sm ring-1 ring-white/20 hover:bg-white/15 transition-all cursor-pointer">
                                    Platform console
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ============== Footer ============== */}
            <footer className="border-t border-ink-200/70 bg-white/60 backdrop-blur-md">
                <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <Logo variant="full" size={28} />
                    </div>
                    <p className="text-xs text-ink-500 uppercase tracking-[0.18em]">
                        &copy; {new Date().getFullYear()} MediFleet — Clinical-grade workspace
                    </p>
                    <div className="flex items-center gap-4 text-xs text-ink-500">
                        <Link to="/portal" className="hover:text-brand-700 transition-colors">Sign in</Link>
                        <Link to="/portal?next=/patient" className="hover:text-brand-700 transition-colors">Patient portal</Link>
                        <Link to="/superadmin/login" className="hover:text-brand-700 transition-colors">Platform</Link>
                    </div>
                </div>
            </footer>
        </div>
    );
}

/* ─────────────────────────────────────────────────────────────────────────── */
/*  Sub-components                                                             */
/* ─────────────────────────────────────────────────────────────────────────── */

function Trust({ icon, label }) {
    return (
        <span className="inline-flex items-center gap-2 font-medium text-ink-600">
            {icon}{label}
        </span>
    );
}

function Stat({ label, value, hint }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl p-5 shadow-soft">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-ink-900">{value}</p>
            <p className="mt-1 text-xs text-ink-500">{hint}</p>
        </div>
    );
}

function SectionHeader({ eyebrow, title, subtitle }) {
    return (
        <div className="max-w-2xl mx-auto text-center">
            <span className="section-eyebrow">{eyebrow}</span>
            <h2 className="mt-2 text-3xl sm:text-4xl font-semibold tracking-tight text-ink-900">{title}</h2>
            <p className="mt-3 text-ink-600 leading-relaxed">{subtitle}</p>
        </div>
    );
}

function FeatureCard({ tone, icon, title, body }) {
    const ring =
        tone === 'brand' ? 'bg-brand-50 text-brand-700 ring-brand-100'
      : tone === 'teal'  ? 'bg-teal-50 text-teal-700 ring-teal-100'
                         : 'bg-accent-50 text-accent-700 ring-accent-100';
    return (
        <div className="group bg-white border border-ink-200/70 rounded-2xl p-6 shadow-soft hover:shadow-elevated hover:border-brand-200 transition-all">
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ring-1 ring-inset ${ring}`}>
                {icon}
            </div>
            <h3 className="text-lg font-semibold tracking-tight text-ink-900">{title}</h3>
            <p className="mt-2 text-sm text-ink-600 leading-relaxed">{body}</p>
            <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 opacity-0 group-hover:opacity-100 transition-opacity">
                Explore <ChevronRight size={12} />
            </div>
        </div>
    );
}

function Step({ n, title, children }) {
    return (
        <div className="relative bg-white border border-ink-200/70 rounded-2xl p-6 shadow-soft">
            <div className="w-9 h-9 rounded-xl bg-brand-gradient flex items-center justify-center text-white font-semibold shadow-glow">
                {n}
            </div>
            <h3 className="mt-4 text-lg font-semibold tracking-tight text-ink-900">{title}</h3>
            <p className="mt-2 text-sm text-ink-600 leading-relaxed">{children}</p>
        </div>
    );
}

function Bullet({ children }) {
    return (
        <li className="flex items-start gap-2 text-sm text-ink-700">
            <CheckCircle2 size={16} className="text-accent-600 shrink-0 mt-0.5" />
            <span>{children}</span>
        </li>
    );
}

function HeroComposition() {
    return (
        <div className="relative">
            {/* Gradient frame */}
            <div className="absolute -inset-4 bg-brand-gradient rounded-3xl opacity-30 blur-2xl" />
            <div className="relative bg-white border border-ink-200/70 rounded-3xl shadow-elevated overflow-hidden">
                {/* Mock header */}
                <div className="px-5 py-3 border-b border-ink-200/70 bg-ink-50/60 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                        <span className="w-2.5 h-2.5 rounded-full bg-accent-400" />
                    </div>
                    <span className="text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em]">Workspace · Clinical</span>
                </div>
                {/* Mock body */}
                <div className="p-6 space-y-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-2xs uppercase tracking-[0.14em] text-ink-500 font-semibold">Today's encounters</p>
                            <p className="mt-1 text-3xl font-semibold tracking-tight text-ink-900">42 <span className="text-base font-normal text-ink-500">patients</span></p>
                        </div>
                        <span className="badge-success">+18% vs avg</span>
                    </div>
                    {/* Tiny chart */}
                    <div className="h-24 rounded-xl bg-gradient-to-br from-brand-50 via-teal-50 to-accent-50 ring-1 ring-ink-100 relative overflow-hidden">
                        <svg viewBox="0 0 200 80" className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
                            <defs>
                                <linearGradient id="hero-line" x1="0" y1="0" x2="200" y2="0" gradientUnits="userSpaceOnUse">
                                    <stop offset="0%" stopColor="#22d3ee" />
                                    <stop offset="50%" stopColor="#14b8a6" />
                                    <stop offset="100%" stopColor="#10b981" />
                                </linearGradient>
                                <linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="80">
                                    <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.25" />
                                    <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                                </linearGradient>
                            </defs>
                            <path d="M0 60 Q 25 50, 40 45 T 80 35 T 120 28 T 160 18 T 200 12 L 200 80 L 0 80 Z" fill="url(#hero-fill)" />
                            <path d="M0 60 Q 25 50, 40 45 T 80 35 T 120 28 T 160 18 T 200 12" stroke="url(#hero-line)" strokeWidth="2.5" fill="none" />
                        </svg>
                    </div>
                    {/* Quick rows */}
                    <div className="space-y-2">
                        <Row label="Clinical desk" tone="brand" right="12 active" />
                        <Row label="Pharmacy queue" tone="teal" right="7 ready" />
                        <Row label="Lab orders" tone="accent" right="3 awaiting" />
                    </div>
                </div>
            </div>
            {/* Floating badge */}
            <div className="hidden lg:flex absolute -bottom-6 -left-6 bg-white border border-ink-200/70 rounded-2xl px-4 py-3 shadow-elevated items-center gap-3 animate-float">
                <div className="w-9 h-9 rounded-xl bg-accent-100 text-accent-700 flex items-center justify-center">
                    <ShieldCheck size={18} />
                </div>
                <div>
                    <p className="text-xs font-semibold text-ink-900">All systems operational</p>
                    <p className="text-2xs text-ink-500">Last check 12s ago</p>
                </div>
            </div>
        </div>
    );
}

function Row({ label, right, tone }) {
    const dot =
        tone === 'brand' ? 'bg-brand-500'
      : tone === 'teal'  ? 'bg-teal-500'
                         : 'bg-accent-500';
    return (
        <div className="flex items-center justify-between p-3 rounded-xl bg-ink-50/60 border border-ink-100">
            <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${dot}`} />
                <span className="text-sm font-medium text-ink-700">{label}</span>
            </div>
            <span className="text-2xs font-semibold text-ink-500 uppercase tracking-wider">{right}</span>
        </div>
    );
}

function ComplianceCard() {
    return (
        <div className="relative bg-white border border-ink-200/70 rounded-3xl shadow-elevated overflow-hidden">
            <div className="absolute inset-0 bg-aurora opacity-50 pointer-events-none" />
            <div className="relative p-8 space-y-5">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-2xl bg-brand-gradient flex items-center justify-center shadow-glow">
                        <Lock size={20} className="text-white" />
                    </div>
                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Security posture</p>
                        <p className="text-base font-semibold text-ink-900 mt-0.5">Defense in depth</p>
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    {[
                        ['Append-only audit', '100%'],
                        ['Tenant isolation', 'Per-DB'],
                        ['Token TTL', '15 min'],
                        ['Refresh rotation', 'On use'],
                        ['Failed-login lockout', '5 / 15m'],
                        ['PII encryption', 'AES-128'],
                    ].map(([label, value]) => (
                        <div key={label} className="p-3 rounded-xl bg-white ring-1 ring-ink-200/70">
                            <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500">{label}</p>
                            <p className="mt-1 text-sm font-semibold text-ink-900">{value}</p>
                        </div>
                    ))}
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-accent-50 ring-1 ring-accent-100">
                    <div className="flex items-center gap-2 text-sm font-semibold text-accent-700">
                        <CheckCircle2 size={16} /> KDPA aligned
                    </div>
                    <span className="text-2xs font-semibold uppercase tracking-wider text-accent-700">Verified</span>
                </div>
            </div>
        </div>
    );
}
