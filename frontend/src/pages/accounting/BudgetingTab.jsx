/* Budgeting — create budgets, edit per-account/period amounts on a grid,
 * and compare against posted actuals. Backed by /api/accounting/budgets. */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { Target, BarChart3, Pencil } from 'lucide-react';
import {
    SectionHeader, DataCard, ModalShell, ModalActions, Field, formatAmount,
} from './ui';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const BUDGET_STATUS_BADGE = {
    draft:    'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    active:   'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    archived: 'bg-ink-50 text-ink-500 ring-1 ring-ink-200',
};

export default function BudgetingTab() {
    const [budgets, setBudgets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openNew, setOpenNew] = useState(false);
    const [selectedId, setSelectedId] = useState(null);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/accounting/budgets');
            setBudgets(r.data || []);
        } catch { toast.error('Could not load budgets.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    if (selectedId) {
        return <BudgetDetail budgetId={selectedId} onBack={() => { setSelectedId(null); load(); }} />;
    }

    return (
        <div className="space-y-4">
            <SectionHeader title="Budgets"
                           subtitle="Plan revenue and expense by account and month, then track against actuals."
                           onNew={() => setOpenNew(true)} />
            <DataCard loading={loading} empty={budgets.length === 0} emptyMsg="No budgets yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Name</th>
                            <th className="text-left px-4 py-2 font-medium">Fiscal year</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th className="text-left px-4 py-2 font-medium">Notes</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {budgets.map(b => (
                            <tr key={b.budget_id} className="hover:bg-ink-50/40">
                                <td className="px-4 py-2 font-medium">
                                    <button onClick={() => setSelectedId(b.budget_id)} className="hover:underline">
                                        {b.name}
                                    </button>
                                </td>
                                <td className="px-4 py-2">{b.fiscal_year}</td>
                                <td className="px-4 py-2">
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${BUDGET_STATUS_BADGE[b.status]}`}>
                                        {b.status}
                                    </span>
                                </td>
                                <td className="px-4 py-2 text-ink-500 truncate max-w-xs">{b.notes || '—'}</td>
                                <td className="px-4 py-2 text-right">
                                    <button onClick={() => setSelectedId(b.budget_id)}
                                            className="inline-flex items-center gap-1 text-xs text-brand-700 hover:underline">
                                        <Pencil size={12} /> Open
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>

            {openNew && <BudgetModal onClose={() => setOpenNew(false)}
                                     onSaved={(id) => { setOpenNew(false); load(); setSelectedId(id); }} />}
        </div>
    );
}

function BudgetModal({ onClose, onSaved }) {
    const [form, setForm] = useState({
        name: '', fiscal_year: new Date().getFullYear(), notes: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.name.trim()) { toast.error('Name is required.'); return; }
        setSaving(true);
        try {
            const r = await apiClient.post('/accounting/budgets', {
                name: form.name.trim(),
                fiscal_year: Number(form.fiscal_year),
                notes: form.notes || null,
            });
            toast.success('Budget created.');
            onSaved(r.data.budget_id);
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not create budget.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title="New budget" onClose={onClose}>
            <div className="space-y-3">
                <Field label="Name *">
                    <input className="input" value={form.name}
                           onChange={(e) => setForm({ ...form, name: e.target.value })}
                           placeholder="e.g. Operating Budget 2026" />
                </Field>
                <Field label="Fiscal year *">
                    <input type="number" className="input" value={form.fiscal_year}
                           onChange={(e) => setForm({ ...form, fiscal_year: e.target.value })} />
                </Field>
                <Field label="Notes">
                    <textarea className="input min-h-[60px]" value={form.notes}
                              onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} submitLabel="Create" />
        </ModalShell>
    );
}

function BudgetDetail({ budgetId, onBack }) {
    const [view, setView] = useState('plan'); // plan | actual
    const [budget, setBudget] = useState(null);
    const [accounts, setAccounts] = useState([]);
    const [periods, setPeriods] = useState([]);
    const [loading, setLoading] = useState(true);

    const load = async () => {
        setLoading(true);
        try {
            const b = await apiClient.get(`/accounting/budgets/${budgetId}`);
            setBudget(b.data);
            const [acc, per] = await Promise.all([
                apiClient.get('/accounting/accounts?include_inactive=false'),
                apiClient.get(`/accounting/fiscal-periods?year=${b.data.fiscal_year}`),
            ]);
            setAccounts((acc.data || []).filter(a => a.is_postable));
            setPeriods((per.data || []).sort((x, y) => x.month - y.month));
        } catch { toast.error('Could not load budget.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, [budgetId]);

    const seedYear = async () => {
        try {
            await apiClient.post('/accounting/fiscal-periods/seed-year', { year: budget.fiscal_year });
            toast.success('Fiscal year periods created.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not seed periods.'); }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div>
                    <button onClick={onBack} className="text-xs text-brand-700 hover:underline">← All budgets</button>
                    <h3 className="text-lg font-semibold text-ink-900 mt-1">
                        {budget?.name} <span className="text-ink-400 font-normal">· {budget?.fiscal_year}</span>
                    </h3>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setView('plan')}
                            className={'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium ' +
                                (view === 'plan' ? 'bg-brand-600 text-white' : 'border border-ink-200 text-ink-600 hover:bg-ink-50')}>
                        <Target size={14} /> Plan
                    </button>
                    <button onClick={() => setView('actual')}
                            className={'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium ' +
                                (view === 'actual' ? 'bg-brand-600 text-white' : 'border border-ink-200 text-ink-600 hover:bg-ink-50')}>
                        <BarChart3 size={14} /> Budget vs Actual
                    </button>
                </div>
            </div>

            {loading ? (
                <div className="p-6 text-sm text-ink-500">Loading...</div>
            ) : periods.length === 0 ? (
                <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 text-sm text-ink-600">
                    No fiscal periods exist for {budget.fiscal_year} yet.
                    <button onClick={seedYear} className="ml-2 text-brand-700 hover:underline font-medium">
                        Create the 12 monthly periods
                    </button>
                </div>
            ) : view === 'plan' ? (
                <BudgetGrid budget={budget} accounts={accounts} periods={periods} />
            ) : (
                <VsActualView budgetId={budgetId} periods={periods} />
            )}
        </div>
    );
}

function BudgetGrid({ budget, accounts, periods }) {
    // values keyed `${account_id}:${period_id}` → string amount.
    const [values, setValues] = useState({});
    const dirty = useRef(new Set());
    const timer = useRef(null);
    const [savedAt, setSavedAt] = useState(null);

    useEffect(() => {
        const v = {};
        for (const l of budget.lines || []) v[`${l.account_id}:${l.period_id}`] = String(l.amount);
        setValues(v);
    }, [budget]);

    const flush = async () => {
        if (dirty.current.size === 0) return;
        const lines = [];
        for (const key of dirty.current) {
            const [aid, pid] = key.split(':').map(Number);
            const raw = values[key];
            const amount = raw === '' || raw == null ? 0 : Number(raw);
            if (Number.isNaN(amount) || amount < 0) continue;
            lines.push({ account_id: aid, period_id: pid, amount });
        }
        dirty.current = new Set();
        if (lines.length === 0) return;
        try {
            await apiClient.put(`/accounting/budgets/${budget.budget_id}/lines`, { lines });
            setSavedAt(new Date());
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save lines.'); }
    };

    const onCellChange = (aid, pid, val) => {
        const key = `${aid}:${pid}`;
        setValues(prev => ({ ...prev, [key]: val }));
        dirty.current.add(key);
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(flush, 800);
    };

    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

    const rowTotal = (aid) =>
        periods.reduce((s, p) => s + Number(values[`${aid}:${p.period_id}`] || 0), 0);
    const colTotal = (pid) =>
        accounts.reduce((s, a) => s + Number(values[`${a.account_id}:${pid}`] || 0), 0);
    const grandTotal = accounts.reduce((s, a) => s + rowTotal(a.account_id), 0);

    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-ink-100 text-xs text-ink-500">
                <span>Edit any cell — changes save automatically.</span>
                {savedAt && <span className="text-emerald-600">Saved {savedAt.toLocaleTimeString()}</span>}
            </div>
            <div className="overflow-x-auto">
                <table className="text-sm border-collapse">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium sticky left-0 bg-ink-50/60 z-10 min-w-[220px]">Account</th>
                            {periods.map(p => (
                                <th key={p.period_id} className="text-right px-2 py-2 font-medium min-w-[90px]">
                                    {MONTHS[p.month - 1]}
                                </th>
                            ))}
                            <th className="text-right px-3 py-2 font-medium min-w-[110px]">Total</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {accounts.map(a => (
                            <tr key={a.account_id} className="hover:bg-ink-50/30">
                                <td className="px-3 py-1.5 sticky left-0 bg-white z-10">
                                    <span className="font-mono text-xs text-ink-500">{a.code}</span>{' '}
                                    {a.name}
                                </td>
                                {periods.map(p => {
                                    const key = `${a.account_id}:${p.period_id}`;
                                    return (
                                        <td key={p.period_id} className="px-1 py-1">
                                            <input type="number" step="0.01" min="0"
                                                   className="input text-right py-1 px-2 w-[90px]"
                                                   value={values[key] ?? ''}
                                                   onChange={(e) => onCellChange(a.account_id, p.period_id, e.target.value)} />
                                        </td>
                                    );
                                })}
                                <td className="px-3 py-1.5 text-right font-mono font-medium">{formatAmount(rowTotal(a.account_id))}</td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot className="bg-ink-50 font-medium">
                        <tr>
                            <td className="px-3 py-2 sticky left-0 bg-ink-50 z-10">Total</td>
                            {periods.map(p => (
                                <td key={p.period_id} className="px-2 py-2 text-right font-mono">{formatAmount(colTotal(p.period_id))}</td>
                            ))}
                            <td className="px-3 py-2 text-right font-mono">{formatAmount(grandTotal)}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}

function VsActualView({ budgetId, periods }) {
    const [periodId, setPeriodId] = useState('');
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const load = async () => {
        setLoading(true);
        try {
            const qs = periodId ? `?period_id=${periodId}` : '';
            const r = await apiClient.get(`/accounting/budgets/${budgetId}/vs-actual${qs}`);
            setData(r.data);
        } catch { toast.error('Could not load comparison.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, [budgetId, periodId]);

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2">
                <span className="text-sm text-ink-600">Period:</span>
                <select className="input w-48" value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
                    <option value="">Full year</option>
                    {periods.map(p => (
                        <option key={p.period_id} value={p.period_id}>{MONTHS[p.month - 1]} {p.year}</option>
                    ))}
                </select>
            </div>

            <DataCard loading={loading} empty={!data || (data.rows || []).length === 0}
                      emptyMsg="No budget lines to compare yet.">
                {data && (
                    <table className="w-full text-sm">
                        <thead className="bg-ink-50/60 text-ink-600">
                            <tr>
                                <th className="text-left px-4 py-2 font-medium">Account</th>
                                <th className="text-right px-4 py-2 font-medium">Budget</th>
                                <th className="text-right px-4 py-2 font-medium">Actual</th>
                                <th className="text-right px-4 py-2 font-medium">Variance</th>
                                <th className="text-right px-4 py-2 font-medium">%</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100">
                            {data.rows.map(r => (
                                <tr key={r.account_id} className="hover:bg-ink-50/40">
                                    <td className="px-4 py-2">
                                        <span className="font-mono text-xs text-ink-500">{r.code}</span> {r.name}
                                    </td>
                                    <td className="px-4 py-2 text-right font-mono">{formatAmount(r.budget)}</td>
                                    <td className="px-4 py-2 text-right font-mono">{formatAmount(r.actual)}</td>
                                    <td className={'px-4 py-2 text-right font-mono ' +
                                        (Number(r.variance) < 0 ? 'text-rose-600' : 'text-emerald-700')}>
                                        {formatAmount(r.variance)}
                                    </td>
                                    <td className="px-4 py-2 text-right text-ink-500">
                                        {r.variance_pct == null ? '—' : `${Number(r.variance_pct).toFixed(1)}%`}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot className="bg-ink-50 font-semibold">
                            <tr>
                                <td className="px-4 py-2">Total</td>
                                <td className="px-4 py-2 text-right font-mono">{formatAmount(data.totals.budget)}</td>
                                <td className="px-4 py-2 text-right font-mono">{formatAmount(data.totals.actual)}</td>
                                <td className={'px-4 py-2 text-right font-mono ' +
                                    (Number(data.totals.variance) < 0 ? 'text-rose-600' : 'text-emerald-700')}>
                                    {formatAmount(data.totals.variance)}
                                </td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                )}
            </DataCard>
        </div>
    );
}
