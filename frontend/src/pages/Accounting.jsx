import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    BookOpen, Coins, CalendarRange, Settings as SettingsIcon,
    Plus, X, ChevronRight, ChevronDown, CheckCircle2, RotateCcw, AlertCircle,
    BarChart3, Download,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

const TABS = [
    { key: 'coa',        label: 'Chart of Accounts', icon: BookOpen },
    { key: 'journal',    label: 'Journal Entries',   icon: CalendarRange },
    { key: 'reports',    label: 'Reports',           icon: BarChart3 },
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
            {tab === 'reports'    && <ReportsTab />}
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


/* ─── Reports ────────────────────────────────────────────────────────────── */

const REPORT_TYPES = [
    { key: 'trial-balance',     label: 'Trial Balance',     range: 'as_of' },
    { key: 'income-statement',  label: 'Income Statement',  range: 'period' },
    { key: 'balance-sheet',     label: 'Balance Sheet',     range: 'as_of' },
    { key: 'cash-flow',         label: 'Cash Flow',         range: 'period' },
    { key: 'daily-collections', label: 'Daily Collections', range: 'period' },
];

function todayISO() { return new Date().toISOString().slice(0, 10); }

function firstOfMonthISO() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

function csvDownload(filename, rows, headers) {
    const escape = (v) => {
        if (v == null) return '';
        const s = String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [headers.map(h => escape(h.label)).join(',')];
    rows.forEach(r => lines.push(headers.map(h => escape(typeof h.get === 'function' ? h.get(r) : r[h.key])).join(',')));
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

function ReportsTab() {
    const [report, setReport] = useState('trial-balance');
    const [asOf, setAsOf] = useState(todayISO());
    const [from, setFrom] = useState(firstOfMonthISO());
    const [to, setTo] = useState(todayISO());
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    const meta = REPORT_TYPES.find(r => r.key === report);

    const load = async () => {
        setLoading(true);
        setData(null);
        try {
            const params = meta.range === 'as_of' ? { as_of: asOf } : { from, to };
            const res = await apiClient.get(`/accounting/reports/${report}`, { params });
            setData(res.data);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load report.');
        } finally {
            setLoading(false);
        }
    };

    // Auto-load when switching reports.
    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [report]);

    return (
        <div className="space-y-4">
            <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-4 flex flex-wrap items-end gap-3">
                <Field label="Report">
                    <select className="input" value={report} onChange={(e) => setReport(e.target.value)}>
                        {REPORT_TYPES.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                    </select>
                </Field>
                {meta.range === 'as_of' ? (
                    <Field label="As of">
                        <input type="date" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
                    </Field>
                ) : (
                    <>
                        <Field label="From">
                            <input type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />
                        </Field>
                        <Field label="To">
                            <input type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} />
                        </Field>
                    </>
                )}
                <button onClick={load} disabled={loading}
                        className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                    {loading ? 'Loading...' : 'Run'}
                </button>
                {data && (
                    <button onClick={() => exportReport(report, data)}
                            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50">
                        <Download size={14} /> Export CSV
                    </button>
                )}
            </div>

            {loading && <div className="p-6 text-sm text-ink-500">Loading...</div>}
            {!loading && data && report === 'trial-balance'     && <TrialBalanceView data={data} />}
            {!loading && data && report === 'income-statement'  && <IncomeStatementView data={data} />}
            {!loading && data && report === 'balance-sheet'     && <BalanceSheetView data={data} />}
            {!loading && data && report === 'cash-flow'         && <CashFlowView data={data} />}
            {!loading && data && report === 'daily-collections' && <DailyCollectionsView data={data} />}
        </div>
    );
}

function exportReport(report, data) {
    if (report === 'trial-balance') {
        csvDownload(`trial-balance-${data.as_of}.csv`, data.rows, [
            { key: 'code', label: 'Code' }, { key: 'name', label: 'Account' },
            { key: 'account_type', label: 'Type' }, { key: 'debit', label: 'Debit' },
            { key: 'credit', label: 'Credit' }, { key: 'balance', label: 'Balance' },
        ]);
    } else if (report === 'income-statement') {
        const rows = [
            ...data.revenue.map(r => ({ section: 'Revenue', ...r })),
            ...data.cogs.map(r => ({ section: 'COGS', ...r })),
            ...data.operating_expenses.map(r => ({ section: 'Operating Expense', ...r })),
        ];
        csvDownload(`income-statement-${data.from_date}-to-${data.to_date}.csv`, rows, [
            { key: 'section', label: 'Section' }, { key: 'code', label: 'Code' },
            { key: 'name', label: 'Account' }, { key: 'amount', label: 'Amount' },
        ]);
    } else if (report === 'balance-sheet') {
        const rows = [
            ...data.assets.map(r => ({ section: 'Asset', ...r })),
            ...data.liabilities.map(r => ({ section: 'Liability', ...r })),
            ...data.equity.map(r => ({ section: 'Equity', ...r })),
            { section: 'Equity', code: '—', name: 'Current Year Earnings', amount: data.current_year_earnings },
        ];
        csvDownload(`balance-sheet-${data.as_of}.csv`, rows, [
            { key: 'section', label: 'Section' }, { key: 'code', label: 'Code' },
            { key: 'name', label: 'Account' }, { key: 'amount', label: 'Amount' },
        ]);
    } else if (report === 'cash-flow') {
        csvDownload(`cash-flow-${data.from_date}-to-${data.to_date}.csv`, [
            { label: 'Operating activities', amount: data.operating },
            { label: 'Investing activities', amount: data.investing },
            { label: 'Financing activities', amount: data.financing },
            { label: 'Net change in cash', amount: data.net_change },
        ], [{ key: 'label', label: 'Section' }, { key: 'amount', label: 'Amount' }]);
    } else if (report === 'daily-collections') {
        csvDownload(`daily-collections-${data.from_date}-to-${data.to_date}.csv`, data.rows, [
            { key: 'date', label: 'Date' }, { key: 'account_code', label: 'Code' },
            { key: 'account_name', label: 'Account' }, { key: 'amount', label: 'Amount' },
        ]);
    }
}

function TrialBalanceView({ data }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            <div className="px-4 py-3 border-b border-ink-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Trial Balance — as of {data.as_of}</h3>
                <span className={'text-xs ' + (Number(data.totals.difference) === 0 ? 'text-emerald-700' : 'text-rose-700')}>
                    Difference: {formatAmount(data.totals.difference)}
                </span>
            </div>
            <table className="w-full text-sm">
                <thead className="bg-ink-50/60 text-ink-600">
                    <tr>
                        <th className="text-left px-4 py-2 font-medium">Code</th>
                        <th className="text-left px-4 py-2 font-medium">Account</th>
                        <th className="text-left px-4 py-2 font-medium">Type</th>
                        <th className="text-right px-4 py-2 font-medium">Debit</th>
                        <th className="text-right px-4 py-2 font-medium">Credit</th>
                        <th className="text-right px-4 py-2 font-medium">Balance</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                    {data.rows.length === 0 ? (
                        <tr><td colSpan={6} className="px-4 py-6 text-ink-500">No posted entries up to this date.</td></tr>
                    ) : data.rows.map(r => (
                        <tr key={r.account_id}>
                            <td className="px-4 py-1.5 font-mono text-xs">{r.code}</td>
                            <td className="px-4 py-1.5">{r.name}</td>
                            <td className="px-4 py-1.5">
                                <span className={`text-xs px-2 py-0.5 rounded-md ${TYPE_TONE[r.account_type] || ''}`}>{r.account_type}</span>
                            </td>
                            <td className="px-4 py-1.5 text-right font-mono">{formatAmount(r.debit)}</td>
                            <td className="px-4 py-1.5 text-right font-mono">{formatAmount(r.credit)}</td>
                            <td className="px-4 py-1.5 text-right font-mono font-semibold">{formatAmount(r.balance)}</td>
                        </tr>
                    ))}
                </tbody>
                <tfoot className="bg-ink-50">
                    <tr>
                        <td colSpan={3} className="px-4 py-2 font-semibold">Totals</td>
                        <td className="px-4 py-2 text-right font-mono font-semibold">{formatAmount(data.totals.debit)}</td>
                        <td className="px-4 py-2 text-right font-mono font-semibold">{formatAmount(data.totals.credit)}</td>
                        <td className="px-4 py-2"></td>
                    </tr>
                </tfoot>
            </table>
        </div>
    );
}

function IncomeStatementView({ data }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
            <h3 className="text-sm font-semibold text-ink-900">
                Income Statement — {data.from_date} to {data.to_date}
            </h3>

            <Section label="Revenue" rows={data.revenue} total={data.total_revenue} totalTone="text-emerald-700" />
            <Section label="Cost of Services" rows={data.cogs} total={data.total_cogs} totalTone="text-amber-700" />
            <Row label="Gross Profit" value={data.gross_profit} bold />
            <Section label="Operating Expenses" rows={data.operating_expenses} total={data.total_operating_expenses} totalTone="text-amber-700" />
            <div className="pt-3 border-t-2 border-ink-200">
                <Row
                    label="Net Income"
                    value={data.net_income}
                    bold
                    tone={Number(data.net_income) >= 0 ? 'text-emerald-700' : 'text-rose-700'}
                />
            </div>
        </div>
    );
}

