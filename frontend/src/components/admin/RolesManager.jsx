import React, { useEffect, useState, useCallback } from 'react';
import { ShieldCheck, Plus, Trash2, X, Lock, Activity, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';

export default function RolesManager() {
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(null); // null | 'new' | role
    const [activeRoleId, setActiveRoleId] = useState(null);
    const [draftPerms, setDraftPerms] = useState(new Set());
    const [savingPerms, setSavingPerms] = useState(false);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [rRes, pRes] = await Promise.all([
                apiClient.get('/admin/roles'),
                apiClient.get('/admin/permissions'),
            ]);
            const rolesData = rRes.data || [];
            setRoles(rolesData);
            setPermissions(pRes.data || []);
            if (rolesData.length && activeRoleId == null) {
                setActiveRoleId(rolesData[0].role_id);
            }
        } catch {
            toast.error('Could not load roles.');
        } finally {
            setLoading(false);
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

    return (
        <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
                <div>
                    <h2 className="text-sm font-bold text-slate-900">Roles & Permissions</h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                        Built-in roles can have permissions edited but not be renamed or deleted. Create custom roles to expand the staff taxonomy.
                    </p>
                </div>
                <button
                    onClick={() => setEditing('new')}
                    className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-lg text-sm font-bold hover:bg-brand-700 shadow-sm"
                >
                    <Plus size={16} /> New Role
                </button>
            </div>

            {loading ? (
                <div className="flex-1 flex items-center justify-center text-slate-400">
                    <Activity className="animate-spin mr-2" /> Loading…
                </div>
            ) : (
                <div className="flex-1 grid grid-cols-1 md:grid-cols-3 overflow-hidden">
                    {/* Roles list */}
                    <div className="border-r border-slate-100 overflow-y-auto custom-scrollbar">
                        <ul className="divide-y divide-slate-100">
                            {roles.map((r) => {
                                const isActive = r.role_id === activeRoleId;
                                return (
                                    <li key={r.role_id}>
                                        <button
                                            onClick={() => setActiveRoleId(r.role_id)}
                                            className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors ${
                                                isActive ? 'bg-brand-50' : 'hover:bg-slate-50'
                                            }`}
                                        >
                                            <span className="shrink-0 w-9 h-9 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center mt-0.5">
                                                {r.is_system ? <Lock size={14} /> : <ShieldCheck size={14} />}
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <p className="text-sm font-bold text-slate-900 truncate">{r.name}</p>
                                                    {r.is_system && (
                                                        <span className="text-2xs font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-slate-200 text-slate-600">
                                                            built-in
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-slate-500 mt-0.5">
                                                    {r.user_count} user{r.user_count === 1 ? '' : 's'} · {r.permissions.length} permission{r.permissions.length === 1 ? '' : 's'}
                                                </p>
                                            </div>
                                            {!r.is_system && (
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); deleteRole(r); }}
                                                    className="p-1 text-slate-400 hover:text-red-600"
                                                    title="Delete custom role"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            )}
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </div>

                    {/* Permission editor */}
                    <div className="md:col-span-2 flex flex-col overflow-hidden">
                        {!activeRole ? (
                            <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                                Pick a role to edit its permissions.
                            </div>
                        ) : (
                            <>
                                <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between gap-4">
                                    <div className="min-w-0">
                                        <h3 className="text-base font-bold text-slate-900 truncate">{activeRole.name}</h3>
                                        {activeRole.description && (
                                            <p className="text-xs text-slate-500 mt-0.5 truncate">{activeRole.description}</p>
                                        )}
                                    </div>
                                    {activeRole.name === 'Admin' ? (
                                        <span className="text-xs font-bold text-slate-500 flex items-center gap-1">
                                            <Lock size={12} /> Locked — full access
                                        </span>
                                    ) : (
                                        <button
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
                                    {Object.entries(groupedPerms).map(([cat, perms]) => (
                                        <div key={cat}>
                                            <h4 className="text-2xs font-bold uppercase tracking-wider text-slate-500 mb-2">{cat}</h4>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                {perms.map((p) => {
                                                    const checked = draftPerms.has(p.codename);
                                                    const locked = activeRole.name === 'Admin';
                                                    return (
                                                        <label
                                                            key={p.codename}
                                                            className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                                                                checked
                                                                    ? 'border-brand-200 bg-brand-50'
                                                                    : 'border-slate-200 bg-white hover:bg-slate-50'
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
                                                                <p className="text-xs font-bold text-slate-900 font-mono">{p.codename}</p>
                                                                {p.description && (
                                                                    <p className="text-2xs text-slate-500 mt-0.5">{p.description}</p>
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
            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-xl bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
                <div className="p-5 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                    <div>
                        <h2 className="text-lg font-bold text-slate-900">
                            {isNew ? 'Create Custom Role' : `Rename ${role.name}`}
                        </h2>
                        <p className="text-xs text-slate-500 mt-1">
                            {isNew
                                ? 'Pick the permissions this role should grant. You can refine the set later.'
                                : 'Use the editor on the right to change permissions.'}
                        </p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-5 overflow-y-auto space-y-4">
                    <div>
                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Role Name</label>
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Triage Officer"
                            className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                            disabled={role?.is_system}
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Description (optional)</label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            placeholder="What this role is for…"
                            className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none"
                        />
                    </div>

                    {isNew && (
                        <div>
                            <label className="block text-xs font-bold text-slate-700 mb-2">Initial Permissions</label>
                            <div className="max-h-72 overflow-y-auto custom-scrollbar border border-slate-200 rounded-lg p-3 space-y-1">
                                {permissions.map((p) => {
                                    const checked = picked.has(p.codename);
                                    return (
                                        <label
                                            key={p.codename}
                                            className={`flex items-start gap-3 p-2 rounded cursor-pointer ${
                                                checked ? 'bg-brand-50' : 'hover:bg-slate-50'
                                            }`}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={checked}
                                                onChange={() => togglePerm(p.codename)}
                                                className="mt-0.5 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                                            />
                                            <div className="min-w-0">
                                                <p className="text-xs font-bold text-slate-800 font-mono">{p.codename}</p>
                                                {p.description && (
                                                    <p className="text-2xs text-slate-500 mt-0.5">{p.description}</p>
                                                )}
                                            </div>
                                        </label>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3 shrink-0">
                    <button onClick={onClose} className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg">
                        Cancel
                    </button>
                    <button
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
