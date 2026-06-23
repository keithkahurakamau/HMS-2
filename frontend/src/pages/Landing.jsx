import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
    ArrowRight, ShieldCheck, Stethoscope, HeartPulse, Lock, Building2,
    Users, Sparkles, CheckCircle2, ChevronRight, BarChart3, Video,
    Pill, TestTube, Bed, Receipt, MessageSquare, Globe2, Play, Phone,
    Calendar, ClipboardList, ScanLine, Package, BookOpen, BadgeCheck,
    Smartphone, Bell, Share2, LayoutDashboard, Settings as SettingsIcon,
    Palette, LifeBuoy, KeyRound, UserCog, FileSearch, FolderHeart,
} from 'lucide-react';
import Logo from '../components/Logo';
import CountUp from '../components/CountUp';
import ContactStrip from '../components/ContactStrip';
import ContactForm from '../components/ContactForm';
import Reveal from '../components/Reveal';
import WebGLHero from '../components/WebGLHero';
import InteractiveDashboard from '../components/InteractiveDashboard';
import HospitalPicker from '../components/HospitalPicker';
import { SystemMockGrid } from '../components/SystemIllustrations';
import Seo from '../components/Seo';

export default function Landing() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    // The hospital picker lives on this page now (combined from the old
    // /portal). `mode` decides where a pick routes next: staff to /login,
    // patient to /patient. Redirects from /portal arrive with ?mode=…
    const [pickerMode, setPickerMode] = useState(
        searchParams.get('mode') === 'patient' ? 'patient' : 'staff'
    );

    // Scroll to the picker and set the intent. Used by every "sign in" /
    // "patient portal" / "book appointment" CTA on the page.
    const goPicker = useCallback((mode) => {
        setPickerMode(mode);
        document.getElementById('find-hospital')?.scrollIntoView({ behavior: 'smooth' });
    }, []);

    // Honour ?mode= (and #find-hospital) on first load, e.g. when /portal
    // forwards a staff or patient bounce here.
    useEffect(() => {
        if (searchParams.get('mode') || window.location.hash === '#find-hospital') {
            const t = window.setTimeout(() => {
                document.getElementById('find-hospital')?.scrollIntoView({ behavior: 'smooth' });
            }, 350);
            return () => window.clearTimeout(t);
        }
    }, [searchParams]);

    return (
        <div className="relative min-h-screen bg-white text-ink-900 font-sans selection:bg-[#00ffff]/30">
            <Seo
                path="/"
                description="MediFleet unifies registration, clinical desk, pharmacy, lab, radiology, wards, and billing into one secure workspace. Run an entire fleet of hospitals from one codebase, fully isolated per tenant."
            />

            {/* ============== Sticky frosted navbar ============== */}
            <header className="fixed top-3 inset-x-3 sm:top-4 sm:inset-x-4 z-50">
                <div className="max-w-7xl mx-auto lp-glass rounded-2xl px-4 sm:px-6 py-3 flex items-center justify-between">
                    <Link to="/" className="flex items-center cursor-pointer" aria-label="MediFleet home">
                        <Logo variant="full" size={32} label="MediFleet" />
                    </Link>
                    <nav className="hidden md:flex items-center gap-1">
                        <a href="#services" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Services</a>
                        <a href="#dashboard" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Live demo</a>
                        <a href="#modules" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Modules</a>
                        <a href="#trust" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Compliance</a>
                    </nav>
                    <div className="flex items-center gap-2">
                        <button type="button" onClick={() => goPicker('patient')} className="hidden sm:inline-flex lp-btn-ghost text-xs cursor-pointer">
                            <Calendar size={14} /> Book appointment
                        </button>
                        <button type="button" onClick={() => goPicker('staff')} className="lp-btn-glow text-xs cursor-pointer">
                            Sign in <ArrowRight size={14} />
                        </button>
                    </div>
                </div>
            </header>

            {/* ============== Hero (split screen, dark teal + cyan glow) ============== */}
            <section className="relative pt-28 pb-24 sm:pt-36 sm:pb-32 overflow-hidden lp-bg-hero lp-grain isolate">
                <div className="absolute inset-0 pointer-events-none">
                    <WebGLHero className="absolute inset-0 opacity-70" />
                    <div className="absolute -top-24 -right-20 size-[40rem] rounded-full bg-[#00ffff]/15 blur-[120px] animate-blob-breathe" />
                    <div className="absolute top-1/2 -left-24 size-[34rem] rounded-full bg-[#008080]/40 blur-[120px] animate-blob-breathe" style={{ animationDelay: '5s' }} />
                    <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-white" />
                </div>

                <div className="relative max-w-7xl mx-auto px-5 sm:px-6 grid lg:grid-cols-2 gap-12 lg:gap-10 items-center">
                    {/* Left: message */}
                    <div className="animate-slide-up">
                        <span className="lp-chip-dark inline-flex">
                            <Sparkles size={12} /> Your health, digitally empowered
                        </span>
                        <h1 className="mt-6 text-4xl sm:text-5xl lg:text-[3.7rem] font-extrabold tracking-tightest leading-[1.04] text-white">
                            Your health,{' '}
                            <span className="lp-text-gradient">digitally</span>{' '}
                            empowered.
                        </h1>
                        <p className="mt-6 text-lg text-[#cdeeee] leading-relaxed max-w-xl">
                            One secure place for your whole hospital and every patient. Book care, see
                            records, manage prescriptions, and run clinical operations end to end, with
                            calm, modern tools that put people first.
                        </p>
                        <div className="mt-8 flex flex-wrap items-center gap-3">
                            <button type="button" onClick={() => goPicker('staff')} className="lp-btn-glow text-base cursor-pointer group">
                                Log in
                                <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
                            </button>
                            <button type="button" onClick={() => goPicker('patient')} className="lp-btn-ghost-dark text-base cursor-pointer">
                                <HeartPulse size={16} /> Patient portal
                            </button>
                        </div>
                        <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs text-[#9fdede]">
                            <Trust icon={<Lock size={14} className="text-[#7dfdfd]" />} label="HttpOnly JWT and CSRF" />
                            <Trust icon={<ShieldCheck size={14} className="text-[#7dfdfd]" />} label="KDPA aligned" />
                            <Trust icon={<Globe2 size={14} className="text-[#7dfdfd]" />} label="Database per tenant" />
                        </div>
                    </div>

                    {/* Right: interactive dashboard illustration */}
                    <div className="relative animate-slide-up lg:pl-4" style={{ animationDelay: '120ms', animationFillMode: 'both' }}>
                        <div className="absolute -inset-6 bg-[#00ffff]/10 rounded-[2rem] blur-3xl pointer-events-none" />
                        <div className="relative animate-float">
                            <InteractiveDashboard />
                        </div>
                        {/* Floating glass stat chip */}
                        <div className="hidden sm:flex absolute -bottom-5 -left-4 lp-glass rounded-2xl px-4 py-3 items-center gap-3 animate-float" style={{ animationDelay: '1.5s' }}>
                            <span className="size-9 rounded-xl bg-[#e6fbfb] text-[#008080] flex items-center justify-center">
                                <ShieldCheck size={18} />
                            </span>
                            <div>
                                <p className="text-xs font-bold text-[#012626]">All systems operational</p>
                                <p className="text-[0.65rem] text-[#64748b]">Last check 12s ago</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ============== Stat strip ============== */}
            <section className="relative -mt-8">
                <div className="max-w-7xl mx-auto px-5 sm:px-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Modules" value={<CountUp to={25} />} hint="Clinical, ops and finance" />
                    <Stat label="Tenant isolation" value={<CountUp to={100} suffix="%" />} hint="Per-database separation" />
                    <Stat label="Permission codes" value={<CountUp to={40} suffix="+" />} hint="Fine-grained RBAC" />
                    <Stat label="Audit retention" value="Always on" hint="Append-only by design" />
                </div>
            </section>

            {/* ============== Find your hospital (combined picker) ============== */}
            <section id="find-hospital" className="py-24 bg-white relative overflow-hidden scroll-mt-24">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-20 left-1/2 -translate-x-1/2 size-[40rem] rounded-full bg-[#00ffff]/8 blur-[130px]" />
                </div>
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6">
                    <div className="max-w-2xl mx-auto text-center">
                        <span className="lp-chip"><Building2 size={12} /> Workspace selector</span>
                        <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">
                            {pickerMode === 'patient' ? 'Find your hospital to view your records' : 'Find your hospital to sign in'}
                        </h2>
                        <p className="mt-3 text-ink-600 leading-relaxed">
                            Every hospital on MediFleet runs on its own dedicated database. Pick yours below
                            and we'll connect you to its workspace.
                        </p>

                        {/* Staff / Patient segmented toggle */}
                        <div className="mt-7 inline-flex p-1.5 rounded-2xl lp-glass" role="tablist" aria-label="Who are you signing in as">
                            <button type="button" role="tab" aria-selected={pickerMode === 'staff'}
                                onClick={() => setPickerMode('staff')}
                                className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-200 ease-in-out cursor-pointer ${
                                    pickerMode === 'staff' ? 'bg-[#008080] text-white shadow-md shadow-[#008080]/30' : 'text-[#015050] hover:bg-[#e6fbfb]'
                                }`}>
                                <Stethoscope size={15} /> I'm staff
                            </button>
                            <button type="button" role="tab" aria-selected={pickerMode === 'patient'}
                                onClick={() => setPickerMode('patient')}
                                className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all duration-200 ease-in-out cursor-pointer ${
                                    pickerMode === 'patient' ? 'bg-[#008080] text-white shadow-md shadow-[#008080]/30' : 'text-[#015050] hover:bg-[#e6fbfb]'
                                }`}>
                                <HeartPulse size={15} /> I'm a patient
                            </button>
                        </div>
                    </div>

                    <div className="mt-12">
                        <HospitalPicker nextPath={pickerMode === 'patient' ? '/patient' : '/login'} />
                    </div>
                </Reveal>
            </section>

            {/* ============== Services (interactive feature cards) ============== */}
            <section id="services" className="py-24 lp-bg-ice relative overflow-hidden">
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6">
                    <SectionHeader
                        eyebrow="What you get"
                        title="Care that meets people where they are"
                        subtitle="Three things patients feel right away, all built on the same secure, audited, tenant-isolated core."
                    />
                    <div className="mt-12 grid md:grid-cols-3 gap-6">
                        <FeatureCard
                            icon={<Video size={22} />}
                            title="Telemedicine"
                            body="Connect patients and clinicians in secure virtual visits, with notes and prescriptions flowing straight into the chart."
                            points={['Secure video consults', 'Notes sync to the record', 'Follow-up scheduling']}
                            onClick={() => navigate('/demo')}
                        />
                        <FeatureCard
                            icon={<HeartPulse size={22} />}
                            title="24/7 triage"
                            body="Capture vitals and acuity the moment a patient arrives, so the right case reaches the right desk first."
                            points={['Vitals and acuity capture', 'Smart queue ordering', 'Critical-value alerts']}
                            featured
                            onClick={() => navigate('/demo')}
                        />
                        <FeatureCard
                            icon={<FolderHeart size={22} />}
                            title="Health records"
                            body="A longitudinal chart patients can actually read, with consent gates and access logs on every clinical write."
                            points={['One continuous chart', 'Consent-gated access', 'KDPA access logging']}
                            onClick={() => goPicker('patient')}
                        />
                    </div>
                </Reveal>
            </section>

            {/* ============== Live interactive dashboard showcase ============== */}
            <section id="dashboard" className="relative py-24 lp-bg-hero isolate overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute -top-24 right-0 size-[34rem] rounded-full bg-[#00ffff]/12 blur-[130px] animate-blob-breathe" />
                    <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-white to-transparent" />
                    <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-b from-transparent to-white" />
                </div>
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6 grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <span className="lp-chip-dark inline-flex"><Play size={12} /> Try it yourself</span>
                        <h2 className="mt-5 text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
                            See exactly what patients get
                        </h2>
                        <p className="mt-4 text-[#cdeeee] leading-relaxed">
                            This is the real patient portal, running live on this page. Switch tabs to
                            check vitals, confirm an appointment, or request a prescription refill, no
                            sign-in required.
                        </p>
                        <ul className="mt-6 space-y-3">
                            <DarkBullet>Live health metrics with trend lines</DarkBullet>
                            <DarkBullet>Upcoming appointments you can confirm</DarkBullet>
                            <DarkBullet>Prescription management with one-tap refills</DarkBullet>
                        </ul>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <button type="button" onClick={() => goPicker('patient')} className="lp-btn-glow text-base cursor-pointer group">
                                Open the real portal <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
                            </button>
                            <Link to="/demo" className="lp-btn-ghost-dark text-base cursor-pointer">
                                <Video size={16} /> Watch the walkthrough
                            </Link>
                        </div>
                    </div>
                    <div className="relative">
                        <div className="absolute -inset-6 bg-[#00ffff]/10 rounded-[2rem] blur-3xl pointer-events-none" />
                        <InteractiveDashboard className="relative" />
                    </div>
                </Reveal>
            </section>

            {/* ============== Modules showcase (all 25) ============== */}
            <section id="modules" className="py-24 bg-white relative overflow-hidden">
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6">
                    <SectionHeader
                        eyebrow="Modules"
                        title="Twenty-five modules, one ledger of truth"
                        subtitle="Every module is gated by per-role permissions, audit-logged, and tenant-isolated. Switch them on à la carte. The 9 always-on modules are bundled in the base subscription."
                    />
                    <ModuleShowcase goPicker={goPicker} />
                </Reveal>
            </section>

            {/* ============== Product preview (real system surfaces) ============== */}
            <section id="preview" className="py-24 lp-bg-ice relative overflow-hidden">
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6">
                    <SectionHeader
                        eyebrow="A look inside"
                        title="The actual screens, not stock art"
                        subtitle="These previews are built from the same components the live workspace ships, so what you see here is what your team works in every day."
                    />
                    <div className="mt-12">
                        <SystemMockGrid />
                    </div>
                    <div className="mt-10 text-center">
                        <Link to="/demo" className="lp-btn-glow text-sm cursor-pointer">
                            <Play size={15} /> Watch the full walkthrough
                        </Link>
                    </div>
                </Reveal>
            </section>

            {/* ============== How it works ============== */}
            <section id="how" className="py-24 bg-white">
                <div className="max-w-7xl mx-auto px-5 sm:px-6">
                    <SectionHeader
                        eyebrow="How it works"
                        title="From sign-up to first encounter in minutes"
                        subtitle="The platform team provisions your hospital, then your admin invites the team and starts seeing patients the same day."
                    />
                    <div className="mt-12 grid md:grid-cols-3 gap-6">
                        <Step n={1} title="Provision your hospital">
                            The MediFleet platform team spins up a dedicated database, applies the schema, seeds RBAC roles, and creates your admin account.
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
            <section id="trust" className="py-24 lp-bg-ice">
                <div className="max-w-7xl mx-auto px-5 sm:px-6 grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <span className="lp-chip">Compliance</span>
                        <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">
                            Built for clinical environments, not retrofitted into one.
                        </h2>
                        <p className="mt-4 text-ink-600 leading-relaxed">
                            Every endpoint enforces tenant isolation at the JWT layer. Every clinical
                            write goes through a consent gate. Every audit row is append-only by trigger,
                            even with database superuser access.
                        </p>
                        <ul className="mt-6 space-y-3">
                            <Bullet>KDPA Section 26: append-only access logs</Bullet>
                            <Bullet>KDPA Section 30: consent-gated clinical writes</Bullet>
                            <Bullet>KDPA Section 40: subject erasure endpoint</Bullet>
                            <Bullet>KDPA Section 43: 72-hour breach countdown</Bullet>
                            <Bullet>HttpOnly JWT cookies, CSRF double-submit, refresh-token reuse detection</Bullet>
                        </ul>
                    </div>
                    <ComplianceCard />
                </div>
            </section>

            {/* ============== CTA ============== */}
            <section className="py-24 bg-white">
                <div className="max-w-5xl mx-auto px-5 sm:px-6">
                    <div className="relative overflow-hidden rounded-[2rem] lp-bg-hero p-10 sm:p-16 shadow-elevated isolate">
                        <div className="absolute -top-24 -right-24 size-96 rounded-full bg-[#00ffff]/20 blur-3xl pointer-events-none" />
                        <div className="absolute -bottom-24 -left-16 size-80 rounded-full bg-[#008080]/40 blur-3xl pointer-events-none" />
                        <div className="relative flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
                            <div>
                                <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white max-w-xl">
                                    Ready to run a calmer hospital?
                                </h2>
                                <p className="mt-3 text-[#cdeeee] max-w-lg">
                                    Sign in to your tenant, or talk to the platform team about provisioning a new workspace.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-3">
                                <button type="button" onClick={() => goPicker('staff')} className="lp-btn-glow cursor-pointer">
                                    Open your hospital <ArrowRight size={16} />
                                </button>
                                <a href="#contact" className="lp-btn-ghost-dark cursor-pointer">
                                    <Phone size={16} /> Talk to us
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ============== Contact form ============== */}
            <section className="relative py-14 sm:py-20 bg-white" id="contact">
                <div className="max-w-2xl mx-auto px-5 sm:px-6">
                    <div className="text-center mb-8">
                        <span className="lp-chip">Get in touch</span>
                        <h2 className="mt-4 text-2xl sm:text-3xl font-extrabold tracking-tight text-[#012626]">Send us a message</h2>
                        <p className="mt-2 text-sm text-ink-600 max-w-xl mx-auto">
                            Tell us about your hospital and what you need, and we'll get back to you within one business day.
                        </p>
                    </div>
                    <ContactForm />
                </div>
            </section>

            {/* ============== Contact strip ============== */}
            <ContactStrip heading="Prefer to reach us directly?" />

            {/* ============== Footer ============== */}
            <footer className="border-t border-[#b2f0f0] bg-[#f2fdfd]">
                <div className="max-w-7xl mx-auto px-5 sm:px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
                    <Logo variant="full" size={28} />
                    <p className="text-xs text-ink-500 uppercase tracking-[0.18em]">
                        {/* react-doctor-disable-next-line react-doctor/rendering-hydration-mismatch-time */}
                        &copy; {new Date().getFullYear()} MediFleet · Clinical-grade workspace
                    </p>
                    <div className="flex items-center gap-4 text-xs font-semibold text-[#015050]">
                        <button type="button" onClick={() => goPicker('staff')} className="hover:text-[#00d4d4] transition-colors cursor-pointer">Sign in</button>
                        <button type="button" onClick={() => goPicker('patient')} className="hover:text-[#00d4d4] transition-colors cursor-pointer">Patient portal</button>
                        <Link to="/demo" className="hover:text-[#00d4d4] transition-colors">Demo</Link>
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
        <span className="inline-flex items-center gap-2 font-medium">
            {icon}{label}
        </span>
    );
}

