import React, { useState, useEffect } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { Building2, Server, Database, Plus, Search, MoreVertical, Edit2, ShieldAlert, Power, CheckCircle2, X, ZapOff, Zap, Lock, Package } from 'lucide-react';
import PageHeader from '../../components/PageHeader';

// Normalize whatever the backend (or network) returned into a single readable
// string. FastAPI 422s come back as a list of {loc, msg, type}; HTTPException
// uses {detail: "..."}; network failures don't have a response at all.
const formatApiError = (err, fallback = 'Request failed.') => {
    if (!err) return fallback;
    if (!err.response) {
        return err.message ? `${fallback} (${err.message})` : fallback;
    }
    const detail = err.response.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d) => {
                const where = Array.isArray(d.loc) ? d.loc.slice(1).join('.') : '';
                return where ? `${where}: ${d.msg}` : d.msg;
            })
            .filter(Boolean)
            .join(' · ') || fallback;
    }
    if (detail && typeof detail === 'object' && detail.msg) return detail.msg;
    return fallback;
};

const showApiError = (err, fallback) => {
    const msg = formatApiError(err, fallback);
    // Pin server-provided messages a bit longer so the operator can read them.
    const duration = err?.response?.data?.detail ? 6000 : 4000;
    toast.error(msg, { duration });
};

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
    const [editForm, setEditForm] = useState({
        name: '', domain: '', theme_color: 'blue', is_premium: false,
        feature_flags: {}, plan_limits: {}, notes: '',
    });
    const [flagDraft, setFlagDraft] = useState({ key: '', value: true });
    const [limitDraft, setLimitDraft] = useState({ key: '', value: 0 });
    const [savingEdit, setSavingEdit] = useState(false);

    // Canonical module catalogue from the backend. Drives the curated package
    // editor below so superadmins can't typo a module key and silently fail
    // to gate anything. Falls back to [] on error — the UI shows just the
    // legacy free-text editor in that case.
    const [moduleCatalogue, setModuleCatalogue] = useState([]);
    const [moduleSearch, setModuleSearch] = useState('');

    const tenantNumericId = (t) => String(t.id || t.tenant_id || '').replace(/^tenant_/, '');

    const openEdit = (tenant) => {
        setEditing(tenant);
        setEditForm({
            name: tenant.name || '',
            domain: tenant.domain || '',
            theme_color: tenant.theme_color || 'blue',
            is_premium: !!tenant.is_premium,
            feature_flags: tenant.feature_flags || {},
            plan_limits: tenant.plan_limits || {},
            notes: tenant.notes || '',
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
            showApiError(err, `Could not update ${editing.name}.`);
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
            showApiError(err, `Could not ${nextActive ? 'reactivate' : 'suspend'} ${tenant.name}.`);
        }
    };

    useEffect(() => {
        fetchTenants();
        // Catalogue rarely changes — fetched once per session.
        apiClient.get('/public/superadmin/module-catalogue')
            .then((res) => setModuleCatalogue(res.data || []))
            .catch(() => setModuleCatalogue([]));
    }, []);

    

    const fetchTenants = async () => {
        setIsLoading(true);
        try {
            // Superadmin view should see suspended tenants too, so they can
            // reactivate them — public picker callers omit this flag.
            const res = await apiClient.get('/public/hospitals?include_inactive=true');
            setTenants(res.data);
        } catch (error) {
            showApiError(error, 'Failed to load global tenant registry.');
        } finally {
            setIsLoading(false);
        }
    };

    const [isProvisioning, setIsProvisioning] = useState(false);

    const handleProvisionTenant = async (e) => {
        e.preventDefault();
        if (isProvisioning) return; // guard against double-submit (which the backend now also handles, but UX wise we want one toast)
        setIsProvisioning(true);
        try {
            const res = await apiClient.post('/public/hospitals', newTenant);
            toast.success('Tenant provisioned: database, schema, and admin account ready.');
            setIsAddModalOpen(false);
            setProvisionResult(res.data);
            setNewTenant({ name: '', domain: '', db_name: '', admin_email: '', admin_full_name: '', theme_color: 'blue', is_premium: false });
            fetchTenants();
        } catch (error) {
            // 409 = duplicate domain/db_name; 400 = validation; 401/403 = auth.
            const fallback = error?.response?.status === 409
                ? 'A tenant with that domain or database name already exists.'
                : 'Failed to provision tenant.';
            showApiError(error, fallback);
        } finally {
            setIsProvisioning(false);
        }
    };

    const filteredTenants = tenants.filter(t => t.name.toLowerCase().includes(searchQuery.toLowerCase()) || t.domain.toLowerCase().includes(searchQuery.toLowerCase()));

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={Building2}
                title="Tenant Fleet Manager"
                subtitle="Regulate hospital instances, database connections, and subscriptions."
                tone="brand"
                actions={
                    <button
                        onClick={() => setIsAddModalOpen(true)}
                        className="btn-primary cursor-pointer"
                        type="button"
                    >
                        <Plus size={15} aria-hidden="true" /> Provision new tenant
                    </button>
                }
            />

            {/* Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: 'Active tenants',         value: tenants.length, icon: Building2, ring: 'bg-brand-50  ring-brand-100  text-brand-700' },
                    { label: 'Premium subscriptions',  value: tenants.filter(t => t.is_premium).length, icon: ShieldAlert, ring: 'bg-amber-50 ring-amber-100 text-amber-700' },
                    { label: 'Database nodes',         value: tenants.length, icon: Database, ring: 'bg-accent-50 ring-accent-100 text-accent-700' },
                ].map(({ label, value, icon: Icon, ring }) => (
                    <div key={label} className="stat-tile">
                        <div className={`stat-icon ${ring}`} aria-hidden="true">
                            <Icon size={18} />
                        </div>
                        <div>
                            <p className="stat-label">{label}</p>
                            <p className="stat-value">{value}</p>
                        </div>
                    </div>
                ))}
                <div className="stat-tile">
                    <div className="stat-icon bg-teal-50 ring-teal-100 text-teal-700" aria-hidden="true">
                        <Server size={18} />
                    </div>
                    <div>
                        <p className="stat-label">Server status</p>
                        <p className="text-base font-semibold text-accent-700 mt-1 flex items-center gap-2">
                            <CheckCircle2 size={16} aria-hidden="true" /> Operational
                        </p>
                    </div>
                </div>
            </div>

            {/* Data Table */}
            <div className="card overflow-hidden">
                <div className="p-4 border-b border-ink-200 flex justify-between items-center">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                        <label htmlFor="tenant-filter-search" className="sr-only">Filter tenants</label>
                        <input
                            id="tenant-filter-search"
                            type="search"
                            placeholder="Filter tenants…"
                            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full sm:w-72 bg-white border border-ink-200 rounded-lg pl-9 pr-4 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                        />
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-ink-50 text-ink-600 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-6 py-3">Tenant</th>
                                <th className="px-6 py-3">Domain routing</th>
                                <th className="px-6 py-3">Database node</th>
                                <th className="px-6 py-3">Subscription tier</th>
                                <th className="px-6 py-3 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100 text-ink-700">
                            {isLoading ? (
                                <tr><td colSpan="5" className="px-6 py-12 text-center text-ink-500">Loading global registry…</td></tr>
                            ) : filteredTenants.map(tenant => {
                                const themeRing = {
                                    blue:    'border-blue-200 bg-blue-50 text-blue-700',
                                    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
                                    teal:    'border-brand-200 bg-brand-50 text-brand-700',
                                    rose:    'border-rose-200 bg-rose-50 text-rose-700',
                                    indigo:  'border-indigo-200 bg-indigo-50 text-indigo-700',
                                }[tenant.theme_color] || 'border-blue-200 bg-blue-50 text-blue-700';
                                return (
                                    <tr key={tenant.id} className="hover:bg-ink-50 transition-colors group">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-9 h-9 rounded-xl flex items-center justify-center border ${themeRing}`}>
                                                    <Building2 size={16} />
                                                </div>
                                                <span className="font-semibold text-ink-900 group-hover:text-brand-700 transition-colors">{tenant.name}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 font-mono text-xs text-ink-600">{tenant.domain}</td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                <Database size={13} className="text-ink-500" aria-hidden="true" />
                                                <span className="font-mono text-xs text-accent-700">{tenant.db_name}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            {tenant.is_premium ? (
                                                <span className="badge-warn">Premium</span>
                                            ) : (
                                                <span className="badge-neutral">Standard</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 text-center">
                                            <div className="flex items-center justify-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                                                <button onClick={() => openEdit(tenant)} aria-label={`Edit ${tenant.name}`}
                                                    className="p-2 hover:bg-ink-100 rounded-lg text-ink-500 hover:text-ink-900 transition-colors cursor-pointer" title="Edit configuration">
                                                    <Edit2 size={15} aria-hidden="true" />
                                                </button>
                                                <button onClick={() => handleSuspendToggle(tenant)}
                                                    aria-label={(tenant.is_active ?? true) ? `Suspend ${tenant.name}` : `Reactivate ${tenant.name}`}
                                                    className={`p-2 rounded-lg transition-colors cursor-pointer ${(tenant.is_active ?? true) ? 'text-ink-500 hover:bg-rose-50 hover:text-rose-600' : 'text-accent-600 hover:bg-accent-50'}`}
                                                    title={(tenant.is_active ?? true) ? 'Suspend instance' : 'Reactivate instance'}>
                                                    {(tenant.is_active ?? true) ? <Power size={15} aria-hidden="true" /> : <Zap size={15} aria-hidden="true" />}
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
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in overflow-y-auto"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="edit-tenant-title"
                >
                    <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-4xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                        <div className="px-4 sm:px-6 py-4 border-b border-ink-200 bg-ink-50 flex justify-between items-center shrink-0 gap-3">
                            <div className="min-w-0">
                                <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Tenant configuration</p>
                                <h2 id="edit-tenant-title" className="text-base sm:text-lg font-semibold text-ink-900 tracking-tight truncate">{editing.name}</h2>
                            </div>
                            <button
                                type="button"
                                onClick={() => setEditing(null)}
                                aria-label="Close"
                                className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 transition-colors cursor-pointer shrink-0"
                            >
                                <X size={18} aria-hidden="true" />
                            </button>
                        </div>

                        <form onSubmit={handleEdit} className="flex-1 overflow-y-auto custom-scrollbar">
                            <div className="grid grid-cols-1 lg:grid-cols-5">
                                {/* ── LEFT column: identity + database + custom flags + notes ───── */}
                                <div className="lg:col-span-2 p-5 sm:p-6 space-y-4 border-b lg:border-b-0 lg:border-r border-ink-200 bg-white">
                                    <div>
                                        <label htmlFor="tenant-name" className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Display Name</label>
                                        <input
                                            id="tenant-name"
                                            required
                                            type="text"
                                            value={editForm.name}
                                            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                                            className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all"
                                        />
                                    </div>
                                    <div>
                                        <label htmlFor="tenant-domain" className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Subdomain Route</label>
                                        <input
                                            id="tenant-domain"
                                            required
                                            type="text"
                                            value={editForm.domain}
                                            onChange={(e) => setEditForm({ ...editForm, domain: e.target.value })}
                                            className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all"
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label htmlFor="tenant-theme" className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Theme</label>
                                            <select
                                                id="tenant-theme"
                                                value={editForm.theme_color}
                                                onChange={(e) => setEditForm({ ...editForm, theme_color: e.target.value })}
                                                className="w-full bg-white border border-ink-200 rounded-lg px-3 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all"
                                            >
                                                <option value="blue">Blue</option>
                                                <option value="emerald">Emerald</option>
                                                <option value="rose">Rose</option>
                                                <option value="indigo">Indigo</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label htmlFor="tenant-tier" className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Tier</label>
                                            <select
                                                id="tenant-tier"
                                                value={editForm.is_premium ? 'true' : 'false'}
                                                onChange={(e) => setEditForm({ ...editForm, is_premium: e.target.value === 'true' })}
                                                className="w-full bg-white border border-ink-200 rounded-lg px-3 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all"
                                            >
                                                <option value="false">Standard</option>
                                                <option value="true">Premium</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div className="bg-ink-50 border border-ink-200 rounded-lg p-3 text-xs text-ink-600">
                                        Database name <code className="text-ink-900 font-mono bg-white px-1.5 py-0.5 rounded border border-ink-200">{editing.db_name}</code> is immutable.
                                    </div>
                                </div>

                                {/* ── RIGHT column: package configuration ─────────────────────────── */}
                                <div className="lg:col-span-3 p-5 sm:p-6 space-y-4 bg-ink-50/40">
                                    {/* Package header */}
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex items-start gap-2.5 min-w-0">
                                            <div className="w-9 h-9 rounded-lg bg-brand-50 ring-1 ring-inset ring-brand-100 flex items-center justify-center shrink-0">
                                                <Package size={16} className="text-brand-700" aria-hidden="true" />
                                            </div>
                                            <div className="min-w-0">
                                                <h3 className="text-sm font-semibold text-ink-900 tracking-tight">Package configuration</h3>
                                                <p className="text-xs text-ink-500 mt-0.5">Modules this hospital has access to.</p>
                                            </div>
                                        </div>
                                        {moduleCatalogue.length > 0 && (() => {
                                            const flags = editForm.feature_flags || {};
                                            const optional = moduleCatalogue.filter((m) => !m.always_on);
                                            const enabled = optional.filter((m) =>
                                                flags[m.key] === undefined ? m.default_enabled : !!flags[m.key]
                                            ).length;
                                            return (
                                                <span className="badge-brand inline-flex items-center gap-1 shrink-0">
                                                    <span className="text-brand-900">{enabled}</span>
                                                    <span className="text-brand-700/70">/ {optional.length}</span>
                                                </span>
                                            );
                                        })()}
                                    </div>

                                    {moduleCatalogue.length === 0 ? (
                                        <p className="text-xs text-ink-500 italic bg-white border border-ink-200 rounded-lg p-3">
                                            Module catalogue unavailable — use the custom-flag editor on the right.
                                        </p>
                                    ) : (
                                        <>
                                            {/* Search + bulk actions */}
                                            <div className="flex flex-col sm:flex-row gap-2">
                                                <div className="relative flex-1 min-w-0">
                                                    <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                                                    <label htmlFor="module-search" className="sr-only">Search modules</label>
                                                    <input
                                                        id="module-search"
                                                        type="search"
                                                        value={moduleSearch}
                                                        onChange={(e) => setModuleSearch(e.target.value)}
                                                        placeholder="Search modules…"
                                                        className="w-full bg-white border border-ink-200 rounded-lg pl-8 pr-3 py-1.5 text-xs text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                                    />
                                                </div>
                                                <div className="flex gap-1.5">
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            const flags = { ...(editForm.feature_flags || {}) };
                                                            moduleCatalogue.filter(m => !m.always_on).forEach(m => { flags[m.key] = true; });
                                                            setEditForm({ ...editForm, feature_flags: flags });
                                                        }}
                                                        className="text-2xs font-semibold px-2.5 py-1.5 bg-white border border-ink-200 rounded-lg text-ink-700 hover:bg-ink-50 cursor-pointer"
                                                    >
                                                        Enable all
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            const flags = { ...(editForm.feature_flags || {}) };
                                                            moduleCatalogue.filter(m => !m.always_on).forEach(m => { flags[m.key] = false; });
                                                            setEditForm({ ...editForm, feature_flags: flags });
                                                        }}
                                                        className="text-2xs font-semibold px-2.5 py-1.5 bg-white border border-ink-200 rounded-lg text-ink-700 hover:bg-ink-50 cursor-pointer"
                                                    >
                                                        Disable all
                                                    </button>
                                                </div>
                                            </div>

                                            {/* Always-on group */}
                                            {(() => {
                                                const needle = moduleSearch.trim().toLowerCase();
                                                const matches = (m) => !needle ||
                                                    m.label.toLowerCase().includes(needle) ||
                                                    m.key.toLowerCase().includes(needle) ||
                                                    m.description.toLowerCase().includes(needle);
                                                const alwaysOn = moduleCatalogue.filter(m => m.always_on && matches(m));
                                                const optional = moduleCatalogue.filter(m => !m.always_on && matches(m));
                                                return (
                                                    <>
                                                        {alwaysOn.length > 0 && (
                                                            <div>
                                                                <div className="flex items-center gap-2 mb-1.5">
                                                                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-500">Base subscription</p>
                                                                    <span className="text-[10px] text-ink-400">always on · cannot be disabled</span>
                                                                </div>
                                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                                                    {alwaysOn.map((m) => (
                                                                        <div key={m.key} className="flex items-center justify-between gap-2 bg-white border border-ink-200 rounded-md px-2.5 py-1.5">
                                                                            <div className="min-w-0">
                                                                                <p className="text-xs font-medium text-ink-900 truncate">{m.label}</p>
                                                                                <p className="text-[10px] text-ink-500 truncate font-mono">{m.key}</p>
                                                                            </div>
                                                                            <Lock size={12} className="text-ink-400 shrink-0" aria-label="Always on" />
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </div>
                                                        )}

                                                        {optional.length > 0 && (
                                                            <div>
                                                                <div className="flex items-center gap-2 mb-1.5">
                                                                    <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-500">Add-on modules</p>
                                                                    <span className="text-[10px] text-ink-400">à la carte</span>
                                                                </div>
                                                                <div className="space-y-1.5">
                                                                    {optional.map((m) => {
                                                                        const flags = editForm.feature_flags || {};
                                                                        const explicit = flags[m.key];
                                                                        const enabled = explicit === undefined ? m.default_enabled : !!explicit;
                                                                        return (
                                                                            <label
                                                                                key={m.key}
                                                                                htmlFor={`mod-${m.key}`}
                                                                                className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 cursor-pointer transition-colors border ${
                                                                                    enabled
                                                                                        ? 'bg-brand-50/60 border-brand-200 hover:bg-brand-50'
                                                                                        : 'bg-white border-ink-200 hover:bg-ink-50'
                                                                                }`}
                                                                            >
                                                                                <div className="min-w-0">
                                                                                    <div className="flex items-center gap-2">
                                                                                        <p className="text-sm font-medium text-ink-900 truncate">{m.label}</p>
                                                                                        {enabled && (
                                                                                            <span className="text-[10px] font-semibold text-accent-700 uppercase tracking-wider shrink-0">On</span>
                                                                                        )}
                                                                                    </div>
                                                                                    <p className="text-xs text-ink-500 truncate mt-0.5">{m.description}</p>
                                                                                </div>
                                                                                <span className="shrink-0 inline-flex items-center">
                                                                                    <input
                                                                                        id={`mod-${m.key}`}
                                                                                        type="checkbox"
                                                                                        aria-label={`Enable ${m.label}`}
                                                                                        checked={enabled}
                                                                                        onChange={(e) => setEditForm({
                                                                                            ...editForm,
                                                                                            feature_flags: { ...flags, [m.key]: e.target.checked },
                                                                                        })}
                                                                                        className="sr-only peer"
                                                                                    />
                                                                                    <span className="w-9 h-5 bg-ink-300 rounded-full peer peer-checked:bg-accent-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-4 after:h-4 after:transition peer-checked:after:translate-x-4" />
                                                                                </span>
                                                                            </label>
                                                                        );
                                                                    })}
                                                                </div>
                                                            </div>
                                                        )}

                                                        {alwaysOn.length === 0 && optional.length === 0 && (
                                                            <p className="text-xs text-ink-500 italic text-center py-4">
                                                                No modules match "{moduleSearch}".
                                                            </p>
                                                        )}
                                                    </>
                                                );
                                            })()}
                                        </>
                                    )}
                                </div>
                            </div>

                            {/* ── BELOW the columns: advanced flags + limits + notes ──────────── */}
                            <div className="p-5 sm:p-6 space-y-4 border-t border-ink-200 bg-white">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                            {/* Custom flags — escape hatch for ad-hoc keys that aren't in the
                                canonical module catalogue. Most operators won't need this; it's
                                here so forward-compat with new flags doesn't require a frontend
                                redeploy. */}
                            <details className="bg-ink-50 border border-ink-200 rounded-lg p-4">
                                <summary className="cursor-pointer text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em]">Custom flags (advanced)</summary>
                                <div className="mt-3 space-y-2">
                                    {(() => {
                                        const known = new Set(moduleCatalogue.map((m) => m.key));
                                        const customs = Object.entries(editForm.feature_flags || {}).filter(([k]) => !known.has(k));
                                        if (customs.length === 0) {
                                            return <p className="text-xs text-ink-500 italic">No custom flags. Use the field below to add one.</p>;
                                        }
                                        return customs.map(([k, v]) => (
                                            <div key={k} className="flex items-center justify-between gap-2 text-sm">
                                                <code className="text-ink-700 font-mono text-xs truncate">{k}</code>
                                                <div className="flex items-center gap-2 shrink-0">
                                                    <label className="inline-flex items-center cursor-pointer">
                                                        <span className="sr-only">Toggle {k}</span>
                                                        <input type="checkbox" checked={!!v}
                                                               aria-label={`Toggle ${k}`}
                                                               onChange={(e) => setEditForm({
                                                                   ...editForm,
                                                                   feature_flags: { ...editForm.feature_flags, [k]: e.target.checked },
                                                               })}
                                                               className="sr-only peer" />
                                                        <span className="w-9 h-5 bg-ink-300 rounded-full peer peer-checked:bg-accent-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-4 after:h-4 after:transition peer-checked:after:translate-x-4" />
                                                    </label>
                                                    <button type="button" onClick={() => {
                                                        const next = { ...editForm.feature_flags };
                                                        delete next[k];
                                                        setEditForm({ ...editForm, feature_flags: next });
                                                    }} className="text-ink-500 hover:text-rose-600 cursor-pointer p-1 -m-1 rounded" aria-label={`Remove ${k}`}>
                                                        <X size={14} aria-hidden="true" />
                                                    </button>
                                                </div>
                                            </div>
                                        ));
                                    })()}
                                </div>
                                <div className="flex flex-wrap gap-2 mt-3">
                                    <label htmlFor="flag-key" className="sr-only">Custom flag key</label>
                                    <input
                                        id="flag-key"
                                        type="text"
                                        placeholder="flag_key"
                                        value={flagDraft.key}
                                        onChange={(e) => setFlagDraft({ ...flagDraft, key: e.target.value })}
                                        className="flex-1 min-w-0 bg-white border border-ink-200 rounded-lg px-3 py-2 text-xs text-ink-900 font-mono focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                    />
                                    <label htmlFor="flag-value" className="sr-only">Custom flag value</label>
                                    <select
                                        id="flag-value"
                                        value={flagDraft.value ? 'true' : 'false'}
                                        onChange={(e) => setFlagDraft({ ...flagDraft, value: e.target.value === 'true' })}
                                        className="bg-white border border-ink-200 rounded-lg px-3 py-2 text-xs text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                    >
                                        <option value="true">On</option>
                                        <option value="false">Off</option>
                                    </select>
                                    <button type="button" onClick={() => {
                                        if (!flagDraft.key.trim()) return;
                                        setEditForm({
                                            ...editForm,
                                            feature_flags: { ...editForm.feature_flags, [flagDraft.key.trim()]: flagDraft.value },
                                        });
                                        setFlagDraft({ key: '', value: true });
                                    }} className="px-3 py-2 bg-ink-100 hover:bg-ink-200 text-ink-700 rounded-lg text-xs font-semibold cursor-pointer">Add</button>
                                </div>
                            </details>

                            {/* Plan limits */}
                            <div className="bg-ink-50 border border-ink-200 rounded-lg p-4">
                                <div className="flex items-center justify-between mb-3">
                                    <div>
                                        <p className="text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em]">Plan limits</p>
                                        <p className="text-xs text-ink-500 mt-0.5">Numeric caps — max_users, storage_gb, max_patients…</p>
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    {Object.keys(editForm.plan_limits || {}).length === 0 && (
                                        <p className="text-xs text-ink-500 italic">No limits set.</p>
                                    )}
                                    {Object.entries(editForm.plan_limits || {}).map(([k, v]) => (
                                        <div key={k} className="grid grid-cols-12 gap-2 items-center">
                                            <code className="col-span-5 text-ink-700 font-mono text-xs truncate">{k}</code>
                                            <label htmlFor={`limit-${k}`} className="sr-only">{k}</label>
                                            <input
                                                id={`limit-${k}`}
                                                type="number"
                                                value={v}
                                                aria-label={`${k} limit`}
                                                onChange={(e) => setEditForm({
                                                    ...editForm,
                                                    plan_limits: { ...editForm.plan_limits, [k]: parseFloat(e.target.value) || 0 },
                                                })}
                                                className="col-span-6 bg-white border border-ink-200 rounded-lg px-3 py-1.5 text-xs text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                            />
                                            <button type="button" onClick={() => {
                                                const next = { ...editForm.plan_limits };
                                                delete next[k];
                                                setEditForm({ ...editForm, plan_limits: next });
                                            }} className="col-span-1 text-ink-500 hover:text-rose-600 cursor-pointer p-1 -m-1 rounded" aria-label={`Remove ${k}`}>
                                                <X size={14} aria-hidden="true" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex flex-wrap gap-2 mt-3">
                                    <label htmlFor="limit-key" className="sr-only">New limit key</label>
                                    <input
                                        id="limit-key"
                                        type="text"
                                        placeholder="limit_key"
                                        value={limitDraft.key}
                                        onChange={(e) => setLimitDraft({ ...limitDraft, key: e.target.value })}
                                        className="flex-1 min-w-0 bg-white border border-ink-200 rounded-lg px-3 py-2 text-xs text-ink-900 font-mono focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                    />
                                    <label htmlFor="limit-val" className="sr-only">New limit value</label>
                                    <input
                                        id="limit-val"
                                        type="number"
                                        placeholder="0"
                                        value={limitDraft.value}
                                        onChange={(e) => setLimitDraft({ ...limitDraft, value: parseFloat(e.target.value) || 0 })}
                                        className="w-24 bg-white border border-ink-200 rounded-lg px-3 py-2 text-xs text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                    />
                                    <button type="button" onClick={() => {
                                        if (!limitDraft.key.trim()) return;
                                        setEditForm({
                                            ...editForm,
                                            plan_limits: { ...editForm.plan_limits, [limitDraft.key.trim()]: limitDraft.value },
                                        });
                                        setLimitDraft({ key: '', value: 0 });
                                    }} className="px-3 py-2 bg-ink-100 hover:bg-ink-200 text-ink-700 rounded-lg text-xs font-semibold cursor-pointer">Add</button>
                                </div>
                            </div>
                                </div>  {/* close advanced grid */}

                                <div>
                                    <label htmlFor="tenant-notes" className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Operator notes</label>
                                    <textarea
                                        id="tenant-notes"
                                        rows="3"
                                        value={editForm.notes}
                                        onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                                        className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none resize-none"
                                        placeholder="Internal note. Not visible to the tenant."
                                    />
                                </div>
                            </div>  {/* close advanced wrapper */}

                            <div className="px-5 sm:px-6 py-4 border-t border-ink-200 bg-ink-50 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 sticky bottom-0">
                                <button type="button" onClick={() => setEditing(null)} className="btn-secondary cursor-pointer">Cancel</button>
                                <button type="submit" disabled={savingEdit}
                                    className="btn-primary disabled:opacity-50 cursor-pointer">
                                    {savingEdit ? 'Saving…' : 'Save changes'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* One-time provisioning result — shows admin temp password.
                Kept amber-accented because this is a one-shot warning surface:
                "save this now, you won't see it again." The amber band reads as
                "important, time-sensitive" against the otherwise neutral light
                surfaces. */}
            {provisionResult && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/40 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-lg overflow-hidden animate-slide-up">
                        <div className="px-6 py-4 border-b border-amber-100 bg-amber-50">
                            <h2 className="text-base font-semibold text-amber-900 tracking-tight">Tenant ready &mdash; admin temporary password</h2>
                            <p className="text-xs text-amber-800 mt-1">Shown once. Deliver to the admin via a secure channel.</p>
                        </div>
                        <div className="p-6 space-y-3 text-sm">
                            <div className="bg-ink-50 border border-ink-200 rounded-xl p-4">
                                <div className="text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em] mb-2">Tenant</div>
                                <div className="text-ink-900 font-semibold">{provisionResult.db_name}</div>
                            </div>
                            <div className="bg-ink-50 border border-ink-200 rounded-xl p-4">
                                <div className="text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em] mb-2">Admin email</div>
                                <div className="text-ink-900 font-mono text-xs break-all">{provisionResult.admin_email}</div>
                            </div>
                            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                                <div className="text-2xs font-semibold text-amber-800 uppercase tracking-[0.14em] mb-2">Temporary password</div>
                                <code className="text-ink-900 font-mono text-base break-all select-all">{provisionResult.admin_temp_password}</code>
                                <button
                                    type="button"
                                    onClick={() => { navigator.clipboard.writeText(provisionResult.admin_temp_password); toast.success('Copied'); }}
                                    className="mt-3 inline-flex items-center gap-1 text-xs text-amber-800 hover:text-amber-900 font-semibold cursor-pointer"
                                >
                                    Copy to clipboard
                                </button>
                            </div>
                            <p className="text-xs text-ink-500 leading-relaxed">
                                The admin will be forced to choose a new password on first login.
                            </p>
                            <div className="flex justify-end pt-2">
                                <button type="button" onClick={() => setProvisionResult(null)} className="btn-primary cursor-pointer">
                                    I&rsquo;ve saved it &mdash; close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Provision Modal */}
            {isAddModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-lg overflow-hidden animate-slide-up">
                        <div className="px-6 py-4 border-b border-ink-200 bg-ink-50 flex justify-between items-center">
                            <h2 className="text-base font-semibold text-ink-900 tracking-tight">Provision new tenant</h2>
                            <button onClick={() => setIsAddModalOpen(false)} aria-label="Close" className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 transition-colors cursor-pointer"><X size={18} /></button>
                        </div>
                        <form onSubmit={handleProvisionTenant} className="p-6 space-y-4">
                            <div>
                                <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Hospital Name</label>
                                <input required type="text" value={newTenant.name} onChange={e => setNewTenant({...newTenant, name: e.target.value})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all" placeholder="e.g. Aga Khan Hospital" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Subdomain Route</label>
                                    <input required type="text" value={newTenant.domain} onChange={e => setNewTenant({...newTenant, domain: e.target.value})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all" placeholder="e.g. agakhan.hms.com" />
                                </div>
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Database Name</label>
                                    <input required type="text" value={newTenant.db_name} onChange={e => setNewTenant({...newTenant, db_name: e.target.value})} className="w-full bg-ink-50 border border-ink-200 rounded-lg px-4 py-2 text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none font-mono text-sm" placeholder="e.g. agakhan_db" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Bootstrap Admin Email</label>
                                    <input required type="email" value={newTenant.admin_email} onChange={e => setNewTenant({...newTenant, admin_email: e.target.value})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all" placeholder="admin@agakhan.com" />
                                </div>
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Admin Full Name</label>
                                    <input required type="text" value={newTenant.admin_full_name} onChange={e => setNewTenant({...newTenant, admin_full_name: e.target.value})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all" placeholder="Jane Mwangi" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Theme Color</label>
                                    <select value={newTenant.theme_color} onChange={e => setNewTenant({...newTenant, theme_color: e.target.value})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all">
                                        <option value="blue">Blue (Default)</option>
                                        <option value="emerald">Emerald</option>
                                        <option value="rose">Rose</option>
                                        <option value="indigo">Indigo</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-2xs font-semibold text-ink-700 uppercase tracking-[0.14em] mb-1.5">Subscription Tier</label>
                                    <select value={newTenant.is_premium} onChange={e => setNewTenant({...newTenant, is_premium: e.target.value === 'true'})} className="w-full bg-white border border-ink-200 rounded-lg px-3.5 py-2.5 text-sm text-ink-900 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-none transition-all">
                                        <option value="false">Standard (Basic Modules)</option>
                                        <option value="true">Premium (All Modules)</option>
                                    </select>
                                </div>
                            </div>
                            <div className="mt-6 pt-5 border-t border-ink-200 flex justify-end gap-2">
                                <button type="button" onClick={() => setIsAddModalOpen(false)} className="btn-secondary cursor-pointer">Cancel</button>
                                <button type="submit" disabled={isProvisioning} className="btn-primary disabled:opacity-60 disabled:cursor-not-allowed">{isProvisioning ? 'Provisioning…' : 'Deploy database instance'}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
