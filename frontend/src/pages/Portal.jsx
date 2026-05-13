import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Building2, Search, ArrowRight, Activity, Sparkles, HeartPulse,
    ShieldCheck, Globe2, Lock, CheckCircle2, X, ChevronRight,
} from 'lucide-react';
import toast from 'react-hot-toast';
import Logo from '../components/Logo';

/**
 * Portal — hospital workspace selector.
 *
 *  Acts as the front door once a visitor decides "I'm a member of a hospital
 *  team." Lives in the same visual family as Landing (cyan/teal/emerald,
 *  floating navbar, white-and-mesh body) so the trip from "I read about
 *  MediFleet" → "I'm picking my hospital" feels like one product.
 *
 *  Premium and theme-color chips remain on each tenant card so a returning
 *  user can spot their hospital at a glance.
 */

const TENANT_CHIP = {
    blue:    { ring: 'bg-blue-50 text-blue-700 ring-blue-100' },
    emerald: { ring: 'bg-accent-50 text-accent-700 ring-accent-100' },
    teal:    { ring: 'bg-teal-50 text-teal-700 ring-teal-100' },
    amber:   { ring: 'bg-amber-50 text-amber-700 ring-amber-100' },
    rose:    { ring: 'bg-rose-50 text-rose-700 ring-rose-100' },
    cyan:    { ring: 'bg-brand-50 text-brand-700 ring-brand-100' },
};

