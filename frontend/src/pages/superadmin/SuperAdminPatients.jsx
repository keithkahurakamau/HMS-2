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
                eyebrow="Console"
                icon={Users}
                title="Patients — cross-tenant"
                subtitle="Read-only browser across every active tenant database."
                tone="brand"
                meta={
                    <span className="badge-success inline-flex items-center gap-1.5">
                        <ShieldCheck size={11} aria-hidden="true" /> Read-only
                    </span>
                }
                actions={
                    <button
                        type="button"
                        onClick={fetchPatients}
                        className="btn-secondary cursor-pointer"
                    >
                        <RefreshCw size={14} aria-hidden="true" /> Refresh
                    </button>
                }
            />

            {/* Filters */}
            <div className="card p-4 flex flex-col sm:flex-row flex-wrap gap-3 sm:items-center">
                <div className="relative flex-1 min-w-0 sm:min-w-[18rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="patient-search" className="sr-only">Search patients</label>
                    <input
                        id="patient-search"
                        type="search"
                        placeholder="Search by name, OP number, phone…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full bg-white border border-ink-200 rounded-lg pl-9 pr-4 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                    />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="tenant-filter" className="sr-only">Filter by tenant</label>
                    <select
                        id="tenant-filter"
                        value={tenantFilter}
                        onChange={(e) => setTenantFilter(e.target.value)}
                        className="w-full sm:w-auto bg-white border border-ink-200 rounded-lg pl-9 pr-8 py-2 text-sm text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                    >
                        <option value="">All tenants ({tenants.length})</option>
                        {tenants.map(t => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
                    </select>
                </div>
                <div className="text-xs text-ink-500 sm:ml-auto">
                    {patients.length} record{patients.length === 1 ? '' : 's'}
                </div>
            </div>

            {errors.length > 0 && (
                <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="text-rose-600 shrink-0 mt-0.5" aria-hidden="true" />
                    <div>
                        <p className="font-semibold uppercase tracking-[0.14em] text-2xs text-rose-700">Partial results</p>
                        <ul className="mt-1 space-y-0.5">
                            {errors.map((e, i) => (
                                <li key={i} className="font-mono"><span className="text-rose-900">{e.tenant_db}</span> · {e.error}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}

            {/* Patient list */}
            {isLoading ? (
                <div className="card p-12 text-center text-ink-600">
                    <Activity className="animate-spin mx-auto mb-2 text-brand-600" size={20} aria-hidden="true" /> Aggregating patients across tenants…
                </div>
            ) : patients.length === 0 ? (
                <div className="card p-12 text-center text-ink-500">
                    No patients match your filters.
                </div>
            ) : (
                <div className="space-y-4">
                    {Object.entries(grouped).map(([key, rows]) => {
                        const [, tenantName] = key.split(':');
                        return (
                            <div key={key} className="card overflow-hidden">
                                <div className="px-5 py-3 border-b border-ink-200 bg-ink-50 flex items-center gap-2">
                                    <Building2 size={14} className="text-brand-600" aria-hidden="true" />
                                    <h2 className="font-semibold text-ink-900 text-sm tracking-tight truncate">{tenantName}</h2>
                                    <span className="text-2xs text-ink-500 font-mono ml-auto shrink-0">{rows.length} patient{rows.length === 1 ? '' : 's'}</span>
                                </div>

                                {/* Desktop table */}
                                <div className="hidden md:block overflow-x-auto">
                                    <table className="w-full text-left text-sm">
                                        <thead className="bg-ink-50 text-ink-600 text-2xs uppercase font-semibold tracking-[0.14em]">
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
                                        <tbody className="divide-y divide-ink-100 text-ink-700">
                                            {rows.map(p => (
                                                <tr key={`${p.tenant_id}:${p.patient_id}`} className="hover:bg-ink-50 transition-colors">
                                                    <td className="px-5 py-3 font-mono text-xs text-brand-700">{p.outpatient_no}</td>
                                                    <td className="px-5 py-3 font-semibold text-ink-900">{p.surname}, {p.other_names}</td>
                                                    <td className="px-5 py-3 text-xs">{p.sex} · {p.date_of_birth || '—'}</td>
                                                    <td className="px-5 py-3 text-xs"><Phone size={11} className="inline mr-1 text-ink-400" aria-hidden="true" /> {p.telephone_1 || '—'}</td>
                                                    <td className="px-5 py-3 text-xs"><MapPin size={11} className="inline mr-1 text-ink-400" aria-hidden="true" /> {p.town || '—'}</td>
                                                    <td className="px-5 py-3 text-xs text-ink-500"><Calendar size={11} className="inline mr-1" aria-hidden="true" /> {p.registered_on ? new Date(p.registered_on).toLocaleDateString() : '—'}</td>
                                                    <td className="px-5 py-3 text-right">
                                                        <button
                                                            type="button"
                                                            onClick={() => openDetail(p)}
                                                            aria-label={`View ${p.outpatient_no}`}
                                                            className="p-2 rounded-lg text-ink-500 hover:text-brand-700 hover:bg-ink-100 transition-colors cursor-pointer"
                                                        >
                                                            <Eye size={15} aria-hidden="true" />
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>

                                {/* Mobile card list — preserves info without horizontal scroll */}
                                <ul className="md:hidden divide-y divide-ink-100">
                                    {rows.map(p => (
                                        <li key={`${p.tenant_id}:${p.patient_id}-mb`} className="p-4">
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0">
                                                    <p className="font-semibold text-ink-900 truncate">{p.surname}, {p.other_names}</p>
                                                    <p className="text-xs text-brand-700 font-mono mt-0.5">{p.outpatient_no}</p>
                                                    <p className="text-xs text-ink-600 mt-1">{p.sex} · {p.date_of_birth || '—'}</p>
                                                    <p className="text-xs text-ink-600 mt-0.5 flex items-center gap-1"><Phone size={11} aria-hidden="true" /> {p.telephone_1 || '—'}</p>
                                                    <p className="text-xs text-ink-500 mt-0.5 flex items-center gap-1"><MapPin size={11} aria-hidden="true" /> {p.town || '—'}</p>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => openDetail(p)}
                                                    aria-label={`View ${p.outpatient_no}`}
                                                    className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-lg text-ink-500 hover:text-brand-700 hover:bg-ink-100 transition-colors cursor-pointer"
                                                >
                                                    <Eye size={18} aria-hidden="true" />
                                                </button>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Detail drawer */}
            {selected && (
                <div
                    className="fixed inset-0 z-50 flex justify-end"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="patient-detail-title"
                >
                    <div
                        className="absolute inset-0 bg-ink-900/50 backdrop-blur-sm"
                        onClick={() => setSelected(null)}
                        aria-hidden="true"
                    />
                    <div className="relative w-full max-w-3xl h-full bg-white border-l border-ink-200 shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="px-4 sm:px-6 py-4 border-b border-ink-200 bg-ink-50 flex items-start justify-between gap-3 shrink-0">
                            <div className="min-w-0">
                                <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-brand-700">Read-only patient view</span>
                                <h2 id="patient-detail-title" className="text-base font-semibold text-ink-900 mt-0.5 truncate">{selected.surname}, {selected.other_names}</h2>
                                <p className="text-xs text-ink-600 mt-0.5">Tenant: <span className="text-ink-900 font-medium">{selected.tenant_name}</span> · OP <span className="font-mono text-brand-700">{selected.outpatient_no}</span></p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setSelected(null)}
                                aria-label="Close patient detail"
                                className="p-2 text-ink-500 hover:text-ink-900 hover:bg-ink-100 rounded-lg cursor-pointer shrink-0"
                            >
                                <X size={18} aria-hidden="true" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 sm:p-6 custom-scrollbar">
                            {detailLoading ? (
                                <div className="text-center py-12 text-ink-600">
                                    <Activity className="animate-spin mx-auto mb-2 text-brand-600" size={20} aria-hidden="true" /> Loading…
                                </div>
                            ) : detail ? (
                                <div className="space-y-4">
                                    <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-xl p-3 text-2xs flex items-center gap-2">
                                        <ShieldCheck size={13} aria-hidden="true" /> Read-only — no actions are exposed in this view.
                                    </div>
                                    <div className="card divide-y divide-ink-100">
                                        {Object.entries(detail).filter(([k]) => k !== 'tenant').map(([k, v]) => (
                                            <div key={k} className="px-4 sm:px-5 py-3 grid grid-cols-1 sm:grid-cols-3 gap-1 sm:gap-3 items-start">
                                                <div className="text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em]">{k.replace(/_/g, ' ')}</div>
                                                <div className="sm:col-span-2 text-sm text-ink-900 break-words">
                                                    {v === null || v === '' ? <span className="text-ink-500 italic">empty</span> :
                                                        typeof v === 'object' ? <code className="font-mono text-xs text-ink-700">{JSON.stringify(v)}</code> :
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
