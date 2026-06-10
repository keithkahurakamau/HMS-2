import React, { useEffect, useMemo, useReducer, useState } from 'react';
import { apiClient } from '../api/client';
import {
    Settings as SettingsIcon, Building2, Clock, Wallet, TestTube, Radio,
    Bell, Shield, Save, RefreshCcw, Activity, Plus, X, Palette, ArrowRight,
    Sparkles,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useJourney } from '../context/JourneyContext';
import PageHeader from '../components/PageHeader';

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

// The settings catalogue + its loading flag are one logical unit.
const initialLoad = { categories: [], isLoading: true };
function loadReducer(state, action) {
    switch (action.type) {
        case 'loading':       return { ...state, isLoading: true };
        case 'setCategories': return { ...state, categories: action.value };
        case 'done':          return { ...state, isLoading: false };
        default:              return state;
    }
}

// The "add a custom setting" modal: its visibility + the draft fields.
const blankCustom = { category: '', key: '', label: '', description: '', data_type: 'string', value: '' };
const initialCustomForm = { show: false, draft: blankCustom };
function customFormReducer(state, action) {
    switch (action.type) {
        case 'open':     return { ...state, show: true };
        case 'close':    return { ...state, show: false };
        case 'setField': return { ...state, draft: { ...state.draft, [action.field]: action.value } };
        case 'reset':    return { show: false, draft: blankCustom };
        default:         return state;
    }
}

