import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    BookOpen, Coins, CalendarRange, Settings as SettingsIcon,
    Plus, X, ChevronRight, ChevronDown, CheckCircle2, RotateCcw, AlertCircle,
    Sliders, Truck, ShieldCheck, Tag, Link2,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

const TABS = [
    { key: 'coa',        label: 'Chart of Accounts', icon: BookOpen },
    { key: 'journal',    label: 'Journal Entries',   icon: CalendarRange },
    { key: 'config',     label: 'Configuration',     icon: Sliders },
    { key: 'currencies', label: 'Currencies & FX',   icon: Coins },
    { key: 'settings',   label: 'Settings',          icon: SettingsIcon },
];

const STATUS_BADGE = {
    draft:    'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    posted:   'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    reversed: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
};

const TYPE_TONE = {
    Asset:     'text-sky-700 bg-sky-50',
    Liability: 'text-rose-700 bg-rose-50',
    Equity:    'text-violet-700 bg-violet-50',
    Revenue:   'text-emerald-700 bg-emerald-50',
    Expense:   'text-amber-700 bg-amber-50',
};

const formatAmount = (v) => {
    const n = Number(v ?? 0);
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export default function Accounting() {
    const [tab, setTab] = useState('coa');

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={BookOpen}
                title="Managerial Accounting"
                subtitle="Chart of accounts, journals, currencies and period control."
                tone="brand"
            />

            <div className="flex flex-wrap gap-2 border-b border-ink-200/70">
                {TABS.map(({ key, label, icon: Icon }) => (
                    <button
                        key={key}
                        onClick={() => setTab(key)}
                        className={
                            'flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ' +
                            (tab === key
                                ? 'border-brand-600 text-brand-700'
                                : 'border-transparent text-ink-500 hover:text-ink-800')
                        }
                    >
                        <Icon size={16} /> {label}
                    </button>
                ))}
            </div>

            {tab === 'coa'        && <ChartOfAccountsTab />}
            {tab === 'journal'    && <JournalEntriesTab />}
            {tab === 'config'     && <ConfigurationTab />}
            {tab === 'currencies' && <CurrenciesTab />}
            {tab === 'settings'   && <SettingsTab />}
        </div>
    );
}


/* ─── Chart of Accounts ──────────────────────────────────────────────────── */

function ChartOfAccountsTab() {
    const [tree, setTree] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openModal, setOpenModal] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/accounts/tree');
            setTree(r.data || []);
        } catch {
            toast.error('Could not load chart of accounts.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    return (
        <div className="space-y-4">
            <div className="flex justify-end">
                <button
                    onClick={() => setOpenModal(true)}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700"
                >
                    <Plus size={16} /> New account
                </button>
            </div>

            <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-2">
                {loading ? (
                    <div className="p-6 text-sm text-ink-500">Loading...</div>
                ) : tree.length === 0 ? (
                    <div className="p-6 text-sm text-ink-500">No accounts yet.</div>
                ) : (
                    <div className="divide-y divide-ink-100">
                        {tree.map((node) => <AccountNode key={node.account_id} node={node} depth={0} />)}
                    </div>
                )}
            </div>

            {openModal && (
                <NewAccountModal
                    flatAccounts={flatten(tree)}
                    onClose={() => setOpenModal(false)}
                    onSaved={() => { setOpenModal(false); load(); }}
                />
            )}
        </div>
    );
}

function flatten(nodes, depth = 0, out = []) {
    nodes.forEach((n) => {
        out.push({ ...n, depth });
        if (n.children?.length) flatten(n.children, depth + 1, out);
    });
    return out;
}