function Stat({ label, value, hint }) {
    return (
        <div className="lp-card p-5">
            <p className="text-2xs font-bold uppercase tracking-[0.14em] text-[#008080]">{label}</p>
            <p className="mt-1 text-2xl font-extrabold tracking-tight text-[#012626]">{value}</p>
            <p className="mt-1 text-xs text-ink-500">{hint}</p>
        </div>
    );
}

function SectionHeader({ eyebrow, title, subtitle }) {
    return (
        <div className="max-w-2xl mx-auto text-center">
            <span className="lp-chip">{eyebrow}</span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">{title}</h2>
            <p className="mt-3 text-ink-600 leading-relaxed">{subtitle}</p>
        </div>
    );
}

function FeatureCard({ icon, title, body, points, featured, onClick }) {
    return (
        // Clickable card with flow content; role="button" is the correct pattern here.
        // react-doctor-disable-next-line react-doctor/prefer-tag-over-role
        <div
            role="button"
            tabIndex={0}
            onClick={onClick}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(); } }}
            className={`lp-card group p-7 cursor-pointer ${featured ? 'lg:-translate-y-3' : ''}`}
        >
            <div className={`size-14 rounded-2xl flex items-center justify-center mb-5 transition-all duration-200 ease-in-out ${
                featured
                    ? 'bg-[#008080] text-white group-hover:bg-[#00d4d4]'
                    : 'bg-[#e6fbfb] text-[#008080] group-hover:bg-[#00ffff]/25'
            }`}>
                {icon}
            </div>
            <h3 className="text-xl font-extrabold tracking-tight text-[#012626]">{title}</h3>
            <p className="mt-2 text-sm text-ink-600 leading-relaxed">{body}</p>
            <ul className="mt-5 space-y-2">
                {points.map((p) => (
                    <li key={p} className="flex items-center gap-2 text-sm text-[#015050] font-medium">
                        <CheckCircle2 size={15} className="text-[#00d4d4] shrink-0" /> {p}
                    </li>
                ))}
            </ul>
            <div className="mt-5 inline-flex items-center gap-1 text-sm font-bold text-[#008080] opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                Learn more <ChevronRight size={14} />
            </div>
        </div>
    );
}

