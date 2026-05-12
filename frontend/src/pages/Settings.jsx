import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import {
    Settings as SettingsIcon, Building2, Clock, Wallet, TestTube, Radio,
    Bell, Shield, Save, RefreshCcw, Activity, Plus, X,
} from 'lucide-react';
import toast from 'react-hot-toast';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Hospital Settings                                                         */
/*                                                                            */
/*  Renders the per-tenant flat KV store grouped by category. Each setting    */
/*  picks its widget from `data_type` so the page is fully data-driven —      */
/*  new categories appear automatically as soon as someone inserts a row.     */
/* ────────────────────────────────────────────────────────────────────────── */

const CATEGORY_META = {
    branding: { label: 'Branding & identity', icon: Building2, accent: 'brand' },
    working_hours: { label: 'Working hours', icon: Clock, accent: 'amber' },
    billing: { label: 'Billing & currency', icon: Wallet, accent: 'accent' },
    laboratory: { label: 'Laboratory defaults', icon: TestTube, accent: 'brand' },
    radiology: { label: 'Radiology defaults', icon: Radio, accent: 'blue' },
    notifications: { label: 'Notifications', icon: Bell, accent: 'amber' },
    privacy: { label: 'Privacy & compliance', icon: Shield, accent: 'rose' },
};

