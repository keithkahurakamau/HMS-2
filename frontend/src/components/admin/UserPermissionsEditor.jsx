import React, { useEffect, useState, useMemo } from 'react';
import { X, Activity, ShieldCheck, Plus, Minus, RotateCcw, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';

/**
 * Per-user permission overrides editor.
 *
 * Mental model: every permission has one of three states for this user —
 *   • inherit — uses the role's default (no override row stored)
 *   • grant   — force-on, even if the role doesn't include it
 *   • revoke  — force-off, even if the role includes it
 *
 * The Admin role can't be overridden (wildcard by design); we render a
 * read-only banner if the target user is an Admin.
 */
export default function UserPermissionsEditor({ user, onClose, onSaved }) {
    const [data, setData] = useState(null);     // GET /admin/users/{id}/permissions
    const [permissions, setPermissions] = useState([]); // catalogue
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // Local working copy: codename -> 'inherit' | 'grant' | 'revoke'
    const [draft, setDraft] = useState({});

    useEffect(() => {
        let cancelled = false;
        (async () => {
            setLoading(true);
            try {
                const [permsRes, userPermsRes] = await Promise.all([
                    apiClient.get('/admin/permissions'),
                    apiClient.get(`/admin/users/${user.user_id}/permissions`),
                ]);
                if (cancelled) return;
                setPermissions(permsRes.data || []);
                setData(userPermsRes.data);

                // Build draft from current state.
                const next = {};
                (userPermsRes.data.granted || []).forEach((c) => { next[c] = 'grant'; });
                (userPermsRes.data.revoked || []).forEach((c) => { next[c] = 'revoke'; });
                setDraft(next);
            } catch (e) {
                toast.error(e.response?.data?.detail || 'Could not load permissions.');
            } finally {
                if (!cancelled) setLoading(false);
            }
        })();
        return () => { cancelled = true; };
    }, [user.user_id]);

    const rolePerms = useMemo(
        () => new Set(data?.role_permissions || []),
        [data]
    );

    // What the saved effective set will be after the draft is applied.
    const effectivePreview = useMemo(() => {
        const grants = new Set(
            Object.entries(draft).filter(([, s]) => s === 'grant').map(([c]) => c)
        );
        const revokes = new Set(
            Object.entries(draft).filter(([, s]) => s === 'revoke').map(([c]) => c)
        );
        const out = new Set(rolePerms);
        grants.forEach((c) => out.add(c));
        revokes.forEach((c) => out.delete(c));
        return out;
    }, [draft, rolePerms]);

    const setState = (codename, state) => {
        setDraft((prev) => {
            const next = { ...prev };
            if (state === 'inherit') delete next[codename];
            else next[codename] = state;
            return next;
        });
    };

    const resetAll = () => setDraft({});

    const save = async () => {
        setSaving(true);
        try {
            const granted = Object.entries(draft).filter(([, s]) => s === 'grant').map(([c]) => c);
            const revoked = Object.entries(draft).filter(([, s]) => s === 'revoke').map(([c]) => c);
            const res = await apiClient.put(
                `/admin/users/${user.user_id}/permissions`,
                { granted, revoked }
            );
            toast.success('Permissions saved.');
            onSaved?.(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not save permissions.');
        } finally {
            setSaving(false);
        }
    };

    const dirty = useMemo(() => {
        const origGrants = new Set(data?.granted || []);
        const origRevokes = new Set(data?.revoked || []);
        const draftGrants = new Set(
            Object.entries(draft).filter(([, s]) => s === 'grant').map(([c]) => c)
        );
        const draftRevokes = new Set(
            Object.entries(draft).filter(([, s]) => s === 'revoke').map(([c]) => c)
        );
        if (origGrants.size !== draftGrants.size) return true;
        if (origRevokes.size !== draftRevokes.size) return true;
        for (const c of origGrants) if (!draftGrants.has(c)) return true;
        for (const c of origRevokes) if (!draftRevokes.has(c)) return true;
        return false;
    }, [draft, data]);

    const grouped = useMemo(() => {
        return permissions.reduce((acc, p) => {
            const cat = p.codename.split(':')[0];
            (acc[cat] ||= []).push(p);
            return acc;
        }, {});
    }, [permissions]);

    const isAdmin = data?.role === 'Admin';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative w-full max-w-3xl bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
                <div className="p-5 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                    <div className="min-w-0">
                        <h2 className="text-lg font-bold text-slate-900 truncate">
                            Permissions: {user.full_name}
                        </h2>
                        <p className="text-xs text-slate-500 mt-1">
                            Role: <span className="font-semibold">{data?.role || user.role}</span> ·
                            Effective permissions are role defaults + grants − revokes.
                        </p>
                    </div>
                    <button onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 rounded-lg hover:bg-ink-100 cursor-pointer">
                        <X size={20} aria-hidden="true" />
                    </button>
                </div>

                {loading ? (
                    <div className="flex-1 flex items-center justify-center py-16 text-slate-400">
                        <Activity className="animate-spin mr-2" /> Loading…
                    </div>
                ) : isAdmin ? (
                    <div className="p-8 text-center">
                        <ShieldCheck size={32} className="mx-auto mb-3 text-amber-500" />
                        <p className="text-sm font-bold text-slate-900 mb-1">Admin permissions are wildcard</p>
                        <p className="text-xs text-slate-500 max-w-md mx-auto">
                            The Admin role grants every permission and cannot be overridden on a per-user basis.
                            Reassign this user to a different role first if you want to limit their access.
                        </p>
                    </div>
                ) : (
                    <>
                        <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-white">
                            <div className="text-xs text-slate-500">
                                <span className="font-semibold text-slate-700">{effectivePreview.size}</span> effective permission{effectivePreview.size === 1 ? '' : 's'}
                                {Object.keys(draft).length > 0 && (
                                    <span className="ml-2 text-amber-600 font-semibold">
                                        ({Object.values(draft).filter(s => s === 'grant').length} grant, {Object.values(draft).filter(s => s === 'revoke').length} revoke)
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={resetAll}
                                disabled={Object.keys(draft).length === 0}
                                className="text-xs font-semibold text-slate-600 hover:text-slate-900 flex items-center gap-1 px-2 py-1 disabled:opacity-40"
                            >
                                <RotateCcw size={12} /> Clear all overrides
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-5">
                            {Object.entries(grouped).map(([cat, perms]) => (
                                <div key={cat}>
                                    <h4 className="text-2xs font-bold uppercase tracking-wider text-slate-500 mb-2">{cat}</h4>
                                    <ul className="divide-y divide-slate-100 border border-slate-200 rounded-lg overflow-hidden">
                                        {perms.map((p) => {
                                            const fromRole = rolePerms.has(p.codename);
                                            const overrideState = draft[p.codename] || 'inherit';
                                            const effective = effectivePreview.has(p.codename);
                                            return (
                                                <li
                                                    key={p.codename}
                                                    className={`grid grid-cols-12 gap-3 items-center px-3 py-2.5 ${
                                                        overrideState !== 'inherit' ? 'bg-amber-50/40' : 'bg-white'
                                                    }`}
                                                >
                                                    <div className="col-span-6 min-w-0">
                                                        <p className="text-xs font-mono font-bold text-slate-900 truncate">
                                                            {p.codename}
                                                        </p>
                                                        <p className="text-2xs text-slate-500 truncate mt-0.5">
                                                            {p.description || '—'}
                                                        </p>
                                                        <div className="flex gap-1.5 mt-1 flex-wrap">
                                                            {fromRole && (
                                                                <span className="text-2xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-semibold uppercase tracking-wider">
                                                                    from role
                                                                </span>
                                                            )}
                                                            {overrideState === 'grant' && (
                                                                <span className="text-2xs px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-semibold uppercase tracking-wider">
                                                                    + granted
                                                                </span>
                                                            )}
                                                            {overrideState === 'revoke' && (
                                                                <span className="text-2xs px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 font-semibold uppercase tracking-wider">
                                                                    − revoked
                                                                </span>
                                                            )}
                                                            <span className={`text-2xs px-1.5 py-0.5 rounded font-semibold uppercase tracking-wider ${
                                                                effective ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'
                                                            }`}>
                                                                {effective ? '✓ effective' : '✗ no access'}
                                                            </span>
                                                        </div>
                                                    </div>
                                                    <div className="col-span-6 flex justify-end gap-1">
                                                        <SegmentBtn
                                                            active={overrideState === 'inherit'}
                                                            onClick={() => setState(p.codename, 'inherit')}
                                                            title="Use role default"
                                                        >
                                                            Inherit
                                                        </SegmentBtn>
                                                        <SegmentBtn
                                                            tone="emerald"
                                                            active={overrideState === 'grant'}
                                                            onClick={() => setState(p.codename, 'grant')}
                                                            title="Force-grant this permission"
                                                            disabled={fromRole}
                                                        >
                                                            <Plus size={11} /> Grant
                                                        </SegmentBtn>
                                                        <SegmentBtn
                                                            tone="rose"
                                                            active={overrideState === 'revoke'}
                                                            onClick={() => setState(p.codename, 'revoke')}
                                                            title="Force-revoke this permission"
                                                            disabled={!fromRole}
                                                        >
                                                            <Minus size={11} /> Revoke
                                                        </SegmentBtn>
                                                    </div>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </div>
                            ))}
                        </div>

                        <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3 shrink-0">
                            <button
                                onClick={onClose}
                                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={save}
                                disabled={!dirty || saving}
                                className="px-6 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg shadow-sm hover:bg-brand-700 disabled:opacity-40 flex items-center gap-2"
                            >
                                {saving ? <Activity className="animate-spin" size={14} /> : <Save size={14} />}
                                Save Overrides
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}


function SegmentBtn({ children, active, onClick, disabled, tone = 'brand', title }) {
    const tones = {
        brand: active ? 'bg-brand-600 text-white' : 'text-slate-600 hover:bg-white',
        emerald: active ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:bg-white',
        rose: active ? 'bg-rose-600 text-white' : 'text-slate-600 hover:bg-white',
    };
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            title={title}
            className={`text-2xs font-bold px-2.5 py-1 rounded-md border border-slate-200 inline-flex items-center gap-1 transition-colors ${tones[tone]} disabled:opacity-30 disabled:cursor-not-allowed`}
        >
            {children}
        </button>
    );
}