function Step({ n, title, children }) {
    return (
        <div className="lp-card p-7">
            <div className="size-10 rounded-xl bg-gradient-to-br from-[#00ffff] to-[#008080] flex items-center justify-center text-[#012626] font-extrabold lp-glow-ring">
                {n}
            </div>
            <h3 className="mt-4 text-lg font-extrabold tracking-tight text-[#012626]">{title}</h3>
            <p className="mt-2 text-sm text-ink-600 leading-relaxed">{children}</p>
        </div>
    );
}

function Bullet({ children }) {
    return (
        <li className="flex items-start gap-2 text-sm text-ink-700">
            <CheckCircle2 size={16} className="text-[#008080] shrink-0 mt-0.5" />
            <span>{children}</span>
        </li>
    );
}

function DarkBullet({ children }) {
    return (
        <li className="flex items-start gap-2 text-sm text-[#cdeeee]">
            <CheckCircle2 size={16} className="text-[#7dfdfd] shrink-0 mt-0.5" />
            <span>{children}</span>
        </li>
    );
}

function ComplianceCard() {
    return (
        <div className="lp-glass rounded-[1.6rem] overflow-hidden">
            <div className="p-8 space-y-5">
                <div className="flex items-center gap-3">
                    <div className="size-12 rounded-2xl bg-gradient-to-br from-[#00ffff] to-[#008080] flex items-center justify-center lp-glow-ring">
                        <Lock size={20} className="text-[#012626]" />
                    </div>
                    <div>
                        <p className="text-2xs font-bold uppercase tracking-[0.14em] text-[#008080]">Security posture</p>
                        <p className="text-base font-extrabold text-[#012626] mt-0.5">Defense in depth</p>
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
                        <div key={label} className="p-3 rounded-xl bg-white/70 ring-1 ring-[#b2f0f0]">
                            <p className="text-2xs font-bold uppercase tracking-[0.12em] text-[#64748b]">{label}</p>
                            <p className="mt-1 text-sm font-extrabold text-[#012626]">{value}</p>
                        </div>
                    ))}
                </div>
                <div className="flex items-center justify-between p-3 rounded-xl bg-[#e6fbfb] ring-1 ring-[#b2f0f0]">
                    <div className="flex items-center gap-2 text-sm font-bold text-[#008080]">
                        <CheckCircle2 size={16} /> KDPA aligned
                    </div>
                    <span className="text-2xs font-bold uppercase tracking-wider text-[#008080]">Verified</span>
                </div>
            </div>
        </div>
    );
}

