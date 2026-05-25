import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
    ArrowRight, ShieldCheck, Stethoscope, HeartPulse, Lock, Activity,
    Users, Building2, Sparkles, CheckCircle2, ChevronRight, BarChart3,
    Pill, TestTube, Bed, Receipt, MessageSquare, Globe2, Workflow,
    // module-grid additions
    Calendar, ClipboardList, ScanLine, Package, BookOpen, BadgeCheck,
    Smartphone, Bell, Share2, LayoutDashboard, Settings as SettingsIcon,
    Palette, LifeBuoy, KeyRound, UserCog, FileSearch,
} from 'lucide-react';
import Logo from '../components/Logo';
import CountUp from '../components/CountUp';
import ContactStrip from '../components/ContactStrip';
import Reveal from '../components/Reveal';
import PremiumBackground from '../components/PremiumBackground';

export default function Landing() {
    const navigate = useNavigate();

    return (
        <div className="relative min-h-screen bg-ink-50 text-ink-900 font-sans">
            {/* Premium reactive background — parallax gradient blobs that
                follow the cursor + a spotlight disc that tracks 1:1. See
                PremiumBackground.jsx for the rAF lerp mechanics. */}
            <PremiumBackground />
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
                    <div className="absolute -top-32 -right-24 w-[40rem] h-[40rem] bg-brand-300/20 rounded-full blur-[120px] animate-blob-breathe" />
                    <div className="absolute -bottom-40 -left-24 w-[36rem] h-[36rem] bg-accent-300/20 rounded-full blur-[120px] animate-blob-breathe" style={{ animationDelay: '5s' }} />
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

            {/* ============== Stat strip (animated on scroll into view) ============== */}
            <section className="relative">
                <div className="max-w-7xl mx-auto px-6 -mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Modules" value={<CountUp to={25} suffix="" />} hint="Clinical, ops & finance" />
                    <Stat label="Tenant isolation" value={<CountUp to={100} suffix="%" />} hint="Per-DB separation" />
                    <Stat label="Permission codes" value={<CountUp to={40} suffix="+" />} hint="Fine-grained RBAC" />
                    <Stat label="Audit retention" value="∞" hint="Append-only by design" />
                </div>
            </section>

            {/* ============== Features ============== */}
            <section id="features" className="py-24">
                <Reveal className="max-w-7xl mx-auto px-6">
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
                </Reveal>
            </section>

            {/* ============== Modules showcase (interactive) ============== */}
            <section id="modules" className="py-24 bg-gradient-to-b from-white via-brand-50/30 to-white relative overflow-hidden">
                {/* Decorative blurred orbs */}
                <div className="absolute -top-24 -left-32 w-[28rem] h-[28rem] bg-brand-300/10 rounded-full blur-[120px] pointer-events-none" />
                <div className="absolute -bottom-32 -right-32 w-[26rem] h-[26rem] bg-accent-300/10 rounded-full blur-[120px] pointer-events-none" />

                <Reveal className="relative max-w-7xl mx-auto px-6">
                    <SectionHeader
                        eyebrow="Modules"
                        title="Twenty-five modules, one ledger of truth"
                        subtitle="Every module is gated by per-role permissions, audit-logged, and tenant-isolated. Switch them on à-la-carte — the 9 always-on modules below are bundled in the base subscription."
                    />
                    <ModuleShowcase navigate={navigate} />
                </Reveal>
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

            {/* ============== Contact strip ============== */}
            <ContactStrip heading="Talk to a human" />

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


/* ──────────────────────────────────────────────────────────────────────────
   ModuleShowcase — interactive tabbed browser for all 25 platform modules.

   Groups the modules by clinical workflow so a visitor scanning the page
   can map "department" → "what does it actually do." Each card has a
   hover-reveal that exposes the three headline features for that module.

   Always-on modules carry a green "Included" badge; à-la-carte modules
   carry an amber "Add-on" badge — same visual taxonomy as the superadmin
   Modules dashboard, so what visitors see here matches what they'll buy.
   ────────────────────────────────────────────────────────────────────── */

const MODULE_GROUPS = [
    {
        key: 'clinical',
        label: 'Clinical Workflow',
        tagline: 'Front-desk to follow-up — one continuous chart.',
        modules: [
            { name: 'Patient Registry', icon: Users, alwaysOn: true,
              desc: 'KDPA-compliant patient onboarding with auto-generated outpatient numbers and treatment-consent capture at first contact.',
              bullets: ['Single search across name, OP#, ID, phone', 'Consent capture inline at registration', 'Soft-delete + audit trail'] },
            { name: 'Appointments', icon: Calendar, alwaysOn: true,
              desc: 'Doctor schedules, slot availability, and automated reminders that respect each provider\'s working hours.',
              bullets: ['Per-doctor calendar', 'Slot-availability lookup', 'SMS/email reminders'] },
            { name: 'Clinical Desk', icon: Stethoscope, alwaysOn: false,
              desc: 'Encounters, vitals, diagnoses, and prescriptions captured in one continuous flow with a consent gate on every write.',
              bullets: ['Queue-driven workflow', 'Vitals history with sparkline trends', 'Prescription return + reprint'] },
            { name: 'Medical History', icon: ClipboardList, alwaysOn: false,
              desc: 'Longitudinal chart across nine entry types — surgical, family, social, immunizations, allergies, mental health, more.',
              bullets: ['Nine structured entry types', 'KDPA Section 26 access log', 'Sensitive-field redaction by role'] },
            { name: 'Privacy & KDPA', icon: ShieldCheck, alwaysOn: false,
              desc: 'Consent records, data-subject access requests, Section 40 erasure, and Section 43 breach notification with 72-hour countdown.',
              bullets: ['DSAR export endpoint', 'Right-to-erasure with audit', 'Breach register with countdown'] },
        ],
    },
    {
        key: 'diagnostics',
        label: 'Diagnostics',
        tagline: 'Order, collect, result, report — with full sample lifecycle.',
        modules: [
            { name: 'Laboratory', icon: TestTube, alwaysOn: false,
              desc: 'Lab catalogue with per-test parameter definitions, barcoded specimen IDs, and result entry with critical-value alerts.',
              bullets: ['Per-test parameter schema', 'Barcoded sample tracking', 'Critical-value notifications'] },
            { name: 'Radiology', icon: ScanLine, alwaysOn: false,
              desc: 'Imaging orders with priority routing, radiologist sign-off requirements, and contrast usage tracking.',
              bullets: ['Routine / Urgent / STAT triage', 'Radiologist sign-off gate', 'Contrast & modality tracking'] },
        ],
    },
    {
        key: 'pharmacy',
        label: 'Pharmacy & Wards',
        tagline: 'Stock-aware dispensing and bed orchestration.',
        modules: [
            { name: 'Pharmacy', icon: Pill, alwaysOn: false,
              desc: 'Post-dispense and OTC payment flows, receipt generation, transaction ledger, and stock-aware dispensing with batch + expiry.',
              bullets: ['SELECT FOR UPDATE on batch decrements', 'Cash / Card / M-Pesa receipts', 'Returned-prescription handling'] },
            { name: 'Inventory', icon: Package, alwaysOn: false,
              desc: 'Stores, suppliers, batches, reusable-asset tracking, low-stock alerts that ping the right team automatically.',
              bullets: ['Per-location stock visibility', 'Reusable asset usage logs', 'Auto-escalating low-stock alerts'] },
            { name: 'Wards & Admissions', icon: Bed, alwaysOn: false,
              desc: 'Real-time bed map, admission/discharge orchestration, per-shift consumption logging, and bed-cleaning hand-off.',
              bullets: ['Locked-row admission to defeat double-book', 'Ward-level consumables ledger', 'Discharge → cleaning workflow'] },
        ],
    },
    {
        key: 'finance',
        label: 'Finance & Payments',
        tagline: 'Encounter-grained billing through full-bench accounting.',
        modules: [
            { name: 'Billing', icon: Receipt, alwaysOn: false,
              desc: 'Encounter-grained invoicing with eager-loaded billing queue, partial-payment support, and consultation-fee shortcuts.',
              bullets: ['Eager-loaded billing queue (no N+1)', 'Idempotency-keyed payments', 'Partial-payment ledger'] },
            { name: 'Managerial Accounting', icon: BookOpen, alwaysOn: false,
              desc: 'Chart of accounts, journals, fiscal periods, debtor lifecycle, bank reconciliation, and IFRS-shaped financial statements.',
              bullets: ['Auto-posting from Billing/Pharmacy/Cheques', 'Phase-6 bank reconciliation', 'Balance-sheet, P&L, cash-flow'] },
            { name: 'Cheques', icon: BadgeCheck, alwaysOn: false,
              desc: 'Cheque receipting with full lifecycle — deposit, clear, bounce, cancel — and automatic GL journals at each transition.',
              bullets: ['4-state lifecycle with audit', 'Auto-post to GL on clear', 'Bounce reversal entries'] },
            { name: 'Pay Hero (M-Pesa)', icon: Smartphone, alwaysOn: false,
              desc: 'Mobile-money collections via the Pay Hero aggregator — STK push, webhook-validated callbacks, per-tenant credentials.',
              bullets: ['HMAC + CIDR webhook auth', 'Per-tenant encrypted creds', 'Receipt-number unique index'] },
        ],
    },
    {
        key: 'communication',
        label: 'Communication',
        tagline: 'Real-time signal, patient-facing channels, escalation.',
        modules: [
            { name: 'Internal Messaging', icon: MessageSquare, alwaysOn: true,
              desc: 'Direct, group, and department conversations with Redis pub/sub fan-out across workers so escalations are real-time.',
              bullets: ['1:1, group, department threads', 'WebSocket + Redis pub/sub', 'Unread badge across tabs'] },
            { name: 'Notifications', icon: Bell, alwaysOn: true,
              desc: 'System + clinical notifications with read-state, deep-links into the originating chart, and bulk read-all.',
              bullets: ['Per-user inbox', 'Deep-link to source record', 'Mark-all-read shortcut'] },
            { name: 'Patient Portal', icon: Globe2, alwaysOn: false,
              desc: 'Self-service portal so patients can see their appointments, billing, and history — with a separate cookie scope from staff.',
              bullets: ['Token-cookie scope (not staff JWT)', 'Read-only history surface', 'Outpatient self-lookup'] },
            { name: 'Referrals', icon: Share2, alwaysOn: false,
              desc: 'Out-bound referrals to specialists with status tracking and inbound queue for receiving facilities.',
              bullets: ['Status state-machine', 'Inbound + outbound queues', 'Specialist directory'] },
            { name: 'Support', icon: LifeBuoy, alwaysOn: true,
              desc: 'In-app helpdesk routed to the MediFleet platform team with priority, status, and SLA-aware response.',
              bullets: ['Ticket lifecycle with audit', 'Platform-team triage UI', 'In-app + email replies'] },
        ],
    },
    {
        key: 'platform',
        label: 'Platform & Admin',
        tagline: 'Identity, branding, role-based access, configuration.',
        modules: [
            { name: 'Dashboard', icon: LayoutDashboard, alwaysOn: true,
              desc: 'Role-based home page that lands every staff member on the page that matches their actual job that hour.',
              bullets: ['Per-role landing pages', 'Worker-agenda for shift handoff', 'Sticky last-section recall'] },
            { name: 'Authentication', icon: KeyRound, alwaysOn: true,
              desc: 'Argon2id with HMAC pepper, JWT HS256 with tenant audience binding, secure cookie sessions, CSRF double-submit.',
              bullets: ['Argon2id + server-side pepper', 'Tenant-audience-bound JWT', 'CSRF + Secure cookies'] },
            { name: 'User Management', icon: UserCog, alwaysOn: true,
              desc: 'Staff directory, roles, permissions catalogue, per-user permission overrides, license-number capture.',
              bullets: ['Role-based + per-user overrides', '40+ permission codenames', 'Licence-number tracking'] },
            { name: 'Settings', icon: SettingsIcon, alwaysOn: true,
              desc: 'Per-tenant key/value configuration store — branding, working hours, billing, lab, radiology, notifications, privacy.',
              bullets: ['Eight setting categories', 'Per-key edit history', 'Sensitive-flag masking'] },
            { name: 'Branding', icon: Palette, alwaysOn: false,
              desc: 'Per-tenant logo, brand colours, background imagery, and printed-document templates — applied across the SPA.',
              bullets: ['Hosted-logo upload', 'Hex-validated colour pairs', 'Custom print templates'] },
        ],
    },
    {
        key: 'insights',
        label: 'Insights',
        tagline: 'Aggregated telemetry and ad-hoc reporting.',
        modules: [
            { name: 'Analytics', icon: BarChart3, alwaysOn: false,
              desc: 'Aggregated dashboards across encounters, pharmacy turnover, lab throughput, and billing performance.',
              bullets: ['Cross-module roll-ups', 'Per-doctor productivity', 'Exportable to CSV'] },
            { name: 'Audit & Access Logs', icon: FileSearch, alwaysOn: true,
              desc: 'Append-only audit trail of every state change, paired with KDPA Section 26 access logs for chart visibility.',
              bullets: ['Append-only by design', 'Section 26 access log per view', 'IP + user + before/after'] },
        ],
    },
];

function ModuleShowcase({ navigate }) {
    const [activeKey, setActiveKey] = useState(MODULE_GROUPS[0].key);
    const active = MODULE_GROUPS.find(g => g.key === activeKey) ?? MODULE_GROUPS[0];

    return (
        <div className="mt-12">
            {/* Pill-style tab nav (horizontally scrollable on mobile) */}
            <div className="overflow-x-auto -mx-6 px-6 pb-2">
                <div role="tablist" aria-label="Module categories" className="inline-flex gap-2 p-1.5 rounded-2xl bg-white/80 backdrop-blur ring-1 ring-ink-200/70 shadow-soft">
                    {MODULE_GROUPS.map(g => {
                        const isActive = g.key === activeKey;
                        return (
                            <button
                                key={g.key}
                                role="tab"
                                aria-selected={isActive}
                                aria-controls={`mod-panel-${g.key}`}
                                onClick={() => setActiveKey(g.key)}
                                className={`px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-all cursor-pointer ${
                                    isActive
                                        ? 'bg-gradient-to-br from-brand-600 to-teal-500 text-white shadow-soft'
                                        : 'text-ink-600 hover:text-ink-900 hover:bg-ink-50'
                                }`}
                            >
                                {g.label}
                                <span className={`ml-1.5 text-2xs font-bold ${isActive ? 'text-white/80' : 'text-ink-400'}`}>
                                    {g.modules.length}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Active group tagline */}
            <p
                key={active.key + '-tag'}
                className="mt-5 text-sm text-ink-600 max-w-2xl animate-fade-in"
            >
                <span className="text-ink-900 font-semibold">{active.label}.</span>{' '}{active.tagline}
            </p>

            {/* Cards grid — keyed by activeKey so cards remount + re-animate on tab switch */}
            <div
                key={active.key}
                id={`mod-panel-${active.key}`}
                role="tabpanel"
                className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            >
                {active.modules.map((m, idx) => (
                    <ModuleCard key={m.name} module={m} delayMs={idx * 60} navigate={navigate} />
                ))}
            </div>

            {/* Footer CTA strip */}
            <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-gradient-to-br from-ink-900 via-brand-900 to-teal-900 text-white p-6">
                <div>
                    <p className="text-sm font-semibold">Don't see what you need? Tell us — we ship modules every sprint.</p>
                    <p className="text-xs text-ink-200 mt-1">Or jump in: the always-on modules are live the moment your hospital is provisioned.</p>
                </div>
                <button
                    onClick={() => navigate('/portal')}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white text-brand-700 font-semibold text-sm hover:bg-ink-50 transition-colors shadow-soft cursor-pointer"
                >
                    Get started <ArrowRight size={14} />
                </button>
            </div>
        </div>
    );
}

function ModuleCard({ module: m, delayMs, navigate }) {
    const Icon = m.icon;
    const [hover, setHover] = useState(false);
    return (
        <div
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}
            onClick={() => navigate('/portal')}
            className="group relative bg-white rounded-2xl p-5 ring-1 ring-ink-200/70 hover:ring-brand-300 shadow-soft hover:shadow-elevated cursor-pointer transition-all animate-slide-up"
            style={{ animationDelay: `${delayMs}ms`, animationFillMode: 'both' }}
        >
            {/* Gradient border reveal on hover */}
            <div className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-br from-brand-500/0 via-brand-500/[0.04] to-teal-500/[0.06]" />

            <div className="relative flex items-start justify-between gap-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-brand-50 to-teal-50 ring-1 ring-brand-100 text-brand-700 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                    <Icon size={20} />
                </div>
                <span className={`text-2xs font-semibold uppercase tracking-[0.12em] px-2 py-1 rounded-md ${
                    m.alwaysOn
                        ? 'bg-accent-50 text-accent-700 ring-1 ring-accent-100'
                        : 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
                }`}>
                    {m.alwaysOn ? 'Included' : 'Add-on'}
                </span>
            </div>

            <h3 className="relative mt-4 text-base font-semibold text-ink-900 group-hover:text-brand-700 transition-colors">
                {m.name}
            </h3>
            <p className="relative mt-1.5 text-sm text-ink-600 leading-relaxed">{m.desc}</p>

            {/* Hover-reveal feature bullets */}
            <ul
                aria-hidden={!hover}
                className={`relative mt-3 space-y-1.5 transition-all duration-300 overflow-hidden ${
                    hover ? 'max-h-40 opacity-100' : 'max-h-0 opacity-0'
                }`}
            >
                {m.bullets.map(b => (
                    <li key={b} className="flex items-start gap-2 text-xs text-ink-700">
                        <CheckCircle2 size={13} className="text-accent-600 shrink-0 mt-0.5" />
                        <span>{b}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

/* CountUp lives in ../components/CountUp.jsx — reused by Portal as well. */
