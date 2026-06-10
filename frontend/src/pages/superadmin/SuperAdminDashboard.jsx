import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import {
    Activity, Building2, CreditCard, Users, TrendingUp, LayoutDashboard,
    AlertTriangle, ArrowUpRight, ArrowDownRight, Crown, LifeBuoy, RefreshCw,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin Global Overview.                                               */
/*                                                                            */
/*  Fetches /api/public/superadmin/overview which aggregates tenant counts,   */
/*  MRR/ARR, 30-day growth, active user totals across tenants, and ticket     */
/*  queue depth. Falls back to a skeleton while loading and to an inline      */
/*  warning if the backend partially fails (e.g. a single tenant DB is        */
/*  unreachable — the rest of the metrics stay accurate).                     */
/* ────────────────────────────────────────────────────────────────────────── */

const TILE_ACCENTS = {
    brand:  'bg-brand-50  text-brand-700  ring-brand-100  dark:bg-brand-500/10  dark:text-brand-300  dark:ring-brand-500/20',
    teal:   'bg-teal-50   text-teal-700   ring-teal-100   dark:bg-teal-500/10   dark:text-teal-300   dark:ring-teal-500/20',
    accent: 'bg-accent-50 text-accent-700 ring-accent-100 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/20',
    amber:  'bg-amber-50  text-amber-700  ring-amber-100  dark:bg-amber-500/10  dark:text-amber-300  dark:ring-amber-500/20',
};

const KES = (n) => `KES ${Number(n || 0).toLocaleString('en-KE')}`;

const formatRelative = (iso) => {
    if (!iso) return '—';
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 30) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
};

