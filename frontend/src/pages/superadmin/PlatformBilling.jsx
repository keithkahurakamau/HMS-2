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
        <div className="space-y-6 animate-in fade-in duration-500">
            <div>
                <h1 className="text-3xl font-black text-white tracking-tight flex items-center gap-3">
                    <CreditCard className="text-emerald-400" /> Billing &amp; Subscriptions
                </h1>
                <p className="text-slate-400 mt-1">Track platform revenue, manage tenant subscription tiers, and project growth.</p>
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
            <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden">
                <div className="p-4 border-b border-slate-800 flex flex-wrap justify-between items-center gap-3 bg-slate-900/50">
                    <h2 className="text-sm font-bold text-white">Tenant Subscriptions</h2>
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Search tenants..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500 w-64"
                        />
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-slate-950 border-b border-slate-800 text-slate-500 text-xs uppercase font-black tracking-wider">
                            <tr>
                                <th className="px-6 py-3">Tenant</th>
                                <th className="px-6 py-3">Tier</th>
                                <th className="px-6 py-3">Monthly Fee</th>
                                <th className="px-6 py-3">Status</th>
                                <th className="px-6 py-3 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800 text-slate-300">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-500"><Activity size={16} className="inline animate-spin mr-2" />Loading…</td></tr>
                            ) : filtered.length === 0 ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-slate-500">No tenants match your filter.</td></tr>
                            ) : filtered.map(tenant => (
                                <tr key={tenant.id} className="hover:bg-slate-800/40">
                                    <td className="px-6 py-3">
                                        <div className="flex items-center gap-2">
                                            <Building2 size={16} className="text-slate-500" />
                                            <div>
                                                <p className="font-bold text-white">{tenant.name}</p>
                                                <p className="text-xs text-slate-500 font-mono">{tenant.domain}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-3">
                                        {tenant.is_premium ? (
                                            <span className="bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider inline-flex items-center gap-1">
                                                <Crown size={10} /> Premium
                                            </span>
                                        ) : (
                                            <span className="bg-slate-800 text-slate-400 border border-slate-700 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider">
                                                Standard
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-3 font-mono text-xs text-slate-400">
                                        {KES(tenant.is_premium ? TIER_PRICING.Premium : TIER_PRICING.Standard)}
                                    </td>
                                    <td className="px-6 py-3">
                                        <span className="inline-flex items-center gap-1.5 text-emerald-400 text-xs font-bold">
                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                            Active
                                        </span>
                                    </td>
                                    <td className="px-6 py-3 text-right">
                                        <button
                                            onClick={() => toggleTier(tenant)}
                                            disabled={updatingId === tenant.id}
                                            className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1 ml-auto ${
                                                tenant.is_premium
                                                    ? 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                                                    : 'bg-amber-600 hover:bg-amber-500 text-white'
                                            } disabled:opacity-50`}
                                        >
                                            {tenant.is_premium ? (<><ArrowDownRight size={12} /> Downgrade</>) : (<><ArrowUpRight size={12} /> Upgrade</>)}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            <div className="text-xs text-slate-500 flex items-center gap-2 px-2">
                <ShieldCheck size={14} className="text-slate-600" /> Tier pricing is configured in the platform settings file.
                Tier changes are written to the master tenant registry and take effect on next billing cycle.
            </div>
        </div>
    );
}

function KpiCard({ icon, label, value, sub, accent }) {
    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
            <div className="flex justify-between items-start mb-2">
                <div className="text-slate-400 text-xs font-bold uppercase tracking-wider">{label}</div>
                {icon}
            </div>
            <div className="text-3xl font-black text-white">{value}</div>
            {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
        </div>
    );
}

function PricingCard({ tier, price, seats, features, accent }) {
    const isAmber = accent === 'amber';
    return (
        <div className={`rounded-xl border ${isAmber ? 'border-amber-500/40 bg-gradient-to-br from-amber-900/10 to-slate-900' : 'border-slate-800 bg-slate-900'} p-5 shadow-lg`}>
            <div className="flex justify-between items-start mb-3">
                <h3 className={`font-black text-lg ${isAmber ? 'text-amber-300' : 'text-white'}`}>{tier}</h3>
                {isAmber && <Crown size={18} className="text-amber-400" />}
            </div>
            <div className="text-3xl font-black text-white mb-1">{price}<span className="text-sm font-bold text-slate-500">/mo</span></div>
            <div className="text-xs text-slate-500 mb-4">{seats} active subscriber{seats !== 1 ? 's' : ''}</div>
            <ul className="space-y-1.5 text-xs text-slate-300">
                {features.map(f => (
                    <li key={f} className="flex gap-2">
                        <span className={isAmber ? 'text-amber-400' : 'text-emerald-400'}>✓</span>
                        {f}
                    </li>
                ))}
            </ul>
        </div>
    );
}
