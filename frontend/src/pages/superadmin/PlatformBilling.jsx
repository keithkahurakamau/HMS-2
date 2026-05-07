import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    CreditCard, TrendingUp, Banknote, Users, Building2, Crown,
    ArrowUpRight, ArrowDownRight, Search, ShieldCheck, Activity,
} from 'lucide-react';

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
            <div>
                <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-amber-400">Console</span>
                <h1 className="text-2xl font-semibold text-white tracking-tight mt-1 flex items-center gap-2">
                    <CreditCard size={22} className="text-accent-400" /> Billing &amp; Subscriptions
                </h1>
                <p className="text-sm text-ink-400 mt-1">Track platform revenue, manage tenant subscription tiers, and project growth.</p>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard
                    icon={<Banknote size={18} className="text-emerald-400" />}
                    label="Monthly Recurring Revenue"
                    value={KES(stats.mrr)}
                    sub={`${stats.total} tenants`}
                    accent="emerald"
                />
                <KpiCard
                    icon={<TrendingUp size={18} className="text-blue-400" />}
                    label="Annual Run Rate"
                    value={KES(stats.arr)}
                    sub="Projected at current tiers"
                    accent="blue"
                />
                <KpiCard
                    icon={<Crown size={18} className="text-amber-400" />}
                    label="Premium Subscribers"
                    value={stats.premium}
                    sub={`${stats.total ? Math.round(stats.premium / stats.total * 100) : 0}% of fleet`}
                    accent="amber"
                />
                <KpiCard
                    icon={<Users size={18} className="text-indigo-400" />}
                    label="Standard Subscribers"
                    value={stats.standard}
                    sub="Eligible for upgrade"
                    accent="indigo"
                />
            </div>

            {/* Tier pricing card */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <PricingCard
                    tier="Standard"
                    price={KES(TIER_PRICING.Standard)}
                    seats={stats.standard}
                    features={['Patients & Clinical Desk', 'Billing & M-Pesa', 'Email support', 'Up to 50 staff seats']}
                    accent="slate"
                />
                <PricingCard
                    tier="Premium"
                    price={KES(TIER_PRICING.Premium)}
                    seats={stats.premium}
                    features={['Everything in Standard', 'Unlimited modules', 'Priority Slack support', 'Custom integrations', 'Unlimited seats']}
                    accent="amber"
                />
            </div>

            {/* Tenant subscription table */}
            <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl overflow-hidden">
                <div className="p-4 border-b border-white/5 flex flex-wrap justify-between items-center gap-3">
                    <h2 className="text-sm font-semibold text-white tracking-tight">Tenant subscriptions</h2>
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                        <input
                            type="text" placeholder="Search tenants…"
                            value={search} onChange={(e) => setSearch(e.target.value)}
                            className="bg-ink-900/60 border border-white/10 rounded-lg pl-9 pr-3 py-1.5 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 w-64 transition-all"
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-white/[0.02] text-ink-400 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-6 py-3">Tenant</th>
                                <th className="px-6 py-3">Tier</th>
                                <th className="px-6 py-3">Monthly fee</th>
                                <th className="px-6 py-3">Status</th>
                                <th className="px-6 py-3 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-ink-300">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500"><Activity size={16} className="inline animate-spin mr-2" />Loading…</td></tr>
                            ) : filtered.length === 0 ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500">No tenants match your filter.</td></tr>
                            ) : filtered.map(tenant => (
                                <tr key={tenant.id} className="hover:bg-white/[0.03] transition-colors">
                                    <td className="px-6 py-3">
                                        <div className="flex items-center gap-2">
                                            <Building2 size={16} className="text-ink-500" />
                                            <div>
                                                <p className="font-semibold text-white">{tenant.name}</p>
                                                <p className="text-xs text-ink-500 font-mono">{tenant.domain}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-3">
                                        {tenant.is_premium ? (
                                            <span className="bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/30 px-2.5 py-0.5 rounded-full text-2xs font-semibold uppercase tracking-wider inline-flex items-center gap-1">
                                                <Crown size={10} /> Premium
                                            </span>
                                        ) : (
                                            <span className="bg-white/5 text-ink-400 ring-1 ring-white/10 px-2.5 py-0.5 rounded-full text-2xs font-semibold uppercase tracking-wider">
                                                Standard
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3 font-mono text-xs text-ink-400">
                                        {KES(tenant.is_premium ? TIER_PRICING.Premium : TIER_PRICING.Standard)}
                                    </td>
                                    <td className="px-6 py-3">
                                        <span className="inline-flex items-center gap-1.5 text-accent-400 text-xs font-semibold">
                                            <span className="w-1.5 h-1.5 rounded-full bg-accent-500 animate-pulse-soft"></span>
                                            Active
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 text-right">
                                        <button onClick={() => toggleTier(tenant)} disabled={updatingId === tenant.id}
                                            className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1 ml-auto ${
                                                tenant.is_premium
                                                    ? 'bg-white/5 hover:bg-white/10 text-ink-300 ring-1 ring-white/10'
                                                    : 'bg-gradient-to-b from-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-700 text-white shadow-soft'
                                            } disabled:opacity-50`}>
                                            {tenant.is_premium ? (<><ArrowDownRight size={12} /> Downgrade</>) : (<><ArrowUpRight size={12} /> Upgrade</>)}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            <div className="text-xs text-ink-500 flex items-start gap-2 px-2 leading-relaxed">
                <ShieldCheck size={14} className="text-ink-600 shrink-0 mt-0.5" /> Tier pricing is configured in the platform settings file. Tier changes are written to the master tenant registry and take effect on next billing cycle.
            </div>
        </div>
    );
}

function KpiCard({ icon, label, value, sub, accent }) {
    return (
        <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-5">
            <div className="flex justify-between items-start mb-3">
                <div className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">{label}</div>
                {icon}
            </div>
            <div className="text-2xl font-semibold text-white tracking-tight">{value}</div>
            {sub && <div className="text-xs text-ink-500 mt-1">{sub}</div>}
        </div>
    );
}

function PricingCard({ tier, price, seats, features, accent }) {
    const isAmber = accent === 'amber';
    return (
        <div className={`rounded-2xl ring-1 backdrop-blur-md p-5 ${isAmber ? 'ring-amber-500/30 bg-gradient-to-br from-amber-500/10 to-amber-900/5' : 'ring-white/10 bg-white/[0.04]'}`}>
            <div className="flex justify-between items-start mb-3">
                <h3 className={`text-lg font-semibold tracking-tight ${isAmber ? 'text-amber-300' : 'text-white'}`}>{tier}</h3>
                {isAmber && <Crown size={18} className="text-amber-400" />}
            </div>
            <div className="text-2xl font-semibold text-white mb-1 tracking-tight">{price}<span className="text-sm font-medium text-ink-400">/mo</span></div>
            <div className="text-xs text-ink-500 mb-4">{seats} active subscriber{seats !== 1 ? 's' : ''}</div>
            <ul className="space-y-1.5 text-xs text-ink-200">
                {features.map(f => (
                    <li key={f} className="flex gap-2">
                        <span className={isAmber ? 'text-amber-400' : 'text-accent-400'}>✓</span>
                        {f}
                    </li>
                ))}
            </ul>
        </div>
    );
}