function BalanceSheetView({ data }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink-900">Balance Sheet — as of {data.as_of}</h3>
                <span className={'text-xs ' + (data.balanced ? 'text-emerald-700' : 'text-rose-700')}>
                    {data.balanced ? 'Balanced' : 'Out of balance'}
                </span>
            </div>

            <Section label="Assets" rows={data.assets} total={data.total_assets} totalTone="text-sky-700" />

            <div className="pt-3 border-t border-ink-200">
                <Section label="Liabilities" rows={data.liabilities} total={data.total_liabilities} totalTone="text-rose-700" />
            </div>

            <div className="pt-3 border-t border-ink-200">
                <h4 className="text-xs font-semibold text-ink-600 uppercase mb-2">Equity</h4>
                {data.equity.map(e => (
                    <Row key={e.account_id} label={`${e.code} — ${e.name}`} value={e.amount} />
                ))}
                <Row label="Current Year Earnings" value={data.current_year_earnings} />
                <Row label="Total Equity" value={data.total_equity} bold tone="text-violet-700" />
            </div>

            <div className="pt-3 border-t-2 border-ink-200">
                <Row label="Total Liabilities + Equity" value={data.total_liabilities_and_equity} bold />
            </div>
        </div>
    );
}

function CashFlowView({ data }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-4">
            <h3 className="text-sm font-semibold text-ink-900">
                Cash Flow — {data.from_date} to {data.to_date}
            </h3>
            <Row label="Operating activities" value={data.operating} />
            <Row label="Investing activities" value={data.investing} />
            <Row label="Financing activities" value={data.financing} />
            <div className="pt-3 border-t border-ink-200">
                <Row
                    label="Net change in cash"
                    value={data.net_change}
                    bold
                    tone={Number(data.net_change) >= 0 ? 'text-emerald-700' : 'text-rose-700'}
                />
            </div>
            <div className="text-xs text-ink-500 grid grid-cols-2 gap-2 pt-3 border-t border-ink-100">
                <div>Cash in: <span className="font-mono">{formatAmount(data.cash_in)}</span></div>
                <div>Cash out: <span className="font-mono">{formatAmount(data.cash_out)}</span></div>
            </div>
        </div>
    );
}

