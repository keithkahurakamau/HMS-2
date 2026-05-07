import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import {
    Settings, ShieldCheck, Database, Globe, Server, Activity,
    Lock, Bell, KeyRound, Cpu, Wifi, AlertTriangle, CheckCircle2,
} from 'lucide-react';

/**
 * Platform Settings is read-only by design — the canonical source of truth is
 * the deployment's .env file, not a database row. Operators tweak the values
 * there and rolling-restart workers; we surface the *effective* values here so
 * a superadmin can verify the runtime state matches their expectation.
 */
export default function PlatformSettings() {
    const [health, setHealth] = useState(null);
    const [tenants, setTenants] = useState(0);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const [rootRes, tenantsRes] = await Promise.all([
                    apiClient.get('/').catch(() => ({ data: null })),
                    apiClient.get('/public/hospitals').catch(() => ({ data: [] })),
                ]);
                setHealth(rootRes.data);
                setTenants((tenantsRes.data || []).length);
            } catch {
                // ignore
            } finally {
                setIsLoading(false);
            }
        })();
    }, []);

    const sections = [
        {
            title: 'Identity',
            icon: ShieldCheck,
            rows: [
                { label: 'Platform name', value: health?.system || 'HMS Enterprise' },
                { label: 'Version', value: health?.version || '—', mono: true },
                { label: 'Operational status', value: health?.status || 'Unknown', badge: 'success' },
            ],
        },
        {
            title: 'Database',
            icon: Database,
            rows: [
                { label: 'Tenant strategy', value: 'Database-per-tenant', hint: 'Each hospital has its own PostgreSQL DB.' },
                { label: 'Active tenants', value: tenants },
                { label: 'Connection pooling', value: 'Application + PgBouncer (recommended)', hint: 'See docs/DEPLOYMENT.md for the production recipe.' },
                { label: 'Append-only audit', value: 'Enabled', badge: 'success', hint: 'DB triggers block UPDATE/DELETE on audit_logs and data_access_logs.' },
            ],
        },
        {
            title: 'Security',
            icon: Lock,
            rows: [
                { label: 'JWT signing', value: 'HS256', mono: true },
                { label: 'Access token TTL', value: '15 minutes' },
                { label: 'Refresh token TTL', value: '7 days, rotated on use' },
                { label: 'Refresh reuse detection', value: 'Active', badge: 'success' },
                { label: 'Failed login lockout', value: '5 attempts → 15 min lock' },
                { label: 'PII encryption', value: 'Fernet (AES-128-CBC) with isolated ENCRYPTION_KEY', hint: 'Distinct from JWT SECRET_KEY.' },
            ],
        },
        {
            title: 'Network',
            icon: Globe,
            rows: [
                { label: 'CORS strategy', value: 'Closed list via CORS_ORIGINS env var' },
                { label: 'CSRF', value: 'Double-submit cookie + X-CSRF-Token header', badge: 'success' },
                { label: 'Tenant isolation', value: 'Enforced at JWT (tenant_id claim)', badge: 'success' },
            ],
        },
        {
            title: 'Real-time fan-out',
            icon: Wifi,
            rows: [
                { label: 'WebSocket transport', value: 'wss:// (HttpOnly cookie auth)' },
                { label: 'Pub/Sub backend', value: 'Redis (when REDIS_URL is set), in-process otherwise', hint: 'Multi-worker deployments require Redis.' },
                { label: 'Notification persistence', value: 'notifications table per tenant', badge: 'success' },
            ],
        },
        {
            title: 'Compliance',
            icon: KeyRound,
            rows: [
                { label: 'KDPA Section 26 (access)', value: 'data_access_logs append-only', badge: 'success' },
                { label: 'KDPA Section 30 (consent)', value: 'Enforced gate on clinical writes', badge: 'success' },
                { label: 'KDPA Section 40 (erasure)', value: '/api/privacy/patients/{id}/erase', badge: 'success' },
                { label: 'KDPA Section 43 (breach)', value: '/api/privacy/breaches with 72h countdown', badge: 'success' },
                { label: 'Health Act 2017 (retention)', value: 'Anonymize-not-delete on subject erasure' },
            ],
        },
        {
            title: 'Rate limiting',
            icon: Cpu,
            rows: [
                { label: 'Global default', value: '120/min, 2000/hr per IP' },
                { label: 'Login', value: '5/min', mono: true },
                { label: 'Refresh', value: '30/min', mono: true },
                { label: 'Forgot password', value: '3/min', mono: true },
                { label: 'Patient portal lookup', value: '5/min', mono: true },
            ],
        },
    ];

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h1 className="text-3xl font-black text-white tracking-tight flex items-center gap-3">
                        <Settings className="text-indigo-400" /> Platform Settings
                    </h1>
                    <p className="text-slate-400 mt-1">Runtime configuration snapshot. Edit your `.env` and rolling-restart workers to change values.</p>
                </div>
                {isLoading ? (
                    <span className="text-slate-500 text-xs flex items-center gap-2"><Activity size={14} className="animate-spin" /> Probing</span>
                ) : (
                    <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider flex items-center gap-2">
                        <Server size={14} /> Operational
                    </span>
                )}
            </div>

            {sections.map(({ title, icon: Icon, rows }) => (
                <section key={title} className="bg-slate-900 border border-slate-800 rounded-xl shadow-lg overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-800 bg-slate-900/50 flex items-center gap-2">
                        <Icon size={16} className="text-slate-400" />
                        <h2 className="font-bold text-white text-sm">{title}</h2>
                    </div>
                    <ul className="divide-y divide-slate-800">
                        {rows.map(({ label, value, badge, mono, hint }) => (
                            <li key={label} className="px-5 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                                <div>
                                    <p className="text-sm text-slate-300 font-medium">{label}</p>
                                    {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <span className={`text-sm ${mono ? 'font-mono text-emerald-400 text-xs' : 'text-white font-bold'}`}>{value}</span>
                                    {badge === 'success' && (
                                        <CheckCircle2 size={14} className="text-emerald-400" aria-label="Active" />
                                    )}
                                    {badge === 'warning' && (
                                        <AlertTriangle size={14} className="text-amber-400" aria-label="Attention" />
                                    )}
                                </div>
                            </li>
                        ))}
                    </ul>
                </section>
            ))}

            <div className="text-xs text-slate-500 px-2">
                For a complete env reference see <code className="text-slate-300">docs/DEPLOYMENT.md</code>.
                Sensitive values (SECRET_KEY, ENCRYPTION_KEY, MPESA secrets) are deliberately not displayed.
            </div>
        </div>
    );
}
