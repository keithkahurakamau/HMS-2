import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
    ArrowRight, Play, Clock, Sparkles, Stethoscope, TestTube, Pill,
    Bed, Receipt, HeartPulse,
} from 'lucide-react';
import Logo from '../components/Logo';
import Reveal from '../components/Reveal';
import WebGLHero from '../components/WebGLHero';
import ContactStrip from '../components/ContactStrip';
import InteractiveDashboard from '../components/InteractiveDashboard';
import { SystemMockGrid } from '../components/SystemIllustrations';
import Seo from '../components/Seo';

/*
 * Demo - guided walkthrough page. The video itself is not live yet, so the
 * stage shows a polished "coming soon" frame in the exact 16:9 slot the
 * recording will drop into later. Everything around it (chapters, the live
 * interactive dashboard, system previews, CTA) stands on its own so the page
 * is useful today and becomes the video's home the moment the file is ready.
 *
 * Shares the premium landing language (lp-*) with Landing and the patient
 * sign-in so the journey feels like one product end to end.
 */

const CHAPTERS = [
    { time: '00:00', icon: Sparkles,    title: 'Provision a hospital',  body: 'Watch a fresh tenant come online with its own database, seeded roles, and an admin account.' },
    { time: '01:10', icon: Stethoscope, title: 'See a patient',          body: 'Registration, triage vitals, and a clinical encounter captured in one continuous chart.' },
    { time: '02:35', icon: TestTube,    title: 'Order and result a test', body: 'A lab order goes out, the sample is collected, and a critical value pings the right desk.' },
    { time: '03:40', icon: Pill,        title: 'Dispense from stock',     body: 'Stock-aware dispensing with batch reservation, then a receipt that posts straight to the ledger.' },
    { time: '04:30', icon: Bed,         title: 'Admit and discharge',     body: 'A live bed map drives admission, the per-shift handover, and the cleaning workflow.' },
    { time: '05:20', icon: Receipt,     title: 'Bill and collect',        body: 'An encounter-grained invoice settles over M-Pesa, with the journal entry written automatically.' },
];

