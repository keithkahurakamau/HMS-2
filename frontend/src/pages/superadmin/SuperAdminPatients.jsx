import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    Users, Search, Building2, Phone, MapPin, Calendar, ShieldCheck,
    Activity, Eye, X, Filter, AlertTriangle, RefreshCw,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin patient browser — READ-ONLY, end-to-end.                       */
/*                                                                            */
/*  No write paths exist. Every column is shown as text only. Cross-tenant    */
/*  reads go through /api/public/superadmin/patients which iterates each      */
/*  active tenant DB in its own session.                                      */
/* ────────────────────────────────────────────────────────────────────────── */

export default function SuperAdminPatients() {
    const [patients, setPatients] = useState([]);
    const [tenants, setTenants] = useState([]);
    const [errors, setErrors] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [tenantFilter, setTenantFilter] = useState('');
    const [selected, setSelected] = useState(null);
    const [detail, setDetail] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get('/public/hospitals?include_inactive=false');
                setTenants(res.data || []);
            } catch {
                // non-fatal — the picker just stays empty
            }
        })();
    }, []);

    useEffect(() => {
        const t = setTimeout(() => fetchPatients(), 350);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search, tenantFilter]);

    const fetchPatients = async () => {
        setIsLoading(true);
        try {
            const params = new URLSearchParams();
            if (search) params.set('search', search);
            if (tenantFilter) params.set('tenant_id', tenantFilter);
            params.set('limit_per_tenant', '100');
            const res = await apiClient.get(`/public/superadmin/patients?${params.toString()}`);
            setPatients(res.data.patients || []);
            setErrors(res.data.errors || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load patients.');
        } finally {
            setIsLoading(false);
        }
    };

    const openDetail = async (p) => {
        setSelected(p);
        setDetail(null);
        setDetailLoading(true);
        try {
            const res = await apiClient.get(`/public/superadmin/patients/${p.tenant_id}/${p.patient_id}`);
            setDetail(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load patient.');
        } finally {
            setDetailLoading(false);
        }
    };

    const grouped = useMemo(() => {
        const map = {};
        for (const p of patients) {
            const key = `${p.tenant_id}:${p.tenant_name}`;
            (map[key] = map[key] || []).push(p);
        }
        return map;
    }, [patients]);

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                surface="dark"
                tone="warning"
                eyebrow="Console"
                icon={Users}
                title="Patients — cross-tenant"
                subtitle="Read-only browser across every active tenant database."
                meta={
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-500/10 ring-1 ring-accent-500/20 text-2xs font-semibold uppercase tracking-wider text-accent-300">
                        <ShieldCheck size={11} /> Read-only
                    </span>
                }
                actions={
                    <button onClick={fetchPatients} className="px-4 py-2 bg-white/5 hover:bg-white/10 text-white rounded-lg text-sm font-semibold ring-1 ring-white/10 flex items-center gap-2 cursor-pointer">
                        <RefreshCw size={14} /> Refresh
                    </button>
                }
            />

            {/* Filters */}
            <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-4 flex flex-wrap gap-3 items-center">
                <div className="relative flex-1 min-w-[18rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                    <input type="text" placeholder="Search by name, OP number, phone…"
                           value={search} onChange={(e) => setSearch(e.target.value)}
                           className="w-full bg-ink-900/60 ring-1 ring-white/10 rounded-lg pl-9 pr-4 py-2 text-sm text-white placeholder-ink-500 focus:outline-none focus:ring-amber-500/30" />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500" />
                    <select value={tenantFilter} onChange={(e) => setTenantFilter(e.target.value)}
                            className="bg-ink-900/60 ring-1 ring-white/10 rounded-lg pl-9 pr-8 py-2 text-sm text-white focus:outline-none focus:ring-amber-500/30">
                        <option value="">All tenants ({tenants.length})</option>
                        {tenants.map(t => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
                    </select>
                </div>
                <div className="text-xs text-ink-400 ml-auto">
                    {patients.length} record{patients.length === 1 ? '' : 's'}
                </div>
            </div>

            {errors.length > 0 && (
                <div className="bg-rose-500/10 ring-1 ring-rose-500/30 text-rose-200 rounded-xl p-4 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="text-rose-400 shrink-0 mt-0.5" />
                    <div>
                        <p className="font-semibold uppercase tracking-[0.14em] text-2xs text-rose-300">Partial results</p>
                        <ul className="mt-1 space-y-0.5">
                            {errors.map((e, i) => (
                                <li key={i} className="font-mono"><span className="text-rose-100">{e.tenant_db}</span> · {e.error}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}

            {/* Patient list */}
            {isLoading ? (
                <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-12 text-center text-ink-400">
                    <Activity className="animate-spin mx-auto mb-2 text-amber-400" size={20} /> Aggregating patients across tenants…
                </div>
            ) : patients.length === 0 ? (
                <div className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl p-12 text-center text-ink-500">
                    No patients match your filters.
                </div>
            ) : (
                <div className="space-y-4">
                    {Object.entries(grouped).map(([key, rows]) => {
                        const [, tenantName] = key.split(':');
                        return (
                            <div key={key} className="bg-white/[0.04] backdrop-blur-md ring-1 ring-white/10 rounded-2xl overflow-hidden">
                                <div className="px-5 py-3 border-b border-white/5 bg-white/[0.02] flex items-center gap-2">
                                    <Building2 size={14} className="text-amber-400" />
                                    <h2 className="font-semibold text-white text-sm tracking-tight">{tenantName}</h2>
                                    <span className="text-2xs text-ink-500 font-mono ml-auto">{rows.length} patient{rows.length === 1 ? '' : 's'}</span>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left text-sm">
                                        <thead className="bg-white/[0.02] text-ink-400 text-2xs uppercase font-semibold tracking-[0.14em]">
                                            <tr>
                                                <th className="px-5 py-3">OP #</th>
                                                <th className="px-5 py-3">Name</th>
                                                <th className="px-5 py-3">Sex / DOB</th>
                                                <th className="px-5 py-3">Phone</th>
                                                <th className="px-5 py-3">Town</th>
                                                <th className="px-5 py-3">Registered</th>
                                                <th className="px-5 py-3 text-right">View</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5 text-ink-300">
                                            {rows.map(p => (
                                                <tr key={`${p.tenant_id}:${p.patient_id}`} className="hover:bg-white/[0.02]">
                                                    <td className="px-5 py-3 font-mono text-xs text-amber-300">{p.outpatient_no}</td>
                                                    <td className="px-5 py-3 font-semibold text-white">{p.surname}, {p.other_names}</td>
                                                    <td className="px-5 py-3 text-xs">{p.sex} · {p.date_of_birth || '—'}</td>
                                                    <td className="px-5 py-3 text-xs"><Phone size={11} className="inline mr-1 text-ink-500" /> {p.telephone_1 || '—'}</td>
                                                    <td className="px-5 py-3 text-xs"><MapPin size={11} className="inline mr-1 text-ink-500" /> {p.town || '—'}</td>
                                                    <td className="px-5 py-3 text-xs text-ink-500"><Calendar size={11} className="inline mr-1" /> {p.registered_on ? new Date(p.registered_on).toLocaleDateString() : '—'}</td>
                                                    <td className="px-5 py-3 text-right">
                                                        <button onClick={() => openDetail(p)} aria-label={`View ${p.outpatient_no}`}
                                                                className="p-2 rounded-lg text-ink-400 hover:text-amber-300 hover:bg-white/10">
                                                            <Eye size={15} />
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Detail drawer */}
            {selected && (
                <div className="fixed inset-0 z-50 flex justify-end">
                    <div className="absolute inset-0 bg-ink-950/80 backdrop-blur-sm" onClick={() => setSelected(null)} />
                    <div className="relative w-full max-w-3xl h-full bg-ink-900 ring-1 ring-white/10 shadow-elevated flex flex-col">
                        <div className="px-6 py-4 border-b border-white/10 bg-white/[0.02] flex items-center justify-between shrink-0">
                            <div>
                                <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-amber-400">Read-only patient view</span>
                                <h2 className="text-base font-semibold text-white mt-0.5">{selected.surname}, {selected.other_names}</h2>
                                <p className="text-xs text-ink-400 mt-0.5">Tenant: <span className="text-ink-200 font-medium">{selected.tenant_name}</span> · OP <span className="font-mono text-amber-300">{selected.outpatient_no}</span></p>
                            </div>
                            <button onClick={() => setSelected(null)} aria-label="Close" className="p-2 text-ink-400 hover:text-white hover:bg-white/10 rounded-lg">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
                            {detailLoading ? (
                                <div className="text-center py-12 text-ink-400">
                                    <Activity className="animate-spin mx-auto mb-2 text-amber-400" size={20} /> Loading…
                                </div>
                            ) : detail ? (
                                <div className="space-y-4">
                                    <div className="bg-amber-500/10 ring-1 ring-amber-500/30 text-amber-100 rounded-xl p-3 text-2xs flex items-center gap-2">
                                        <ShieldCheck size={13} /> Read-only — no actions are exposed in this view.
                                    </div>
                                    <div className="bg-white/[0.04] ring-1 ring-white/10 rounded-2xl divide-y divide-white/5">
                                        {Object.entries(detail).filter(([k]) => k !== 'tenant').map(([k, v]) => (
                                            <div key={k} className="px-5 py-3 grid grid-cols-3 gap-3 items-start">
                                                <div className="text-2xs font-semibold text-ink-400 uppercase tracking-[0.14em]">{k.replace(/_/g, ' ')}</div>
                                                <div className="col-span-2 text-sm text-ink-100 break-words">
                                                    {v === null || v === '' ? <span className="text-ink-500 italic">empty</span> :
                                                        typeof v === 'object' ? <code className="font-mono text-xs">{JSON.stringify(v)}</code> :
                                                        String(v)}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <p className="text-ink-500 text-sm">Unable to load patient.</p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
