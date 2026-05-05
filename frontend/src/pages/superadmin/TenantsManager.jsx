import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { Building2, Server, Database, Plus, Search, MoreVertical, Edit2, ShieldAlert, Power, CheckCircle2 } from 'lucide-react';

export default function TenantsManager() {
    const [tenants, setTenants] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    
    // New Tenant Form State
    const [newTenant, setNewTenant] = useState({
        name: '', domain: '', db_name: '', theme_color: 'blue', is_premium: false
    });

    useEffect(() => {
        fetchTenants();
    }, []);

    const fetchTenants = async () => {
        setIsLoading(true);
        try {
            const res = await apiClient.get('/public/hospitals');
            setTenants(res.data);
        } catch (error) {
            toast.error("Failed to load global tenant registry");
        } finally {
            setIsLoading(false);
        }
    };

    const handleProvisionTenant = async (e) => {
        e.preventDefault();
        try {
            await apiClient.post('/public/hospitals', newTenant);
            toast.success("Tenant database provisioned successfully!");
            setIsAddModalOpen(false);
            setNewTenant({ name: '', domain: '', db_name: '', theme_color: 'blue', is_premium: false });
            fetchTenants();
        } catch (error) {
            toast.error("Failed to provision tenant.");
        }
    };

    const filteredTenants = tenants.filter(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()) || t.domain.toLowerCase().includes(searchQuery.toLowerCase()));

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-black text-white tracking-tight">Tenant Fleet Manager</h1>
                    <p className="text-slate-400 mt-1">Regulate hospital instances, database connections, and subscriptions.</p>
                </div>
                <button 
                    onClick={() => setIsAddModalOpen(true)}
                    className="bg-amber-600 hover:bg-amber-700 text-white px-5 py-2.5 rounded-lg text-sm font-bold shadow-lg shadow-amber-500/20 flex items-center gap-2 transition-colors"
                >
                    <Plus size={18} /> Provision New Tenant
                </button>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                    <div className="flex justify-between items-start mb-2">
                        <div className="text-slate-400 text-sm font-bold uppercase tracking-wider">Active Tenants</div>
                        <Building2 size={18} className="text-blue-500" />
                    </div>
                    <div className="text-3xl font-black text-white">{tenants.length}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                    <div className="flex justify-between items-start mb-2">
                        <div className="text-slate-400 text-sm font-bold uppercase tracking-wider">Premium Subscriptions</div>
                        <ShieldAlert size={18} className="text-amber-500" />
                    </div>
                    <div className="text-3xl font-black text-white">{tenants.filter(t => t.is_premium).length}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                    <div className="flex justify-between items-start mb-2">
                        <div className="text-slate-400 text-sm font-bold uppercase tracking-wider">Database Nodes</div>
                        <Database size={18} className="text-emerald-500" />
                    </div>
                    <div className="text-3xl font-black text-white">{tenants.length}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                    <div className="flex justify-between items-start mb-2">
                        <div className="text-slate-400 text-sm font-bold uppercase tracking-wider">Server Status</div>
                        <Server size={18} className="text-indigo-500" />
                    </div>
                    <div className="text-lg font-black text-emerald-400 flex items-center gap-2 mt-1">
                        <CheckCircle2 size={18} /> Operational
                    </div>
                </div>
            </div>

            {/* Data Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden">
                <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
                    <div className="relative">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                        <input 
                            type="text" 
                            placeholder="Filter tenants..." 
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="bg-slate-950 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-amber-500 w-72 transition-colors"
                        />
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-slate-950 border-b border-slate-800 text-slate-500 text-xs uppercase font-black tracking-wider">
                            <tr>
                                <th className="px-6 py-4">Tenant / Hospital Name</th>
                                <th className="px-6 py-4">Domain Routing</th>
                                <th className="px-6 py-4">Database Node</th>
                                <th className="px-6 py-4">Subscription Tier</th>
                                <th className="px-6 py-4 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800 text-slate-300">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-8 text-center text-slate-500">Loading global registry...</td></tr>
                            ) : filteredTenants.map(tenant => (
                                <tr key={tenant.id} className="hover:bg-slate-800/50 transition-colors group">
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center border border-${tenant.theme_color}-500/30 bg-${tenant.theme_color}-500/10 text-${tenant.theme_color}-400`}>
                                                <Building2 size={16} />
                                            </div>
                                            <span className="font-bold text-white group-hover:text-amber-400 transition-colors">{tenant.name}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 font-mono text-xs text-slate-400">{tenant.domain}</td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-2">
                                            <Database size={14} className="text-slate-500" />
                                            <span className="font-mono text-xs text-emerald-400">{tenant.db_name}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {tenant.is_premium ? (
                                            <span className="bg-amber-500/10 text-amber-500 border border-amber-500/20 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider">Premium</span>
                                        ) : (
                                            <span className="bg-slate-800 text-slate-400 border border-slate-700 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider">Standard</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex items-center justify-center gap-2 opacity-50 group-hover:opacity-100 transition-opacity">
                                            <button className="p-1.5 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors" title="Edit Configuration"><Edit2 size={16} /></button>
                                            <button className="p-1.5 hover:bg-rose-500/20 rounded text-slate-400 hover:text-rose-500 transition-colors" title="Suspend Instance"><Power size={16} /></button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Provision Modal */}
            {isAddModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/50 flex justify-between items-center">
                            <h2 className="text-lg font-black text-white">Provision New Tenant</h2>
                            <button onClick={() => setIsAddModalOpen(false)} className="text-slate-500 hover:text-white"><MoreVertical size={20}/></button>
                        </div>
                        <form onSubmit={handleProvisionTenant} className="p-6 space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Hospital Name</label>
                                <input required type="text" value={newTenant.name} onChange={e => setNewTenant({...newTenant, name: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none" placeholder="e.g. Aga Khan Hospital" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Subdomain Route</label>
                                    <input required type="text" value={newTenant.domain} onChange={e => setNewTenant({...newTenant, domain: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none" placeholder="e.g. agakhan.hms.com" />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Database Name</label>
                                    <input required type="text" value={newTenant.db_name} onChange={e => setNewTenant({...newTenant, db_name: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none font-mono text-sm" placeholder="e.g. agakhan_db" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Theme Color</label>
                                    <select value={newTenant.theme_color} onChange={e => setNewTenant({...newTenant, theme_color: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none">
                                        <option value="blue">Blue (Default)</option>
                                        <option value="emerald">Emerald</option>
                                        <option value="rose">Rose</option>
                                        <option value="indigo">Indigo</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Subscription Tier</label>
                                    <select value={newTenant.is_premium} onChange={e => setNewTenant({...newTenant, is_premium: e.target.value === 'true'})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none">
                                        <option value="false">Standard (Basic Modules)</option>
                                        <option value="true">Premium (All Modules)</option>
                                    </select>
                                </div>
                            </div>
                            <div className="mt-6 pt-6 border-t border-slate-800 flex justify-end gap-3">
                                <button type="button" onClick={() => setIsAddModalOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-400 hover:text-white transition-colors">Cancel</button>
                                <button type="submit" className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-bold shadow-lg shadow-amber-500/20 transition-colors">Deploy Database Instance</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