export default function Portal() {
    const [hospitals, setHospitals] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        const fetchHospitals = async () => {
            try {
                const res = await apiClient.get('/public/hospitals');
                setHospitals(res.data || []);
            } catch (error) {
                toast.error('Failed to load hospital registry.');
            } finally {
                setIsLoading(false);
            }
        };
        fetchHospitals();

        localStorage.removeItem('hms_tenant_id');
        localStorage.removeItem('hms_tenant_name');
    }, []);

    const filteredHospitals = hospitals.filter((h) =>
        h.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        h.domain.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const handleSelectTenant = (tenant) => {
        localStorage.setItem('hms_tenant_id', tenant.db_name);
        localStorage.setItem('hms_tenant_name', tenant.name);
        toast.success(`Connected to ${tenant.name}`);
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-ink-50 text-ink-900 font-sans">
            {/* ============== Floating navbar ============== */}
            <header className="fixed top-4 inset-x-4 z-50">
                <div className="max-w-7xl mx-auto bg-white/85 backdrop-blur-xl border border-ink-200/70 rounded-2xl shadow-soft px-4 sm:px-6 py-3 flex items-center justify-between">
                    <Link to="/" className="flex items-center cursor-pointer" aria-label="MediFleet home">
                        <Logo variant="full" size={32} label="MediFleet" />
                    </Link>
                    <nav className="hidden md:flex items-center gap-1">
                        <Link to="/" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors cursor-pointer">Home</Link>
                        <Link to="/patient" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors cursor-pointer">Patient portal</Link>
                        <Link to="/superadmin/login" className="px-3 py-2 text-sm font-medium text-ink-600 hover:text-ink-900 transition-colors cursor-pointer">Platform</Link>
                    </nav>
                    <button
                        type="button"
                        onClick={() => document.getElementById('directory')?.scrollIntoView({ behavior: 'smooth' })}
                        className="btn-primary text-xs cursor-pointer"
                    >
                        Find my hospital <ArrowRight size={14} />
                    </button>
                </div>
            </header>

            {/* ============== Hero ============== */}
            <section className="relative pt-32 pb-12 sm:pt-40 sm:pb-16 overflow-hidden">
                <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute inset-0 bg-aurora" />
                    <div className="absolute inset-0 bg-grid-faint bg-grid-faint opacity-50" />
                    <div className="absolute -top-24 -right-24 w-[36rem] h-[36rem] bg-brand-300/20 rounded-full blur-[120px]" />
                    <div className="absolute -bottom-32 -left-24 w-[32rem] h-[32rem] bg-accent-300/20 rounded-full blur-[120px]" />
                </div>

                <div className="relative max-w-5xl mx-auto px-6 text-center animate-slide-up">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/80 ring-1 ring-brand-200 text-2xs font-semibold uppercase tracking-[0.16em] text-brand-700">
                        <Sparkles size={12} className="text-teal-500" />
                        Hospital workspace selector
                    </span>
                    <h1 className="mt-6 text-3xl sm:text-5xl font-semibold tracking-tightest leading-[1.05]">
                        Pick your{' '}
                        <span className="text-gradient-brand">hospital</span>{' '}
                        to sign in.
                    </h1>
                    <p className="mt-5 text-base sm:text-lg text-ink-600 leading-relaxed max-w-2xl mx-auto">
                        Every hospital on MediFleet runs on its own dedicated database. Find your
                        organization below — we'll connect you to its workspace.
                    </p>

                    {/* Inline search */}
                    <form
                        onSubmit={(e) => e.preventDefault()}
                        className="mt-8 max-w-xl mx-auto"
                        role="search"
                    >
                        <label htmlFor="hospital-search" className="sr-only">
                            Search for your hospital
                        </label>
                        <div className="relative">
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-ink-400" size={20} aria-hidden="true" />
                            <input
                                id="hospital-search"
                                type="search"
                                placeholder="Hospital name or domain (e.g. mayoclinic.hms.co.ke)"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-12 pr-12 py-3.5 bg-white border border-ink-200 rounded-2xl text-ink-900 placeholder-ink-400 shadow-soft focus:outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15 transition-all text-base"
                                autoComplete="off"
                            />
                            {searchQuery && (
                                <button
                                    type="button"
                                    onClick={() => setSearchQuery('')}
                                    aria-label="Clear search"
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors cursor-pointer"
                                >
                                    <X size={16} />
                                </button>
                            )}
                        </div>
                    </form>

                    {/* Trust strip */}
                    <div className="mt-10 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 text-xs text-ink-500">
                        <Trust icon={<Lock size={14} className="text-brand-600" />} label="HttpOnly JWT · CSRF" />
                        <Trust icon={<ShieldCheck size={14} className="text-teal-600" />} label="KDPA aligned" />
                        <Trust icon={<Globe2 size={14} className="text-accent-600" />} label="Database per tenant" />
                    </div>
                </div>
            </section>

            {/* ============== Hospital directory ============== */}
            <section id="directory" className="relative pb-16 sm:pb-24 -mt-2">
                <div className="max-w-7xl mx-auto px-6">
                    <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
                        <div>
                            <span className="section-eyebrow">Directory</span>
                            <h2 className="mt-1 text-2xl sm:text-3xl font-semibold tracking-tight text-ink-900">
                                {isLoading
                                    ? 'Scanning global registry…'
                                    : `${filteredHospitals.length} ${filteredHospitals.length === 1 ? 'hospital' : 'hospitals'} available`}
                            </h2>
                            <p className="mt-1 text-sm text-ink-500">
                                Click a card to connect to its instance, then sign in with your staff credentials.
                            </p>
                        </div>
                        {!isLoading && (
                            <div className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500">
                                Showing {filteredHospitals.length} of {hospitals.length}
                            </div>
                        )}
                    </div>

                    {isLoading ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                            {Array.from({ length: 6 }).map((_, i) => (
                                <div key={i} className="bg-white border border-ink-200/70 rounded-2xl p-5 animate-pulse-soft">
                                    <div className="w-10 h-10 rounded-xl bg-ink-100" />
                                    <div className="mt-4 h-4 w-2/3 rounded bg-ink-100" />
                                    <div className="mt-2 h-3 w-1/2 rounded bg-ink-100/70" />
                                    <div className="mt-6 h-3 w-1/3 rounded bg-ink-100/60" />
                                </div>
                            ))}
                        </div>
                    ) : filteredHospitals.length > 0 ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredHospitals.map((tenant) => {
                                const chip = TENANT_CHIP[tenant.theme_color] || TENANT_CHIP.cyan;
                                return (
                                    <button
                                        key={tenant.id}
                                        onClick={() => handleSelectTenant(tenant)}
                                        className="group text-left bg-white border border-ink-200/70 hover:border-brand-300 rounded-2xl p-5 shadow-soft hover:shadow-elevated transition-all duration-200 flex flex-col justify-between min-h-[12rem] cursor-pointer focus-visible:ring-4 focus-visible:ring-brand-500/20 focus-visible:border-brand-500"
                                    >
                                        <div>
                                            <div className="flex items-start justify-between mb-4">
                                                <div className={`w-11 h-11 rounded-xl flex items-center justify-center ring-1 ring-inset ${chip.ring}`}>
                                                    <Building2 size={18} />
                                                </div>
                                                {tenant.is_premium && (
                                                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-accent-50 ring-1 ring-inset ring-accent-100 text-accent-700 text-2xs font-semibold uppercase tracking-wider">
                                                        <Sparkles size={10} /> Premium
                                                    </span>
                                                )}
                                            </div>
                                            <h3 className="text-base font-semibold text-ink-900 group-hover:text-brand-700 transition-colors tracking-tight">
                                                {tenant.name}
                                            </h3>
                                            <p className="text-xs text-ink-500 mt-1 truncate font-mono">{tenant.domain}</p>
                                        </div>
                                        <div className="mt-5 flex items-center justify-between text-xs font-semibold text-ink-500 group-hover:text-brand-700 transition-colors">
                                            <span className="inline-flex items-center gap-1.5">
                                                <CheckCircle2 size={12} className="text-accent-500" /> Active instance
                                            </span>
                                            <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="bg-white border border-dashed border-ink-300 rounded-2xl p-12 text-center">
                            <div className="w-14 h-14 rounded-2xl bg-brand-50 ring-1 ring-brand-100 text-brand-600 mx-auto flex items-center justify-center mb-4">
                                <Building2 size={24} />
                            </div>
                            <h3 className="text-base font-semibold text-ink-900">No matches for &ldquo;{searchQuery}&rdquo;</h3>
                            <p className="text-sm text-ink-500 mt-1 max-w-md mx-auto">
                                Double-check the spelling, or contact your system administrator if your hospital isn't listed yet.
                            </p>
                            <button
                                type="button"
                                onClick={() => setSearchQuery('')}
                                className="mt-5 btn-secondary cursor-pointer"
                            >
                                <X size={14} /> Clear search
                            </button>
                        </div>
                    )}
                </div>
            </section>

            {/* ============== Other paths card row ============== */}
            <section className="pb-20 sm:pb-28">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="grid md:grid-cols-3 gap-4">
                        <PathCard
                            to="/patient"
                            tone="teal"
                            icon={<HeartPulse size={18} />}
                            title="I'm a patient"
                            body="Look up appointments, lab results, prescriptions, and bills."
                            cta="Open Patient Portal"
                        />
                        <PathCard
                            to="/superadmin/login"
                            tone="warning"
                            icon={<ShieldCheck size={18} />}
                            title="Platform team"
                            body="Manage tenants, billing, and platform-wide settings."
                            cta="Console sign-in"
                        />
                        <PathCard
                            to="/"
                            tone="brand"
                            icon={<Sparkles size={18} />}
                            title="New to MediFleet?"
                            body="Read about the platform, modules, and security posture."
                            cta="Visit landing page"
                        />
                    </div>
                </div>
            </section>

            {/* ============== Footer ============== */}
            <footer className="border-t border-ink-200/70 bg-white/60 backdrop-blur-md">
                <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
                    <Logo variant="full" size={28} />
                    <p className="text-xs text-ink-500 uppercase tracking-[0.18em]">
                        &copy; {new Date().getFullYear()} MediFleet &mdash; Multi-tenant clinical cloud
                    </p>
                    <div className="flex items-center gap-4 text-xs text-ink-500">
                        <Link to="/" className="hover:text-brand-700 transition-colors cursor-pointer">Home</Link>
                        <Link to="/patient" className="hover:text-brand-700 transition-colors cursor-pointer">Patient portal</Link>
                        <Link to="/superadmin/login" className="hover:text-brand-700 transition-colors cursor-pointer">Platform</Link>
                    </div>
                </div>
            </footer>
        </div>
    );
}

/* ─────────────────────────────────────────────────────────────────────────── */

function Trust({ icon, label }) {
    return (
        <span className="inline-flex items-center gap-2 font-medium text-ink-600">
            {icon}{label}
        </span>
    );
}

function PathCard({ to, icon, title, body, cta, tone }) {
    const ring =
        tone === 'brand'   ? 'bg-brand-50 text-brand-700 ring-brand-100'
      : tone === 'teal'    ? 'bg-teal-50 text-teal-700 ring-teal-100'
      : tone === 'warning' ? 'bg-amber-50 text-amber-700 ring-amber-100'
                           : 'bg-accent-50 text-accent-700 ring-accent-100';
    return (
        <Link
            to={to}
            className="group bg-white border border-ink-200/70 hover:border-brand-300 rounded-2xl p-5 shadow-soft hover:shadow-elevated transition-all cursor-pointer"
        >
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center ring-1 ring-inset ${ring}`}>
                {icon}
            </div>
            <h3 className="mt-4 text-base font-semibold tracking-tight text-ink-900">{title}</h3>
            <p className="mt-1.5 text-sm text-ink-600 leading-relaxed">{body}</p>
            <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-brand-700">
                {cta} <ChevronRight size={12} className="transition-transform group-hover:translate-x-0.5" />
            </div>
        </Link>
    );
}
