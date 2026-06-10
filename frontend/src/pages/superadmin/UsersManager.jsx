import React, { useEffect, useMemo, useReducer, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    KeyRound, Search, Building2, ShieldCheck, ShieldAlert, Activity, Filter,
    AlertTriangle, RefreshCw, Lock, Unlock, UserCheck, UserX, Copy, Check, X,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin — Users & Access (cross-tenant).                               */
/*                                                                            */
/*  SECURE BY DESIGN. Passwords are Argon2id-hashed (one-way) and are NEVER   */
/*  fetched or displayed — there is no endpoint that can return one. The      */
/*  recovery model is RESET, not reveal: issue a one-time temp password       */
/*  (forced change at next login), unlock a locked account, or disable it.    */
/* ────────────────────────────────────────────────────────────────────────── */

function StatusBadge({ user }) {
    if (!user.is_active) {
        return <span className="badge bg-rose-50 text-rose-700 ring-1 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20 inline-flex items-center gap-1"><UserX size={11} aria-hidden="true" /> Disabled</span>;
    }
    if (user.is_locked) {
        return <span className="badge bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20 inline-flex items-center gap-1"><Lock size={11} aria-hidden="true" /> Locked</span>;
    }
    if (user.must_change_password) {
        return <span className="badge bg-sky-50 text-sky-700 ring-1 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/20 inline-flex items-center gap-1"><KeyRound size={11} aria-hidden="true" /> Must reset</span>;
    }
    return <span className="badge-success inline-flex items-center gap-1"><UserCheck size={11} aria-hidden="true" /> Active</span>;
}

// Cross-tenant user list + the tenant picker + per-tenant load errors + loading
// flag are loaded together, so they share one reducer.
const initialData = { users: [], tenants: [], errors: [], isLoading: true };
function dataReducer(state, action) {
    switch (action.type) {
        case 'setTenants': return { ...state, tenants: action.value };
        case 'loading':    return { ...state, isLoading: true };
        case 'loaded':     return { ...state, users: action.users, errors: action.errors };
        case 'done':       return { ...state, isLoading: false };
        default:           return state;
    }
}

// The one-time temp-password result modal: the issued result + its copied flag.
const initialTempPwd = { tempResult: null, copied: false };
function tempPwdReducer(state, action) {
    switch (action.type) {
        case 'show':      return { tempResult: action.result, copied: false };
        case 'clear':     return { tempResult: null, copied: false };
        case 'setCopied': return { ...state, copied: action.value };
        default:          return state;
    }
}

// Pure helper hoisted to module scope (no component state).
const keyOf = (u) => `${u.tenant_id}:${u.user_id}`;

const RESET_BADGE = (
    <span className="badge-success inline-flex items-center gap-1.5">
        <ShieldCheck size={11} aria-hidden="true" /> Reset, not reveal
    </span>
);

export default function UsersManager() {
    const [data, dispatchData] = useReducer(dataReducer, initialData);
    const { users, tenants, errors, isLoading } = data;
    const [search, setSearch] = useState('');
    const [tenantFilter, setTenantFilter] = useState('');
    const [busyKey, setBusyKey] = useState(null);     // user currently being acted on
    const [tempPwd, dispatchTemp] = useReducer(tempPwdReducer, initialTempPwd);
    const { tempResult, copied } = tempPwd;

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get('/public/hospitals?include_inactive=false');
                dispatchData({ type: 'setTenants', value: res.data || [] });
            } catch {
                // non-fatal — picker just stays empty
            }
        })();
    }, []);

    useEffect(() => {
        const t = setTimeout(() => fetchUsers(), 350);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search, tenantFilter]);

    const fetchUsers = async () => {
        dispatchData({ type: 'loading' });
        try {
            const params = new URLSearchParams();
            if (search) params.set('search', search);
            if (tenantFilter) params.set('tenant_id', tenantFilter);
            params.set('limit_per_tenant', '200');
            const res = await apiClient.get(`/public/superadmin/users?${params.toString()}`);
            dispatchData({ type: 'loaded', users: res.data.users || [], errors: res.data.errors || [] });
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load users.');
        } finally {
            dispatchData({ type: 'done' });
        }
    };

    const resetPassword = async (u) => {
        if (!window.confirm(`Issue a one-time temporary password for ${u.full_name} (${u.email})?\n\nTheir current password stops working immediately and they must set a new one at next login.`)) return;
        setBusyKey(keyOf(u));
        try {
            const res = await apiClient.post(`/public/superadmin/users/${u.tenant_id}/${u.user_id}/reset-password`, {});
            dispatchTemp({ type: 'show', result: { user: u, temporary_password: res.data.temporary_password } });
            toast.success('Temporary password issued.');
            fetchUsers();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to reset password.');
        } finally {
            setBusyKey(null);
        }
    };

    const accountAction = async (u, body, label) => {
        setBusyKey(keyOf(u));
        try {
            await apiClient.post(`/public/superadmin/users/${u.tenant_id}/${u.user_id}/account`, body);
            toast.success(`User ${label}.`);
            fetchUsers();
        } catch (e) {
            toast.error(e.response?.data?.detail || `Failed to ${label} user.`);
        } finally {
            setBusyKey(null);
        }
    };

    const toggleActive = (u) => {
        if (u.is_active && !window.confirm(`Disable ${u.full_name}? They will be signed out and unable to log in.`)) return;
        accountAction(u, { is_active: !u.is_active }, u.is_active ? 'disabled' : 'enabled');
    };
    const unlock = (u) => accountAction(u, { unlock: true }, 'unlocked');

    const copyTemp = async () => {
        try {
            await navigator.clipboard.writeText(tempResult.temporary_password);
            dispatchTemp({ type: 'setCopied', value: true });
            setTimeout(() => dispatchTemp({ type: 'setCopied', value: false }), 2000);
        } catch {
            toast.error('Copy failed — select and copy manually.');
        }
    };

    const grouped = useMemo(() => {
        const map = {};
        for (const u of users) {
            const key = `${u.tenant_id}:${u.tenant_name}`;
            (map[key] = map[key] || []).push(u);
        }
        return map;
    }, [users]);

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Console"
                icon={KeyRound}
                title="Users & Access — cross-tenant"
                subtitle="Recover access securely: reset, unlock, or disable. Passwords are never shown."
                tone="brand"
                meta={RESET_BADGE}
                actions={
                    <button type="button" onClick={fetchUsers} className="btn-secondary cursor-pointer">
                        <RefreshCw size={14} aria-hidden="true" /> Refresh
                    </button>
                }
            />

            {/* Why no "view password" — keeps the security model explicit. */}
            <div className="bg-sky-50 border border-sky-200 text-sky-900 dark:bg-sky-500/10 dark:border-sky-500/20 dark:text-sky-200 rounded-xl p-3 text-xs flex items-start gap-2">
                <ShieldCheck size={14} className="text-sky-600 dark:text-sky-400 shrink-0 mt-0.5" aria-hidden="true" />
                <span>
                    Passwords are stored as one-way Argon2id hashes and cannot be displayed by anyone — including platform staff.
                    To get a user back in, <strong>issue a temporary password</strong> (they’re forced to change it on next login) or <strong>unlock</strong> their account.
                </span>
            </div>

            {/* Filters */}
            <div className="card p-4 flex flex-col sm:flex-row flex-wrap gap-3 sm:items-center">
                <div className="relative flex-1 min-w-0 sm:min-w-[18rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="user-search" className="sr-only">Search users</label>
                    <input
                        id="user-search"
                        type="search"
                        placeholder="Search by name, email, or role…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-4 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 transition-all"
                    />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="user-tenant-filter" className="sr-only">Filter by tenant</label>
                    <select
                        id="user-tenant-filter"
                        value={tenantFilter}
                        onChange={(e) => setTenantFilter(e.target.value)}
                        className="w-full sm:w-auto bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-8 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                    >
                        <option value="">All tenants ({tenants.length})</option>
                        {tenants.map(t => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
                    </select>
                </div>
                <div className="text-xs text-ink-500 dark:text-ink-400 sm:ml-auto">
                    {users.length} user{users.length === 1 ? '' : 's'}
                </div>
            </div>

            {errors.length > 0 && (
                <div className="bg-rose-50 border border-rose-200 text-rose-800 dark:bg-rose-500/10 dark:border-rose-500/20 dark:text-rose-200 rounded-xl p-4 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" aria-hidden="true" />
                    <div>
                        <p className="font-semibold uppercase tracking-[0.14em] text-2xs text-rose-700 dark:text-rose-300">Partial results</p>
                        <ul className="mt-1 space-y-0.5">
                            {errors.map((e) => (
                                <li key={`${e.tenant_db}-${e.error}`} className="font-mono"><span className="text-rose-900 dark:text-rose-200">{e.tenant_db}</span> · {e.error}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}

            {isLoading ? (
                <div className="card p-12 text-center text-ink-600 dark:text-ink-400">
                    <Activity className="animate-spin mx-auto mb-2 text-brand-600" size={20} aria-hidden="true" /> Aggregating users across tenants…
                </div>
            ) : users.length === 0 ? (
                <div className="card p-12 text-center text-ink-500 dark:text-ink-400">No users match your filters.</div>
            ) : (
                <div className="space-y-4">
                    {Object.entries(grouped).map(([key, rows]) => {
                        const [, tenantName] = key.split(':');
                        return (
                            <div key={key} className="card overflow-hidden">
                                <div className="px-5 py-3 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex items-center gap-2">
                                    <Building2 size={14} className="text-brand-600" aria-hidden="true" />
                                    <h2 className="font-semibold text-ink-900 dark:text-white text-sm tracking-tight truncate">{tenantName}</h2>
                                    <span className="text-2xs text-ink-500 dark:text-ink-400 font-mono ml-auto shrink-0">{rows.length} user{rows.length === 1 ? '' : 's'}</span>
                                </div>

                                {/* Desktop table */}
                                <div className="hidden lg:block overflow-x-auto">
                                    <table className="w-full text-left text-sm">
                                        <thead className="bg-ink-50 dark:bg-ink-800/40 text-ink-600 dark:text-ink-400 text-2xs uppercase font-semibold tracking-[0.14em]">
                                            <tr>
                                                <th className="px-5 py-3">Name</th>
                                                <th className="px-5 py-3">Email</th>
                                                <th className="px-5 py-3">Role</th>
                                                <th className="px-5 py-3">Status</th>
                                                <th className="px-5 py-3 text-right">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-ink-100 dark:divide-ink-800 text-ink-700 dark:text-ink-200">
                                            {rows.map(u => {
                                                const busy = busyKey === keyOf(u);
                                                return (
                                                    <tr key={keyOf(u)} className="hover:bg-ink-50 dark:hover:bg-ink-800/50 transition-colors">
                                                        <td className="px-5 py-3 font-semibold text-ink-900 dark:text-white">{u.full_name}</td>
                                                        <td className="px-5 py-3 text-xs text-ink-600 dark:text-ink-400">{u.email}</td>
                                                        <td className="px-5 py-3 text-xs">{u.role || '—'}</td>
                                                        <td className="px-5 py-3"><StatusBadge user={u} /></td>
                                                        <td className="px-5 py-3">
                                                            <div className="flex items-center justify-end gap-1.5">
                                                                <button type="button" disabled={busy} onClick={() => resetPassword(u)}
                                                                    className="btn-xs btn-secondary cursor-pointer disabled:opacity-50" title="Issue temporary password">
                                                                    <KeyRound size={13} aria-hidden="true" /> Reset
                                                                </button>
                                                                {u.is_locked && (
                                                                    <button type="button" disabled={busy} onClick={() => unlock(u)}
                                                                        className="btn-xs btn-secondary cursor-pointer disabled:opacity-50" title="Clear lockout">
                                                                        <Unlock size={13} aria-hidden="true" /> Unlock
                                                                    </button>
                                                                )}
                                                                <button type="button" disabled={busy} onClick={() => toggleActive(u)}
                                                                    className={`btn-xs cursor-pointer disabled:opacity-50 ${u.is_active ? 'btn-danger-ghost' : 'btn-secondary'}`}
                                                                    title={u.is_active ? 'Disable account' : 'Enable account'}>
                                                                    {u.is_active ? <UserX size={13} aria-hidden="true" /> : <UserCheck size={13} aria-hidden="true" />}
                                                                    {u.is_active ? 'Disable' : 'Enable'}
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>

                                {/* Mobile / tablet card list — no horizontal scroll, no overlap */}
                                <ul className="lg:hidden divide-y divide-ink-100 dark:divide-ink-800">
                                    {rows.map(u => {
                                        const busy = busyKey === keyOf(u);
                                        return (
                                            <li key={`${keyOf(u)}-mb`} className="p-4 space-y-3">
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <p className="font-semibold text-ink-900 dark:text-white truncate">{u.full_name}</p>
                                                        <p className="text-xs text-ink-600 dark:text-ink-400 truncate">{u.email}</p>
                                                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">{u.role || '—'}</p>
                                                    </div>
                                                    <StatusBadge user={u} />
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    <button type="button" disabled={busy} onClick={() => resetPassword(u)}
                                                        className="btn-xs btn-secondary cursor-pointer disabled:opacity-50 min-h-[2.75rem]">
                                                        <KeyRound size={13} aria-hidden="true" /> Reset password
                                                    </button>
                                                    {u.is_locked && (
                                                        <button type="button" disabled={busy} onClick={() => unlock(u)}
                                                            className="btn-xs btn-secondary cursor-pointer disabled:opacity-50 min-h-[2.75rem]">
                                                            <Unlock size={13} aria-hidden="true" /> Unlock
                                                        </button>
                                                    )}
                                                    <button type="button" disabled={busy} onClick={() => toggleActive(u)}
                                                        className={`btn-xs cursor-pointer disabled:opacity-50 min-h-[2.75rem] ${u.is_active ? 'btn-danger-ghost' : 'btn-secondary'}`}>
                                                        {u.is_active ? <UserX size={13} aria-hidden="true" /> : <UserCheck size={13} aria-hidden="true" />}
                                                        {u.is_active ? 'Disable' : 'Enable'}
                                                    </button>
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* One-time temp-password reveal modal */}
            {tempResult && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="temp-pw-title">
                    <div className="absolute inset-0 bg-ink-900/50 backdrop-blur-sm" onClick={() => dispatchTemp({ type: 'clear' })} aria-hidden="true" />
                    <div className="relative w-full max-w-md bg-white dark:bg-ink-900 rounded-2xl shadow-elevated border border-ink-200 dark:border-ink-800 p-6 animate-slide-up">
                        <div className="flex items-start justify-between gap-3 mb-4">
                            <div className="flex items-center gap-2">
                                <span className="inline-flex items-center justify-center size-9 rounded-xl bg-accent-100 text-accent-700 dark:bg-accent-500/10 dark:text-accent-300"><KeyRound size={18} aria-hidden="true" /></span>
                                <h2 id="temp-pw-title" className="text-base font-semibold text-ink-900 dark:text-white">Temporary password</h2>
                            </div>
                            <button type="button" onClick={() => dispatchTemp({ type: 'clear' })} aria-label="Close"
                                className="p-2 text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-lg cursor-pointer">
                                <X size={18} aria-hidden="true" />
                            </button>
                        </div>
                        <p className="text-sm text-ink-600 dark:text-ink-400 mb-4">
                            Share this with <strong className="text-ink-900 dark:text-white">{tempResult.user.full_name}</strong> ({tempResult.user.email}) over a secure channel.
                            It’s shown <strong>once</strong> and they must change it at next login.
                        </p>
                        <div className="flex items-center gap-2 bg-ink-50 dark:bg-ink-800/40 border border-ink-200 dark:border-ink-800 rounded-xl p-3">
                            <code className="flex-1 font-mono text-sm text-ink-900 dark:text-white break-all select-all">{tempResult.temporary_password}</code>
                            <button type="button" onClick={copyTemp} aria-label="Copy temporary password"
                                className="shrink-0 p-2 rounded-lg text-ink-500 dark:text-ink-400 hover:text-brand-700 hover:bg-ink-100 dark:hover:bg-ink-800/50 transition-colors cursor-pointer">
                                {copied ? <Check size={16} className="text-accent-600" aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
                            </button>
                        </div>
                        <div className="mt-4 bg-amber-50 border border-amber-200 text-amber-900 dark:bg-amber-500/10 dark:border-amber-500/20 dark:text-amber-200 rounded-xl p-3 text-2xs flex items-start gap-2">
                            <ShieldAlert size={13} className="shrink-0 mt-0.5" aria-hidden="true" /> Don’t send this over an insecure channel. It won’t be shown again.
                        </div>
                        <button type="button" onClick={() => dispatchTemp({ type: 'clear' })} className="btn-primary w-full mt-5">Done</button>
                    </div>
                </div>
            )}
        </div>
    );
}
