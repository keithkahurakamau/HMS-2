import React, { useEffect, useReducer, useState, useCallback } from 'react';
import { ShieldCheck, Plus, Trash2, X, Lock, Activity, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';

// Friendly section labels for permission categories. Keys match the prefix
// before the `:` in a codename (e.g. `mpesa:read` → "M-Pesa"). Unknown
// prefixes fall through to a title-cased version of the prefix itself.
const CATEGORY_LABELS = {
    users: 'User Management',
    roles: 'Roles & Custom Permissions',
    departments: 'Departments',
    dashboard: 'Dashboard',
    patients: 'Patient Registry',
    appointments: 'Appointments',
    clinical: 'Clinical Desk',
    history: 'Medical History',
    pharmacy: 'Pharmacy',
    inventory: 'Inventory',
    laboratory: 'Laboratory',
    radiology: 'Radiology',
    wards: 'Wards & Admissions',
    billing: 'Billing',
    cheques: 'Cheques',
    mpesa: 'M-Pesa',
    messaging: 'Internal Messaging',
    referrals: 'Referrals',
    settings: 'Hospital Settings',
    branding: 'Branding',
    notifications: 'Notifications',
    support: 'MediFleet Support',
    analytics: 'Analytics',
    patient_portal: 'Patient Portal',
    privacy: 'Privacy (KDPA)',
    accounting: 'Managerial Accounting',
};

// Order categories follow the module catalogue in the backend so the editor
// reads top-to-bottom in the same shape the superadmin sees in tenant modules.
const CATEGORY_ORDER = [
    'users', 'roles', 'departments',
    'dashboard',
    'patients', 'appointments',
    'clinical', 'history',
    'pharmacy', 'inventory',
    'laboratory', 'radiology',
    'wards',
    'billing', 'cheques', 'mpesa',
    'messaging', 'referrals',
    'settings', 'branding', 'notifications',
    'support',
    'analytics', 'patient_portal', 'privacy',
    'accounting',
];

const categoryLabel = (prefix) =>
    CATEGORY_LABELS[prefix] ||
    prefix.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');

// Roles + permission catalogue + loading flag are loaded together by fetchAll,
// so they share one reducer.
const initialRoles = { roles: [], permissions: [], loading: true };
function rolesReducer(state, action) {
    switch (action.type) {
        case 'start':  return { ...state, loading: true };
        case 'loaded': return { ...state, roles: action.roles, permissions: action.permissions };
        case 'done':   return { ...state, loading: false };
        default:       return state;
    }
}

export default function RolesManager() {
    const [rolesState, dispatch] = useReducer(rolesReducer, initialRoles);
    const { roles, permissions, loading } = rolesState;
    const [editing, setEditing] = useState(null); // null | 'new' | role
    const [activeRoleId, setActiveRoleId] = useState(null);
    const [draftPerms, setDraftPerms] = useState(new Set());
    const [savingPerms, setSavingPerms] = useState(false);

    const fetchAll = useCallback(async () => {
        dispatch({ type: 'start' });
        try {
            const [rRes, pRes] = await Promise.all([
                apiClient.get('/admin/roles'),
                apiClient.get('/admin/permissions'),
            ]);
            const rolesData = rRes.data || [];
            dispatch({ type: 'loaded', roles: rolesData, permissions: pRes.data || [] });
            if (rolesData.length && activeRoleId == null) {
                setActiveRoleId(rolesData[0].role_id);
            }
        } catch {
            toast.error('Could not load roles.');
        } finally {
            dispatch({ type: 'done' });
        }
    }, [activeRoleId]);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    const activeRole = roles.find((r) => r.role_id === activeRoleId);
    const activePermsKey = activeRole ? activeRole.permissions.join('|') : '';

    // When the active role changes, reset the draft permission set.
    useEffect(() => {
        if (activeRole) {
            setDraftPerms(new Set(activeRole.permissions));
        }
        // activePermsKey is the change-detection signal for the role's perms.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeRoleId, activePermsKey]);

    const togglePerm = (codename) => {
        setDraftPerms((prev) => {
            const next = new Set(prev);
            if (next.has(codename)) next.delete(codename); else next.add(codename);
            return next;
        });
    };

    const savePerms = async () => {
        if (!activeRole) return;
        if (activeRole.name === 'Admin') {
            toast.error('Admin permissions cannot be edited — they cover everything.');
            return;
        }
        setSavingPerms(true);
        try {
            await apiClient.put(`/admin/roles/id/${activeRole.role_id}/permissions`, {
                permissions: Array.from(draftPerms),
            });
            toast.success('Permissions saved.');
            fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not save permissions.');
        } finally {
            setSavingPerms(false);
        }
    };

    const deleteRole = async (role) => {
        if (role.is_system) return;
        if (role.user_count > 0) {
            toast.error(`Cannot delete: ${role.user_count} user(s) still have this role.`);
            return;
        }
        if (!window.confirm(`Delete custom role "${role.name}"?`)) return;
        try {
            await apiClient.delete(`/admin/roles/${role.role_id}`);
            toast.success('Role deleted.');
            if (role.role_id === activeRoleId) setActiveRoleId(null);
            fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not delete role.');
        }
    };

    const dirty = activeRole &&
        (draftPerms.size !== activeRole.permissions.length ||
         activeRole.permissions.some((p) => !draftPerms.has(p)));

    const groupedPerms = permissions.reduce((acc, p) => {
        const cat = p.codename.split(':')[0];
        (acc[cat] ||= []).push(p);
        return acc;
    }, {});
    // Show categories in module-catalogue order so M-Pesa, Inventory etc.
    // appear grouped by hospital workflow rather than alphabetical noise.
    const orderedCategories = Object.keys(groupedPerms).sort((a, b) => {
        const ai = CATEGORY_ORDER.indexOf(a);
        const bi = CATEGORY_ORDER.indexOf(b);
        if (ai === -1 && bi === -1) return a.localeCompare(b);
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
    });

    return (
        <div className="flex-1 bg-white dark:bg-ink-900 border border-slate-200 dark:border-ink-800 rounded-xl shadow-sm overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-100 dark:border-ink-800 flex items-center justify-between bg-slate-50 dark:bg-ink-800/40">
                <div>
                    <h2 className="text-sm font-bold text-slate-900 dark:text-white">Roles & Permissions</h2>
                    <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5">
                        Built-in roles can have permissions edited but not be renamed or deleted. Create custom roles to expand the staff taxonomy.
                    </p>
                </div>
                <button type="button"
                    onClick={() => setEditing('new')}
                    className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-bold hover:bg-brand-700 shadow-sm"
                >
                    <Plus size={16} /> New Role
                </button>
            </div>

            {loading ? (
                <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-ink-400">
                    <Activity className="animate-spin mr-2" /> Loading…
                </div>
            ) : (
                <div className="flex-1 grid grid-cols-1 md:grid-cols-3 overflow-hidden">
                    {/* Roles list */}
                    <div className="border-r border-slate-100 dark:border-ink-800 overflow-y-auto custom-scrollbar">
                        <ul className="divide-y divide-slate-100 dark:divide-ink-800">
                            {roles.map((r) => {
                                const isActive = r.role_id === activeRoleId;
                                return (
                                    <li key={r.role_id}>
                                        {/* Clickable row containing a Delete button — a native <button> can't nest another, so role="button" is the correct pattern here. */}
                                        {/* react-doctor-disable-next-line react-doctor/prefer-tag-over-role */}
                                        <div role="button" tabIndex={0}
                                            onClick={() => setActiveRoleId(r.role_id)}
                                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActiveRoleId(r.role_id); } }}
                                            className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors cursor-pointer ${
                                                isActive ? 'bg-brand-50 dark:bg-brand-500/15' : 'hover:bg-slate-50 dark:hover:bg-ink-800/50'
                                            }`}
                                        >
                                            <span className="shrink-0 size-9 rounded-xl bg-slate-100 dark:bg-ink-800/40 text-slate-600 dark:text-ink-400 flex items-center justify-center mt-0.5">
                                                {r.is_system ? <Lock size={14} /> : <ShieldCheck size={14} />}
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <p className="text-sm font-bold text-slate-900 dark:text-white truncate">{r.name}</p>
                                                    {r.is_system && (
                                                        <span className="text-2xs font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-200 dark:bg-ink-800/40 text-slate-600 dark:text-ink-400">
                                                            built-in
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5">
                                                    {r.user_count} user{r.user_count === 1 ? '' : 's'} · {r.permissions.length} permission{r.permissions.length === 1 ? '' : 's'}
                                                </p>
                                            </div>
                                            {!r.is_system && (
                                                <button type="button"
                                                    onClick={(e) => { e.stopPropagation(); deleteRole(r); }}
                                                    className="p-1 text-slate-400 hover:text-red-600 dark:hover:text-red-300"
                                                    title="Delete custom role"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            )}
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>

                    {/* Permission editor */}
                    <div className="md:col-span-2 flex flex-col overflow-hidden">
                        {!activeRole ? (
                            <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-ink-400 text-sm">
                                Pick a role to edit its permissions.
                            </div>
                        ) : (
                            <>
                                <div className="px-5 py-3 border-b border-slate-100 dark:border-ink-800 flex items-center justify-between gap-4">
                                    <div className="min-w-0">
                                        <h3 className="text-base font-bold text-slate-900 dark:text-white truncate">{activeRole.name}</h3>
                                        {activeRole.description && (
                                            <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5 truncate">{activeRole.description}</p>
                                        )}
                                    </div>
                                    {activeRole.name === 'Admin' ? (
                                        <span className="text-xs font-bold text-slate-500 dark:text-ink-400 flex items-center gap-1">
                                            <Lock size={12} /> Locked — full access
                                        </span>
                                    ) : (
                                        <button type="button"
                                            onClick={savePerms}
                                            disabled={!dirty || savingPerms}
                                            className="px-4 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg hover:bg-brand-700 disabled:opacity-40 flex items-center gap-2"
                                        >
                                            {savingPerms ? <Activity className="animate-spin" size={14} /> : <Save size={14} />}
                                            Save Changes
                                        </button>
                                    )}
                                </div>

                                <div className="flex-1 overflow-y-auto p-5 space-y-5 custom-scrollbar">
                                    {orderedCategories.map((cat) => (
                                        <div key={cat}>
                                            <h4 className="text-2xs font-bold uppercase tracking-wider text-slate-500 dark:text-ink-400 mb-2">{categoryLabel(cat)}</h4>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                {groupedPerms[cat].map((p) => {
                                                    const checked = draftPerms.has(p.codename);
                                                    const locked = activeRole.name === 'Admin';
                                                    return (
                                                        <label
                                                            key={p.codename}
                                                            className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                                                                checked
                                                                    ? 'border-brand-200 dark:border-brand-500/30 bg-brand-50 dark:bg-brand-500/15'
                                                                    : 'border-slate-200 dark:border-ink-800 bg-white dark:bg-ink-900 hover:bg-slate-50 dark:hover:bg-ink-800/50'
                                                            } ${locked ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}
                                                        >
                                                            <input
                                                                type="checkbox"
                                                                checked={checked}
                                                                disabled={locked}
                                                                onChange={() => togglePerm(p.codename)}
                                                                className="mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                                                            />
                                                            <div className="min-w-0">
                                                                <p className="text-xs font-bold text-slate-900 dark:text-white font-mono">{p.codename}</p>
                                                                {p.description && (
                                                                    <p className="text-2xs text-slate-500 dark:text-ink-400 mt-0.5">{p.description}</p>
                                                                )}
                                                            </div>
                                                        </label>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {editing && (
                <RoleEditor
                    role={editing === 'new' ? null : editing}
                    permissions={permissions}
                    onClose={() => setEditing(null)}
                    onSaved={(newRoleId) => {
                        setEditing(null);
                        if (newRoleId) setActiveRoleId(newRoleId);
                        fetchAll();
                    }}
                />
            )}
        </div>
    );
}


function RoleEditor({ role, permissions, onClose, onSaved }) {
    const isNew = !role;
    const [name, setName] = useState(role?.name || '');
    const [description, setDescription] = useState(role?.description || '');
    const [picked, setPicked] = useState(new Set(role?.permissions || ['messaging:read', 'messaging:write']));
    const [busy, setBusy] = useState(false);

    const togglePerm = (codename) => {
        setPicked((prev) => {
            const next = new Set(prev);
            if (next.has(codename)) next.delete(codename); else next.add(codename);
            return next;
        });
    };

    const save = async () => {
        if (!name.trim()) { toast.error('Role needs a name.'); return; }
        setBusy(true);
        try {
            if (isNew) {
                const res = await apiClient.post('/admin/roles', {
                    name: name.trim(),
                    description: description.trim() || null,
                    permissions: Array.from(picked),
                });
                toast.success('Role created.');
                onSaved(res.data.role_id);
            } else {
                await apiClient.patch(`/admin/roles/${role.role_id}`, {
                    name: name.trim(),
                    description: description.trim() || null,
                });
                toast.success('Role updated.');
                onSaved(role.role_id);
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not save role.');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-xl bg-white dark:bg-ink-900 rounded-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
                <div className="p-5 border-b border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40 flex justify-between items-center">
                    <div>
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                            {isNew ? 'Create Custom Role' : `Rename ${role.name}`}
                        </h2>
                        <p className="text-xs text-slate-500 dark:text-ink-400 mt-1">
                            {isNew
                                ? 'Pick the permissions this role should grant. You can refine the set later.'
                                : 'Use the editor on the right to change permissions.'}
                        </p>
                    </div>
                    <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-700 dark:hover:text-ink-200">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-5 overflow-y-auto space-y-4">
                    <div>
                        <label htmlFor="rolesm-role-name" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Role Name</label>
                        <input id="rolesm-role-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Triage Officer"
                            className="w-full px-4 py-2.5 border border-slate-200 dark:border-ink-800 dark:bg-ink-900 dark:text-white rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                            disabled={role?.is_system}
                        />
                    </div>
                    <div>
                        <label htmlFor="rolesm-description-optional" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Description (optional)</label>
                        <textarea id="rolesm-description-optional"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            placeholder="What this role is for…"
                            className="w-full px-4 py-2.5 border border-slate-200 dark:border-ink-800 dark:bg-ink-900 dark:text-white rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none"
                        />
                    </div>

                    {isNew && (
                        <div>
                            <span className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-2">Initial Permissions</span>
                            <div className="max-h-72 overflow-y-auto custom-scrollbar border border-slate-200 dark:border-ink-800 rounded-lg p-3 space-y-3">
                                {(() => {
                                    const grouped = permissions.reduce((acc, p) => {
                                        const cat = p.codename.split(':')[0];
                                        (acc[cat] ||= []).push(p);
                                        return acc;
                                    }, {});
                                    const cats = Object.keys(grouped).sort((a, b) => {
                                        const ai = CATEGORY_ORDER.indexOf(a);
                                        const bi = CATEGORY_ORDER.indexOf(b);
                                        if (ai === -1 && bi === -1) return a.localeCompare(b);
                                        if (ai === -1) return 1;
                                        if (bi === -1) return -1;
                                        return ai - bi;
                                    });
                                    return cats.map((cat) => (
                                        <div key={cat}>
                                            <h5 className="text-2xs font-bold uppercase tracking-wider text-slate-500 dark:text-ink-400 mb-1 px-1">
                                                {categoryLabel(cat)}
                                            </h5>
                                            {grouped[cat].map((p) => {
                                                const checked = picked.has(p.codename);
                                                return (
                                                    <label
                                                        key={p.codename}
                                                        className={`flex items-start gap-3 p-2 rounded cursor-pointer ${
                                                            checked ? 'bg-brand-50 dark:bg-brand-500/15' : 'hover:bg-slate-50 dark:hover:bg-ink-800/50'
                                                        }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={checked}
                                                            onChange={() => togglePerm(p.codename)}
                                                            className="mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                                                        />
                                                        <div className="min-w-0">
                                                            <p className="text-xs font-bold text-slate-800 dark:text-ink-200 font-mono">{p.codename}</p>
                                                            {p.description && (
                                                                <p className="text-2xs text-slate-500 dark:text-ink-400 mt-0.5">{p.description}</p>
                                                            )}
                                                        </div>
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    ));
                                })()}
                            </div>
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40 flex justify-end gap-3 shrink-0">
                    <button type="button" onClick={onClose} className="px-4 py-2 text-sm font-bold text-slate-600 dark:text-ink-400 hover:bg-slate-200 dark:hover:bg-ink-800/50 rounded-lg">
                        Cancel
                    </button>
                    <button type="button"
                        onClick={save}
                        disabled={busy}
                        className="px-6 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg shadow-sm hover:bg-brand-700 disabled:opacity-50"
                    >
                        {busy ? 'Saving…' : (isNew ? 'Create Role' : 'Save')}
                    </button>
                </div>
            </div>
        </div>
    );
}
