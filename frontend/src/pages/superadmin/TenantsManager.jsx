import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { Building2, Server, Database, Plus, Search, MoreVertical, Edit2, ShieldAlert, Power, CheckCircle2, X, ZapOff, Zap } from 'lucide-react';

export default function TenantsManager() {
    const [tenants, setTenants] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    
    // New Tenant Form State
    const [newTenant, setNewTenant] = useState({
        name: '', domain: '', db_name: '', admin_email: '', admin_full_name: '',
        theme_color: 'blue', is_premium: false
    });

    // Surface the one-time temp password returned by the backend.
    const [provisionResult, setProvisionResult] = useState(null);

    // Edit modal state.
    const [editing, setEditing] = useState(null);   // tenant being edited
    const [editForm, setEditForm] = useState({ name: '', domain: '', theme_color: 'blue', is_premium: false });
    const [savingEdit, setSavingEdit] = useState(false);

    const tenantNumericId = (t) => String(t.id || '').replace(/^tenant_/, '');

    const openEdit = (tenant) => {
        setEditing(tenant);
        setEditForm({
            name: tenant.name || '',
            domain: tenant.domain || '',
            theme_color: tenant.theme_color || 'blue',
            is_premium: !!tenant.is_premium,
        });
    };

    const handleEdit = async (e) => {
        e.preventDefault();
        if (!editing) return;
        setSavingEdit(true);
        try {
            await apiClient.patch(`/public/hospitals/${tenantNumericId(editing)}`, editForm);
            toast.success(`${editing.name} updated.`);
            setEditing(null);
            fetchTenants();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Update failed.');
        } finally {
            setSavingEdit(false);
        }
    };

    const handleSuspendToggle = async (tenant) => {
        const nextActive = !(tenant.is_active ?? true);
        if (!nextActive && !window.confirm(`Suspend ${tenant.name}? Users will be unable to log in until reactivated.`)) {
            return;
        }
        try {
            await apiClient.patch(`/public/hospitals/${tenantNumericId(tenant)}`, { is_active: nextActive });
            toast.success(`${tenant.name} ${nextActive ? 'reactivated' : 'suspended'}.`);
            fetchTenants();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Action failed.');
        }
    };

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
            const res = await apiClient.post('/public/hospitals', newTenant);
            toast.success("Tenant provisioned: database, schema, and admin account ready.");
            setIsAddModalOpen(false);
            setProvisionResult(res.data);
            setNewTenant({ name: '', domain: '', db_name: '', admin_email: '', admin_full_name: '', theme_color: 'blue', is_premium: false });
            fetchTenants();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to provision tenant.");
        }
    };

    const filteredTenants = tenants.filter(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()) || t.domain.toLowerCase().includes(searchQuery.toLowerCase()));

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-amber-400">Console</span>
                    <h1 className="text-2xl font-semibold text-white tracking-tight mt-1">Tenant Fleet Manager</h1>
                    <p className="text-sm text-ink-400 mt-1">Regulate hospital instances, database connections, and subscriptions.</p>
                </div>
                <button onClick={() => setIsAddModalOpen(true)}
                    className="inline-flex items-center gap-2 bg-gradient-to-b from-amber-500 to-amber-600 hover:from-amber-500 hover:to-amber-700 text-white px-4 py-2.5 rounded-xl text-sm font-semibold shadow-glow transition-all">
                    <Plus size={15} /> Provision new tenant
                </button>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: 'Active tenants',         value: tenants.length, icon: Building2, ring: 'bg-blue-500/10 ring-blue-500/20 text-blue-400' },
                    { label: 'Premium subscriptions',  value: tenants.filter(t => t.is_premium).length, icon: ShieldAlert, ring: 'bg-amber-500/10 ring-amber-500/20 text-amber-400' },
                    { label: 'Database nodes',         value: tenants.length, icon: Database, ring: 'bg-accent-500/10 ring-accent-500/20 text-accent-400' },
                ].map(({ label, value, icon: Icon, ring }) => (
                    <div key={label} className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-5">
                        <div className="flex justify-between items-start mb-4">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ring-1 ring-inset ${ring}`}>
                                <Icon size={18} />
                            </div>
                        </div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">{label}</p>
                        <p className="text-2xl font-semibold text-white mt-1 tracking-tight">{value}</p>
                    </div>
                ))}
                <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-5">
                    <div className="flex justify-between items-start mb-4">
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center ring-1 ring-inset bg-indigo-500/10 ring-indigo-500/20 text-indigo-400">
                            <Server size={18} />
                        </div>
                    </div>
                    <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">Server status</p>
                    <p className="text-base font-semibold text-accent-400 mt-1 flex items-center gap-2">
                        <CheckCircle2 size={16} /> Operational
                    </p>
                </div>
            </div>

            {/* Data Table */}
            <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl overflow-hidden">
                <div className="p-4 border-b border-white/5 flex justify-between items-center">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                        <input
                            type="text" placeholder="Filter tenants…"
                            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                            className="bg-ink-900/60 border border-white/10 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-ink-500 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/20 w-72 transition-all"
                        />
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-white/[0.02] text-ink-400 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-6 py-3">Tenant</th>
                                <th className="px-6 py-3">Domain routing</th>
                                <th className="px-6 py-3">Database node</th>
                                <th className="px-6 py-3">Subscription tier</th>
                                <th className="px-6 py-3 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-ink-300">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500">Loading global registry…</td></tr>
                            ) : filteredTenants.map(tenant => {
                                const themeRing = {
                                    blue:    'border-blue-500/30 bg-blue-500/10 text-blue-400',
                                    emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
                                    teal:    'border-brand-500/30 bg-brand-500/10 text-brand-300',
                                    rose:    'border-rose-500/30 bg-rose-500/10 text-rose-400',
                                    indigo:  'border-indigo-500/30 bg-indigo-500/10 text-indigo-400',
                                }[tenant.theme_color] || 'border-blue-500/30 bg-blue-500/10 text-blue-400';
                                return (
                                    <tr key={tenant.id} className="hover:bg-white/[0.03] transition-colors group">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${themeRing}`}>
                                                    <Building2 size={16} />
                                                </div>
                                                <span className="font-semibold text-white group-hover:text-amber-300 transition-colors">{tenant.name}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 font-mono text-xs text-ink-400">{tenant.domain}</td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                <Database size={13} className="text-ink-500" />
                                                <span className="font-mono text-xs text-accent-400">{tenant.db_name}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            {tenant.is_premium ? (
                                                <span className="bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20 px-2.5 py-0.5 rounded-full text-2xs font-semibold uppercase tracking-wider">Premium</span>
                                            ) : (
                                                <span className="bg-white/5 text-ink-400 ring-1 ring-white/10 px-2.5 py-0.5 rounded-full text-2xs font-semibold uppercase tracking-wider">Standard</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-center">
                                            <div className="flex items-center justify-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                                                <button onClick={() => openEdit(tenant)} aria-label={`Edit ${tenant.name}`}
                                                    className="p-2 hover:bg-white/10 rounded-lg text-ink-400 hover:text-white transition-colors" title="Edit configuration">
                                                    <Edit2 size={15} />
                                                </button>
                                                <button onClick={() => handleSuspendToggle(tenant)}
                                                    aria-label={(tenant.is_active ?? true) ? `Suspend ${tenant.name}` : `Reactivate ${tenant.name}`}
                                                    className={`p-2 rounded-lg transition-colors ${(tenant.is_active ?? true) ? 'text-ink-400 hover:bg-rose-500/20 hover:text-rose-400' : 'text-accent-400 hover:bg-accent-500/20'}`}
                                                    title={(tenant.is_active ?? true) ? 'Suspend instance' : 'Reactivate instance'}>
                                                    {(tenant.is_active ?? true) ? <Power size={15} /> : <Zap size={15} />}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Edit tenant modal */}
            {editing && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/50 flex justify-between items-center">
                            <h2 className="text-lg font-black text-white">Edit Tenant — <span className="text-amber-400">{editing.name}</span></h2>
                            <button onClick={() => setEditing(null)} aria-label="Close" className="text-slate-500 hover:text-white"><X size={20} /></button>
                        </div>
                        <form onSubmit={handleEdit} className="p-6 space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Display Name</label>
                                <input
                                    required
                                    type="text"
                                    value={editForm.name}
                                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Subdomain Route</label>
                                <input
                                    required
                                    type="text"
                                    value={editForm.domain}
                                    onChange={(e) => setEditForm({ ...editForm, domain: e.target.value })}
                                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Theme Color</label>
                                    <select
                                        value={editForm.theme_color}
                                        onChange={(e) => setEditForm({ ...editForm, theme_color: e.target.value })}
                                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none"
                                    >
                                        <option value="blue">Blue</option>
                                        <option value="emerald">Emerald</option>
                                        <option value="rose">Rose</option>
                                        <option value="indigo">Indigo</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Subscription Tier</label>
                                    <select
                                        value={editForm.is_premium ? 'true' : 'false'}
                                        onChange={(e) => setEditForm({ ...editForm, is_premium: e.target.value === 'true' })}
                                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none"
                                    >
                                        <option value="false">Standard</option>
                                        <option value="true">Premium</option>
                                    </select>
                                </div>
                            </div>
                            <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3 text-xs text-slate-400">
                                Database name <code className="text-slate-300 font-mono">{editing.db_name}</code> is immutable.
                            </div>
                            <div className="mt-6 pt-6 border-t border-slate-800 flex justify-end gap-3">
                                <button type="button" onClick={() => setEditing(null)} className="px-5 py-2.5 text-sm font-bold text-slate-400 hover:text-white">Cancel</button>
                                <button
                                    type="submit"
                                    disabled={savingEdit}
                                    className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-bold disabled:opacity-50"
                                >
                                    {savingEdit ? 'Saving…' : 'Save changes'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* One-time provisioning result — shows admin temp password */}
            {provisionResult && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
                    <div className="bg-slate-900 border border-amber-500/50 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
                        <div className="px-6 py-4 border-b border-slate-800 bg-amber-500/10">
                            <h2 className="text-lg font-black text-amber-400">Tenant ready — admin temporary password</h2>
                            <p className="text-xs text-amber-300/80 mt-1">Shown once. Deliver to the admin via a secure channel.</p>
                        </div>
                        <div className="p-6 space-y-4 text-sm">
                            <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Tenant</div>
                                <div className="text-white font-bold">{provisionResult.db_name}</div>
                            </div>
                            <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Admin email</div>
                                <div className="text-white font-mono text-xs break-all">{provisionResult.admin_email}</div>
                            </div>
                            <div className="bg-slate-950 border border-amber-500/30 rounded-lg p-4">
                                <div className="text-xs font-bold text-amber-400 uppercase tracking-wider mb-2">Temporary password</div>
                                <code className="text-emerald-300 font-mono text-base break-all select-all">{provisionResult.admin_temp_password}</code>
                                <button
                                    onClick={() => { navigator.clipboard.writeText(provisionResult.admin_temp_password); toast.success('Copied'); }}
                                    className="mt-3 text-xs text-amber-400 hover:text-amber-300 font-bold"
                                >
                                    Copy to clipboard
                                </button>
                            </div>
                            <p className="text-xs text-slate-400">
                                The admin will be forced to choose a new password on first login.
                            </p>
                            <div className="flex justify-end pt-2">
                                <button
                                    onClick={() => setProvisionResult(null)}
                                    className="px-5 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-bold"
                                >
                                    I've saved it — close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

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
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Bootstrap Admin Email</label>
                                    <input required type="email" value={newTenant.admin_email} onChange={e => setNewTenant({...newTenant, admin_email: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none" placeholder="admin@agakhan.com" />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1.5">Admin Full Name</label>
                                    <input required type="text" value={newTenant.admin_full_name} onChange={e => setNewTenant({...newTenant, admin_full_name: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white focus:border-amber-500 focus:outline-none" placeholder="Jane Mwangi" />
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