export default function Demo() {
    const navigate = useNavigate();

    return (
        <div className="relative min-h-screen bg-white text-ink-900 font-sans selection:bg-[#00ffff]/30">
            <Seo
                title="Product demo"
                path="/demo"
                description="A guided walkthrough of MediFleet: provision a hospital, see a patient, run the lab, dispense from stock, manage wards, and collect payment, all in one secure workspace."
            />

            {/* ============== Sticky frosted navbar ============== */}
            <header className="fixed top-3 inset-x-3 sm:top-4 sm:inset-x-4 z-50">
                <div className="max-w-7xl mx-auto lp-glass rounded-2xl px-4 sm:px-6 py-3 flex items-center justify-between">
                    <Link to="/" className="flex items-center cursor-pointer" aria-label="MediFleet home">
                        <Logo variant="full" size={32} label="MediFleet" />
                    </Link>
                    <nav className="hidden md:flex items-center gap-1">
                        <Link to="/" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Home</Link>
                        <Link to="/#modules" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Modules</Link>
                        <Link to="/demo" className="px-3 py-2 text-sm font-bold text-[#008080] transition-colors duration-200">Demo</Link>
                        <Link to="/?mode=staff#find-hospital" className="px-3 py-2 text-sm font-semibold text-[#015050] hover:text-[#008080] transition-colors duration-200">Find your hospital</Link>
                    </nav>
                    <button type="button" onClick={() => navigate('/?mode=staff#find-hospital')} className="lp-btn-glow text-xs cursor-pointer">
                        Sign in <ArrowRight size={14} />
                    </button>
                </div>
            </header>

            {/* ============== Hero with the video stage ============== */}
            <section className="relative pt-28 pb-24 sm:pt-36 sm:pb-28 overflow-hidden lp-bg-hero lp-grain isolate">
                <div className="absolute inset-0 pointer-events-none">
                    <WebGLHero className="absolute inset-0 opacity-70" />
                    <div className="absolute -top-32 -right-24 size-[40rem] bg-[#00ffff]/15 rounded-full blur-[120px] animate-blob-breathe" />
                    <div className="absolute top-1/3 -left-24 size-[34rem] bg-[#008080]/40 rounded-full blur-[120px] animate-blob-breathe" style={{ animationDelay: '5s' }} />
                    <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-b from-transparent to-white" />
                </div>

                <div className="relative max-w-5xl mx-auto px-5 sm:px-6 text-center animate-slide-up">
                    <span className="lp-chip-dark inline-flex"><Play size={11} /> Guided walkthrough</span>
                    <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tightest leading-[1.05] text-white">
                        See MediFleet{' '}
                        <span className="lp-text-gradient">in motion</span>.
                    </h1>
                    <p className="mt-5 text-lg text-[#cdeeee] leading-relaxed max-w-2xl mx-auto">
                        One short walkthrough takes a patient from the front desk through the lab,
                        pharmacy, wards, and billing, so you can see the whole flow before you sign in.
                    </p>

                    {/* 16:9 video stage (placeholder until the recording lands) */}
                    <div className="mt-10 max-w-4xl mx-auto">
                        <div className="relative aspect-video rounded-3xl overflow-hidden lp-glass-dark">
                            {/* When the video is ready, replace this block with the <video>/<iframe>. */}
                            <div className="absolute inset-0 bg-grid opacity-[0.12]" />
                            <div className="relative h-full flex flex-col items-center justify-center gap-4">
                                <span className="relative size-20 rounded-full bg-[#00ffff]/15 ring-1 ring-[#00ffff]/40 backdrop-blur-md flex items-center justify-center">
                                    <span className="absolute inline-flex size-20 rounded-full bg-[#00ffff]/30 animate-ping" />
                                    <Play size={30} className="relative text-white translate-x-0.5" />
                                </span>
                                <div className="text-center">
                                    <p className="text-sm font-bold text-white">Walkthrough recording coming soon</p>
                                    <p className="text-2xs text-[#9fdede] mt-1 uppercase tracking-[0.16em]">Roughly six minutes, end to end</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                        <button type="button" onClick={() => navigate('/?mode=staff#find-hospital')} className="lp-btn-glow text-base cursor-pointer group">
                            Open your hospital
                            <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
                        </button>
                        <Link to="/#modules" className="lp-btn-ghost-dark text-base cursor-pointer">
                            Browse the modules
                        </Link>
                    </div>
                </div>
            </section>

            {/* ============== Try the live portal ============== */}
            <section className="py-24 lp-bg-ice relative overflow-hidden">
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6 grid lg:grid-cols-2 gap-12 items-center">
                    <div>
                        <span className="lp-chip"><Play size={12} /> Interactive, no sign-in</span>
                        <h2 className="mt-4 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">
                            While the video renders, click around the real thing
                        </h2>
                        <p className="mt-4 text-ink-600 leading-relaxed">
                            This is the live patient portal. Switch tabs to read vitals, confirm an
                            appointment, or request a prescription refill. It is the same interface
                            patients use after they verify.
                        </p>
                        <div className="mt-8 flex flex-wrap gap-3">
                            <button type="button" onClick={() => navigate('/?mode=patient#find-hospital')} className="lp-btn-glow text-base cursor-pointer group">
                                Open the real portal <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
                            </button>
                        </div>
                    </div>
                    <div className="relative">
                        <div className="absolute -inset-6 bg-[#00ffff]/10 rounded-[2rem] blur-3xl pointer-events-none" />
                        <InteractiveDashboard className="relative" />
                    </div>
                </Reveal>
            </section>

            {/* ============== Chapters ============== */}
            <section className="py-24 bg-white">
                <Reveal className="max-w-7xl mx-auto px-5 sm:px-6">
                    <div className="max-w-2xl mx-auto text-center">
                        <span className="lp-chip">What you will see</span>
                        <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">
                            Six chapters, one patient journey
                        </h2>
                        <p className="mt-3 text-ink-600 leading-relaxed">
                            The walkthrough follows a single patient across every department, so each
                            chapter picks up exactly where the last one left off.
                        </p>
                    </div>
                    <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                        {CHAPTERS.map((c, idx) => {
                            const Icon = c.icon;
                            return (
                                <div
                                    key={c.title}
                                    className="lp-card group p-6 animate-slide-up"
                                    style={{ animationDelay: `${idx * 60}ms`, animationFillMode: 'both' }}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="size-12 rounded-2xl bg-[#e6fbfb] text-[#008080] flex items-center justify-center group-hover:bg-[#00ffff]/25 group-hover:scale-105 transition-all duration-200">
                                            <Icon size={20} />
                                        </div>
                                        <span className="inline-flex items-center gap-1 text-2xs font-bold text-[#008080] font-mono">
                                            <Clock size={11} /> {c.time}
                                        </span>
                                    </div>
                                    <h3 className="mt-4 text-base font-extrabold tracking-tight text-[#012626]">{c.title}</h3>
                                    <p className="mt-1.5 text-sm text-ink-600 leading-relaxed">{c.body}</p>
                                </div>
                            );
                        })}
                    </div>
                </Reveal>
            </section>

            {/* ============== System previews ============== */}
            <section className="py-24 lp-bg-ice relative overflow-hidden">
                <Reveal className="relative max-w-7xl mx-auto px-5 sm:px-6">
                    <div className="max-w-2xl mx-auto text-center">
                        <span className="lp-chip">Real surfaces</span>
                        <h2 className="mt-3 text-3xl sm:text-4xl font-extrabold tracking-tight text-[#012626]">
                            The actual screens, not stock art
                        </h2>
                        <p className="mt-3 text-ink-600 leading-relaxed">
                            These previews are built from the same components the live workspace uses,
                            so what you see here is what your team works in every day.
                        </p>
                    </div>
                    <div className="mt-12">
                        <SystemMockGrid />
                    </div>
                </Reveal>
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
                                    Want a closer look at your own data?
                                </h2>
                                <p className="mt-3 text-[#cdeeee] max-w-lg">
                                    Sign in to your hospital, or talk to the platform team about provisioning a new workspace.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-3">
                                <button type="button" onClick={() => navigate('/?mode=staff#find-hospital')} className="lp-btn-glow cursor-pointer">
                                    Open your hospital <ArrowRight size={16} />
                                </button>
                                <button type="button" onClick={() => navigate('/?mode=patient#find-hospital')} className="lp-btn-ghost-dark cursor-pointer">
                                    <HeartPulse size={16} /> Patient portal
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ============== Contact strip ============== */}
            <ContactStrip heading="Questions before you dive in?" />

            {/* ============== Footer ============== */}
            <footer className="border-t border-[#b2f0f0] bg-[#f2fdfd]">
                <div className="max-w-7xl mx-auto px-5 sm:px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
                    <Logo variant="full" size={28} />
                    <p className="text-xs text-ink-500 uppercase tracking-[0.18em]">
                        {/* react-doctor-disable-next-line react-doctor/rendering-hydration-mismatch-time */}
                        &copy; {new Date().getFullYear()} MediFleet · Clinical-grade workspace
                    </p>
                    <div className="flex items-center gap-4 text-xs font-semibold text-[#015050]">
                        <Link to="/" className="hover:text-[#00d4d4] transition-colors">Home</Link>
                        <Link to="/?mode=staff#find-hospital" className="hover:text-[#00d4d4] transition-colors">Sign in</Link>
                        <Link to="/superadmin/login" className="hover:text-[#00d4d4] transition-colors">Platform</Link>
                    </div>
                </div>
            </footer>
        </div>
    );
}