function DailyCollectionsView({ data }) {
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            <div className="px-4 py-3 border-b border-ink-100 flex items-center justify-between">
                <h3 className="text-sm font-semibold">
                    Daily Collections — {data.from_date} to {data.to_date}
                </h3>
                <span className="text-xs text-ink-700">Total: <span className="font-mono font-semibold">{formatAmount(data.total)}</span></span>
            </div>
            <table className="w-full text-sm">
                <thead className="bg-ink-50/60 text-ink-600">
                    <tr>
                        <th className="text-left px-4 py-2 font-medium">Date</th>
                        <th className="text-left px-4 py-2 font-medium">Code</th>
                        <th className="text-left px-4 py-2 font-medium">Account</th>
                        <th className="text-right px-4 py-2 font-medium">Amount</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                    {data.rows.length === 0 ? (
                        <tr><td colSpan={4} className="px-4 py-6 text-ink-500">No cash collections in this window.</td></tr>
                    ) : data.rows.map((r, idx) => (
                        <tr key={idx}>
                            <td className="px-4 py-1.5">{r.date}</td>
                            <td className="px-4 py-1.5 font-mono text-xs">{r.account_code}</td>
                            <td className="px-4 py-1.5">{r.account_name}</td>
                            <td className="px-4 py-1.5 text-right font-mono">{formatAmount(r.amount)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function Section({ label, rows, total, totalTone }) {
    if (!rows || rows.length === 0) {
        return (
            <div>
                <h4 className="text-xs font-semibold text-ink-600 uppercase mb-2">{label}</h4>
                <Row label={`Total ${label}`} value={total} bold tone={totalTone} />
            </div>
        );
    }
    return (
        <div>
            <h4 className="text-xs font-semibold text-ink-600 uppercase mb-2">{label}</h4>
            {rows.map(r => <Row key={r.account_id} label={`${r.code} — ${r.name}`} value={r.amount} />)}
            <Row label={`Total ${label}`} value={total} bold tone={totalTone} />
        </div>
    );
}

function Row({ label, value, bold, tone }) {
    return (
        <div className={'flex items-baseline justify-between py-1 ' + (bold ? 'border-t border-ink-100 mt-1 pt-2' : '')}>
            <span className={'text-sm ' + (bold ? 'font-semibold text-ink-900' : 'text-ink-700')}>{label}</span>
            <span className={'font-mono text-sm ' + (bold ? 'font-semibold ' : '') + (tone || 'text-ink-900')}>
                {formatAmount(value)}
            </span>
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
