import React, { useEffect, useState, useCallback } from 'react';
import { Building2, Plus, Search, Trash2, Edit3, X, UserCheck, Activity } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';

export default function DepartmentsManager() {
    const [departments, setDepartments] = useState([]);
    const [staff, setStaff] = useState([]);
    const [loading, setLoading] = useState(true);

    const [editing, setEditing] = useState(null); // null | 'new' | dept object
    const [search, setSearch] = useState('');

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [dRes, sRes] = await Promise.all([
                apiClient.get('/messaging/departments'),
                apiClient.get('/admin/users'),
            ]);
            setDepartments(dRes.data || []);
            setStaff((sRes.data || []).filter((u) => u.is_active));
        } catch {
            toast.error('Could not load departments.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    const filtered = departments.filter((d) =>
        d.name.toLowerCase().includes(search.toLowerCase())
    );

    const remove = async (dept) => {
        if (!window.confirm(`Delete department "${dept.name}"? Members and chat history go with it.`)) return;
        try {
            await apiClient.delete(`/messaging/departments/${dept.department_id}`);
            toast.success('Department deleted.');
            fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not delete.');
        }
    };

    return (
        <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
            <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-50">
                <div className="relative w-full max-w-md">
                    <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search departments..."
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                </div>
                <button
                    onClick={() => setEditing('new')}
                    className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 text-white rounded-lg text-sm font-bold hover:bg-brand-700 shadow-sm"
                >
                    <Plus size={18} /> New Department
                </button>
            </div>

            <div className="flex-1 overflow-auto p-4">
                {loading ? (
                    <div className="text-center py-12 text-slate-400">
                        <Activity className="animate-spin mx-auto mb-2" /> Loading…
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="text-center py-12 text-slate-400">
                        <Building2 size={32} className="mx-auto mb-2 opacity-40" />
                        No departments yet. Create one — its members will share a private channel automatically.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {filtered.map((d) => (
                            <div key={d.department_id} className="bg-white border border-slate-200 rounded-xl p-4 hover:shadow-soft transition-shadow">
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <span className="shrink-0 w-10 h-10 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center">
                                            <Building2 size={18} />
                                        </span>
                                        <div className="min-w-0">
                                            <h3 className="font-bold text-slate-900 truncate">{d.name}</h3>
                                            <p className="text-xs text-slate-500">{d.member_count} member{d.member_count === 1 ? '' : 's'}</p>
                                        </div>
                                    </div>
                                </div>
                                {d.description && (
                                    <p className="text-xs text-slate-600 line-clamp-2 mb-3">{d.description}</p>
                                )}
                                <div className="flex flex-wrap gap-1 mb-3">
                                    {d.members.slice(0, 4).map((m) => (
                                        <span key={m.user_id} className="text-2xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                                            {m.full_name}
                                        </span>
                                    ))}
                                    {d.members.length > 4 && (
                                        <span className="text-2xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                                            +{d.members.length - 4} more
                                        </span>
                                    )}
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setEditing(d)}
                                        className="flex-1 text-xs font-bold px-3 py-1.5 rounded border border-slate-200 text-brand-600 hover:bg-brand-50 hover:border-brand-200 flex items-center justify-center gap-1"
                                    >
                                        <Edit3 size={12} /> Edit
                                    </button>
                                    <button
                                        onClick={() => remove(d)}
                                        className="text-xs font-bold px-3 py-1.5 rounded border border-slate-200 text-red-600 hover:bg-red-50 hover:border-red-200 flex items-center justify-center gap-1"
                                    >
                                        <Trash2 size={12} /> Delete
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {editing && (
                <DepartmentEditor
                    dept={editing === 'new' ? null : editing}
                    staff={staff}
                    onClose={() => setEditing(null)}
                    onSaved={() => { setEditing(null); fetchAll(); }}
                />
            )}
        </div>
    );
}


function DepartmentEditor({ dept, staff, onClose, onSaved }) {
    const isNew = !dept;
    const [name, setName] = useState(dept?.name || '');
    const [description, setDescription] = useState(dept?.description || '');
    const [memberIds, setMemberIds] = useState(new Set((dept?.members || []).map((m) => m.user_id)));
    const [search, setSearch] = useState('');
    const [busy, setBusy] = useState(false);

    const toggle = (uid) => {
        setMemberIds((prev) => {
            const next = new Set(prev);
            if (next.has(uid)) next.delete(uid); else next.add(uid);
            return next;
        });
    };

    const save = async () => {
        if (!name.trim()) { toast.error('Department needs a name.'); return; }
        setBusy(true);
        try {
            let dept_id;
            if (isNew) {
                const res = await apiClient.post('/messaging/departments', {
                    name: name.trim(),
                    description: description.trim() || null,
                    member_ids: Array.from(memberIds),
                });
                dept_id = res.data.department_id;
                toast.success('Department created.');
            } else {
                await apiClient.patch(`/messaging/departments/${dept.department_id}`, {
                    name: name.trim(),
                    description: description.trim() || null,
                });
                await apiClient.put(`/messaging/departments/${dept.department_id}/members`, {
                    member_ids: Array.from(memberIds),
                });
                dept_id = dept.department_id;
                toast.success('Department updated.');
            }
            onSaved(dept_id);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not save.');
        } finally {
            setBusy(false);
        }
    };

    const filtered = staff.filter((u) =>
        !search ||
        u.full_name.toLowerCase().includes(search.toLowerCase()) ||
        u.email.toLowerCase().includes(search.toLowerCase()) ||
        (u.role || '').toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
                <div className="p-5 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                    <div>
                        <h2 className="text-lg font-bold text-slate-900">
                            {isNew ? 'Create Department' : `Edit ${dept.name}`}
                        </h2>
                        <p className="text-xs text-slate-500 mt-1">
                            Members get an auto-managed group chat with each other.
                        </p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-5 overflow-y-auto space-y-4">
                    <div>
                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Name</label>
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. ICU Day Shift"
                            className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Description</label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            placeholder="Why this department exists, who should be in it…"
                            className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none"
                        />
                    </div>

                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-xs font-bold text-slate-700">
                                Members ({memberIds.size})
                            </label>
                            <div className="relative w-56">
                                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="Filter staff..."
                                    className="w-full pl-8 pr-3 py-1.5 border border-slate-200 rounded-md text-xs focus:ring-2 focus:ring-brand-500 outline-none"
                                />
                            </div>
                        </div>
                        <div className="max-h-72 overflow-y-auto custom-scrollbar border border-slate-200 rounded-lg">
                            <ul className="divide-y divide-slate-100">
                                {filtered.map((u) => {
                                    const checked = memberIds.has(u.user_id);
                                    return (
                                        <li key={u.user_id}>
                                            <label className={`flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors ${checked ? 'bg-brand-50' : 'hover:bg-slate-50'}`}>
                                                <input
                                                    type="checkbox"
                                                    checked={checked}
                                                    onChange={() => toggle(u.user_id)}
                                                    className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                                                />
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-sm font-semibold text-slate-900 truncate">{u.full_name}</p>
                                                    <p className="text-xs text-slate-500 truncate">{u.role} · {u.email}</p>
                                                </div>
                                                {checked && <UserCheck size={16} className="text-brand-600" />}
                                            </label>
                                        </li>
                                    );
                                })}
                            </ul>
                        </div>
                    </div>
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
                        {busy ? 'Saving…' : (isNew ? 'Create Department' : 'Save Changes')}
                    </button>
                </div>
            </div>
        </div>
    );
}
