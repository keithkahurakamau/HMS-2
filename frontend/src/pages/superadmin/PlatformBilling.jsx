import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    CreditCard, TrendingUp, Banknote, Users, Building2, Crown,
    ArrowUpRight, ArrowDownRight, Search, ShieldCheck, Activity, Check,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

const TIER_PRICING = {
    Premium: 49500,
    Standard: 18500,
};

export default function PlatformBilling() {
    const [tenants, setTenants] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [updatingId, setUpdatingId] = useState(null);

    const fetchTenants = async () => {
        setIsLoading(true);
        try {
            const res = await apiClient.get('/public/hospitals');
            setTenants(res.data || []);
        } catch (e) {
            toast.error('Failed to load tenants');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchTenants(); }, []);

    const stats = useMemo(() => {
        const premium = tenants.filter(t => t.is_premium).length;
        const standard = tenants.length - premium;
        const mrr = premium * TIER_PRICING.Premium + standard * TIER_PRICING.Standard;
        return {
            total: tenants.length,
            premium,
            standard,
            mrr,
            arr: mrr * 12,
        };
    }, [tenants]);

    const filtered = tenants.filter(t =>
        t.name.toLowerCase().includes(search.toLowerCase()) ||
        t.domain.toLowerCase().includes(search.toLowerCase())
    );

    const toggleTier = async (tenant) => {
        const tenantId = String(tenant.id).replace(/^tenant_/, '');
        setUpdatingId(tenant.id);
        try {
            await apiClient.patch(`/public/hospitals/${tenantId}`, {
                is_premium: !tenant.is_premium,
            });
            toast.success(`${tenant.name} → ${tenant.is_premium ? 'Standard' : 'Premium'}`);
            fetchTenants();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Update failed');
        } finally {
            setUpdatingId(null);
        }
    };

    const KES = (n) => `KES ${(n || 0).toLocaleString('en-KE')}`;

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={CreditCard}
                title="Billing & Subscriptions"
                subtitle="Track platform revenue, manage tenant subscription tiers, and project growth."
                tone="accent"
            />

            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard
                    icon={Banknote}
                    label="Monthly Recurring Revenue"
                    value={KES(stats.mrr)}
                    sub={`${stats.total} tenants`}
                    accent="accent"
                />
                <KpiCard
                    icon={TrendingUp}
                    label="Annual Run Rate"
                    value={KES(stats.arr)}
                    sub="Projected at current tiers"
                    accent="brand"
                />
                <KpiCard
                    icon={Crown}
                    label="Premium Subscribers"
                    value={stats.premium}
                    sub={`${stats.total ? Math.round(stats.premium / stats.total * 100) : 0}% of fleet`}
                    accent="amber"
                />
                <KpiCard
                    icon={Users}
                    label="Standard Subscribers"
                    value={stats.standard}
                    sub="Eligible for upgrade"
                    accent="teal"
                />
            </div>

            {/* Tier pricing card */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <PricingCard
                    tier="Standard"
                    price={KES(TIER_PRICING.Standard)}
                    seats={stats.standard}
                    features={['Patients & Clinical Desk', 'Billing & M-Pesa', 'Email support', 'Up to 50 staff seats']}
                    highlight={false}
                />
                <PricingCard
                    tier="Premium"
                    price={KES(TIER_PRICING.Premium)}
                    seats={stats.premium}
                    features={['Everything in Standard', 'Unlimited modules', 'Priority Slack support', 'Custom integrations', 'Unlimited seats']}
                    highlight
                />
            </div>

            {/* Tenant subscription table */}
            <div className="card overflow-hidden">
                <div className="p-4 border-b border-ink-200 flex flex-col sm:flex-row sm:flex-wrap sm:justify-between sm:items-center gap-3">
                    <h2 className="text-sm font-semibold text-ink-900 tracking-tight">Tenant subscriptions</h2>
                    <div className="relative w-full sm:w-auto">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                        <label htmlFor="billing-search" className="sr-only">Search tenants</label>
                        <input
                            id="billing-search"
                            type="search"
                            placeholder="Search tenants…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full sm:w-64 bg-white border border-ink-200 rounded-lg pl-9 pr-3 py-1.5 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                        />
                    </div>
                </div>

                {/* Desktop table */}
                <div className="hidden md:block overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-ink-50 text-ink-600 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-6 py-3">Tenant</th>
                                <th className="px-6 py-3">Tier</th>
                                <th className="px-6 py-3">Monthly fee</th>
                                <th className="px-6 py-3">Status</th>
                                <th className="px-6 py-3 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100 text-ink-700">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500">
                                    <Activity size={16} className="inline animate-spin mr-2 text-brand-600" aria-hidden="true" />Loading…
                                </td></tr>
                            ) : filtered.length === 0 ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500">No tenants match your filter.</td></tr>
                            ) : filtered.map(tenant => (
                                <tr key={tenant.id} className="hover:bg-ink-50 transition-colors">
                                    <td className="px-6 py-3">
                                        <div className="flex items-center gap-2">
                                            <Building2 size={16} className="text-ink-400" aria-hidden="true" />
                                            <div className="min-w-0">
                                                <p className="font-semibold text-ink-900 truncate">{tenant.name}</p>
                                                <p className="text-xs text-ink-500 font-mono truncate">{tenant.domain}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-3">
                                        {tenant.is_premium ? (
                                            <span className="badge-warn inline-flex items-center gap-1">
                                                <Crown size={10} aria-hidden="true" /> Premium
                                            </span>
                                        ) : (
                                            <span className="badge-neutral">Standard</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3 font-mono text-xs text-ink-700">
                                        {KES(tenant.is_premium ? TIER_PRICING.Premium : TIER_PRICING.Standard)}
                                    </td>
                                    <td className="px-6 py-3">
                                        <span className="inline-flex items-center gap-1.5 text-accent-700 text-xs font-semibold">
                                            <span className="w-1.5 h-1.5 rounded-full bg-accent-500 animate-pulse-soft" aria-hidden="true"></span>
                                            Active
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 text-right">
                                        <button
                                            type="button"
                                            onClick={() => toggleTier(tenant)}
                                            disabled={updatingId === tenant.id}
                                            className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors inline-flex items-center gap-1 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                                                tenant.is_premium
                                                    ? 'bg-ink-100 hover:bg-ink-200 text-ink-700 border border-ink-200'
                                                    : 'bg-brand-600 hover:bg-brand-700 text-white shadow-soft'
                                            }`}
                                        >
                                            {tenant.is_premium ? (
                                                <><ArrowDownRight size={12} aria-hidden="true" /> Downgrade</>
                                            ) : (
                                                <><ArrowUpRight size={12} aria-hidden="true" /> Upgrade</>
                                            )}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Mobile card list */}
                <ul className="md:hidden divide-y divide-ink-100">
                    {isLoading ? (
                        <li className="p-8 text-center text-ink-500">
                            <Activity size={16} className="inline animate-spin mr-2 text-brand-600" aria-hidden="true" />Loading…
                        </li>
                    ) : filtered.length === 0 ? (
                        <li className="p-8 text-center text-ink-500">No tenants match your filter.</li>
                    ) : filtered.map(tenant => (
                        <li key={`${tenant.id}-mb`} className="p-4">
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                    <p className="font-semibold text-ink-900 truncate">{tenant.name}</p>
                                    <p className="text-xs text-ink-500 font-mono truncate">{tenant.domain}</p>
                                    <div className="mt-2 flex flex-wrap items-center gap-2">
                                        {tenant.is_premium ? (
                                            <span className="badge-warn inline-flex items-center gap-1"><Crown size={10} aria-hidden="true" /> Premium</span>
                                        ) : (
                                            <span className="badge-neutral">Standard</span>
                                        )}
                                        <span className="text-xs font-mono text-ink-700">
                                            {KES(tenant.is_premium ? TIER_PRICING.Premium : TIER_PRICING.Standard)}/mo
                                        </span>
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => toggleTier(tenant)}
                                    disabled={updatingId === tenant.id}
                                    aria-label={tenant.is_premium ? `Downgrade ${tenant.name}` : `Upgrade ${tenant.name}`}
                                    className={`shrink-0 text-xs font-semibold px-3 py-2 rounded-lg transition-colors inline-flex items-center gap-1 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] ${
                                        tenant.is_premium
                                            ? 'bg-ink-100 hover:bg-ink-200 text-ink-700 border border-ink-200'
                                            : 'bg-brand-600 hover:bg-brand-700 text-white shadow-soft'
                                    }`}
                                >
                                    {tenant.is_premium ? (
                                        <><ArrowDownRight size={12} aria-hidden="true" /> Downgrade</>
                                    ) : (
                                        <><ArrowUpRight size={12} aria-hidden="true" /> Upgrade</>
                                    )}
                                </button>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>

            <p className="text-xs text-ink-500 flex items-start gap-2 px-2 leading-relaxed">
                <ShieldCheck size={14} className="text-ink-400 shrink-0 mt-0.5" aria-hidden="true" />
                Tier pricing is configured in the platform settings file. Tier changes are written to the master tenant registry and take effect on next billing cycle.
            </p>
        </div>
    );
}

const KPI_ACCENT = {
    accent: 'bg-accent-50 ring-accent-100 text-accent-700',
    brand:  'bg-brand-50  ring-brand-100  text-brand-700',
    amber:  'bg-amber-50  ring-amber-100  text-amber-700',
    teal:   'bg-teal-50   ring-teal-100   text-teal-700',
};

function KpiCard({ icon: Icon, label, value, sub, accent }) {
    return (
        <div className="stat-tile">
            <div className={`stat-icon ${KPI_ACCENT[accent] || KPI_ACCENT.brand}`} aria-hidden="true">
                <Icon size={18} />
            </div>
            <div>
                <p className="stat-label">{label}</p>
                <p className="stat-value">{value}</p>
                {sub && <p className="text-xs text-ink-500 mt-1">{sub}</p>}
            </div>
        </div>
    );
}

function PricingCard({ tier, price, seats, features, highlight }) {
    return (
        <div className={`rounded-2xl border p-5 ${
            highlight
                ? 'bg-gradient-to-br from-amber-50 to-amber-100/60 border-amber-200 shadow-soft'
                : 'card'
        }`}>
            <div className="flex justify-between items-start mb-3">
                <h3 className={`text-lg font-semibold tracking-tight ${highlight ? 'text-amber-900' : 'text-ink-900'}`}>{tier}</h3>
                {highlight && <Crown size={18} className="text-amber-700" aria-hidden="true" />}
            </div>
            <div className="flex items-baseline gap-1 mb-1">
                <span className="text-2xl font-semibold tracking-tight text-ink-900">{price}</span>
                <span className="text-sm font-medium text-ink-500">/mo</span>
            </div>
            <div className="text-xs text-ink-500 mb-4">{seats} active subscriber{seats !== 1 ? 's' : ''}</div>
            <ul className="space-y-1.5 text-xs text-ink-700">
                {features.map(f => (
                    <li key={f} className="flex items-start gap-2">
                        <Check size={14} className={`shrink-0 mt-0.5 ${highlight ? 'text-amber-700' : 'text-accent-600'}`} aria-hidden="true" />
                        <span>{f}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