function AccountNode({ node, depth }) {
    const [open, setOpen] = useState(depth < 1);
    const hasChildren = node.children?.length > 0;
    return (
        <div>
            <div
                className="flex items-center gap-2 px-3 py-2 hover:bg-ink-50/60"
                style={{ paddingLeft: 12 + depth * 16 }}
            >
                {hasChildren ? (
                    <button onClick={() => setOpen(!open)} className="text-ink-400 hover:text-ink-700">
                        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                ) : (
                    <span className="w-[14px]" />
                )}
                <span className="font-mono text-xs text-ink-500 w-16">{node.code}</span>
                <span className="text-sm font-medium text-ink-900 flex-1">{node.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-md ${TYPE_TONE[node.account_type] || 'text-ink-600 bg-ink-50'}`}>
                    {node.account_type}
                </span>
                {!node.is_postable && (
                    <span className="text-[10px] uppercase tracking-wider text-ink-400">rollup</span>
                )}
                {!node.is_active && (
                    <span className="text-[10px] uppercase tracking-wider text-rose-400">inactive</span>
                )}
            </div>
            {open && hasChildren && (
                <div className="divide-y divide-ink-100">
                    {node.children.map((c) => <AccountNode key={c.account_id} node={c} depth={depth + 1} />)}
                </div>
            )}
        </div>
    );
}

function NewAccountModal({ flatAccounts, onClose, onSaved }) {
    const [form, setForm] = useState({
        code: '', name: '', account_type: 'Asset', parent_id: '', is_postable: true,
    });
    const [saving, setSaving] = useState(false);

    const parents = flatAccounts.filter((a) => a.account_type === form.account_type);

    const submit = async () => {
        if (!form.code || !form.name) {
            toast.error('Code and name are required.');
            return;
        }
        setSaving(true);
        try {
            await apiClient.post('/accounting/accounts', {
                code: form.code.trim(),
                name: form.name.trim(),
                account_type: form.account_type,
                parent_id: form.parent_id || null,
                is_postable: form.is_postable,
            });
            toast.success('Account created.');
            onSaved();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not create account.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="New account" onClose={onClose}>
            <div className="space-y-3">
                <Field label="Code">
                    <input className="input" value={form.code}
                           onChange={(e) => setForm({ ...form, code: e.target.value })}
                           placeholder="e.g. 1180" />
                </Field>
                <Field label="Name">
                    <input className="input" value={form.name}
                           onChange={(e) => setForm({ ...form, name: e.target.value })}
                           placeholder="e.g. Prepayments" />
                </Field>
                <Field label="Type">
                    <select className="input" value={form.account_type}
                            onChange={(e) => setForm({ ...form, account_type: e.target.value, parent_id: '' })}>
                        {['Asset', 'Liability', 'Equity', 'Revenue', 'Expense'].map((t) =>
                            <option key={t} value={t}>{t}</option>)}
                    </select>
                </Field>
                <Field label="Parent (optional)">
                    <select className="input" value={form.parent_id}
                            onChange={(e) => setForm({ ...form, parent_id: e.target.value })}>
                        <option value="">— none —</option>
                        {parents.map((a) =>
                            <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
                <label className="flex items-center gap-2 text-sm text-ink-700">
                    <input type="checkbox" checked={form.is_postable}
                           onChange={(e) => setForm({ ...form, is_postable: e.target.checked })} />
                    Postable (uncheck for roll-up only)
                </label>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}


/* ─── Journal Entries ────────────────────────────────────────────────────── */

function JournalEntriesTab() {
    const [entries, setEntries] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openModal, setOpenModal] = useState(false);
    const [accounts, setAccounts] = useState([]);
    const [currencies, setCurrencies] = useState([]);

    const load = async () => {
        setLoading(true);
        try {
            const [eRes, aRes, cRes] = await Promise.all([
                apiClient.get('/accounting/journal-entries'),
                apiClient.get('/accounting/accounts?include_inactive=false'),
                apiClient.get('/accounting/currencies'),
            ]);
            setEntries(eRes.data || []);
            setAccounts((aRes.data || []).filter((a) => a.is_postable));
            setCurrencies(cRes.data || []);
        } catch {
            toast.error('Could not load journal entries.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const post = async (id) => {
        try {
            await apiClient.post(`/accounting/journal-entries/${id}/post`);
            toast.success('Entry posted.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not post entry.');
        }
    };

    const reverse = async (id) => {
        const reason = window.prompt('Reason for reversal (optional):') || '';
        try {
            await apiClient.post(`/accounting/journal-entries/${id}/reverse`, null,
                { params: reason ? { reason } : {} });
            toast.success('Entry reversed.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not reverse entry.');
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex justify-end">
                <button
                    onClick={() => setOpenModal(true)}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700"
                >
                    <Plus size={16} /> New journal entry
                </button>
            </div>

            <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">#</th>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                            <th className="text-left px-4 py-2 font-medium">Currency</th>
                            <th className="text-left px-4 py-2 font-medium">Reference</th>
                            <th className="text-left px-4 py-2 font-medium">Memo</th>
                            <th className="text-right px-4 py-2 font-medium">Total (Dr)</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th className="px-4 py-2"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {loading ? (
                            <tr><td colSpan={8} className="px-4 py-6 text-ink-500">Loading...</td></tr>
                        ) : entries.length === 0 ? (
                            <tr><td colSpan={8} className="px-4 py-6 text-ink-500">No entries yet.</td></tr>
                        ) : entries.map((e) => {
                            const totalDr = (e.lines || []).reduce((s, l) => s + Number(l.debit || 0), 0);
                            return (
                                <tr key={e.entry_id}>
                                    <td className="px-4 py-2 font-mono text-xs">{e.entry_number}</td>
                                    <td className="px-4 py-2">{e.entry_date}</td>
                                    <td className="px-4 py-2">{e.currency_code}</td>
                                    <td className="px-4 py-2">{e.reference || '—'}</td>
                                    <td className="px-4 py-2 text-ink-600">{e.memo || '—'}</td>
                                    <td className="px-4 py-2 text-right font-mono">{formatAmount(totalDr)}</td>
                                    <td className="px-4 py-2">
                                        <span className={`text-xs px-2 py-0.5 rounded-md ${STATUS_BADGE[e.status]}`}>
                                            {e.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-2 text-right">
                                        {e.status === 'draft' && (
                                            <button onClick={() => post(e.entry_id)}
                                                    className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline">
                                                <CheckCircle2 size={14} /> Post
                                            </button>
                                        )}
                                        {e.status === 'posted' && (
                                            <button onClick={() => reverse(e.entry_id)}
                                                    className="inline-flex items-center gap-1 text-xs text-rose-700 hover:underline">
                                                <RotateCcw size={14} /> Reverse
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {openModal && (
                <NewJournalModal
                    accounts={accounts}
                    currencies={currencies}
                    onClose={() => setOpenModal(false)}
                    onSaved={() => { setOpenModal(false); load(); }}
                />
            )}
        </div>
    );
}

function NewJournalModal({ accounts, currencies, onClose, onSaved }) {
    const baseCur = currencies.find((c) => c.is_base)?.code || 'KES';
    const [form, setForm] = useState({
        entry_date: new Date().toISOString().slice(0, 10),
        currency_code: baseCur,
        reference: '',
        memo: '',
    });
    const [lines, setLines] = useState([
        { account_id: '', debit: '', credit: '', description: '' },
        { account_id: '', debit: '', credit: '', description: '' },
    ]);
    const [saving, setSaving] = useState(false);

    const totals = useMemo(() => {
        const dr = lines.reduce((s, l) => s + Number(l.debit || 0), 0);
        const cr = lines.reduce((s, l) => s + Number(l.credit || 0), 0);
        return { dr, cr, balanced: dr === cr && dr > 0 };
    }, [lines]);

    const setLine = (idx, patch) => {
        setLines((prev) => prev.map((l, i) => i === idx ? { ...l, ...patch } : l));
    };

    const addLine = () => setLines([...lines, { account_id: '', debit: '', credit: '', description: '' }]);
    const removeLine = (idx) => setLines(lines.filter((_, i) => i !== idx));

    const submit = async () => {
        const cleaned = lines
            .filter((l) => l.account_id && (Number(l.debit) > 0 || Number(l.credit) > 0))
            .map((l) => ({
                account_id: Number(l.account_id),
                debit: Number(l.debit || 0),
                credit: Number(l.credit || 0),
                description: l.description || null,
            }));
        if (cleaned.length < 2) {
            toast.error('Need at least two non-empty lines.');
            return;
        }
        setSaving(true);
        try {
            await apiClient.post('/accounting/journal-entries', {
                entry_date: form.entry_date,
                currency_code: form.currency_code,
                memo: form.memo || null,
                reference: form.reference || null,
                lines: cleaned,
            });
            toast.success('Draft entry created.');
            onSaved();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not create entry.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="New journal entry" onClose={onClose} wide>
            <div className="grid grid-cols-3 gap-3">
                <Field label="Date">
                    <input type="date" className="input" value={form.entry_date}
                           onChange={(e) => setForm({ ...form, entry_date: e.target.value })} />
                </Field>
                <Field label="Currency">
                    <select className="input" value={form.currency_code}
                            onChange={(e) => setForm({ ...form, currency_code: e.target.value })}>
                        {currencies.map((c) =>
                            <option key={c.currency_id} value={c.code}>{c.code} — {c.name}</option>)}
                    </select>
                </Field>
                <Field label="Reference">
                    <input className="input" value={form.reference}
                           onChange={(e) => setForm({ ...form, reference: e.target.value })}
                           placeholder="optional" />
                </Field>
            </div>
            <Field label="Memo">
                <input className="input" value={form.memo}
                       onChange={(e) => setForm({ ...form, memo: e.target.value })}
                       placeholder="optional" />
            </Field>

            <div className="mt-4 border border-ink-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50 text-ink-600">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium">Account</th>
                            <th className="text-right px-3 py-2 font-medium w-32">Debit</th>
                            <th className="text-right px-3 py-2 font-medium w-32">Credit</th>
                            <th className="text-left px-3 py-2 font-medium">Description</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {lines.map((l, idx) => (
                            <tr key={idx}>
                                <td className="px-3 py-1.5">
                                    <select className="input" value={l.account_id}
                                            onChange={(e) => setLine(idx, { account_id: e.target.value })}>
                                        <option value="">—</option>
                                        {accounts.map((a) =>
                                            <option key={a.account_id} value={a.account_id}>
                                                {a.code} — {a.name}
                                            </option>)}
                                    </select>
                                </td>
                                <td className="px-3 py-1.5">
                                    <input type="number" step="0.01" className="input text-right"
                                           value={l.debit}
                                           onChange={(e) => setLine(idx, { debit: e.target.value, credit: e.target.value ? '' : l.credit })} />
                                </td>
                                <td className="px-3 py-1.5">
                                    <input type="number" step="0.01" className="input text-right"
                                           value={l.credit}
                                           onChange={(e) => setLine(idx, { credit: e.target.value, debit: e.target.value ? '' : l.debit })} />
                                </td>
                                <td className="px-3 py-1.5">
                                    <input className="input" value={l.description}
                                           onChange={(e) => setLine(idx, { description: e.target.value })} />
                                </td>
                                <td className="px-2">
                                    {lines.length > 2 && (
                                        <button onClick={() => removeLine(idx)} className="text-ink-400 hover:text-rose-600">
                                            <X size={14} />
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot className="bg-ink-50">
                        <tr>
                            <td className="px-3 py-2">
                                <button onClick={addLine}
                                        className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1">
                                    <Plus size={12} /> Add line
                                </button>
                            </td>
                            <td className="px-3 py-2 text-right font-mono">{formatAmount(totals.dr)}</td>
                            <td className="px-3 py-2 text-right font-mono">{formatAmount(totals.cr)}</td>
                            <td colSpan={2} className="px-3 py-2">
                                {totals.balanced ? (
                                    <span className="text-xs text-emerald-700 inline-flex items-center gap-1">
                                        <CheckCircle2 size={12} /> Balanced
                                    </span>
                                ) : (
                                    <span className="text-xs text-amber-700 inline-flex items-center gap-1">
                                        <AlertCircle size={12} /> Out of balance
                                    </span>
                                )}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <ModalActions onClose={onClose} onSubmit={submit} saving={saving}
                          submitLabel="Save as draft" />
        </ModalShell>
    );
}


/* ─── Currencies & FX ────────────────────────────────────────────────────── */

function CurrenciesTab() {
    const [currencies, setCurrencies] = useState([]);
    const [rates, setRates] = useState([]);
    const [openCur, setOpenCur] = useState(false);
    const [openFx, setOpenFx] = useState(false);

    const load = async () => {
        try {
            const [c, r] = await Promise.all([
                apiClient.get('/accounting/currencies'),
                apiClient.get('/accounting/fx-rates'),
            ]);
            setCurrencies(c.data || []);
            setRates(r.data || []);
        } catch {
            toast.error('Could not load currency data.');
        }
    };

    useEffect(() => { load(); }, []);

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Currencies */}
            <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft">
                <div className="flex items-center justify-between p-4 border-b border-ink-100">
                    <h3 className="text-sm font-semibold text-ink-900">Currencies</h3>
                    <button onClick={() => setOpenCur(true)}
                            className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1">
                        <Plus size={12} /> Add
                    </button>
                </div>
                <div className="divide-y divide-ink-100">
                    {currencies.map((c) => (
                        <div key={c.currency_id} className="flex items-center justify-between px-4 py-2.5">
                            <div>
                                <div className="text-sm font-medium text-ink-900">
                                    {c.code}{c.is_base && <span className="ml-2 text-[10px] uppercase tracking-wider text-brand-700 bg-brand-50 px-1.5 py-0.5 rounded">base</span>}
                                </div>
                                <div className="text-xs text-ink-500">{c.name}{c.symbol ? ` · ${c.symbol}` : ''}</div>
                            </div>
                            <span className={'text-xs ' + (c.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                {c.is_active ? 'active' : 'inactive'}
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            {/* FX Rates */}
            <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft">
                <div className="flex items-center justify-between p-4 border-b border-ink-100">
                    <h3 className="text-sm font-semibold text-ink-900">Exchange rates</h3>
                    <button onClick={() => setOpenFx(true)}
                            className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1">
                        <Plus size={12} /> Record rate
                    </button>
                </div>
                <div className="divide-y divide-ink-100 max-h-96 overflow-auto">
                    {rates.length === 0 ? (
                        <div className="p-6 text-sm text-ink-500">No rates recorded yet.</div>
                    ) : rates.map((r) => (
                        <div key={r.fx_rate_id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                            <span className="font-mono">{r.from_currency} → {r.to_currency}</span>
                            <span className="font-mono text-ink-700">{Number(r.rate).toFixed(6)}</span>
                            <span className="text-xs text-ink-500">{r.effective_date}</span>
                        </div>
                    ))}
                </div>
            </div>

            {openCur && <NewCurrencyModal onClose={() => setOpenCur(false)} onSaved={() => { setOpenCur(false); load(); }} />}
            {openFx && <NewFxRateModal currencies={currencies} onClose={() => setOpenFx(false)} onSaved={() => { setOpenFx(false); load(); }} />}
        </div>
    );
}

function NewCurrencyModal({ onClose, onSaved }) {
    const [form, setForm] = useState({ code: '', name: '', symbol: '', decimals: 2, is_base: false });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.code || !form.name) { toast.error('Code and name required.'); return; }
        setSaving(true);
        try {
            await apiClient.post('/accounting/currencies', { ...form, code: form.code.toUpperCase() });
            toast.success('Currency added.');
            onSaved();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not add currency.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="Add currency" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Code (ISO-4217)"><input className="input" maxLength={3}
                    value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="USD" /></Field>
                <Field label="Name"><input className="input"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="US Dollar" /></Field>
                <Field label="Symbol"><input className="input"
                    value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} placeholder="$" /></Field>
                <Field label="Decimals"><input type="number" className="input"
                    value={form.decimals} onChange={(e) => setForm({ ...form, decimals: Number(e.target.value) })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-700 mt-3">
                <input type="checkbox" checked={form.is_base}
                       onChange={(e) => setForm({ ...form, is_base: e.target.checked })} />
                Set as base currency
            </label>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

function NewFxRateModal({ currencies, onClose, onSaved }) {
    const [form, setForm] = useState({
        from_currency: '', to_currency: '', rate: '', effective_date: new Date().toISOString().slice(0, 10),
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.from_currency || !form.to_currency || !form.rate) {
            toast.error('All fields required.'); return;
        }
        setSaving(true);
        try {
            await apiClient.post('/accounting/fx-rates', {
                ...form,
                rate: Number(form.rate),
            });
            toast.success('Rate recorded.');
            onSaved();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not record rate.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="Record exchange rate" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3">
                <Field label="From">
                    <select className="input" value={form.from_currency}
                            onChange={(e) => setForm({ ...form, from_currency: e.target.value })}>
                        <option value="">—</option>
                        {currencies.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
                    </select>
                </Field>
                <Field label="To">
                    <select className="input" value={form.to_currency}
                            onChange={(e) => setForm({ ...form, to_currency: e.target.value })}>
                        <option value="">—</option>
                        {currencies.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
                    </select>
                </Field>
                <Field label="Rate"><input type="number" step="0.000001" className="input"
                    value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} /></Field>
                <Field label="Effective date"><input type="date" className="input"
                    value={form.effective_date} onChange={(e) => setForm({ ...form, effective_date: e.target.value })} /></Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}


/* ─── Settings ───────────────────────────────────────────────────────────── */

function SettingsTab() {
    const [settings, setSettings] = useState(null);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        try {
            const r = await apiClient.get('/accounting/settings');
            setSettings(r.data);
        } catch {
            toast.error('Could not load settings.');
        }
    };

    useEffect(() => { load(); }, []);

    const save = async () => {
        if (!settings) return;
        setSaving(true);
        try {
            await apiClient.patch('/accounting/settings', {
                go_live_date: settings.go_live_date,
                fiscal_year_start_month: settings.fiscal_year_start_month,
            });
            toast.success('Settings saved.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save settings.');
        } finally {
            setSaving(false);
        }
    };

    const seedYear = async () => {
        const yearStr = window.prompt('Year to seed periods for (e.g. 2026):', new Date().getFullYear().toString());
        if (!yearStr) return;
        try {
            await apiClient.post('/accounting/fiscal-periods/seed-year', { year: Number(yearStr) });
            toast.success(`Seeded periods for ${yearStr}.`);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not seed periods.');
        }
    };

    if (!settings) return <div className="text-sm text-ink-500 p-6">Loading...</div>;

    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5 max-w-2xl">
            <Field label="Base currency">
                <input className="input bg-ink-50" value={settings.base_currency_code} disabled />
                <p className="text-xs text-ink-500 mt-1">
                    Change the base currency from the Currencies tab. Locked once any entry is posted.
                </p>
            </Field>
            <Field label="Go-live date">
                <input type="date" className="input"
                       value={settings.go_live_date || ''}
                       onChange={(e) => setSettings({ ...settings, go_live_date: e.target.value || null })} />
                <p className="text-xs text-ink-500 mt-1">
                    Auto-posting from other modules will ignore anything dated before this.
                </p>
            </Field>
            <Field label="Fiscal year start month">
                <select className="input"
                        value={settings.fiscal_year_start_month}
                        onChange={(e) => setSettings({ ...settings, fiscal_year_start_month: Number(e.target.value) })}>
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((m) =>
                        <option key={m} value={m}>{new Date(2000, m - 1, 1).toLocaleString(undefined, { month: 'long' })}</option>)}
                </select>
            </Field>

            <div className="flex items-center gap-3 pt-2">
                <button onClick={save} disabled={saving}
                        className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                    {saving ? 'Saving...' : 'Save settings'}
                </button>
                <button onClick={seedYear}
                        className="px-4 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50">
                    Seed fiscal periods for a year
                </button>
            </div>
        </div>
    );
}


/* ─── Configuration ──────────────────────────────────────────────────────── */

const CONFIG_SECTIONS = [
    { key: 'suppliers',  label: 'Suppliers',           icon: Truck },
    { key: 'insurance',  label: 'Insurance Providers', icon: ShieldCheck },
    { key: 'schemes',    label: 'Medical Schemes',     icon: ShieldCheck },
    { key: 'pricelist',  label: 'Price List',          icon: Tag },
    { key: 'mappings',   label: 'Ledger Mappings',     icon: Link2 },
];

function ConfigurationTab() {
    const [section, setSection] = useState('suppliers');
    return (
        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-6">
            <aside className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-2 h-fit">
                <nav className="space-y-1">
                    {CONFIG_SECTIONS.map(({ key, label, icon: Icon }) => (
                        <button key={key}
                                onClick={() => setSection(key)}
                                className={
                                    'w-full flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors ' +
                                    (section === key
                                        ? 'bg-brand-50 text-brand-700 font-medium'
                                        : 'text-ink-600 hover:bg-ink-50')
                                }>
                            <Icon size={16} /> {label}
                        </button>
                    ))}
                </nav>
            </aside>
            <div>
                {section === 'suppliers'  && <SuppliersSection />}
                {section === 'insurance'  && <InsuranceSection />}
                {section === 'schemes'    && <SchemesSection />}
                {section === 'pricelist'  && <PriceListSection />}
                {section === 'mappings'   && <MappingsSection />}
            </div>
        </div>
    );
}

/* Suppliers */
function SuppliersSection() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/config/suppliers?include_inactive=true');
            setItems(r.data || []);
        } catch { toast.error('Could not load suppliers.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    return (
        <div className="space-y-4">
            <SectionHeader title="Suppliers" subtitle="Vendors you buy goods and services from."
                           onNew={() => { setEditing(null); setOpen(true); }} />
            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No suppliers yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Name</th>
                            <th className="text-left px-4 py-2 font-medium">Contact</th>
                            <th className="text-left px-4 py-2 font-medium">KRA PIN</th>
                            <th className="text-right px-4 py-2 font-medium">Terms (days)</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map((s) => (
                            <tr key={s.supplier_id}>
                                <td className="px-4 py-1.5 font-medium">{s.name}</td>
                                <td className="px-4 py-1.5 text-ink-600">{s.contact_person || '—'}{s.email ? ` · ${s.email}` : ''}</td>
                                <td className="px-4 py-1.5 font-mono text-xs">{s.tax_pin || '—'}</td>
                                <td className="px-4 py-1.5 text-right">{s.payment_terms_days}</td>
                                <td className="px-4 py-1.5">
                                    <span className={'text-xs ' + (s.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                        {s.is_active ? 'active' : 'inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-1.5 text-right">
                                    <button onClick={() => { setEditing(s); setOpen(true); }}
                                            className="text-xs text-brand-700 hover:underline">Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {open && <SupplierModal initial={editing}
                                    onClose={() => setOpen(false)}
                                    onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function SupplierModal({ initial, onClose, onSaved }) {
    const isEdit = !!initial;
    const [accounts, setAccounts] = useState([]);
    const [form, setForm] = useState(initial || {
        name: '', contact_person: '', email: '', phone: '', address: '',
        tax_pin: '', payment_terms_days: 30, default_payable_account_id: '',
        notes: '',
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        apiClient.get('/accounting/accounts?include_inactive=false')
            .then(r => setAccounts((r.data || []).filter(a => a.account_type === 'Liability' && a.is_postable)))
            .catch(() => {});
    }, []);

    const submit = async () => {
        if (!form.name) { toast.error('Name required.'); return; }
        setSaving(true);
        try {
            const payload = {
                ...form,
                default_payable_account_id: form.default_payable_account_id || null,
            };
            if (isEdit) await apiClient.patch(`/accounting/config/suppliers/${initial.supplier_id}`, payload);
            else await apiClient.post('/accounting/config/suppliers', payload);
            toast.success(isEdit ? 'Supplier updated.' : 'Supplier created.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={isEdit ? 'Edit supplier' : 'New supplier'} onClose={onClose} wide>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Name *"><input className="input" value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
                <Field label="Contact person"><input className="input" value={form.contact_person || ''}
                    onChange={(e) => setForm({ ...form, contact_person: e.target.value })} /></Field>
                <Field label="Email"><input type="email" className="input" value={form.email || ''}
                    onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
                <Field label="Phone"><input className="input" value={form.phone || ''}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
                <Field label="KRA PIN"><input className="input" value={form.tax_pin || ''}
                    onChange={(e) => setForm({ ...form, tax_pin: e.target.value })} /></Field>
                <Field label="Payment terms (days)"><input type="number" className="input" value={form.payment_terms_days}
                    onChange={(e) => setForm({ ...form, payment_terms_days: Number(e.target.value) })} /></Field>
                <Field label="Default payable account">
                    <select className="input" value={form.default_payable_account_id || ''}
                            onChange={(e) => setForm({ ...form, default_payable_account_id: e.target.value })}>
                        <option value="">— default (2110 Accounts Payable) —</option>
                        {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
                {isEdit && (
                    <Field label="Status">
                        <select className="input" value={form.is_active ? 'active' : 'inactive'}
                                onChange={(e) => setForm({ ...form, is_active: e.target.value === 'active' })}>
                            <option value="active">Active</option>
                            <option value="inactive">Inactive</option>
                        </select>
                    </Field>
                )}
            </div>
            <Field label="Address">
                <textarea className="input min-h-[60px]" value={form.address || ''}
                          onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
            <Field label="Notes">
                <textarea className="input min-h-[60px]" value={form.notes || ''}
                          onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

/* Insurance providers */
function InsuranceSection() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/config/insurance-providers?include_inactive=true');
            setItems(r.data || []);
        } catch { toast.error('Could not load providers.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    return (
        <div className="space-y-4">
            <SectionHeader title="Insurance Providers" subtitle="Insurers your hospital accepts (NHIF, AAR, Jubilee, etc.)."
                           onNew={() => { setEditing(null); setOpen(true); }} />
            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No providers yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Name</th>
                            <th className="text-left px-4 py-2 font-medium">Contact</th>
                            <th className="text-left px-4 py-2 font-medium">Phone</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map((p) => (
                            <tr key={p.provider_id}>
                                <td className="px-4 py-1.5 font-medium">{p.name}</td>
                                <td className="px-4 py-1.5 text-ink-600">{p.contact_person || '—'}{p.email ? ` · ${p.email}` : ''}</td>
                                <td className="px-4 py-1.5">{p.phone || '—'}</td>
                                <td className="px-4 py-1.5">
                                    <span className={'text-xs ' + (p.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                        {p.is_active ? 'active' : 'inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-1.5 text-right">
                                    <button onClick={() => { setEditing(p); setOpen(true); }}
                                            className="text-xs text-brand-700 hover:underline">Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {open && <ProviderModal initial={editing}
                                    onClose={() => setOpen(false)}
                                    onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function ProviderModal({ initial, onClose, onSaved }) {
    const isEdit = !!initial;
    const [accounts, setAccounts] = useState([]);
    const [form, setForm] = useState(initial || {
        name: '', contact_person: '', email: '', phone: '', address: '',
        default_receivable_account_id: '', notes: '',
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        apiClient.get('/accounting/accounts?include_inactive=false')
            .then(r => setAccounts((r.data || []).filter(a => a.account_type === 'Asset' && a.is_postable)))
            .catch(() => {});
    }, []);

    const submit = async () => {
        if (!form.name) { toast.error('Name required.'); return; }
        setSaving(true);
        try {
            const payload = { ...form, default_receivable_account_id: form.default_receivable_account_id || null };
            if (isEdit) await apiClient.patch(`/accounting/config/insurance-providers/${initial.provider_id}`, payload);
            else await apiClient.post('/accounting/config/insurance-providers', payload);
            toast.success(isEdit ? 'Provider updated.' : 'Provider created.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={isEdit ? 'Edit insurance provider' : 'New insurance provider'} onClose={onClose}>
            <div className="space-y-3">
                <Field label="Name *"><input className="input" value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
                <div className="grid grid-cols-2 gap-3">
                    <Field label="Contact person"><input className="input" value={form.contact_person || ''}
                        onChange={(e) => setForm({ ...form, contact_person: e.target.value })} /></Field>
                    <Field label="Email"><input type="email" className="input" value={form.email || ''}
                        onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
                    <Field label="Phone"><input className="input" value={form.phone || ''}
                        onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
                    <Field label="Default receivable account">
                        <select className="input" value={form.default_receivable_account_id || ''}
                                onChange={(e) => setForm({ ...form, default_receivable_account_id: e.target.value })}>
                            <option value="">— default (1150 Insurance Receivable) —</option>
                            {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                        </select>
                    </Field>
                </div>
                <Field label="Address">
                    <textarea className="input min-h-[60px]" value={form.address || ''}
                              onChange={(e) => setForm({ ...form, address: e.target.value })} />
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

/* Medical schemes */
function SchemesSection() {
    const [items, setItems] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [sR, pR] = await Promise.all([
                apiClient.get('/accounting/config/medical-schemes?include_inactive=true'),
                apiClient.get('/accounting/config/insurance-providers?include_inactive=true'),
            ]);
            setItems(sR.data || []);
            setProviders(pR.data || []);
        } catch { toast.error('Could not load schemes.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const providerName = (id) => providers.find(p => p.provider_id === id)?.name || '—';

    return (
        <div className="space-y-4">
            <SectionHeader title="Medical Schemes" subtitle="Per-provider product variants (e.g. AAR Standard, NHIF Civil Servants)."
                           onNew={() => { setEditing(null); setOpen(true); }}
                           disabled={providers.length === 0}
                           disabledMsg="Add an insurance provider first." />
            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No schemes yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Provider</th>
                            <th className="text-left px-4 py-2 font-medium">Scheme</th>
                            <th className="text-left px-4 py-2 font-medium">Code</th>
                            <th className="text-right px-4 py-2 font-medium">Coverage limit</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map((s) => (
                            <tr key={s.scheme_id}>
                                <td className="px-4 py-1.5 text-ink-600">{providerName(s.provider_id)}</td>
                                <td className="px-4 py-1.5 font-medium">{s.name}</td>
                                <td className="px-4 py-1.5 font-mono text-xs">{s.scheme_code || '—'}</td>
                                <td className="px-4 py-1.5 text-right font-mono">
                                    {s.coverage_limit ? formatAmount(s.coverage_limit) : '—'}
                                </td>
                                <td className="px-4 py-1.5">
                                    <span className={'text-xs ' + (s.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                        {s.is_active ? 'active' : 'inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-1.5 text-right">
                                    <button onClick={() => { setEditing(s); setOpen(true); }}
                                            className="text-xs text-brand-700 hover:underline">Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {open && <SchemeModal initial={editing} providers={providers}
                                  onClose={() => setOpen(false)}
                                  onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function SchemeModal({ initial, providers, onClose, onSaved }) {
    const isEdit = !!initial;
    const [form, setForm] = useState(initial || {
        provider_id: providers[0]?.provider_id || '',
        name: '', scheme_code: '', coverage_limit: '', notes: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.name || !form.provider_id) { toast.error('Provider and name required.'); return; }
        setSaving(true);
        try {
            const payload = {
                ...form,
                provider_id: Number(form.provider_id),
                coverage_limit: form.coverage_limit ? Number(form.coverage_limit) : null,
            };
            if (isEdit) {
                const patch = { ...payload };
                delete patch.provider_id;
                await apiClient.patch(`/accounting/config/medical-schemes/${initial.scheme_id}`, patch);
            } else await apiClient.post('/accounting/config/medical-schemes', payload);
            toast.success(isEdit ? 'Scheme updated.' : 'Scheme created.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={isEdit ? 'Edit scheme' : 'New medical scheme'} onClose={onClose}>
            <div className="space-y-3">
                <Field label="Provider *">
                    <select className="input" value={form.provider_id}
                            disabled={isEdit}
                            onChange={(e) => setForm({ ...form, provider_id: e.target.value })}>
                        {providers.map(p => <option key={p.provider_id} value={p.provider_id}>{p.name}</option>)}
                    </select>
                </Field>
                <Field label="Scheme name *"><input className="input" value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
                <div className="grid grid-cols-2 gap-3">
                    <Field label="Scheme code"><input className="input" value={form.scheme_code || ''}
                        onChange={(e) => setForm({ ...form, scheme_code: e.target.value })} /></Field>
                    <Field label="Coverage limit"><input type="number" step="0.01" className="input"
                        value={form.coverage_limit || ''}
                        onChange={(e) => setForm({ ...form, coverage_limit: e.target.value })} /></Field>
                </div>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

/* Price list */
function PriceListSection() {
    const [items, setItems] = useState([]);
    const [categories, setCategories] = useState([]);
    const [filter, setFilter] = useState('');
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [pR, cR] = await Promise.all([
                apiClient.get(`/accounting/config/price-list?include_inactive=true${filter ? `&category=${filter}` : ''}`),
                apiClient.get('/accounting/config/price-list/categories'),
            ]);
            setItems(pR.data || []);
            setCategories(cR.data || []);
        } catch { toast.error('Could not load price list.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filter]);

    return (
        <div className="space-y-4">
            <SectionHeader title="Price List" subtitle="Master list of billable services."
                           onNew={() => { setEditing(null); setOpen(true); }} />
            <div className="flex items-center gap-2">
                <span className="text-xs text-ink-500">Filter:</span>
                <select className="input max-w-xs" value={filter} onChange={(e) => setFilter(e.target.value)}>
                    <option value="">All categories</option>
                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
            </div>
            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No price items yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Code</th>
                            <th className="text-left px-4 py-2 font-medium">Service</th>
                            <th className="text-left px-4 py-2 font-medium">Category</th>
                            <th className="text-right px-4 py-2 font-medium">Unit price</th>
                            <th className="text-right px-4 py-2 font-medium">Tax %</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map((p) => (
                            <tr key={p.price_id}>
                                <td className="px-4 py-1.5 font-mono text-xs">{p.service_code}</td>
                                <td className="px-4 py-1.5">{p.name}</td>
                                <td className="px-4 py-1.5">
                                    <span className="text-xs px-2 py-0.5 rounded-md bg-ink-50 text-ink-700">{p.category}</span>
                                </td>
                                <td className="px-4 py-1.5 text-right font-mono">{formatAmount(p.unit_price)}</td>
                                <td className="px-4 py-1.5 text-right">{Number(p.tax_rate_pct).toFixed(1)}%</td>
                                <td className="px-4 py-1.5">
                                    <span className={'text-xs ' + (p.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                        {p.is_active ? 'active' : 'inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-1.5 text-right">
                                    <button onClick={() => { setEditing(p); setOpen(true); }}
                                            className="text-xs text-brand-700 hover:underline">Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {open && <PriceModal initial={editing} categories={categories}
                                 onClose={() => setOpen(false)}
                                 onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function PriceModal({ initial, categories, onClose, onSaved }) {
    const isEdit = !!initial;
    const [accounts, setAccounts] = useState([]);
    const [form, setForm] = useState(initial || {
        service_code: '', name: '', category: categories[0] || 'Consultation',
        unit_price: '', revenue_account_id: '', tax_rate_pct: 0, description: '',
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        apiClient.get('/accounting/accounts?account_type=Revenue&include_inactive=false')
            .then(r => setAccounts((r.data || []).filter(a => a.is_postable)))
            .catch(() => {});
    }, []);

    const submit = async () => {
        if (!form.name || (!isEdit && !form.service_code)) {
            toast.error('Service code and name required.'); return;
        }
        setSaving(true);
        try {
            const payload = {
                ...form,
                unit_price: Number(form.unit_price || 0),
                tax_rate_pct: Number(form.tax_rate_pct || 0),
                revenue_account_id: form.revenue_account_id || null,
            };
            if (isEdit) {
                const patch = { ...payload };
                delete patch.service_code;
                await apiClient.patch(`/accounting/config/price-list/${initial.price_id}`, patch);
            } else await apiClient.post('/accounting/config/price-list', payload);
            toast.success(isEdit ? 'Item updated.' : 'Item created.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={isEdit ? 'Edit price item' : 'New price item'} onClose={onClose} wide>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Service code *"><input className="input" value={form.service_code}
                    disabled={isEdit}
                    onChange={(e) => setForm({ ...form, service_code: e.target.value })} /></Field>
                <Field label="Category *">
                    <select className="input" value={form.category}
                            onChange={(e) => setForm({ ...form, category: e.target.value })}>
                        {categories.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                </Field>
                <Field label="Service name *" >
                    <input className="input" value={form.name}
                           onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </Field>
                <Field label="Unit price *"><input type="number" step="0.01" className="input"
                    value={form.unit_price}
                    onChange={(e) => setForm({ ...form, unit_price: e.target.value })} /></Field>
                <Field label="Tax rate (%)"><input type="number" step="0.01" className="input"
                    value={form.tax_rate_pct}
                    onChange={(e) => setForm({ ...form, tax_rate_pct: e.target.value })} /></Field>
                <Field label="Revenue account">
                    <select className="input" value={form.revenue_account_id || ''}
                            onChange={(e) => setForm({ ...form, revenue_account_id: e.target.value })}>
                        <option value="">— default (per ledger mapping) —</option>
                        {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
            </div>
            <Field label="Description">
                <textarea className="input min-h-[60px]" value={form.description || ''}
                          onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

/* Ledger mappings */
function MappingsSection() {
    const [catalogue, setCatalogue] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [cR, aR] = await Promise.all([
                apiClient.get('/accounting/config/ledger-mappings/catalogue'),
                apiClient.get('/accounting/accounts?include_inactive=false'),
            ]);
            setCatalogue(cR.data || []);
            setAccounts((aR.data || []).filter(a => a.is_postable));
        } catch { toast.error('Could not load ledger mappings.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const codeName = (id) => {
        if (!id) return '— unset —';
        const a = accounts.find(x => x.account_id === id);
        return a ? `${a.code} ${a.name}` : `#${id}`;
    };

    return (
        <div className="space-y-4">
            <div>
                <h3 className="text-lg font-semibold text-ink-900">Ledger Mappings</h3>
                <p className="text-sm text-ink-600 mt-1">
                    These tell auto-posting (Phase 4) which accounts to use for each event. Defaults are seeded
                    to match the default CoA — re-point them if you renamed or restructured accounts.
                </p>
            </div>
            <DataCard loading={loading} empty={catalogue.length === 0} emptyMsg="No mappings.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Source key</th>
                            <th className="text-left px-4 py-2 font-medium">Description</th>
                            <th className="text-left px-4 py-2 font-medium">Debit (Dr)</th>
                            <th className="text-left px-4 py-2 font-medium">Credit (Cr)</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {catalogue.map((c) => (
                            <tr key={c.source_key}>
                                <td className="px-4 py-1.5 font-mono text-xs">{c.source_key}</td>
                                <td className="px-4 py-1.5 text-ink-600">{c.description}</td>
                                <td className="px-4 py-1.5">{codeName(c.mapping?.debit_account_id)}</td>
                                <td className="px-4 py-1.5">{codeName(c.mapping?.credit_account_id)}</td>
                                <td className="px-4 py-1.5 text-right">
                                    {c.mapping ? (
                                        <button onClick={() => setEditing(c.mapping)}
                                                className="text-xs text-brand-700 hover:underline">Edit</button>
                                    ) : (
                                        <span className="text-xs text-amber-700">missing</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {editing && <MappingModal initial={editing} accounts={accounts}
                                      onClose={() => setEditing(null)}
                                      onSaved={() => { setEditing(null); load(); }} />}
        </div>
    );
}

function MappingModal({ initial, accounts, onClose, onSaved }) {
    const [form, setForm] = useState({
        debit_account_id: initial.debit_account_id || '',
        credit_account_id: initial.credit_account_id || '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        setSaving(true);
        try {
            await apiClient.patch(`/accounting/config/ledger-mappings/${initial.mapping_id}`, {
                debit_account_id: form.debit_account_id ? Number(form.debit_account_id) : null,
                credit_account_id: form.credit_account_id ? Number(form.credit_account_id) : null,
            });
            toast.success('Mapping updated.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={`Edit mapping: ${initial.source_key}`} onClose={onClose}>
            <p className="text-xs text-ink-500 mb-3">
                When this event fires, Phase 4 auto-posting will Dr the debit account and Cr the credit account.
            </p>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Debit account">
                    <select className="input" value={form.debit_account_id || ''}
                            onChange={(e) => setForm({ ...form, debit_account_id: e.target.value })}>
                        <option value="">— unset —</option>
                        {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
                <Field label="Credit account">
                    <select className="input" value={form.credit_account_id || ''}
                            onChange={(e) => setForm({ ...form, credit_account_id: e.target.value })}>
                        <option value="">— unset —</option>
                        {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

/* Config helpers */
function SectionHeader({ title, subtitle, onNew, disabled, disabledMsg }) {
    return (
        <div className="flex items-start justify-between">
            <div>
                <h3 className="text-lg font-semibold text-ink-900">{title}</h3>
                {subtitle && <p className="text-sm text-ink-600 mt-1">{subtitle}</p>}
            </div>
            <button onClick={onNew} disabled={disabled} title={disabled ? disabledMsg : undefined}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed">
                <Plus size={16} /> New
            </button>
        </div>
    );
}

function DataCard({ loading, empty, emptyMsg, children }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            {loading ? (
                <div className="p-6 text-sm text-ink-500">Loading...</div>
            ) : empty ? (
                <div className="p-6 text-sm text-ink-500">{emptyMsg}</div>
            ) : children}
        </div>
    );
}


/* ─── shared shells ──────────────────────────────────────────────────────── */

function ModalShell({ title, onClose, wide, children }) {
    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className={'bg-white rounded-2xl shadow-elevated w-full ' + (wide ? 'max-w-3xl' : 'max-w-md')}>
                <div className="flex items-center justify-between p-4 border-b border-ink-100">
                    <h3 className="text-sm font-semibold text-ink-900">{title}</h3>
                    <button onClick={onClose} className="text-ink-400 hover:text-ink-700">
                        <X size={18} />
                    </button>
                </div>
                <div className="p-5">{children}</div>
            </div>
        </div>
    );
}

function ModalActions({ onClose, onSubmit, saving, submitLabel = 'Save' }) {
    return (
        <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-ink-100">
            <button onClick={onClose}
                    className="px-3 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50">
                Cancel
            </button>
            <button onClick={onSubmit} disabled={saving}
                    className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                {saving ? 'Saving...' : submitLabel}
            </button>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <label className="block">
            <span className="block text-xs font-medium text-ink-600 mb-1">{label}</span>
            {children}
        </label>
    );
}
