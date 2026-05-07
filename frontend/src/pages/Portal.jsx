import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import { Building2, Search, ArrowRight, ShieldCheck, Activity } from 'lucide-react';
import toast from 'react-hot-toast';

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
                toast.error("Failed to load hospital registry.");
            } finally {
                setIsLoading(false);
            }
        };
        fetchHospitals();
        
        // Clear any existing tenant or auth when arriving at the portal
        localStorage.removeItem('hms_tenant_id');
        localStorage.removeItem('hms_tenant_name');
    }, []);

    const filteredHospitals = hospitals.filter(h => 
        h.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
        h.domain.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const handleSelectTenant = (tenant) => {
        // Set the active database/tenant for the API interceptor
        localStorage.setItem('hms_tenant_id', tenant.db_name);
        localStorage.setItem('hms_tenant_name', tenant.name);
        
        // Optional: Apply specific branding CSS variables based on tenant.theme_color
        
        toast.success(`Connected to ${tenant.name}`);
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4 sm:p-8">
            {/* Ambient Background Glow */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-brand-600/20 rounded-full blur-[128px]"></div>
                <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent-600/20 rounded-full blur-[128px]"></div>
            </div>

            <div className="relative z-10 w-full max-w-4xl flex flex-col items-center">
                {/* Brand Header */}
                <div className="flex items-center gap-3 mb-8">
                    <div className="w-12 h-12 bg-gradient-to-tr from-brand-600 to-accent-600 rounded-xl flex items-center justify-center shadow-lg shadow-brand-500/30">
                        <ShieldCheck size={28} className="text-white" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-black text-white tracking-tight">HMS <span className="text-brand-500">Enterprise</span></h1>
                        <p className="text-slate-400 font-medium text-sm tracking-wide uppercase">Global Cloud Infrastructure</p>
                    </div>
                </div>

                <div className="w-full bg-slate-900/80 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 sm:p-12 shadow-2xl">
                    <div className="text-center mb-10">
                        <h2 className="text-2xl font-bold text-white mb-2">Select Your Organization</h2>
                        <p className="text-slate-400">Search for your hospital's workspace to connect to your dedicated cloud instance.</p>
                    </div>

                    {/* Search Bar */}
                    <div className="relative max-w-xl mx-auto mb-10">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={24} />
                        <input 
                            type="text" 
                            placeholder="Search by hospital name or domain (e.g., somewhat.hms.co.ke)..." 
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-14 pr-6 py-4 bg-slate-950 border border-slate-700 rounded-2xl text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/50 transition-all text-lg shadow-inner"
                        />
                    </div>

                    {/* Hospital Directory */}
                    {isLoading ? (
                        <div className="flex flex-col items-center justify-center py-12 text-brand-500">
                            <Activity className="animate-spin mb-4" size={32} />
                            <p className="text-slate-400 font-medium">Scanning global registry...</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredHospitals.length > 0 ? (
                                filteredHospitals.map(tenant => (
                                    <div 
                                        key={tenant.id}
                                        onClick={() => handleSelectTenant(tenant)}
                                        className="group bg-slate-800/50 hover:bg-slate-800 border border-slate-700 hover:border-brand-500 rounded-2xl p-5 cursor-pointer transition-all hover:shadow-lg hover:shadow-brand-500/10 flex flex-col justify-between h-full"
                                    >
                                        <div>
                                            <div className="flex justify-between items-start mb-3">
                                                <div className={`w-10 h-10 rounded-lg flex items-center justify-center bg-${tenant.theme_color}-500/20 border border-${tenant.theme_color}-500/30 text-${tenant.theme_color}-400`}>
                                                    <Building2 size={20} />
                                                </div>
                                                {tenant.is_premium && (
                                                    <span className="bg-gradient-to-r from-amber-500 to-orange-500 text-white text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full shadow-sm">
                                                        Premium
                                                    </span>
                                                )}
                                            </div>
                                            <h3 className="text-lg font-bold text-white group-hover:text-brand-400 transition-colors">{tenant.name}</h3>
                                            <p className="text-sm text-slate-500 mt-1 truncate">{tenant.domain}</p>
                                        </div>
                                        <div className="mt-6 flex items-center justify-between text-sm font-bold text-slate-400 group-hover:text-brand-400 transition-colors">
                                            <span>Connect to instance</span>
                                            <ArrowRight size={18} className="transform group-hover:translate-x-1 transition-transform" />
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div className="col-span-full text-center py-12 bg-slate-900 border border-slate-800 rounded-2xl">
                                    <Building2 size={48} className="mx-auto text-slate-700 mb-4" />
                                    <h3 className="text-lg font-bold text-slate-300">No organizations found</h3>
                                    <p className="text-slate-500">Check your spelling or contact your system administrator.</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
                
                <div className="mt-8 flex flex-col items-center gap-2">
                    <button
                        type="button"
                        onClick={() => navigate('/patient')}
                        className="text-sm text-brand-400 hover:text-brand-300 font-bold underline-offset-4 hover:underline"
                    >
                        Are you a patient? Open the Patient Portal →
                    </button>
                    <p className="text-slate-500 text-sm">Powered by Advanced Agentic Cloud Infrastructure</p>
                </div>
            </div>
        </div>
    );
}