export default function Settings() {
    const { restartAll } = useJourney();
    const [load, dispatchLoad] = useReducer(loadReducer, initialLoad);
    const { categories, isLoading } = load;
    const [drafts, setDrafts] = useState({});       // {setting_id: new value}
    const [saving, setSaving] = useState(false);
    const [activeCategory, setActiveCategory] = useState(null);
    const [customForm, dispatchCustom] = useReducer(customFormReducer, initialCustomForm);
    const { show: showCustomForm, draft: customDraft } = customForm;

    useEffect(() => { fetchSettings(); }, []);

    const fetchSettings = async () => {
        dispatchLoad({ type: 'loading' });
        try {
            const res = await apiClient.get('/settings/');
            dispatchLoad({ type: 'setCategories', value: res.data.categories || [] });
            if (!activeCategory && (res.data.categories || []).length > 0) {
                setActiveCategory(res.data.categories[0].key);
            }
            setDrafts({});
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load settings.');
        } finally {
            dispatchLoad({ type: 'done' });
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
                    <span className="sr-only">{item.label || item.key}</span>
                    <input type="checkbox"
                           checked={current === true || current === 'true'}
                           onChange={(e) => set(e.target.checked)} className="sr-only peer" />
                    <span className="w-11 h-6 bg-ink-200 dark:bg-ink-700 rounded-full peer peer-checked:bg-brand-500 transition relative after:absolute after:left-0.5 after:top-0.5 after:bg-white after:rounded-full after:w-5 after:h-5 after:transition peer-checked:after:translate-x-5" />
                </label>
            );
        }
        if (item.data_type === 'number') {
            return <input type="number" aria-label={item.label || item.key} className="input" value={current ?? ''} onChange={(e) => set(e.target.value)} />;
        }
        if (item.data_type === 'json') {
            return <textarea rows="3" aria-label={item.label || item.key} className="input font-mono text-xs resize-none"
                             value={typeof current === 'string' ? current : JSON.stringify(current ?? null, null, 2)}
                             onChange={(e) => set(e.target.value)} />;
        }
        return <input type={item.is_sensitive ? 'password' : 'text'} aria-label={item.label || item.key} className="input"
                      value={current ?? ''} onChange={(e) => set(e.target.value)} />;
    };

    const save = async () => {
        if (dirtyIds.length === 0) {
            toast('Nothing to save', { icon: 'ℹ️' });
            return;
        }
        const updates = allItems.flatMap(i =>
            i.setting_id in drafts
                ? [{ category: i._cat, key: i.key, value: drafts[i.setting_id], data_type: i.data_type }]
                : []);

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
            dispatchCustom({ type: 'reset' });
            await fetchSettings();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to add setting.');
        }
    };

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Administration"
                icon={SettingsIcon}
                title="Hospital Settings"
                subtitle="Branding, working hours, billing, lab/radiology defaults, notifications & compliance."
                actions={
                    <>
                        <button
                            data-tour="restart-tours"
                            type="button"
                            onClick={() => { restartAll(); toast.success('All product tours will replay on next visit.'); }}
                            className="btn-secondary cursor-pointer"
                            title="Reset every module's intro tour so they replay next time you visit"
                        >
                            <Sparkles size={15} /> Replay tours
                        </button>
                        <button type="button" onClick={fetchSettings} className="btn-secondary cursor-pointer"><RefreshCcw size={15} /> Refresh</button>
                        <button type="button" data-tour="settings-custom" onClick={() => dispatchCustom({ type: 'open' })} className="btn-secondary cursor-pointer"><Plus size={15} /> Custom setting</button>
                        <button type="button" data-tour="settings-save" onClick={save} disabled={saving || dirtyIds.length === 0} className="btn-primary disabled:opacity-50 cursor-pointer">
                            {saving ? <Activity size={15} className="animate-spin" /> : <Save size={15} />} Save changes ({dirtyIds.length})
                        </button>
                    </>
                }
            />

            {/* Branding Studio promo card — distinct from the flat key/value store. */}
            <Link
                to="/app/branding"
                className="block group relative overflow-hidden rounded-2xl bg-brand-gradient text-white p-6 shadow-soft hover:shadow-elevated transition-all cursor-pointer"
            >
                <div className="absolute inset-0 bg-aurora opacity-60 pointer-events-none" />
                <div className="relative flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-4">
                        <div className="size-12 rounded-2xl bg-white/15 backdrop-blur ring-1 ring-white/20 flex items-center justify-center">
                            <Palette size={20} />
                        </div>
                        <div>
                            <p className="text-2xs font-semibold uppercase tracking-[0.16em] text-white/80">New</p>
                            <h2 className="text-lg font-semibold tracking-tight mt-0.5">Branding Studio</h2>
                            <p className="text-sm text-white/85 mt-1">
                                Upload your logo, set a sign-in background, override brand colours, configure print templates.
                            </p>
                        </div>
                    </div>
                    <span className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white dark:bg-ink-900 text-brand-700 dark:text-brand-300 font-semibold text-sm group-hover:bg-ink-50 dark:group-hover:bg-ink-800/50 transition-colors">
                        Open Studio <ArrowRight size={14} />
                    </span>
                </div>
            </Link>

            {isLoading ? (
                <div className="card p-12 text-center text-ink-400">
                    <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading settings…
                </div>
            ) : categories.length === 0 ? (
                <div className="card p-12 text-center text-ink-500">No settings have been configured yet.</div>
            ) : (
                <div className="grid grid-cols-12 gap-4">
                    {/* Category nav */}
                    <nav data-tour="settings-categories" className="col-span-12 md:col-span-3 card p-2 flex md:flex-col gap-1 overflow-x-auto">
                        {categories.map(c => {
                            const meta = CATEGORY_META[c.key] || { label: c.key.replace(/_/g, ' '), icon: SettingsIcon };
                            const Icon = meta.icon;
                            const active = activeCategory === c.key;
                            return (
                                <button type="button" key={c.key} onClick={() => setActiveCategory(c.key)}
                                        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${active ? 'bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 ring-1 ring-brand-200 dark:ring-brand-500/20' : 'text-ink-600 dark:text-ink-400 hover:bg-ink-50 dark:hover:bg-ink-800/50'}`}>
                                    <Icon size={15} />
                                    <span className="capitalize">{meta.label}</span>
                                    <span className="ml-auto text-2xs text-ink-400">{c.items.length}</span>
                                </button>
                            );
                        })}
                    </nav>

                    {/* Setting list */}
                    <div data-tour="settings-list" className="col-span-12 md:col-span-9 card overflow-hidden">
                        <div className="p-5 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/40">
                            <h2 className="font-semibold text-ink-900 dark:text-white">
                                {(CATEGORY_META[activeCategory]?.label || activeCategory)}
                            </h2>
                            <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">Each row is a key/value pair. Sensitive values are masked when read back.</p>
                        </div>
                        <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                            {itemsForActive.map(item => {
                                const dirty = item.setting_id in drafts;
                                return (
                                    <li key={item.setting_id} className={`px-5 py-4 grid grid-cols-12 gap-3 items-center ${dirty ? 'bg-amber-50/40 dark:bg-amber-500/10' : ''}`}>
                                        <div className="col-span-12 md:col-span-5">
                                            <p className="text-sm font-medium text-ink-800 dark:text-ink-200">{item.label || item.key}</p>
                                            <p className="text-xs text-ink-500 dark:text-ink-400 font-mono">{item.key}</p>
                                            {item.description && <p className="text-xs text-ink-500 dark:text-ink-400 mt-1 leading-relaxed">{item.description}</p>}
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
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => dispatchCustom({ type: 'close' })} />
                    <div className="relative w-full max-w-lg bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                            <h2 className="text-lg font-semibold dark:text-white flex items-center gap-2"><Plus size={18} /> Add custom setting</h2>
                            <button type="button" onClick={() => dispatchCustom({ type: 'close' })} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full cursor-pointer">
                                <X size={20} aria-hidden="true" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-ink-50/60 dark:bg-ink-800/40">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label htmlFor="settin-category" className="label">Category *</label>
                                    <input id="settin-category" className="input" value={customDraft.category}
                                           onChange={e => dispatchCustom({ type: 'setField', field: 'category', value: e.target.value })}
                                           placeholder="e.g. integrations" />
                                </div>
                                <div>
                                    <label htmlFor="settin-key" className="label">Key *</label>
                                    <input id="settin-key" className="input" value={customDraft.key}
                                           onChange={e => dispatchCustom({ type: 'setField', field: 'key', value: e.target.value })}
                                           placeholder="e.g. slack_webhook" />
                                </div>
                            </div>
                            <div>
                                <label htmlFor="settin-display-label" className="label">Display label</label>
                                <input id="settin-display-label" className="input" value={customDraft.label}
                                       onChange={e => dispatchCustom({ type: 'setField', field: 'label', value: e.target.value })} />
                            </div>
                            <div>
                                <label htmlFor="settin-description" className="label">Description</label>
                                <textarea id="settin-description" rows="2" className="input resize-none" value={customDraft.description}
                                          onChange={e => dispatchCustom({ type: 'setField', field: 'description', value: e.target.value })} />
                            </div>
                            <div>
                                <label htmlFor="settin-type" className="label">Type</label>
                                <select id="settin-type" className="input" value={customDraft.data_type}
                                        onChange={e => dispatchCustom({ type: 'setField', field: 'data_type', value: e.target.value })}>
                                    <option value="string">string</option>
                                    <option value="number">number</option>
                                    <option value="boolean">boolean</option>
                                    <option value="json">json</option>
                                </select>
                            </div>
                            <div>
                                <label htmlFor="settin-initial-value" className="label">Initial value</label>
                                <input id="settin-initial-value" className="input" value={customDraft.value}
                                       onChange={e => dispatchCustom({ type: 'setField', field: 'value', value: e.target.value })} />
                            </div>
                        </div>
                        <div className="p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex justify-end gap-2 shrink-0">
                            <button type="button" onClick={() => dispatchCustom({ type: 'close' })} className="btn-secondary">Cancel</button>
                            <button type="button" onClick={saveCustom} className="btn-primary"><Save size={15} /> Add setting</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
