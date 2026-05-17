import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    BookOpen, Coins, CalendarRange, Settings as SettingsIcon,
    Plus, X, ChevronRight, ChevronDown, CheckCircle2, RotateCcw, AlertCircle,
    Sliders, Truck, ShieldCheck, Tag, Link2,
    BarChart3, Download,
    Users as UsersIcon, Send, FileText, Wallet,
    Landmark, ArrowDownToLine, Check, Slash,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

const TABS = [
    { key: 'coa',        label: 'Chart of Accounts', icon: BookOpen },
    { key: 'journal',    label: 'Journal Entries',   icon: CalendarRange },
    { key: 'reports',    label: 'Reports',           icon: BarChart3 },
    { key: 'debtors',    label: 'Debtors',           icon: UsersIcon },
    { key: 'bank',       label: 'Bank',              icon: Landmark },
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
            {tab === 'reports'    && <ReportsTab />}
            {tab === 'debtors'    && <DebtorsTab />}
            {tab === 'bank'       && <BankTab />}
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




/* ─── Debtors (claim schedules + client deposits) ────────────────────────── */

const DEBTORS_SECTIONS = [
    { key: 'claims',   label: 'Insurance Claims', icon: FileText },
    { key: 'deposits', label: 'Client Deposits',  icon: Wallet },
];

const CLAIM_STATUS_BADGE = {
    draft:     'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    submitted: 'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
    settled:   'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    rejected:  'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
};

const DEPOSIT_STATUS_BADGE = {
    available:         'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    partially_applied: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    fully_applied:     'bg-ink-50 text-ink-600 ring-1 ring-ink-200',
    refunded:          'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
};

function DebtorsTab() {
    const [section, setSection] = useState('claims');
    return (
        <div className="grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)] gap-6">
            <aside className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-2 h-fit">
                <nav className="space-y-1">
                    {DEBTORS_SECTIONS.map(({ key, label, icon: Icon }) => (
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
                {section === 'claims'   && <ClaimsSection />}
                {section === 'deposits' && <DepositsSection />}
            </div>
        </div>
    );
}

function ClaimsSection() {
    const [items, setItems] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [selected, setSelected] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [c, p] = await Promise.all([
                apiClient.get('/accounting/debtors/claims'),
                apiClient.get('/accounting/config/insurance-providers'),
            ]);
            setItems(c.data || []);
            setProviders(p.data || []);
        } catch { toast.error('Could not load claims.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const providerName = (id) => providers.find(p => p.provider_id === id)?.name || '—';

    const submit = async (id) => {
        try {
            await apiClient.post(`/accounting/debtors/claims/${id}/submit`);
            toast.success('Claim submitted.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not submit.'); }
    };

    const settle = async (id) => {
        const amount = window.prompt('Settled amount:');
        if (!amount) return;
        const ref = window.prompt('Settlement reference (optional):') || '';
        try {
            await apiClient.post(`/accounting/debtors/claims/${id}/settle`, {
                settled_amount: Number(amount),
                settlement_reference: ref || null,
            });
            toast.success('Claim settled.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not settle.'); }
    };

    const reject = async (id) => {
        const reason = window.prompt('Rejection reason:');
        if (!reason) return;
        try {
            await apiClient.post(`/accounting/debtors/claims/${id}/reject`, { reason });
            toast.success('Claim rejected.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not reject.'); }
    };

    return (
        <div className="space-y-4">
            <SectionHeader title="Insurance Claims" subtitle="Batch invoices into claim schedules; submit to insurers; settle on payment."
                           onNew={() => setOpen(true)}
                           disabled={providers.length === 0}
                           disabledMsg="Add an insurance provider first (Configuration tab)." />

            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No claim schedules yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Number</th>
                            <th className="text-left px-4 py-2 font-medium">Provider</th>
                            <th className="text-left px-4 py-2 font-medium">Period</th>
                            <th className="text-right px-4 py-2 font-medium">Items</th>
                            <th className="text-right px-4 py-2 font-medium">Claimed</th>
                            <th className="text-right px-4 py-2 font-medium">Settled</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map(c => (
                            <tr key={c.schedule_id} className="hover:bg-ink-50/40">
                                <td className="px-4 py-2 font-mono text-xs">
                                    <button onClick={() => setSelected(c)} className="hover:underline">
                                        {c.schedule_number}
                                    </button>
                                </td>
                                <td className="px-4 py-2">{providerName(c.provider_id)}</td>
                                <td className="px-4 py-2 text-ink-600">{c.period_from} → {c.period_to}</td>
                                <td className="px-4 py-2 text-right">{c.items?.length || 0}</td>
                                <td className="px-4 py-2 text-right font-mono">{formatAmount(c.total_amount)}</td>
                                <td className="px-4 py-2 text-right font-mono">{c.settled_amount ? formatAmount(c.settled_amount) : '—'}</td>
                                <td className="px-4 py-2">
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${CLAIM_STATUS_BADGE[c.status]}`}>
                                        {c.status}
                                    </span>
                                </td>
                                <td className="px-4 py-2 text-right space-x-2">
                                    {c.status === 'draft' && (
                                        <button onClick={() => submit(c.schedule_id)}
                                                className="inline-flex items-center gap-1 text-xs text-sky-700 hover:underline">
                                            <Send size={12} /> Submit
                                        </button>
                                    )}
                                    {c.status === 'submitted' && (
                                        <>
                                            <button onClick={() => settle(c.schedule_id)}
                                                    className="text-xs text-emerald-700 hover:underline">Settle</button>
                                            <button onClick={() => reject(c.schedule_id)}
                                                    className="text-xs text-rose-700 hover:underline">Reject</button>
                                        </>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>

            {open && <ClaimModal providers={providers}
                                 onClose={() => setOpen(false)}
                                 onSaved={() => { setOpen(false); load(); }} />}
            {selected && <ClaimDetailsModal claim={selected} providerName={providerName(selected.provider_id)}
                                            onClose={() => setSelected(null)} />}
        </div>
    );
}

function ClaimModal({ providers, onClose, onSaved }) {
    const [schemes, setSchemes] = useState([]);
    const [form, setForm] = useState({
        provider_id: providers[0]?.provider_id || '',
        scheme_id: '',
        period_from: firstOfMonthISO(),
        period_to: todayISO(),
        notes: '',
    });
    const [items, setItems] = useState([{
        invoice_reference: '', patient_name: '', member_number: '', amount_claimed: '',
    }]);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!form.provider_id) { setSchemes([]); return; }
        apiClient.get(`/accounting/config/medical-schemes?provider_id=${form.provider_id}`)
            .then(r => setSchemes(r.data || []))
            .catch(() => setSchemes([]));
    }, [form.provider_id]);

    const setItem = (idx, patch) =>
        setItems(prev => prev.map((it, i) => i === idx ? { ...it, ...patch } : it));
    const addItem = () => setItems([...items, { invoice_reference: '', patient_name: '', member_number: '', amount_claimed: '' }]);
    const removeItem = (idx) => setItems(items.filter((_, i) => i !== idx));

    const total = useMemo(() =>
        items.reduce((s, it) => s + Number(it.amount_claimed || 0), 0), [items]);

    const submit = async () => {
        const cleaned = items.filter(i => Number(i.amount_claimed) > 0).map(i => ({
            invoice_reference: i.invoice_reference || null,
            patient_name: i.patient_name || null,
            member_number: i.member_number || null,
            amount_claimed: Number(i.amount_claimed),
        }));
        if (cleaned.length === 0) { toast.error('Add at least one item.'); return; }
        setSaving(true);
        try {
            await apiClient.post('/accounting/debtors/claims', {
                provider_id: Number(form.provider_id),
                scheme_id: form.scheme_id ? Number(form.scheme_id) : null,
                period_from: form.period_from,
                period_to: form.period_to,
                notes: form.notes || null,
                items: cleaned,
            });
            toast.success('Claim created (draft).');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title="New claim schedule" onClose={onClose} wide>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Provider *">
                    <select className="input" value={form.provider_id}
                            onChange={(e) => setForm({ ...form, provider_id: e.target.value, scheme_id: '' })}>
                        {providers.map(p => <option key={p.provider_id} value={p.provider_id}>{p.name}</option>)}
                    </select>
                </Field>
                <Field label="Scheme">
                    <select className="input" value={form.scheme_id}
                            onChange={(e) => setForm({ ...form, scheme_id: e.target.value })}>
                        <option value="">— any/none —</option>
                        {schemes.map(s => <option key={s.scheme_id} value={s.scheme_id}>{s.name}</option>)}
                    </select>
                </Field>
                <Field label="Period from *">
                    <input type="date" className="input" value={form.period_from}
                           onChange={(e) => setForm({ ...form, period_from: e.target.value })} />
                </Field>
                <Field label="Period to *">
                    <input type="date" className="input" value={form.period_to}
                           onChange={(e) => setForm({ ...form, period_to: e.target.value })} />
                </Field>
            </div>

            <div className="mt-4 border border-ink-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50 text-ink-600">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium">Invoice ref</th>
                            <th className="text-left px-3 py-2 font-medium">Patient</th>
                            <th className="text-left px-3 py-2 font-medium">Member #</th>
                            <th className="text-right px-3 py-2 font-medium w-32">Amount</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map((it, idx) => (
                            <tr key={idx}>
                                <td className="px-3 py-1.5"><input className="input" value={it.invoice_reference}
                                    onChange={e => setItem(idx, { invoice_reference: e.target.value })} /></td>
                                <td className="px-3 py-1.5"><input className="input" value={it.patient_name}
                                    onChange={e => setItem(idx, { patient_name: e.target.value })} /></td>
                                <td className="px-3 py-1.5"><input className="input" value={it.member_number}
                                    onChange={e => setItem(idx, { member_number: e.target.value })} /></td>
                                <td className="px-3 py-1.5"><input type="number" step="0.01" className="input text-right"
                                    value={it.amount_claimed}
                                    onChange={e => setItem(idx, { amount_claimed: e.target.value })} /></td>
                                <td className="px-2">
                                    {items.length > 1 && (
                                        <button onClick={() => removeItem(idx)} className="text-ink-400 hover:text-rose-600">
                                            <X size={14} />
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot className="bg-ink-50">
                        <tr>
                            <td colSpan={3} className="px-3 py-2">
                                <button onClick={addItem}
                                        className="text-xs text-brand-700 hover:underline inline-flex items-center gap-1">
                                    <Plus size={12} /> Add item
                                </button>
                            </td>
                            <td className="px-3 py-2 text-right font-mono font-semibold">{formatAmount(total)}</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <Field label="Notes">
                <textarea className="input min-h-[60px]" value={form.notes}
                          onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} submitLabel="Create draft" />
        </ModalShell>
    );
}

function ClaimDetailsModal({ claim, providerName, onClose }) {
    return (
        <ModalShell title={`Claim ${claim.schedule_number}`} onClose={onClose} wide>
            <div className="grid grid-cols-3 gap-3 text-sm mb-4">
                <div><div className="text-xs text-ink-500">Provider</div>{providerName}</div>
                <div><div className="text-xs text-ink-500">Period</div>{claim.period_from} → {claim.period_to}</div>
                <div><div className="text-xs text-ink-500">Status</div>
                    <span className={`text-xs px-2 py-0.5 rounded-md ${CLAIM_STATUS_BADGE[claim.status]}`}>
                        {claim.status}
                    </span>
                </div>
                <div><div className="text-xs text-ink-500">Total claimed</div><span className="font-mono">{formatAmount(claim.total_amount)}</span></div>
                {claim.settled_amount && <div><div className="text-xs text-ink-500">Settled</div><span className="font-mono">{formatAmount(claim.settled_amount)}</span></div>}
                {claim.settlement_reference && <div><div className="text-xs text-ink-500">Settlement ref</div>{claim.settlement_reference}</div>}
            </div>
            {claim.rejection_reason && (
                <div className="mb-4 p-3 bg-rose-50 text-rose-700 text-sm rounded-lg">
                    Rejected: {claim.rejection_reason}
                </div>
            )}
            <div className="border border-ink-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50 text-ink-600">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium">Invoice ref</th>
                            <th className="text-left px-3 py-2 font-medium">Patient</th>
                            <th className="text-left px-3 py-2 font-medium">Member #</th>
                            <th className="text-right px-3 py-2 font-medium">Amount</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {claim.items.map(it => (
                            <tr key={it.item_id}>
                                <td className="px-3 py-1.5">{it.invoice_reference || (it.invoice_id ? `#${it.invoice_id}` : '—')}</td>
                                <td className="px-3 py-1.5">{it.patient_name || '—'}</td>
                                <td className="px-3 py-1.5 font-mono text-xs">{it.member_number || '—'}</td>
                                <td className="px-3 py-1.5 text-right font-mono">{formatAmount(it.amount_claimed)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </ModalShell>
    );
}

function DepositsSection() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [applying, setApplying] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/debtors/deposits');
            setItems(r.data || []);
        } catch { toast.error('Could not load deposits.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    return (
        <div className="space-y-4">
            <SectionHeader title="Client Deposits" subtitle="Patient pre-payments held as a liability until applied to invoices."
                           onNew={() => setOpen(true)} />

            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No deposits yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Number</th>
                            <th className="text-left px-4 py-2 font-medium">Patient #</th>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                            <th className="text-left px-4 py-2 font-medium">Method</th>
                            <th className="text-right px-4 py-2 font-medium">Amount</th>
                            <th className="text-right px-4 py-2 font-medium">Applied</th>
                            <th className="text-right px-4 py-2 font-medium">Available</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map(d => {
                            const avail = Number(d.amount) - Number(d.amount_applied || 0);
                            return (
                                <tr key={d.deposit_id}>
                                    <td className="px-4 py-1.5 font-mono text-xs">{d.deposit_number}</td>
                                    <td className="px-4 py-1.5">{d.patient_id}</td>
                                    <td className="px-4 py-1.5">{d.deposit_date}</td>
                                    <td className="px-4 py-1.5">{d.method}</td>
                                    <td className="px-4 py-1.5 text-right font-mono">{formatAmount(d.amount)}</td>
                                    <td className="px-4 py-1.5 text-right font-mono">{formatAmount(d.amount_applied || 0)}</td>
                                    <td className="px-4 py-1.5 text-right font-mono font-semibold">{formatAmount(avail)}</td>
                                    <td className="px-4 py-1.5">
                                        <span className={`text-xs px-2 py-0.5 rounded-md ${DEPOSIT_STATUS_BADGE[d.status]}`}>
                                            {d.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-1.5 text-right">
                                        {avail > 0 && (
                                            <button onClick={() => setApplying(d)}
                                                    className="text-xs text-brand-700 hover:underline">
                                                Apply
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </DataCard>

            {open && <DepositModal onClose={() => setOpen(false)} onSaved={() => { setOpen(false); load(); }} />}
            {applying && <DepositApplyModal deposit={applying}
                                            onClose={() => setApplying(null)}
                                            onSaved={() => { setApplying(null); load(); }} />}
        </div>
    );
}

function DepositModal({ onClose, onSaved }) {
    const [form, setForm] = useState({
        patient_id: '', deposit_date: todayISO(), amount: '',
        method: 'Cash', reference: '', notes: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.patient_id || !form.amount) {
            toast.error('Patient and amount required.'); return;
        }
        setSaving(true);
        try {
            await apiClient.post('/accounting/debtors/deposits', {
                patient_id: Number(form.patient_id),
                deposit_date: form.deposit_date,
                amount: Number(form.amount),
                method: form.method,
                reference: form.reference || null,
                notes: form.notes || null,
            });
            toast.success('Deposit recorded.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title="New deposit" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Patient ID *"><input type="number" className="input" value={form.patient_id}
                    onChange={(e) => setForm({ ...form, patient_id: e.target.value })} /></Field>
                <Field label="Date"><input type="date" className="input" value={form.deposit_date}
                    onChange={(e) => setForm({ ...form, deposit_date: e.target.value })} /></Field>
                <Field label="Amount *"><input type="number" step="0.01" className="input" value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
                <Field label="Method">
                    <select className="input" value={form.method}
                            onChange={(e) => setForm({ ...form, method: e.target.value })}>
                        {['Cash', 'Bank', 'M-Pesa', 'Cheque', 'Card'].map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                </Field>
                <Field label="Reference"><input className="input" value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder="Receipt no., M-Pesa code, etc." /></Field>
            </div>
            <Field label="Notes">
                <textarea className="input min-h-[60px]" value={form.notes}
                          onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

function DepositApplyModal({ deposit, onClose, onSaved }) {
    const available = Number(deposit.amount) - Number(deposit.amount_applied || 0);
    const [form, setForm] = useState({ invoice_id: '', amount: available.toFixed(2), notes: '' });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.invoice_id || !form.amount) { toast.error('Invoice and amount required.'); return; }
        if (Number(form.amount) > available) {
            toast.error(`Max available: ${formatAmount(available)}`); return;
        }
        setSaving(true);
        try {
            await apiClient.post(`/accounting/debtors/deposits/${deposit.deposit_id}/apply`, {
                invoice_id: Number(form.invoice_id),
                amount: Number(form.amount),
                notes: form.notes || null,
            });
            toast.success('Deposit applied.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not apply.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={`Apply deposit ${deposit.deposit_number}`} onClose={onClose}>
            <p className="text-sm text-ink-600 mb-3">
                Patient #{deposit.patient_id} · Available: <span className="font-mono font-semibold">{formatAmount(available)}</span>
            </p>
            <div className="space-y-3">
                <Field label="Invoice ID *"><input type="number" className="input" value={form.invoice_id}
                    onChange={(e) => setForm({ ...form, invoice_id: e.target.value })} /></Field>
                <Field label="Amount to apply *">
                    <input type="number" step="0.01" max={available} className="input" value={form.amount}
                           onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                </Field>
                <Field label="Notes">
                    <textarea className="input min-h-[50px]" value={form.notes}
                              onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} submitLabel="Apply" />
        </ModalShell>
    );
}




/* ─── Bank ───────────────────────────────────────────────────────────────── */

const BANK_SECTIONS = [
    { key: 'accounts',     label: 'Bank Accounts',  icon: Landmark },
    { key: 'transactions', label: 'Transactions',   icon: ArrowDownToLine },
    { key: 'reconcile',    label: 'Reconciliation', icon: Check },
];

const RECON_BADGE = {
    unreconciled: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    matched:      'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    ignored:      'bg-ink-50 text-ink-500 ring-1 ring-ink-200',
};

function BankTab() {
    const [section, setSection] = useState('accounts');
    return (
        <div className="grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)] gap-6">
            <aside className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-2 h-fit">
                <nav className="space-y-1">
                    {BANK_SECTIONS.map(({ key, label, icon: Icon }) => (
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
                {section === 'accounts'     && <BankAccountsSection />}
                {section === 'transactions' && <BankTransactionsSection />}
                {section === 'reconcile'    && <ReconciliationSection />}
            </div>
        </div>
    );
}

function BankAccountsSection() {
    const [items, setItems] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const [b, a] = await Promise.all([
                apiClient.get('/accounting/bank/accounts?include_inactive=true'),
                apiClient.get('/accounting/accounts?account_type=Asset&include_inactive=false'),
            ]);
            setItems(b.data || []);
            setAccounts((a.data || []).filter(x => x.is_postable));
        } catch { toast.error('Could not load bank accounts.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const accountName = (id) => {
        const a = accounts.find(x => x.account_id === id);
        return a ? `${a.code} ${a.name}` : '—';
    };

    return (
        <div className="space-y-4">
            <SectionHeader title="Bank Accounts" subtitle="Bank accounts linked to GL asset accounts for reconciliation."
                           onNew={() => { setEditing(null); setOpen(true); }} />
            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No bank accounts yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Name</th>
                            <th className="text-left px-4 py-2 font-medium">Bank</th>
                            <th className="text-left px-4 py-2 font-medium">Account #</th>
                            <th className="text-left px-4 py-2 font-medium">Currency</th>
                            <th className="text-left px-4 py-2 font-medium">GL link</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map(b => (
                            <tr key={b.bank_account_id}>
                                <td className="px-4 py-1.5 font-medium">{b.name}</td>
                                <td className="px-4 py-1.5">{b.bank_name}{b.branch ? ` · ${b.branch}` : ''}</td>
                                <td className="px-4 py-1.5 font-mono text-xs">{b.account_number}</td>
                                <td className="px-4 py-1.5">{b.currency_code}</td>
                                <td className="px-4 py-1.5 text-ink-600">{accountName(b.gl_account_id)}</td>
                                <td className="px-4 py-1.5">
                                    <span className={'text-xs ' + (b.is_active ? 'text-emerald-700' : 'text-ink-400')}>
                                        {b.is_active ? 'active' : 'inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-1.5 text-right">
                                    <button onClick={() => { setEditing(b); setOpen(true); }}
                                            className="text-xs text-brand-700 hover:underline">Edit</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>
            {open && <BankAccountModal initial={editing} accounts={accounts}
                                       onClose={() => setOpen(false)}
                                       onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function BankAccountModal({ initial, accounts, onClose, onSaved }) {
    const isEdit = !!initial;
    const [form, setForm] = useState(initial || {
        name: '', bank_name: '', branch: '', account_number: '', swift_code: '',
        currency_code: 'KES', gl_account_id: '', opening_balance: 0, notes: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.name || !form.bank_name || !form.account_number) {
            toast.error('Name, bank, and account number are required.'); return;
        }
        setSaving(true);
        try {
            const payload = { ...form,
                gl_account_id: form.gl_account_id || null,
                opening_balance: Number(form.opening_balance || 0),
            };
            if (isEdit) await apiClient.patch(`/accounting/bank/accounts/${initial.bank_account_id}`, payload);
            else await apiClient.post('/accounting/bank/accounts', payload);
            toast.success(isEdit ? 'Account updated.' : 'Account created.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={isEdit ? 'Edit bank account' : 'New bank account'} onClose={onClose} wide>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Name *"><input className="input" value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Main Operations" /></Field>
                <Field label="Bank *"><input className="input" value={form.bank_name}
                    onChange={(e) => setForm({ ...form, bank_name: e.target.value })} placeholder="e.g. Equity Bank" /></Field>
                <Field label="Branch"><input className="input" value={form.branch || ''}
                    onChange={(e) => setForm({ ...form, branch: e.target.value })} /></Field>
                <Field label="Account number *"><input className="input" value={form.account_number}
                    onChange={(e) => setForm({ ...form, account_number: e.target.value })} /></Field>
                <Field label="SWIFT"><input className="input" value={form.swift_code || ''}
                    onChange={(e) => setForm({ ...form, swift_code: e.target.value })} /></Field>
                <Field label="Currency"><input className="input" maxLength={3} value={form.currency_code}
                    onChange={(e) => setForm({ ...form, currency_code: e.target.value.toUpperCase() })} /></Field>
                <Field label="GL account">
                    <select className="input" value={form.gl_account_id || ''}
                            onChange={(e) => setForm({ ...form, gl_account_id: e.target.value })}>
                        <option value="">— pick an Asset account —</option>
                        {accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.code} — {a.name}</option>)}
                    </select>
                </Field>
                <Field label="Opening balance"><input type="number" step="0.01" className="input"
                    value={form.opening_balance}
                    onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} /></Field>
            </div>
            <Field label="Notes">
                <textarea className="input min-h-[50px]" value={form.notes || ''}
                          onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

function BankTransactionsSection() {
    const [items, setItems] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [filter, setFilter] = useState({ account_id: '', status: '' });
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [a] = await Promise.all([
                apiClient.get('/accounting/bank/accounts'),
            ]);
            setAccounts(a.data || []);
            const params = {};
            if (filter.account_id) params.bank_account_id = filter.account_id;
            if (filter.status) params.status = filter.status;
            const t = await apiClient.get('/accounting/bank/transactions', { params });
            setItems(t.data || []);
        } catch { toast.error('Could not load transactions.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [filter]);

    const accountName = (id) => accounts.find(a => a.bank_account_id === id)?.name || '—';

    return (
        <div className="space-y-4">
            <SectionHeader title="Bank Transactions" subtitle="Statement lines imported or keyed in manually."
                           onNew={() => setOpen(true)}
                           disabled={accounts.length === 0}
                           disabledMsg="Add a bank account first." />

            <div className="flex flex-wrap items-center gap-3">
                <select className="input max-w-xs" value={filter.account_id}
                        onChange={(e) => setFilter({ ...filter, account_id: e.target.value })}>
                    <option value="">All accounts</option>
                    {accounts.map(a => <option key={a.bank_account_id} value={a.bank_account_id}>{a.name}</option>)}
                </select>
                <select className="input max-w-xs" value={filter.status}
                        onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
                    <option value="">All statuses</option>
                    <option value="unreconciled">Unreconciled</option>
                    <option value="matched">Matched</option>
                    <option value="ignored">Ignored</option>
                </select>
            </div>

            <DataCard loading={loading} empty={items.length === 0} emptyMsg="No transactions.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                            <th className="text-left px-4 py-2 font-medium">Account</th>
                            <th className="text-left px-4 py-2 font-medium">Description</th>
                            <th className="text-left px-4 py-2 font-medium">Reference</th>
                            <th className="text-right px-4 py-2 font-medium">Amount</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map(t => (
                            <tr key={t.bank_transaction_id}>
                                <td className="px-4 py-1.5">{t.transaction_date}</td>
                                <td className="px-4 py-1.5">{accountName(t.bank_account_id)}</td>
                                <td className="px-4 py-1.5 text-ink-700">{t.description}</td>
                                <td className="px-4 py-1.5 font-mono text-xs">{t.reference || '—'}</td>
                                <td className={'px-4 py-1.5 text-right font-mono ' +
                                    (Number(t.amount) >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                                    {Number(t.amount) >= 0 ? '+' : ''}{formatAmount(t.amount)}
                                </td>
                                <td className="px-4 py-1.5">
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${RECON_BADGE[t.reconciliation_status]}`}>
                                        {t.reconciliation_status}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>

            {open && <BankTxModal accounts={accounts} onClose={() => setOpen(false)}
                                  onSaved={() => { setOpen(false); load(); }} />}
        </div>
    );
}

function BankTxModal({ accounts, onClose, onSaved }) {
    const [form, setForm] = useState({
        bank_account_id: accounts[0]?.bank_account_id || '',
        transaction_date: todayISO(),
        description: '',
        amount: '',
        running_balance: '',
        reference: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.bank_account_id || !form.description || !form.amount) {
            toast.error('Account, description, and amount are required.'); return;
        }
        setSaving(true);
        try {
            await apiClient.post('/accounting/bank/transactions', {
                bank_account_id: Number(form.bank_account_id),
                transaction_date: form.transaction_date,
                description: form.description,
                amount: Number(form.amount),
                running_balance: form.running_balance ? Number(form.running_balance) : null,
                reference: form.reference || null,
            });
            toast.success('Transaction added.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title="New bank transaction" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Bank account *">
                    <select className="input" value={form.bank_account_id}
                            onChange={(e) => setForm({ ...form, bank_account_id: e.target.value })}>
                        {accounts.map(a => <option key={a.bank_account_id} value={a.bank_account_id}>{a.name}</option>)}
                    </select>
                </Field>
                <Field label="Date *"><input type="date" className="input" value={form.transaction_date}
                    onChange={(e) => setForm({ ...form, transaction_date: e.target.value })} /></Field>
                <Field label="Description *">
                    <input className="input" value={form.description}
                           onChange={(e) => setForm({ ...form, description: e.target.value })} />
                </Field>
                <Field label="Reference">
                    <input className="input" value={form.reference}
                           onChange={(e) => setForm({ ...form, reference: e.target.value })} />
                </Field>
                <Field label="Amount * (signed: + in / − out)"><input type="number" step="0.01" className="input"
                    value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
                <Field label="Running balance"><input type="number" step="0.01" className="input"
                    value={form.running_balance}
                    onChange={(e) => setForm({ ...form, running_balance: e.target.value })} /></Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} />
        </ModalShell>
    );
}

function ReconciliationSection() {
    const [accounts, setAccounts] = useState([]);
    const [selected, setSelected] = useState('');
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [matching, setMatching] = useState(null);

    const loadAccounts = async () => {
        try {
            const r = await apiClient.get('/accounting/bank/accounts');
            setAccounts(r.data || []);
            if ((r.data || []).length > 0 && !selected) setSelected(r.data[0].bank_account_id);
        } catch { toast.error('Could not load accounts.'); }
    };
    useEffect(() => { loadAccounts(); }, []);

    const loadItems = async () => {
        if (!selected) return;
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/bank/transactions', {
                params: { bank_account_id: selected, status: 'unreconciled' },
            });
            setItems(r.data || []);
        } catch { toast.error('Could not load transactions.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { loadItems(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [selected]);

    const ignore = async (id) => {
        const reason = window.prompt('Ignore reason:');
        if (!reason) return;
        try {
            await apiClient.post(`/accounting/bank/transactions/${id}/ignore`, { reason });
            toast.success('Marked ignored.');
            loadItems();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not ignore.'); }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-end justify-between">
                <div>
                    <h3 className="text-lg font-semibold text-ink-900">Reconciliation</h3>
                    <p className="text-sm text-ink-600 mt-1">Match unreconciled bank lines to journal entries.</p>
                </div>
                <Field label="Account">
                    <select className="input min-w-[200px]" value={selected}
                            onChange={(e) => setSelected(e.target.value)}>
                        <option value="">—</option>
                        {accounts.map(a => <option key={a.bank_account_id} value={a.bank_account_id}>{a.name}</option>)}
                    </select>
                </Field>
            </div>

            <DataCard loading={loading} empty={items.length === 0}
                      emptyMsg={selected ? 'Nothing left to reconcile here.' : 'Pick an account above.'}>
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                            <th className="text-left px-4 py-2 font-medium">Description</th>
                            <th className="text-left px-4 py-2 font-medium">Reference</th>
                            <th className="text-right px-4 py-2 font-medium">Amount</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {items.map(t => (
                            <tr key={t.bank_transaction_id}>
                                <td className="px-4 py-1.5">{t.transaction_date}</td>
                                <td className="px-4 py-1.5">{t.description}</td>
                                <td className="px-4 py-1.5 font-mono text-xs">{t.reference || '—'}</td>
                                <td className={'px-4 py-1.5 text-right font-mono ' +
                                    (Number(t.amount) >= 0 ? 'text-emerald-700' : 'text-rose-700')}>
                                    {Number(t.amount) >= 0 ? '+' : ''}{formatAmount(t.amount)}
                                </td>
                                <td className="px-4 py-1.5 text-right space-x-2">
                                    <button onClick={() => setMatching(t)}
                                            className="text-xs text-emerald-700 hover:underline inline-flex items-center gap-1">
                                        <Check size={12} /> Match
                                    </button>
                                    <button onClick={() => ignore(t.bank_transaction_id)}
                                            className="text-xs text-ink-500 hover:underline inline-flex items-center gap-1">
                                        <Slash size={12} /> Ignore
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>

            {matching && <MatchModal tx={matching}
                                     onClose={() => setMatching(null)}
                                     onSaved={() => { setMatching(null); loadItems(); }} />}
        </div>
    );
}

function MatchModal({ tx, onClose, onSaved }) {
    const [candidates, setCandidates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get(`/accounting/bank/transactions/${tx.bank_transaction_id}/candidates`);
            setCandidates(r.data || []);
        } catch { toast.error('Could not load candidates.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

    const match = async (line_id) => {
        setSaving(true);
        try {
            await apiClient.post(`/accounting/bank/transactions/${tx.bank_transaction_id}/match`, {
                journal_line_id: line_id,
            });
            toast.success('Matched.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not match.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title="Match bank transaction" onClose={onClose} wide>
            <div className="text-sm text-ink-600 mb-3">
                {tx.transaction_date} · {tx.description} · <span className="font-mono">{formatAmount(tx.amount)}</span>
            </div>
            {loading ? (
                <div className="p-6 text-sm text-ink-500">Searching for candidates...</div>
            ) : candidates.length === 0 ? (
                <div className="p-6 text-sm text-ink-500">
                    No matching journal lines found within ±7 days at the same amount.
                </div>
            ) : (
                <div className="border border-ink-200 rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-ink-50 text-ink-600">
                            <tr>
                                <th className="text-left px-3 py-2 font-medium">Entry</th>
                                <th className="text-left px-3 py-2 font-medium">Date</th>
                                <th className="text-right px-3 py-2 font-medium">Debit</th>
                                <th className="text-right px-3 py-2 font-medium">Credit</th>
                                <th className="text-left px-3 py-2 font-medium">Memo</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100">
                            {candidates.map(c => (
                                <tr key={c.line_id}>
                                    <td className="px-3 py-1.5 font-mono text-xs">{c.entry_number}</td>
                                    <td className="px-3 py-1.5">{c.entry_date}</td>
                                    <td className="px-3 py-1.5 text-right font-mono">{formatAmount(c.debit)}</td>
                                    <td className="px-3 py-1.5 text-right font-mono">{formatAmount(c.credit)}</td>
                                    <td className="px-3 py-1.5 text-ink-600">{c.memo || c.description || '—'}</td>
                                    <td className="px-3 py-1.5 text-right">
                                        <button onClick={() => match(c.line_id)} disabled={saving}
                                                className="text-xs text-emerald-700 hover:underline">
                                            Match
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <div className="flex justify-end pt-4">
                <button onClick={onClose} className="px-3 py-2 rounded-lg border border-ink-200 text-sm hover:bg-ink-50">Close</button>
            </div>
        </ModalShell>
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