/* ──────────────────────────────────────────────────────────────────────────
   ModuleShowcase - interactive tabbed browser for all 25 platform modules.
   Groups the modules by clinical workflow. Always-on modules carry an
   "Included" badge; a-la-carte modules carry an "Add-on" badge, the same
   taxonomy used in the superadmin Modules dashboard.
   ────────────────────────────────────────────────────────────────────── */

const MODULE_GROUPS = [
    {
        key: 'clinical',
        label: 'Clinical Workflow',
        tagline: 'Front desk to follow-up on one continuous chart.',
        modules: [
            { name: 'Patient Registry', icon: Users, alwaysOn: true,
              desc: 'KDPA-compliant patient onboarding with auto-generated outpatient numbers and treatment-consent capture at first contact.',
              bullets: ['Single search across name, OP#, ID, phone', 'Consent capture inline at registration', 'Soft-delete and audit trail'] },
            { name: 'Appointments', icon: Calendar, alwaysOn: true,
              desc: 'Doctor schedules, slot availability, and automated reminders that respect each provider\'s working hours.',
              bullets: ['Per-doctor calendar', 'Slot-availability lookup', 'SMS and email reminders'] },
            { name: 'Clinical Desk', icon: Stethoscope, alwaysOn: false,
              desc: 'Encounters, vitals, diagnoses, and prescriptions captured in one continuous flow with a consent gate on every write.',
              bullets: ['Queue-driven workflow', 'Vitals history with sparkline trends', 'Prescription return and reprint'] },
            { name: 'Medical History', icon: ClipboardList, alwaysOn: false,
              desc: 'Longitudinal chart across nine entry types: surgical, family, social, immunizations, allergies, mental health, and more.',
              bullets: ['Nine structured entry types', 'KDPA Section 26 access log', 'Sensitive-field redaction by role'] },
            { name: 'Privacy and KDPA', icon: ShieldCheck, alwaysOn: false,
              desc: 'Consent records, data-subject access requests, Section 40 erasure, and Section 43 breach notification with a 72-hour countdown.',
              bullets: ['DSAR export endpoint', 'Right-to-erasure with audit', 'Breach register with countdown'] },
        ],
    },
    {
        key: 'diagnostics',
        label: 'Diagnostics',
        tagline: 'Order, collect, result, and report, with full sample lifecycle.',
        modules: [
            { name: 'Laboratory', icon: TestTube, alwaysOn: false,
              desc: 'Lab catalogue with per-test parameter definitions, barcoded specimen IDs, and result entry with critical-value alerts.',
              bullets: ['Per-test parameter schema', 'Barcoded sample tracking', 'Critical-value notifications'] },
            { name: 'Radiology', icon: ScanLine, alwaysOn: false,
              desc: 'Imaging orders with priority routing, radiologist sign-off requirements, and contrast usage tracking.',
              bullets: ['Routine, Urgent, STAT triage', 'Radiologist sign-off gate', 'Contrast and modality tracking'] },
        ],
    },
    {
        key: 'pharmacy',
        label: 'Pharmacy and Wards',
        tagline: 'Stock-aware dispensing and bed orchestration.',
        modules: [
            { name: 'Pharmacy', icon: Pill, alwaysOn: false,
              desc: 'Post-dispense and OTC payment flows, receipt generation, transaction ledger, and stock-aware dispensing with batch and expiry.',
              bullets: ['Locked-row batch decrements', 'Cash, card, M-Pesa receipts', 'Returned-prescription handling'] },
            { name: 'Inventory', icon: Package, alwaysOn: false,
              desc: 'Stores, suppliers, batches, reusable-asset tracking, and low-stock alerts that ping the right team automatically.',
              bullets: ['Per-location stock visibility', 'Reusable asset usage logs', 'Auto-escalating low-stock alerts'] },
            { name: 'Wards and Admissions', icon: Bed, alwaysOn: false,
              desc: 'Real-time bed map, admission and discharge orchestration, per-shift consumption logging, and bed-cleaning hand-off.',
              bullets: ['Locked-row admission to defeat double-book', 'Ward-level consumables ledger', 'Discharge to cleaning workflow'] },
        ],
    },
    {
        key: 'finance',
        label: 'Finance and Payments',
        tagline: 'Encounter-grained billing through full-bench accounting.',
        modules: [
            { name: 'Billing', icon: Receipt, alwaysOn: false,
              desc: 'Encounter-grained invoicing with an eager-loaded billing queue, partial-payment support, and consultation-fee shortcuts.',
              bullets: ['Eager-loaded billing queue', 'Idempotency-keyed payments', 'Partial-payment ledger'] },
            { name: 'Managerial Accounting', icon: BookOpen, alwaysOn: false,
              desc: 'Chart of accounts, journals, fiscal periods, debtor lifecycle, bank reconciliation, and IFRS-shaped financial statements.',
              bullets: ['Auto-posting from Billing, Pharmacy, Cheques', 'Bank reconciliation', 'Balance sheet, P&L, cash-flow'] },
            { name: 'Cheques', icon: BadgeCheck, alwaysOn: false,
              desc: 'Cheque receipting with a full lifecycle (deposit, clear, bounce, cancel) and automatic GL journals at each transition.',
              bullets: ['4-state lifecycle with audit', 'Auto-post to GL on clear', 'Bounce reversal entries'] },
            { name: 'M-Pesa Payments', icon: Smartphone, alwaysOn: false,
              desc: 'Mobile-money collections at the till and pharmacy: STK push to the customer, webhook-validated receipts, settled to your bank.',
              bullets: ['HMAC and CIDR webhook auth', 'Encrypted at rest', 'Receipt-number unique index'] },
        ],
    },
    {
        key: 'communication',
        label: 'Communication',
        tagline: 'Real-time signal, patient-facing channels, escalation.',
        modules: [
            { name: 'Internal Messaging', icon: MessageSquare, alwaysOn: true,
              desc: 'Direct, group, and department conversations with Redis pub/sub fan-out across workers so escalations are real-time.',
              bullets: ['1:1, group, department threads', 'WebSocket and Redis pub/sub', 'Unread badge across tabs'] },
            { name: 'Notifications', icon: Bell, alwaysOn: true,
              desc: 'System and clinical notifications with read-state, deep-links into the originating chart, and bulk read-all.',
              bullets: ['Per-user inbox', 'Deep-link to source record', 'Mark-all-read shortcut'] },
            { name: 'Patient Portal', icon: Globe2, alwaysOn: false,
              desc: 'Self-service portal so patients can see their appointments, billing, and history, with a separate cookie scope from staff.',
              bullets: ['Token-cookie scope, not staff JWT', 'Read-only history surface', 'Outpatient self-lookup'] },
            { name: 'Referrals', icon: Share2, alwaysOn: false,
              desc: 'Outbound referrals to specialists with status tracking and an inbound queue for receiving facilities.',
              bullets: ['Status state-machine', 'Inbound and outbound queues', 'Specialist directory'] },
            { name: 'Support', icon: LifeBuoy, alwaysOn: true,
              desc: 'In-app helpdesk routed to the MediFleet platform team with priority, status, and SLA-aware response.',
              bullets: ['Ticket lifecycle with audit', 'Platform-team triage UI', 'In-app and email replies'] },
        ],
    },
    {
        key: 'platform',
        label: 'Platform and Admin',
        tagline: 'Identity, branding, role-based access, configuration.',
        modules: [
            { name: 'Dashboard', icon: LayoutDashboard, alwaysOn: true,
              desc: 'Role-based home page that lands every staff member on the page that matches their actual job that hour.',
              bullets: ['Per-role landing pages', 'Worker-agenda for shift handoff', 'Sticky last-section recall'] },
            { name: 'Authentication', icon: KeyRound, alwaysOn: true,
              desc: 'Argon2id with HMAC pepper, JWT HS256 with tenant audience binding, secure cookie sessions, and CSRF double-submit.',
              bullets: ['Argon2id and server-side pepper', 'Tenant-audience-bound JWT', 'CSRF and secure cookies'] },
            { name: 'User Management', icon: UserCog, alwaysOn: true,
              desc: 'Staff directory, roles, permissions catalogue, per-user permission overrides, and license-number capture.',
              bullets: ['Role-based and per-user overrides', '40+ permission codenames', 'Licence-number tracking'] },
            { name: 'Settings', icon: SettingsIcon, alwaysOn: true,
              desc: 'Per-tenant key/value configuration store for branding, working hours, billing, lab, radiology, notifications, and privacy.',
              bullets: ['Eight setting categories', 'Per-key edit history', 'Sensitive-flag masking'] },
            { name: 'Branding', icon: Palette, alwaysOn: false,
              desc: 'Per-tenant logo, brand colours, background imagery, and printed-document templates, applied across the SPA.',
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
            { name: 'Audit and Access Logs', icon: FileSearch, alwaysOn: true,
              desc: 'Append-only audit trail of every state change, paired with KDPA Section 26 access logs for chart visibility.',
              bullets: ['Append-only by design', 'Section 26 access log per view', 'IP, user, before and after'] },
        ],
    },
];

function ModuleShowcase({ goPicker }) {
    const [activeKey, setActiveKey] = useState(MODULE_GROUPS[0].key);
    const active = MODULE_GROUPS.find(g => g.key === activeKey) ?? MODULE_GROUPS[0];

    return (
        <div className="mt-12">
            {/* Pill-style tab nav */}
            <div className="overflow-x-auto -mx-5 px-5 sm:-mx-6 sm:px-6 pb-2">
                <div role="tablist" aria-label="Module categories" className="inline-flex gap-2 p-1.5 rounded-2xl lp-glass">
                    {MODULE_GROUPS.map(g => {
                        const isActive = g.key === activeKey;
                        return (
                            <button type="button"
                                key={g.key}
                                role="tab"
                                aria-selected={isActive}
                                aria-controls={`mod-panel-${g.key}`}
                                onClick={() => setActiveKey(g.key)}
                                className={`px-4 py-2 rounded-xl text-sm font-bold whitespace-nowrap transition-all duration-200 ease-in-out cursor-pointer ${
                                    isActive
                                        ? 'bg-[#008080] text-white shadow-md shadow-[#008080]/30'
                                        : 'text-[#015050] hover:bg-[#e6fbfb]'
                                }`}
                            >
                                {g.label}
                                <span className={`ml-1.5 text-2xs font-bold ${isActive ? 'text-[#7dfdfd]' : 'text-[#94a3b8]'}`}>
                                    {g.modules.length}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>

            <p key={active.key + '-tag'} className="mt-5 text-sm text-ink-600 max-w-2xl animate-fade-in">
                <span className="text-[#012626] font-bold">{active.label}.</span>{' '}{active.tagline}
            </p>

            <div key={active.key} id={`mod-panel-${active.key}`} role="tabpanel"
                className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {active.modules.map((m, idx) => (
                    <ModuleCard key={m.name} module={m} delayMs={idx * 60} goPicker={goPicker} />
                ))}
            </div>

            <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl lp-bg-hero text-white p-6 isolate">
                <div>
                    <p className="text-sm font-bold">Don't see what you need? Tell us, and we ship modules every sprint.</p>
                    <p className="text-xs text-[#9fdede] mt-1">Or jump in: the always-on modules are live the moment your hospital is provisioned.</p>
                </div>
                <button type="button" onClick={() => goPicker('staff')} className="lp-btn-glow text-sm cursor-pointer">
                    Get started <ArrowRight size={14} />
                </button>
            </div>
        </div>
    );
}

function ModuleCard({ module: m, delayMs, goPicker }) {
    const Icon = m.icon;
    const [hover, setHover] = useState(false);
    return (
        // react-doctor-disable-next-line react-doctor/prefer-tag-over-role
        <div
            role="button"
            tabIndex={0}
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}
            onClick={() => goPicker('staff')}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goPicker('staff'); } }}
            className="lp-card group p-5 cursor-pointer animate-slide-up"
            style={{ animationDelay: `${delayMs}ms`, animationFillMode: 'both' }}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="size-11 rounded-xl bg-[#e6fbfb] text-[#008080] flex items-center justify-center shrink-0 group-hover:bg-[#00ffff]/25 group-hover:scale-105 transition-all duration-200">
                    <Icon size={20} />
                </div>
                <span className={`text-2xs font-bold uppercase tracking-[0.12em] px-2 py-1 rounded-md ${
                    m.alwaysOn
                        ? 'bg-[#008080] text-white'
                        : 'bg-[#e6fbfb] text-[#008080] ring-1 ring-[#b2f0f0]'
                }`}>
                    {m.alwaysOn ? 'Included' : 'Add-on'}
                </span>
            </div>

            <h3 className="mt-4 text-base font-extrabold text-[#012626] group-hover:text-[#008080] transition-colors duration-200">
                {m.name}
            </h3>
            <p className="mt-1.5 text-sm text-ink-600 leading-relaxed">{m.desc}</p>

            <ul
                aria-hidden={!hover}
                className={`mt-3 space-y-1.5 transition-all duration-300 overflow-hidden ${
                    hover ? 'max-h-40 opacity-100' : 'max-h-0 opacity-0'
                }`}
            >
                {m.bullets.map(b => (
                    <li key={b} className="flex items-start gap-2 text-xs text-[#015050]">
                        <CheckCircle2 size={13} className="text-[#00d4d4] shrink-0 mt-0.5" />
                        <span>{b}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