export default function Settings() {
    const [categories, setCategories] = useState([]);
    const [drafts, setDrafts] = useState({});       // {setting_id: new value}
    const [saving, setSaving] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [activeCategory, setActiveCategory] = useState(null);
    const [showCustomForm, setShowCustomForm] = useState(false);
    const [customDraft, setCustomDraft] = useState({
        category: '', key: '', label: '', description: '',
        data_type: 'string', value: '',
    });

    useEffect(() => { fetchSettings(); }, []);

    const fetchSettings = async () => {
        setIsLoading(true);
        try {
            const res = await apiClient.get('/settings/');
            setCategories(res.data.categories || []);
            if (!activeCategory && (res.data.categories || []).length > 0) {
                setActiveCategory(res.data.categories[0].key);
            }
            setDrafts({});
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load settings.');
        } finally {
            setIsLoading(false);
        }
    };

    const setDraft = (id, value) => setDrafts(d => ({ ...d, [id]: value }));
    const dirtyIds = useMemo(() => Object.keys(drafts), [drafts]);

    const allItems = useMemo(() => categories.flatMap(c => c.items.map(i => ({ ...i, _cat: c.key }))), [categories]);
    const itemsForActive = useMemo(
        () => allItems.filter(i => i._cat === activeCategory),
        [allItems, activeCategory],
    );

    const renderInput = (item) => {
        const current = item.setting_id in drafts ? drafts[item.setting_id] : item.value;
        const set = (v) => setDraft(item.setting_id, v);

        if (item.data_type === 'boolean') {
            return (
                <label className="inline-flex items-center cursor-pointer">
                    <input type="checkbox"
                           checked={current === true || current === 'true'}
                           onChange={(e) => set(e.target.checked)} className="sr-only peer" />
                    <span className="w-11 h-6 bg-ink-200 rounded-full peer peer-checked:bg-brand-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-5 after:h-5 after:transition peer-checked:after:translate-x-5" />
                </label>
            );
        }
        if (item.data_type === 'number') {
            return <input type="number" className="input" value={current ?? ''} onChange={(e) => set(e.target.value)} />;
        }
        if (item.data_type === 'json') {
            return <textarea rows="3" className="input font-mono text-xs resize-none"
                             value={typeof current === 'string' ? current : JSON.stringify(current ?? null, null, 2)}
                             onChange={(e) => set(e.target.value)} />;
        }
        return <input type={item.is_sensitive ? 'password' : 'text'} className="input"
                      value={current ?? ''} onChange={(e) => set(e.target.value)} />;
    };

    const save = async () => {
        if (dirtyIds.length === 0) {
            toast('Nothing to save', { icon: 'ℹ️' });
            return;
        }
        const updates = allItems
            .filter(i => i.setting_id in drafts)
            .map(i => ({ category: i._cat, key: i.key, value: drafts[i.setting_id], data_type: i.data_type }));

        setSaving(true);
        try {
            await apiClient.put('/settings/bulk', { updates });
            toast.success(`${updates.length} setting(s) saved.`);
            await fetchSettings();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed.');
        } finally {
            setSaving(false);
        }
    };

    const saveCustom = async () => {
        if (!customDraft.category || !customDraft.key) {
            return toast.error('Category and key are required.');
        }
        try {
            await apiClient.put('/settings/', customDraft);
            toast.success('Custom setting added.');
            setShowCustomForm(false);
            setCustomDraft({ category: '', key: '', label: '', description: '', data_type: 'string', value: '' });
            await fetchSettings();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to add setting.');
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <span className="section-eyebrow">Administration</span>
                    <h1 className="section-title mt-1 flex items-center gap-2">
                        <SettingsIcon size={22} className="text-brand-600" /> Hospital Settings
                    </h1>
                    <p className="section-sub">Branding, working hours, billing, lab/radiology defaults, notifications &amp; compliance.</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={fetchSettings} className="btn-secondary"><RefreshCcw size={15} /> Refresh</button>
                    <button onClick={() => setShowCustomForm(true)} className="btn-secondary"><Plus size={15} /> Custom setting</button>
                    <button onClick={save} disabled={saving || dirtyIds.length === 0} className="btn-primary disabled:opacity-50">
                        {saving ? <Activity size={15} className="animate-spin" /> : <Save size={15} />} Save changes ({dirtyIds.length})
                    </button>
                </div>
            </div>

            {isLoading ? (
                <div className="card p-12 text-center text-ink-400">
                    <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading settings…
                </div>
            ) : categories.length === 0 ? (
                <div className="card p-12 text-center text-ink-500">No settings have been configured yet.</div>
            ) : (
                <div className="grid grid-cols-12 gap-4">
                    {/* Category nav */}
                    <nav className="col-span-12 md:col-span-3 card p-2 flex md:flex-col gap-1 overflow-x-auto">
                        {categories.map(c => {
                            const meta = CATEGORY_META[c.key] || { label: c.key.replace(/_/g, ' '), icon: SettingsIcon };
                            const Icon = meta.icon;
                            const active = activeCategory === c.key;
                            return (
                                <button key={c.key} onClick={() => setActiveCategory(c.key)}
                                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${active ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-200' : 'text-ink-600 hover:bg-ink-50'}`}>
                                    <Icon size={15} />
                                    <span className="capitalize">{meta.label}</span>
                                    <span className="ml-auto text-2xs text-ink-400">{c.items.length}</span>
                                </button>
                            );
                        })}
                    </nav>

                    {/* Setting list */}
                    <div className="col-span-12 md:col-span-9 card overflow-hidden">
                        <div className="p-5 border-b border-ink-100 bg-ink-50/40">
                            <h2 className="font-semibold text-ink-900">
                                {(CATEGORY_META[activeCategory]?.label || activeCategory)}
                            </h2>
                            <p className="text-xs text-ink-500 mt-0.5">Each row is a key/value pair. Sensitive values are masked when read back.</p>
                        </div>
                        <ul className="divide-y divide-ink-100">
                            {itemsForActive.map(item => {
                                const dirty = item.setting_id in drafts;
                                return (
                                    <li key={item.setting_id} className={`px-5 py-4 grid grid-cols-12 gap-3 items-center ${dirty ? 'bg-amber-50/40' : ''}`}>
                                        <div className="col-span-12 md:col-span-5">
                                            <p className="text-sm font-medium text-ink-800">{item.label || item.key}</p>
                                            <p className="text-xs text-ink-500 font-mono">{item.key}</p>
                                            {item.description && <p className="text-xs text-ink-500 mt-1 leading-relaxed">{item.description}</p>}
                                        </div>
                                        <div className="col-span-12 md:col-span-6">{renderInput(item)}</div>
                                        <div className="col-span-12 md:col-span-1 text-right">
                                            <span className={`badge-${dirty ? 'warn' : 'neutral'} text-2xs`}>
                                                {dirty ? 'Edited' : item.data_type}
                                            </span>
                                        </div>
                                    </li>
                                );
                            })}
                            {itemsForActive.length === 0 && (
                                <li className="p-10 text-center text-ink-400 text-sm">No settings in this category yet.</li>
                            )}
                        </ul>
                    </div>
                </div>
            )}

            {showCustomForm && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setShowCustomForm(false)} />
                    <div className="relative w-full max-w-lg bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 shrink-0">
                            <h2 className="text-lg font-semibold flex items-center gap-2"><Plus size={18} /> Add custom setting</h2>
                            <button onClick={() => setShowCustomForm(false)} className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full">
                                <X size={20} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-ink-50/60">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="label">Category *</label>
                                    <input className="input" value={customDraft.category}
                                           onChange={e => setCustomDraft({ ...customDraft, category: e.target.value })}
                                           placeholder="e.g. integrations" />
                                </div>
                                <div>
                                    <label className="label">Key *</label>
                                    <input className="input" value={customDraft.key}
                                           onChange={e => setCustomDraft({ ...customDraft, key: e.target.value })}
                                           placeholder="e.g. slack_webhook" />
                                </div>
                            </div>
                            <div>
                                <label className="label">Display label</label>
                                <input className="input" value={customDraft.label}
                                       onChange={e => setCustomDraft({ ...customDraft, label: e.target.value })} />
                            </div>
                            <div>
                                <label className="label">Description</label>
                                <textarea rows="2" className="input resize-none" value={customDraft.description}
                                          onChange={e => setCustomDraft({ ...customDraft, description: e.target.value })} />
                            </div>
                            <div>
                                <label className="label">Type</label>
                                <select className="input" value={customDraft.data_type}
                                        onChange={e => setCustomDraft({ ...customDraft, data_type: e.target.value })}>
                                    <option value="string">string</option>
                                    <option value="number">number</option>
                                    <option value="boolean">boolean</option>
                                    <option value="json">json</option>
                                </select>
                            </div>
                            <div>
                                <label className="label">Initial value</label>
                                <input className="input" value={customDraft.value}
                                       onChange={e => setCustomDraft({ ...customDraft, value: e.target.value })} />
                            </div>
                        </div>
                        <div className="p-4 border-t border-ink-100 bg-white flex justify-end gap-2 shrink-0">
                            <button onClick={() => setShowCustomForm(false)} className="btn-secondary">Cancel</button>
                            <button onClick={saveCustom} className="btn-primary"><Save size={15} /> Add setting</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
