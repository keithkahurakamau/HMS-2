import React, { useState } from 'react';
import { useNavigate, Navigate, useLocation } from 'react-router-dom';
import { apiClient } from '../../api/client';
import {
    ShieldAlert, Activity, Eye, EyeOff, Lock, ArrowRight
} from 'lucide-react';
import toast from 'react-hot-toast';
import Logo from '../../components/Logo';

const TOKEN_KEY = 'hms_superadmin_token';
const NAME_KEY = 'hms_superadmin_name';
const EXPIRES_KEY = 'hms_superadmin_expires_at';

export const isSuperAdminAuthenticated = () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return false;
    const expiresAt = parseInt(localStorage.getItem(EXPIRES_KEY) || '0', 10);
    if (expiresAt && Date.now() >= expiresAt) {
        clearSuperAdminSession();
        return false;
    }
    return true;
};

export const clearSuperAdminSession = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(NAME_KEY);
    localStorage.removeItem(EXPIRES_KEY);
};

export default function SuperAdminLogin() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();

    if (isSuperAdminAuthenticated()) {
        const next = location.state?.from?.pathname || '/superadmin/dashboard';
        return <Navigate to={next} replace />;
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            const res = await apiClient.post('/public/superadmin/login', { email, password });
            const { access_token, full_name, expires_in } = res.data || {};
            if (!access_token) throw new Error('Missing token');
            localStorage.setItem(TOKEN_KEY, access_token);
            if (full_name) localStorage.setItem(NAME_KEY, full_name);
            // Server tells us the TTL — record absolute expiry so the guard can
            // pre-empt 401s when the operator returns to the tab later.
            const ttlSeconds = typeof expires_in === 'number' ? expires_in : 20 * 60;
            localStorage.setItem(EXPIRES_KEY, String(Date.now() + ttlSeconds * 1000));
            toast.success('Superadmin authenticated');
            const next = location.state?.from?.pathname || '/superadmin/dashboard';
            navigate(next, { replace: true });
        } catch (err) {
            const detail = err.response?.data?.detail || 'Invalid superadmin credentials';
            toast.error(detail);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen w-full bg-ink-950 text-white flex items-center justify-center p-6 relative overflow-hidden">
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute -top-40 -left-32 w-[36rem] h-[36rem] bg-amber-500/10 rounded-full blur-[120px]" />
                <div className="absolute -bottom-40 -right-32 w-[36rem] h-[36rem] bg-brand-500/10 rounded-full blur-[120px]" />
                <div className="absolute inset-0 bg-grid opacity-[0.05]" />
            </div>

            <div className="relative z-10 w-full max-w-md animate-slide-up">
                <div className="flex items-center justify-between mb-8">
                    <Logo variant="full" size={36} label="MediFleet" sublabel="Platform Console" tone="mono-light" />
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/15 ring-1 ring-amber-400/30">
                        <ShieldAlert size={11} className="text-amber-300" />
                        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-300">Restricted</span>
                    </span>
                </div>

                <div className="bg-white/[0.04] backdrop-blur-2xl border border-white/10 rounded-3xl p-8 shadow-elevated">
                    <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 ring-1 ring-amber-500/20 text-2xs font-semibold uppercase tracking-[0.14em] text-amber-300">
                        <Lock size={12} /> Restricted access
                    </span>
                    <h2 className="mt-4 text-2xl font-semibold tracking-tight">Superadmin sign-in</h2>
                    <p className="mt-2 text-sm text-ink-400">
                        This console manages tenants, billing, and platform-wide settings. Authentication is required.
                    </p>

                    <form className="space-y-5 mt-7" onSubmit={handleSubmit}>
                        <div>
                            <label htmlFor="sa-email" className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-400">Email</label>
                            <input
                                id="sa-email"
                                type="email"
                                required
                                autoComplete="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="superadmin@hms.co.ke"
                                className="mt-1.5 w-full bg-ink-950/60 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-ink-500 focus:outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/20 transition-all"
                            />
                        </div>

                        <div>
                            <label htmlFor="sa-password" className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-400">Password</label>
                            <div className="relative mt-1.5">
                                <input
                                    id="sa-password"
                                    type={showPassword ? 'text' : 'password'}
                                    required
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    className="w-full bg-ink-950/60 border border-white/10 rounded-xl px-4 py-3 pr-11 text-white placeholder-ink-500 focus:outline-none focus:border-amber-500 focus:ring-4 focus:ring-amber-500/20 transition-all"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword((s) => !s)}
                                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-ink-400 hover:text-white hover:bg-white/5 transition-colors"
                                >
                                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 text-white font-semibold tracking-tight shadow-glow hover:from-amber-400 hover:to-orange-500 disabled:opacity-60 disabled:cursor-not-allowed transition-all group"
                        >
                            {isSubmitting ? (
                                <>
                                    <Activity className="animate-spin" size={18} />
                                    Verifying&hellip;
                                </>
                            ) : (
                                <>
                                    Enter console
                                    <ArrowRight size={18} className="transition-transform group-hover:translate-x-0.5" />
                                </>
                            )}
                        </button>

                        <div className="flex items-center justify-center gap-2 pt-2 text-xs text-ink-500">
                            <ShieldAlert size={14} className="text-amber-400" />
                            Platform-level credentials only &mdash; not a hospital workspace login
                        </div>
                    </form>
                </div>

                <p className="mt-8 text-center text-2xs text-ink-500 uppercase tracking-[0.18em]">
                    MediFleet &middot; Platform back-office
                </p>
            </div>
        </div>
    );
}
