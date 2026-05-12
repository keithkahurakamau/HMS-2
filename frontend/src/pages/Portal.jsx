import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { Building2, Search, ArrowRight, ShieldCheck, Activity, Sparkles, HeartPulse } from 'lucide-react';
import toast from 'react-hot-toast';

const THEME_RING = {
    blue:    'bg-blue-500/15 ring-blue-400/30 text-blue-300',
    emerald: 'bg-emerald-500/15 ring-emerald-400/30 text-emerald-300',
    teal:    'bg-brand-500/15 ring-brand-400/30 text-brand-300',
    amber:   'bg-amber-500/15 ring-amber-400/30 text-amber-300',
    rose:    'bg-rose-500/15 ring-rose-400/30 text-rose-300',
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
        <div className="min-h-screen bg-ink-950 text-white flex flex-col items-center justify-center p-4 sm:p-8 relative overflow-hidden">
            {/* Ambient background */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute -top-40 -left-32 w-[36rem] h-[36rem] bg-brand-500/15 rounded-full blur-[120px]" />
                <div className="absolute -bottom-40 -right-32 w-[36rem] h-[36rem] bg-accent-500/15 rounded-full blur-[120px]" />
                <div className="absolute inset-0 bg-grid opacity-[0.05]" />
            </div>

            <div className="relative z-10 w-full max-w-5xl flex flex-col items-center animate-slide-up">
                {/* Brand header */}
                <div className="flex items-center gap-3 mb-8">
                    <div className="w-12 h-12 rounded-2xl bg-brand-gradient flex items-center justify-center shadow-glow">
                        <ShieldCheck size={24} className="text-white" />
                    </div>
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight">
                            <span className="text-gradient-brand">MediFleet</span>
                        </h1>
                        <p className="text-2xs sm:text-xs text-ink-400 font-semibold uppercase tracking-[0.18em] mt-0.5">
                            Multi-tenant cloud infrastructure
                        </p>
                    </div>
                </div>

                <div className="w-full bg-white/[0.04] backdrop-blur-2xl border border-white/10 rounded-3xl p-6 sm:p-10 shadow-elevated">
                    <div className="text-center mb-8 sm:mb-10">
                        <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 ring-1 ring-white/10 text-2xs font-semibold uppercase tracking-[0.14em] text-white/85">
                            <Sparkles size={12} className="text-brand-300" />
                            Hospital workspace
                        </span>
                        <h2 className="mt-4 text-2xl sm:text-3xl font-semibold tracking-tight">Select your organization</h2>
                        <p className="mt-2 text-sm text-ink-400 max-w-xl mx-auto">
                            Search for your hospital's workspace to connect to your dedicated cloud instance.
                        </p>
                    </div>

                    {/* Search */}
                    <div className="relative max-w-xl mx-auto mb-8 sm:mb-10">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-ink-500" size={20} />
                        <input
                            type="text"
                            placeholder="Hospital name or domain (e.g. mayoclinic.hms.co.ke)"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-12 pr-4 py-3.5 bg-ink-950/60 border border-white/10 rounded-2xl text-white placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-500/20 transition-all text-base"
                        />
                    </div>

                    {/* Directory */}
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-16 text-brand-300">
                            <Activity className="animate-spin mb-3" size={28} />
                            <p className="text-sm text-ink-400 font-medium">Scanning global registry…</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredHospitals.length > 0 ? (
                                filteredHospitals.map((tenant) => {
                                    const ringStyle = THEME_RING[tenant.theme_color] || THEME_RING.teal;
                                    return (
                                        <button
                                            key={tenant.id}
                                            onClick={() => handleSelectTenant(tenant)}
                                            className="group text-left bg-white/[0.03] hover:bg-white/[0.07] border border-white/10 hover:border-brand-400/40 rounded-2xl p-5 transition-all duration-200 hover:-translate-y-0.5 flex flex-col justify-between"
                                        >
                                            <div>
                                                <div className="flex justify-between items-start mb-4">
                                                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center ring-1 ring-inset ${ringStyle}`}>
                                                        <Building2 size={18} />
                                                    </div>
                                                    {tenant.is_premium && (
                                                        <span className="inline-flex items-center gap-1 bg-gradient-to-r from-amber-400 to-orange-500 text-white text-2xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full shadow-soft">
                                                            <Sparkles size={10} /> Premium
                                                        </span>
                                                    )}
                                                </div>
                                                <h3 className="text-base font-semibold text-white group-hover:text-brand-300 transition-colors tracking-tight">
                                                    {tenant.name}
                                                </h3>
                                                <p className="text-xs text-ink-500 mt-1 truncate">{tenant.domain}</p>
                                            </div>
                                            <div className="mt-5 flex items-center justify-between text-xs font-semibold text-ink-400 group-hover:text-brand-300 transition-colors">
                                                <span>Connect to instance</span>
                                                <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
                                            </div>
                                        </button>
                                    );
                                })
                            ) : (
                                <div className="col-span-full text-center py-12 bg-white/[0.02] border border-white/5 rounded-2xl">
                                    <Building2 size={40} className="mx-auto text-ink-700 mb-3" />
                                    <h3 className="text-base font-semibold text-ink-300">No organizations found</h3>
                                    <p className="text-sm text-ink-500 mt-1">Check your spelling or contact your system administrator.</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="mt-8 flex flex-col items-center gap-3">
                    <button
                        type="button"
                        onClick={() => navigate('/patient')}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/[0.04] hover:bg-white/[0.08] ring-1 ring-white/10 text-sm font-semibold text-brand-300 hover:text-brand-200 transition-colors"
                    >
                        <HeartPulse size={14} />
                        Are you a patient? Open the Patient Portal
                        <ArrowRight size={14} />
                    </button>
                    <p className="text-2xs text-ink-500 uppercase tracking-[0.18em]">
                        Powered by Advanced Agentic Cloud Infrastructure
                    </p>
                </div>
            </div>
        </div>
    );
}
