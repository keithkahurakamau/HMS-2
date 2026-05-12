import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
    ShieldAlert, Activity, Eye, EyeOff,
    Stethoscope, HeartPulse, Lock, ArrowRight
} from 'lucide-react';
import ChangePassword from './ChangePassword';
import { TenantLogo } from '../components/Logo';
import { useBranding } from '../context/BrandingContext';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const { login, mustChangePassword, pendingUserId, clearMustChange } = useAuth();
    const navigate = useNavigate();
    const { branding } = useBranding();

    const tenantName = localStorage.getItem('hms_tenant_name') || 'MediFleet';
    const tenantId = localStorage.getItem('hms_tenant_id');
    const hasTenantBg = !!branding.background_data_url;

    // If the operator reached /login by typing the URL directly, we have no
    // tenant context — the API client wouldn't attach X-Tenant-ID and the
    // login backend would 400. Bounce them to the Portal so they pick a
    // hospital first.
    useEffect(() => {
        if (!tenantId) {
            toast('Pick your hospital first.', { icon: 'ℹ️' });
            navigate('/portal', { replace: true });
        }
    }, [tenantId, navigate]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!tenantId) {
            toast.error('No hospital selected. Choose one from the portal.');
            navigate('/portal', { replace: true });
            return;
        }
        setIsSubmitting(true);
        const result = await login(email, password);
        if (result?.success) {
            navigate('/app/dashboard');
        }
        setIsSubmitting(false);
    };

    if (mustChangePassword && pendingUserId) {
        return <ChangePassword userId={pendingUserId} onSuccess={() => { clearMustChange(); }} />;
    }

    return (
        <div className="min-h-screen w-full grid lg:grid-cols-5 bg-ink-50">
            {/* ============== Brand panel (left, lg+) ============== */}
            <aside className="hidden lg:flex lg:col-span-2 relative overflow-hidden bg-brand-gradient text-white">
                {/* Tenant background image, when uploaded — overlaid under the gradient. */}
                {hasTenantBg && (
                    <div
                        className="absolute inset-0 bg-cover bg-center opacity-40 mix-blend-overlay pointer-events-none"
                        style={{ backgroundImage: `url("${branding.background_data_url}")` }}
                        aria-hidden="true"
                    />
                )}
                {/* Decorative mesh + grid */}
                <div className="absolute inset-0 bg-aurora opacity-80 pointer-events-none" />
                <div className="absolute inset-0 bg-grid opacity-[0.07] pointer-events-none" />
                <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-accent-400/20 blur-3xl pointer-events-none" />
                <div className="absolute -bottom-40 -left-20 w-[28rem] h-[28rem] rounded-full bg-brand-400/20 blur-3xl pointer-events-none" />

                <div className="relative z-10 flex flex-col justify-between w-full p-12 xl:p-16">
                    {/* Logo */}
                    <TenantLogo
                        src={branding.logo_data_url}
                        fallbackLabel={tenantName}
                        sublabel="Hospital workspace"
                        size={44}
                        tone="mono-light"
                    />

                    {/* Headline */}
                    <div className="max-w-md">
                        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 ring-1 ring-white/20 text-2xs font-semibold uppercase tracking-[0.14em] text-white/85">
                            <span className="w-1.5 h-1.5 rounded-full bg-accent-400 animate-pulse-soft" />
                            Clinical-grade workspace
                        </span>
                        <h1 className="mt-6 text-4xl xl:text-5xl font-semibold leading-[1.05] tracking-tight">
                            Care, coordinated.
                            <span className="block text-white/70 font-light mt-2">One platform for every shift.</span>
                        </h1>
                        <p className="mt-6 text-white/75 text-base leading-relaxed">
                            Sign in to access patient records, clinical workflows, billing, and pharmacy &mdash; all in one secure environment.
                        </p>
                    </div>

                    {/* Feature row */}
                    <div className="grid grid-cols-3 gap-4">
                        <Feature icon={<Stethoscope size={18} />} label="Clinical" />
                        <Feature icon={<HeartPulse size={18} />} label="Real-time" />
                        <Feature icon={<Lock size={18} />} label="HIPAA-aware" />
                    </div>
                </div>
            </aside>

            {/* ============== Form panel (right) ============== */}
            <main className="lg:col-span-3 flex flex-col justify-center items-center px-6 py-12 sm:px-10 relative">
                {/* Mobile brand bar */}
                <div className="lg:hidden w-full max-w-md mb-10">
                    <TenantLogo
                        src={branding.logo_data_url}
                        fallbackLabel={tenantName}
                        sublabel="Hospital workspace"
                        size={40}
                        tone="mono-dark"
                    />
                </div>

                <div className="w-full max-w-md animate-slide-up">
                    <div className="mb-8">
                        <span className="section-eyebrow">Welcome back</span>
                        <h2 className="mt-2 text-3xl font-semibold text-ink-900 tracking-tight">Sign in to your workspace</h2>
                        <p className="mt-2 text-sm text-ink-500">
                            Enter your credentials to continue. New here?{' '}
                            <Link to="/portal" className="text-brand-600 font-semibold hover:text-brand-700">View hospitals</Link>.
                        </p>
                    </div>

                    <form className="space-y-5" onSubmit={handleSubmit}>
                        <div>
                            <label htmlFor="email" className="label">Email address</label>
                            <input
                                id="email"
                                type="email"
                                required
                                autoComplete="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="input-lg"
                                placeholder="you@hospital.com"
                            />
                        </div>

                        <div>
                            <div className="flex items-baseline justify-between">
                                <label htmlFor="password" className="label">Password</label>
                                <Link to="/forgot-password" className="text-xs font-semibold text-brand-600 hover:text-brand-700">
                                    Forgot password?
                                </Link>
                            </div>
                            <div className="relative">
                                <input
                                    id="password"
                                    type={showPassword ? 'text' : 'password'}
                                    required
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="input-lg pr-11"
                                    placeholder="••••••••"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(s => !s)}
                                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors"
                                >
                                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="btn-primary w-full py-3 text-base group"
                        >
                            {isSubmitting ? (
                                <>
                                    <Activity className="animate-spin" size={18} />
                                    Authenticating&hellip;
                                </>
                            ) : (
                                <>
                                    Sign in
                                    <ArrowRight size={18} className="transition-transform group-hover:translate-x-0.5" />
                                </>
                            )}
                        </button>

                        <div className="flex items-center justify-center gap-2 pt-2 text-xs text-ink-500">
                            <ShieldAlert size={14} className="text-brand-500" />
                            Secured via HttpOnly JWT &mdash; encrypted in transit and at rest
                        </div>
                    </form>
                </div>

                <p className="mt-12 text-2xs text-ink-400 uppercase tracking-[0.16em]">
                    &copy; {new Date().getFullYear()} {tenantName}
                </p>
            </main>
        </div>
    );
}

function Feature({ icon, label }) {
    return (
        <div className="flex flex-col items-start gap-2 p-3 rounded-xl bg-white/[0.06] ring-1 ring-white/10 backdrop-blur-sm">
            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-white/90">
                {icon}
            </div>
            <span className="text-xs font-semibold text-white/85">{label}</span>
        </div>
    );
}
