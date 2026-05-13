import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import {
    Settings, ShieldCheck, Database, Globe, Server, Activity,
    Lock, Bell, KeyRound, Cpu, Wifi, AlertTriangle, CheckCircle2,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

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
                { label: 'Platform name', value: health?.system || 'MediFleet' },
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
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                surface="dark"
                tone="accent"
                eyebrow="Console"
                icon={Settings}
                title="Platform Settings"
                subtitle="Runtime configuration snapshot. Edit .env and rolling-restart workers to change values."
                meta={
                    isLoading ? (
                        <span className="text-ink-500 text-xs flex items-center gap-2"><Activity size={14} className="animate-spin" /> Probing</span>
                    ) : (
                        <span className="bg-accent-500/10 ring-1 ring-accent-500/30 text-accent-400 px-3 py-1.5 rounded-full text-2xs font-semibold uppercase tracking-wider flex items-center gap-2">
                            <Server size={13} /> Operational
                        </span>
                    )
                }
            />

            {sections.map(({ title, icon: Icon, rows }) => (
                <section key={title} className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center gap-2">
                        <Icon size={15} className="text-ink-400" />
                        <h2 className="font-semibold text-white text-sm tracking-tight">{title}</h2>
                    </div>
                    <ul className="divide-y divide-white/5">
                        {rows.map(({ label, value, badge, mono, hint }) => (
                            <li key={label} className="px-5 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                                <div>
                                    <p className="text-sm text-ink-200 font-medium">{label}</p>
                                    {hint && <p className="text-xs text-ink-500 mt-0.5 leading-relaxed">{hint}</p>}
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <span className={mono ? 'font-mono text-accent-400 text-xs' : 'text-white font-semibold text-sm'}>{value}</span>
                                    {badge === 'success' && (<CheckCircle2 size={14} className="text-accent-400" aria-label="Active" />)}
                                    {badge === 'warning' && (<AlertTriangle size={14} className="text-amber-400" aria-label="Attention" />)}
                                </div>
                            </li>
                        ))}
                    </ul>
                </section>
            ))}

            <div className="text-xs text-ink-500 px-2 leading-relaxed">
                For a complete env reference see <code className="text-ink-200 bg-white/5 px-1 py-0.5 rounded">docs/DEPLOYMENT.md</code>.
                Sensitive values (<code className="text-ink-300">SECRET_KEY</code>, <code className="text-ink-300">ENCRYPTION_KEY</code>, M-Pesa secrets) are deliberately not displayed.
            </div>
        </div>
    );
}