export default function SuperAdminDashboard() {
    const navigate = useNavigate();
    const [overview, setOverview] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isError, setIsError] = useState(false);

    const fetchOverview = async () => {
        setIsLoading(true);
        setIsError(false);
        try {
            const res = await apiClient.get('/public/superadmin/overview');
            setOverview(res.data);
        } catch (_e) {
            setIsError(true);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchOverview(); }, []);

    const tiles = useMemo(() => {
        if (!overview) return [];
        return [
            {
                icon: Building2,
                label: 'Active tenants',
                value: overview.tenants?.active ?? 0,
                sub: `${overview.tenants?.premium ?? 0} premium · ${overview.tenants?.standard ?? 0} standard`,
                accent: 'brand',
                onClick: () => navigate('/superadmin/tenants'),
            },
            {
                icon: Users,
                label: 'Total active users',
                value: (overview.users?.total_active ?? 0).toLocaleString(),
                sub: overview.users?.errors?.length
                    ? `${overview.users.errors.length} tenant(s) unreachable`
                    : 'across all tenant databases',
                accent: 'teal',
            },
            {
                icon: CreditCard,
                label: 'Monthly recurring revenue',
                value: KES(overview.revenue?.mrr),
                sub: `${KES(overview.revenue?.arr)} ARR projected`,
                accent: 'accent',
                onClick: () => navigate('/superadmin/billing'),
            },
            {
                icon: TrendingUp,
                label: 'Growth (30d)',
                value: `${overview.growth?.percent ?? 0}%`,
                sub: `${overview.growth?.new_tenants ?? 0} new tenants in window`,
                accent: 'amber',
                growth: overview.growth?.percent ?? 0,
            },
        ];
    }, [overview, navigate]);

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={LayoutDashboard}
                title="Global Overview"
                subtitle="Real-time platform metrics and revenue telemetry across all tenants."
                tone="brand"
                actions={
                    <button
                        type="button"
                        onClick={fetchOverview}
                        className="btn-secondary cursor-pointer"
                        disabled={isLoading}
                    >
                        <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} aria-hidden="true" />
                        Refresh
                    </button>
                }
            />

            {/* Inline partial-data warning. Shown when at least one tenant DB
                failed to count users — the rest of the metrics are still good. */}
            {overview?.users?.errors?.length > 0 && (
                <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-amber-900 dark:text-amber-200 rounded-xl p-3 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
                    <div>
                        <p className="font-semibold uppercase tracking-[0.14em] text-2xs text-amber-800 dark:text-amber-300">Partial data</p>
                        <p className="mt-0.5">
                            User counts could not be aggregated for {overview.users.errors.length} tenant{overview.users.errors.length === 1 ? '' : 's'}.
                            The shown total excludes them. Check the affected database{overview.users.errors.length === 1 ? '' : 's'}:{' '}
                            <span className="font-mono">{overview.users.errors.map(e => e.tenant).join(', ')}</span>
                        </p>
                    </div>
                </div>
            )}

            {isError && (
                <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-rose-900 dark:text-rose-200 rounded-xl p-3 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="text-rose-700 dark:text-rose-400 shrink-0 mt-0.5" aria-hidden="true" />
                    <div>
                        <p className="font-semibold uppercase tracking-[0.14em] text-2xs text-rose-800 dark:text-rose-300">Could not load overview</p>
                        <p className="mt-0.5">The platform telemetry endpoint failed. Try refreshing in a moment.</p>
                    </div>
                </div>
            )}

            {/* KPI tiles */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {isLoading && !overview
                    ? [0, 1, 2, 3].map((i) => <StatSkeleton key={i} />)
                    : tiles.map(({ icon: Icon, label, value, sub, accent, onClick, growth }) => {
                        const TileEl = onClick ? 'button' : 'div';
                        return (
                            <TileEl
                                key={label}
                                type={onClick ? 'button' : undefined}
                                onClick={onClick}
                                className={`stat-tile text-left ${onClick ? 'cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2' : ''}`}
                            >
                                <div className={`stat-icon ${TILE_ACCENTS[accent] || TILE_ACCENTS.brand}`} aria-hidden="true">
                                    <Icon size={18} />
                                </div>
                                <div className="min-w-0">
                                    <p className="stat-label">{label}</p>
                                    <p className="stat-value truncate">{value}</p>
                                    {sub && (
                                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-1 flex items-center gap-1">
                                            {growth !== undefined && (
                                                growth >= 0
                                                    ? <ArrowUpRight size={11} className="text-accent-600 dark:text-accent-400" aria-hidden="true" />
                                                    : <ArrowDownRight size={11} className="text-rose-600 dark:text-rose-400" aria-hidden="true" />
                                            )}
                                            <span className="truncate">{sub}</span>
                                        </p>
                                    )}
                                </div>
                            </TileEl>
                        );
                    })
                }
            </div>

            {/* Secondary row: recent tenants + ticket queue depth */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="card overflow-hidden lg:col-span-2">
                    <div className="px-5 py-3 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                            <Building2 size={15} className="text-brand-700 dark:text-brand-400 shrink-0" aria-hidden="true" />
                            <h2 className="font-semibold text-ink-900 dark:text-white text-sm tracking-tight">Recently provisioned</h2>
                        </div>
                        <button
                            type="button"
                            onClick={() => navigate('/superadmin/tenants')}
                            className="text-2xs font-semibold text-brand-700 dark:text-brand-400 hover:text-brand-800 dark:hover:text-brand-300 uppercase tracking-wider cursor-pointer"
                        >
                            View all
                        </button>
                    </div>
                    {isLoading && !overview ? (
                        <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                            {[0, 1, 2].map(i => <RowSkeleton key={i} />)}
                        </ul>
                    ) : overview?.recent_tenants?.length ? (
                        <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                            {overview.recent_tenants.map(t => (
                                <li key={t.tenant_id} className="px-5 py-3 flex items-center justify-between gap-3 hover:bg-ink-50/60 dark:hover:bg-ink-800/50 transition-colors">
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-semibold text-ink-900 dark:text-white truncate">{t.name}</span>
                                            {t.is_premium && (
                                                <span className="badge-warn inline-flex items-center gap-1">
                                                    <Crown size={10} aria-hidden="true" /> Premium
                                                </span>
                                            )}
                                            {!t.is_active && (
                                                <span className="badge-neutral">Suspended</span>
                                            )}
                                        </div>
                                        <p className="text-xs text-ink-500 dark:text-ink-400 font-mono truncate mt-0.5">{t.domain}</p>
                                    </div>
                                    <span className="text-xs text-ink-500 dark:text-ink-400 shrink-0 tabular-nums" title={t.created_at ? new Date(t.created_at).toLocaleString() : ''}>
                                        {formatRelative(t.created_at)}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <div className="p-8 text-center text-sm text-ink-500 dark:text-ink-400">
                            No tenants provisioned yet.
                        </div>
                    )}
                </div>

                <div className="card overflow-hidden">
                    <div className="px-5 py-3 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex items-center gap-2">
                        <LifeBuoy size={15} className="text-brand-700 dark:text-brand-400 shrink-0" aria-hidden="true" />
                        <h2 className="font-semibold text-ink-900 dark:text-white text-sm tracking-tight">Support queue</h2>
                    </div>
                    {isLoading && !overview ? (
                        <div className="p-6 space-y-3">
                            <div className="h-8 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
                            <div className="h-8 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
                        </div>
                    ) : (
                        <div className="p-5 space-y-3">
                            <button
                                type="button"
                                onClick={() => navigate('/superadmin/support')}
                                className="w-full flex items-center justify-between p-3 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 hover:bg-blue-100 dark:hover:bg-blue-500/20 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                            >
                                <span className="text-sm font-medium text-blue-900 dark:text-blue-300">Open</span>
                                <span className="text-2xl font-semibold text-blue-900 dark:text-blue-300 tabular-nums">{overview?.tickets?.open ?? 0}</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => navigate('/superadmin/support')}
                                className="w-full flex items-center justify-between p-3 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                            >
                                <span className="text-sm font-medium text-amber-900 dark:text-amber-300">In progress</span>
                                <span className="text-2xl font-semibold text-amber-900 dark:text-amber-300 tabular-nums">{overview?.tickets?.in_progress ?? 0}</span>
                            </button>
                            <button
                                type="button"
                                onClick={() => navigate('/superadmin/support')}
                                className="w-full text-xs font-semibold text-brand-700 dark:text-brand-400 hover:text-brand-800 dark:hover:text-brand-300 uppercase tracking-wider mt-2 cursor-pointer"
                            >
                                Open support inbox →
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Tenant-status mini-distribution */}
            {overview && (
                <div className="card p-5">
                    <div className="flex items-center justify-between mb-4 gap-3">
                        <div>
                            <h2 className="font-semibold text-ink-900 dark:text-white text-sm tracking-tight">Fleet composition</h2>
                            <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">Distribution across the {overview.tenants.total} provisioned tenant{overview.tenants.total === 1 ? '' : 's'}.</p>
                        </div>
                        <Activity size={16} className="text-brand-700 dark:text-brand-400 shrink-0" aria-hidden="true" />
                    </div>
                    <DistroBar
                        segments={[
                            { label: 'Premium',   value: overview.tenants.premium,   className: 'bg-amber-500' },
                            { label: 'Standard',  value: overview.tenants.standard,  className: 'bg-brand-500' },
                            { label: 'Suspended', value: overview.tenants.suspended, className: 'bg-ink-300' },
                        ]}
                    />
                </div>
            )}
        </div>
    );
}

function StatSkeleton() {
    return (
        <div className="stat-tile">
            <div className="size-11 rounded-xl bg-ink-100 dark:bg-ink-800 animate-pulse" />
            <div className="space-y-2 flex-1">
                <div className="h-3 w-20 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
                <div className="h-6 w-28 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
                <div className="h-3 w-32 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
            </div>
        </div>
    );
}

function RowSkeleton() {
    return (
        <li className="px-5 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-1.5">
                <div className="h-4 w-40 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
                <div className="h-3 w-28 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
            </div>
            <div className="h-3 w-16 bg-ink-100 dark:bg-ink-800 rounded animate-pulse" />
        </li>
    );
}

function DistroBar({ segments }) {
    const total = segments.reduce((acc, s) => acc + (s.value || 0), 0);
    if (total === 0) {
        return <p className="text-xs text-ink-500 dark:text-ink-400 italic">No tenants provisioned yet.</p>;
    }
    return (
        <div>
            {/* Composite CSS bar chart presented as one image; no native <img> fits. */}
            {/* react-doctor-disable-next-line react-doctor/prefer-tag-over-role */}
            <div className="h-2.5 bg-ink-100 dark:bg-ink-800 rounded-full overflow-hidden flex" role="img" aria-label="Tenant composition">
                {segments.map((s) => {
                    const pct = total > 0 ? (s.value / total) * 100 : 0;
                    if (pct === 0) return null;
                    return (
                        <div
                            key={s.label}
                            className={s.className}
                            style={{ width: `${pct}%` }}
                            title={`${s.label}: ${s.value} (${pct.toFixed(1)}%)`}
                        />
                    );
                })}
            </div>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-ink-700 dark:text-ink-200">
                {segments.map((s) => (
                    <li key={s.label} className="flex items-center gap-2">
                        <span className={`size-2.5 rounded-sm ${s.className}`} aria-hidden="true" />
                        <span className="font-medium">{s.label}</span>
                        <span className="text-ink-500 dark:text-ink-400 tabular-nums">{s.value}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
