import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Building2, Search, ArrowRight, CheckCircle2, Sparkles, X,
    Award, Layers, Zap,
} from 'lucide-react';
import toast from 'react-hot-toast';
import CountUp from './CountUp';

/*
 * HospitalPicker — the multi-tenant "find your hospital" step, extracted from
 * the old standalone /portal page so it can live as a section on the Landing
 * page. Selecting a hospital records the tenant in localStorage (so the API
 * client attaches X-Tenant-ID on the next call) and routes the visitor to
 * `nextPath` — /login for staff, /patient for the patient portal.
 *
 * Premium landing language (lp-*) so it matches the rest of the page.
 */

const SORT_OPTIONS = [
    { key: 'name', label: 'A to Z', cmp: (a, b) => a.name.localeCompare(b.name) },
    { key: 'newest', label: 'Newest', cmp: (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0) },
    { key: 'premium', label: 'Premium first', cmp: (a, b) => (b.is_premium ? 1 : 0) - (a.is_premium ? 1 : 0) || a.name.localeCompare(b.name) },
];

// Cursor-following radial highlight on each card (scoped via CSS vars so it
// doesn't re-render the grid).
const handleMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${((e.clientX - r.left) / r.width) * 100}%`);
    e.currentTarget.style.setProperty('--my', `${((e.clientY - r.top) / r.height) * 100}%`);
};

export default function HospitalPicker({ nextPath = '/login' }) {
    const [hospitals, setHospitals] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [sortKey, setSortKey] = useState('name');
    const navigate = useNavigate();

    useEffect(() => {
        const fetchHospitals = async () => {
            try {
                const res = await apiClient.get('/public/hospitals');
                setHospitals(res.data || []);
            } catch {
                toast.error('Failed to load hospital registry.');
            } finally {
                setIsLoading(false);
            }
        };
        fetchHospitals();
        localStorage.removeItem('hms_tenant_id');
        localStorage.removeItem('hms_tenant_name');
    }, []);

    const filteredHospitals = useMemo(() => {
        const needle = searchQuery.trim().toLowerCase();
        const filtered = needle
            ? hospitals.filter((h) =>
                h.name.toLowerCase().includes(needle)
                || h.domain.toLowerCase().includes(needle))
            : hospitals;
        const sorter = SORT_OPTIONS.find(o => o.key === sortKey) || SORT_OPTIONS[0];
        return filtered.toSorted(sorter.cmp);
    }, [hospitals, searchQuery, sortKey]);

    const premiumCount = hospitals.filter(h => h.is_premium).length;

    const handleSelect = (tenant) => {
        localStorage.setItem('hms_tenant_id', tenant.db_name);
        localStorage.setItem('hms_tenant_name', tenant.name);
        toast.success(`Connected to ${tenant.name}`);
        navigate(nextPath);
    };

    return (
        <div>
            {/* Search */}
            <form onSubmit={(e) => e.preventDefault()} className="max-w-xl mx-auto" role="search">
                <label htmlFor="hospital-search" className="sr-only">Search for your hospital</label>
                <div className="relative">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-[#64748b]" size={20} aria-hidden="true" />
                    <input
                        id="hospital-search"
                        type="search"
                        placeholder="Hospital name or domain (e.g. mayoclinic.hms.co.ke)"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-12 pr-12 py-3.5 bg-white border border-[#b2f0f0] rounded-2xl text-[#012626] placeholder-[#94a3b8] shadow-sm focus:outline-none focus:border-[#008080] focus:ring-4 focus:ring-[#00ffff]/25 transition-all duration-200 text-base"
                        autoComplete="off"
                    />
                    {searchQuery && (
                        <button type="button" onClick={() => setSearchQuery('')} aria-label="Clear search"
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg text-[#64748b] hover:text-[#008080] hover:bg-[#e6fbfb] transition-colors duration-200 cursor-pointer">
                            <X size={16} />
                        </button>
                    )}
                </div>
            </form>

            {/* Live platform stats */}
            {!isLoading && hospitals.length > 0 && (
                <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 gap-3 max-w-4xl mx-auto">
                    <PickerStat icon={<Building2 size={16} />} label="Hospitals" value={<CountUp to={hospitals.length} />} hint="on the platform today" />
                    <PickerStat icon={<Award size={16} />} label="Premium tier" value={<CountUp to={premiumCount} />} hint="active subscriptions" />
                    <PickerStat icon={<Layers size={16} />} label="Modules" value={<CountUp to={25} />} hint="per hospital, à la carte" />
                    <PickerStat icon={<Zap size={16} />} label="Connect time" value={<CountUp to={2} suffix="s" />} hint="from pick to workspace" />
                </div>
            )}

            {/* Sort chips */}
            {!isLoading && hospitals.length > 1 && (
                <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-[0.14em] text-[#64748b] mr-1">Sort</span>
                    {SORT_OPTIONS.map(opt => {
                        const isActive = opt.key === sortKey;
                        return (
                            <button key={opt.key} type="button" onClick={() => setSortKey(opt.key)}
                                className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all duration-200 ease-in-out cursor-pointer ${
                                    isActive
                                        ? 'bg-[#008080] text-white shadow-md shadow-[#008080]/30'
                                        : 'bg-white ring-1 ring-[#b2f0f0] text-[#015050] hover:ring-[#00d4d4]'
                                }`}>
                                {opt.label}
                            </button>
                        );
                    })}
                </div>
            )}

            {/* Directory */}
            <div className="mt-8">
                {isLoading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <div key={`skeleton-${i}`} className="lp-card p-5 animate-pulse-soft">
                                <div className="size-10 rounded-xl bg-[#e6fbfb]" />
                                <div className="mt-4 h-4 w-2/3 rounded bg-[#e6fbfb]" />
                                <div className="mt-2 h-3 w-1/2 rounded bg-[#e6fbfb]/70" />
                                <div className="mt-6 h-3 w-1/3 rounded bg-[#e6fbfb]/60" />
                            </div>
                        ))}
                    </div>
                ) : filteredHospitals.length > 0 ? (
                    <>
                        <p className="text-center text-xs font-semibold text-[#64748b] mb-4">
                            Showing {filteredHospitals.length} of {hospitals.length} {hospitals.length === 1 ? 'hospital' : 'hospitals'}
                        </p>
                        <div key={sortKey + ':' + searchQuery} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredHospitals.map((tenant, idx) => (
                                <HospitalCard key={tenant.id} tenant={tenant} delayMs={idx * 40} onSelect={handleSelect} />
                            ))}
                        </div>
                    </>
                ) : (
                    <div className="lp-glass rounded-2xl p-12 text-center max-w-lg mx-auto">
                        <div className="size-14 rounded-2xl bg-[#e6fbfb] ring-1 ring-[#b2f0f0] text-[#008080] mx-auto flex items-center justify-center mb-4">
                            <Building2 size={24} />
                        </div>
                        <h3 className="text-base font-extrabold text-[#012626]">No matches for &ldquo;{searchQuery}&rdquo;</h3>
                        <p className="text-sm text-ink-500 mt-1 max-w-md mx-auto">
                            Double-check the spelling, or contact your system administrator if your hospital isn't listed yet.
                        </p>
                        <button type="button" onClick={() => setSearchQuery('')} className="mt-5 lp-btn-ghost cursor-pointer">
                            <X size={14} /> Clear search
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

function PickerStat({ icon, label, value, hint }) {
    return (
        <div className="lp-card p-4">
            <div className="flex items-center gap-2 text-2xs font-bold uppercase tracking-[0.14em] text-[#64748b]">
                <span className="text-[#008080]">{icon}</span>{label}
            </div>
            <p className="mt-1.5 text-2xl font-extrabold tracking-tight text-[#012626] tabular-nums">{value}</p>
            <p className="mt-0.5 text-xs text-ink-500">{hint}</p>
        </div>
    );
}

function HospitalCard({ tenant, delayMs, onSelect }) {
    return (
        <button
            type="button"
            onClick={() => onSelect(tenant)}
            onMouseMove={handleMove}
            style={{
                animationDelay: `${delayMs}ms`,
                animationFillMode: 'both',
                background: 'radial-gradient(360px circle at var(--mx, 50%) var(--my, 50%), rgba(0, 255, 255, 0.1), transparent 40%), rgba(255,255,255,0.7)',
            }}
            className="lp-card group relative text-left p-5 flex flex-col justify-between min-h-[12rem] cursor-pointer animate-reveal-up overflow-hidden focus-visible:outline-none focus-visible:lp-glow-ring"
        >
            <div>
                <div className="flex items-start justify-between mb-4">
                    <div className="size-11 rounded-xl bg-[#e6fbfb] text-[#008080] flex items-center justify-center group-hover:bg-[#00ffff]/25 group-hover:scale-105 transition-all duration-200">
                        <Building2 size={18} />
                    </div>
                    {tenant.is_premium && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-[#008080] text-white text-2xs font-bold uppercase tracking-wider">
                            <Sparkles size={10} /> Premium
                        </span>
                    )}
                </div>
                <h3 className="text-base font-extrabold text-[#012626] group-hover:text-[#008080] transition-colors duration-200 tracking-tight">
                    {tenant.name}
                </h3>
                <p className="text-xs text-ink-500 mt-1 truncate font-mono">{tenant.domain}</p>
            </div>
            <div className="mt-5 flex items-center justify-between text-xs font-bold text-[#015050]">
                <span className="inline-flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-[#00d4d4]" /> Active instance
                </span>
                <ArrowRight size={14} className="transition-transform duration-200 group-hover:translate-x-1.5" />
            </div>
        </button>
    );
}
