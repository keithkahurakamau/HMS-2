import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Wallet, Search, Plus, X, Save, Activity, CheckCircle2, AlertCircle,
    Filter, Banknote, TrendingUp, Calendar, Building2, RefreshCw,
    ArrowDownCircle, XCircle, Eye,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Cheque Register                                                           */
/*                                                                            */
/*  Lifecycle: Received → Deposited → Cleared (posts Payment) | Bounced       */
/*             Cancelled (any non-terminal state)                              */
/* ────────────────────────────────────────────────────────────────────────── */

const STATUS_META = {
    Received:  { label: 'Received',  badge: 'badge-info',    accent: 'bg-blue-500/10 ring-blue-500/20 text-blue-600',     icon: Wallet },
    Deposited: { label: 'Deposited', badge: 'badge-warn',    accent: 'bg-amber-500/10 ring-amber-500/20 text-amber-600',  icon: ArrowDownCircle },
    Cleared:   { label: 'Cleared',   badge: 'badge-success', accent: 'bg-emerald-500/10 ring-emerald-500/20 text-emerald-600', icon: CheckCircle2 },
    Bounced:   { label: 'Bounced',   badge: 'badge-danger',  accent: 'bg-rose-500/10 ring-rose-500/20 text-rose-600',     icon: AlertCircle },
    Cancelled: { label: 'Cancelled', badge: 'badge-neutral', accent: 'bg-ink-200 text-ink-600',                            icon: XCircle },
};

const DRAWER_TYPES = ['Insurance', 'Employer', 'Patient', 'Government', 'Other'];

const EMPTY_CHEQUE = {
    cheque_number: '', drawer_name: '', drawer_type: 'Insurance',
    bank_name: '', bank_branch: '', amount: '', currency: 'KES',
    date_on_cheque: '', invoice_id: '', patient_id: '', notes: '',
};

export default function Cheques() {
    const [cheques, setCheques] = useState([]);
    const [summary, setSummary] = useState({});
    const [isLoading, setIsLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [drawerFilter, setDrawerFilter] = useState('');

    // Modal state
    const [isNewOpen, setIsNewOpen] = useState(false);
    const [newDraft, setNewDraft] = useState(EMPTY_CHEQUE);
    const [submitting, setSubmitting] = useState(false);

    // Detail drawer
    const [active, setActive] = useState(null);
    const [actionPanel, setActionPanel] = useState(null); // 'deposit' | 'clear' | 'bounce' | 'cancel'
    const [actionDraft, setActionDraft] = useState({});

    useEffect(() => { fetchAll(); }, []);
    useEffect(() => {
        const t = setTimeout(fetchAll, 300);
        return () => clearTimeout(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [search, statusFilter, drawerFilter]);

    const fetchAll = async () => {
        setIsLoading(true);
        try {
            const params = new URLSearchParams();
            if (search) params.set('search', search);
            if (statusFilter) params.set('status', statusFilter);
            if (drawerFilter) params.set('drawer_type', drawerFilter);
            const [listRes, sumRes] = await Promise.all([
                apiClient.get(`/cheques/?${params.toString()}`),
                apiClient.get('/cheques/summary'),
            ]);
            setCheques(listRes.data || []);
            setSummary(sumRes.data || {});
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load cheque register.');
        } finally {
            setIsLoading(false);
        }
    };

    /* ─── Create ─── */

    const submitNew = async (e) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            const body = {
                ...newDraft,
                amount: parseFloat(newDraft.amount) || 0,
                date_on_cheque: newDraft.date_on_cheque || null,
                invoice_id: newDraft.invoice_id ? parseInt(newDraft.invoice_id) : null,
                patient_id: newDraft.patient_id ? parseInt(newDraft.patient_id) : null,
            };
            await apiClient.post('/cheques/', body);
            toast.success('Cheque recorded.');
            setIsNewOpen(false);
            setNewDraft(EMPTY_CHEQUE);
            fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not record cheque.');
        } finally {
            setSubmitting(false);
        }
    };

    /* ─── State transitions ─── */

    const openAction = (cheque, action) => {
        setActive(cheque);
        setActionPanel(action);
        setActionDraft(
            action === 'deposit'
                ? { deposit_account: '', deposit_date: new Date().toISOString().slice(0, 10) }
                : action === 'clear'
                    ? { clearance_date: new Date().toISOString().slice(0, 10) }
                    : { reason: '' }
        );
    };

    const submitAction = async () => {
        if (!active || !actionPanel) return;
        try {
            let payload = {};
            if (actionPanel === 'deposit') {
                if (!actionDraft.deposit_account) return toast.error('Deposit account is required.');
                payload = {
                    deposit_account: actionDraft.deposit_account,
                    deposit_date: actionDraft.deposit_date ? new Date(actionDraft.deposit_date).toISOString() : null,
                };
            } else if (actionPanel === 'clear') {
                payload = { clearance_date: actionDraft.clearance_date ? new Date(actionDraft.clearance_date).toISOString() : null };
            } else if (actionPanel === 'bounce' || actionPanel === 'cancel') {
                if (!actionDraft.reason?.trim()) return toast.error('A reason is required.');
                payload = { reason: actionDraft.reason };
            }

            const res = await apiClient.post(`/cheques/${active.cheque_id}/${actionPanel}`, payload);
            toast.success(`Cheque ${actionPanel}ed.`);
            setActive(res.data);
            setActionPanel(null);
            fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || `Could not ${actionPanel} cheque.`);
        }
    };

    /* ─── Derived ─── */

    const kpiTiles = useMemo(() => ([
        { key: 'Received',  label: 'Received',  icon: Wallet,         accent: 'blue'    },
        { key: 'Deposited', label: 'In transit',icon: ArrowDownCircle, accent: 'amber'   },
        { key: 'Cleared',   label: 'Cleared',   icon: CheckCircle2,    accent: 'emerald' },
        { key: 'Bounced',   label: 'Bounced',   icon: AlertCircle,     accent: 'rose'    },
    ]), []);

    return (
        <div className="space-y-6 animate-fade-in">
            <PageHeader
                eyebrow="Finance"
                icon={Banknote}
                title="Cheque Register"
                subtitle="Track every cheque from receipt through clearance — including bounces."
                actions={
                    <>
                        <button onClick={fetchAll} className="btn-secondary cursor-pointer"><RefreshCw size={15} /> Refresh</button>
                        <button onClick={() => setIsNewOpen(true)} className="btn-primary cursor-pointer"><Plus size={15} /> Record cheque</button>
                    </>
                }
            />

            {/* KPIs */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {kpiTiles.map((tile) => {
                    const s = summary[tile.key] || { count: 0, total: 0 };
                    const ring = {
                        blue:    'bg-blue-50    ring-blue-200    text-blue-700',
                        amber:   'bg-amber-50   ring-amber-200   text-amber-700',
                        emerald: 'bg-emerald-50 ring-emerald-200 text-emerald-700',
                        rose:    'bg-rose-50    ring-rose-200    text-rose-700',
                    }[tile.accent];
                    const TileIcon = tile.icon;
                    return (
                        <div key={tile.key} className={`card p-4 ring-1 ${ring}`}>
                            <div className="flex justify-between items-start">
                                <div>
                                    <p className="text-2xs font-semibold uppercase tracking-[0.14em] opacity-80">{tile.label}</p>
                                    <p className="text-2xl font-semibold mt-1">{s.count}</p>
                                    <p className="text-xs font-mono mt-0.5 opacity-80">KES {Number(s.total).toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
                                </div>
                                <TileIcon size={20} className="opacity-60" />
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Filters */}
            <div className="card p-3 flex flex-wrap gap-3 items-center">
                <div className="relative flex-1 min-w-[16rem]">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                    <input type="text" placeholder="Cheque #, drawer, bank…"
                           value={search} onChange={e => setSearch(e.target.value)}
                           className="input pl-9" />
                </div>
                <div className="relative">
                    <Filter size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                    <select className="input pl-9 pr-8" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                        <option value="">All statuses</option>
                        {Object.keys(STATUS_META).map(s => <option key={s}>{s}</option>)}
                    </select>
                </div>
                <div className="relative">
                    <Building2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                    <select className="input pl-9 pr-8" value={drawerFilter} onChange={e => setDrawerFilter(e.target.value)}>
                        <option value="">All drawers</option>
                        {DRAWER_TYPES.map(d => <option key={d}>{d}</option>)}
                    </select>
                </div>
                <span className="ml-auto text-xs text-ink-500">{cheques.length} cheque{cheques.length === 1 ? '' : 's'}</span>
            </div>

            {/* Table */}
            <div className="card overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="table-clean min-w-[900px]">
                        <thead>
                            <tr>
                                <th>Cheque #</th>
                                <th>Drawer</th>
                                <th>Bank</th>
                                <th>Amount</th>
                                <th>Date received</th>
                                <th>Status</th>
                                <th className="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan="7" className="text-center py-10 text-ink-400">
                                    <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={20} /> Loading…
                                </td></tr>
                            ) : cheques.length === 0 ? (
                                <tr><td colSpan="7" className="text-center py-10 text-ink-500">No cheques match the current filters.</td></tr>
                            ) : cheques.map(c => {
                                const meta = STATUS_META[c.status] || {};
                                return (
                                    <tr key={c.cheque_id} className="hover:bg-ink-50/40">
                                        <td className="font-mono text-xs font-semibold text-brand-700">{c.cheque_number}</td>
                                        <td>
                                            <div className="font-medium text-ink-900">{c.drawer_name}</div>
                                            <div className="text-2xs text-ink-500">{c.drawer_type}</div>
                                        </td>
                                        <td>
                                            <div className="text-sm text-ink-700">{c.bank_name}</div>
                                            {c.bank_branch && <div className="text-2xs text-ink-500">{c.bank_branch}</div>}
                                        </td>
                                        <td className="font-mono text-sm">{c.currency} {Number(c.amount).toLocaleString()}</td>
                                        <td className="text-xs text-ink-500">
                                            <Calendar size={11} className="inline mr-1 text-ink-400" />
                                            {c.date_received ? new Date(c.date_received).toLocaleDateString() : '—'}
                                        </td>
                                        <td><span className={meta.badge}>{c.status}</span></td>
                                        <td className="text-right">
                                            <button onClick={() => setActive(c)} className="p-1.5 text-ink-400 hover:text-brand-600 hover:bg-brand-50 rounded" aria-label="View">
                                                <Eye size={15} />
                                            </button>
                                            {c.status === 'Received' && (
                                                <button onClick={() => openAction(c, 'deposit')} className="ml-1 text-xs font-semibold px-2 py-1 rounded text-amber-700 bg-amber-50 hover:bg-amber-100">
                                                    Deposit
                                                </button>
                                            )}
                                            {c.status === 'Deposited' && (
                                                <>
                                                    <button onClick={() => openAction(c, 'clear')} className="ml-1 text-xs font-semibold px-2 py-1 rounded text-emerald-700 bg-emerald-50 hover:bg-emerald-100">
                                                        Clear
                                                    </button>
                                                    <button onClick={() => openAction(c, 'bounce')} className="ml-1 text-xs font-semibold px-2 py-1 rounded text-rose-700 bg-rose-50 hover:bg-rose-100">
                                                        Bounce
                                                    </button>
                                                </>
                                            )}
                                            {(c.status === 'Received' || c.status === 'Deposited') && (
                                                <button onClick={() => openAction(c, 'cancel')} className="ml-1 text-xs font-semibold px-2 py-1 rounded text-ink-600 bg-ink-100 hover:bg-ink-200">
                                                    Cancel
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── New cheque modal ── */}
            {isNewOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsNewOpen(false)} />
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 shrink-0">
                            <div>
                                <span className="section-eyebrow">Finance</span>
                                <h2 className="text-xl font-semibold mt-1 flex items-center gap-2"><Banknote size={20} className="text-brand-600" /> Record cheque</h2>
                            </div>
                            <button onClick={() => setIsNewOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full">
                                <X size={20} />
                            </button>
                        </div>
                        <form onSubmit={submitNew} className="flex-1 overflow-y-auto p-5 bg-ink-50/60 space-y-4">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="label">Cheque number *</label>
                                    <input required className="input" value={newDraft.cheque_number}
                                           onChange={e => setNewDraft({ ...newDraft, cheque_number: e.target.value })} />
                                </div>
                                <div>
                                    <label className="label">Date on cheque</label>
                                    <input type="date" className="input" value={newDraft.date_on_cheque}
                                           onChange={e => setNewDraft({ ...newDraft, date_on_cheque: e.target.value })} />
                                </div>
                                <div className="col-span-2">
                                    <label className="label">Drawer name *</label>
                                    <input required className="input" value={newDraft.drawer_name}
                                           onChange={e => setNewDraft({ ...newDraft, drawer_name: e.target.value })}
                                           placeholder="e.g. Jubilee Insurance Ltd" />
                                </div>
                                <div>
                                    <label className="label">Drawer type *</label>
                                    <select className="input" value={newDraft.drawer_type}
                                            onChange={e => setNewDraft({ ...newDraft, drawer_type: e.target.value })}>
                                        {DRAWER_TYPES.map(d => <option key={d}>{d}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="label">Amount *</label>
                                    <input required type="number" min="0.01" step="0.01" className="input" value={newDraft.amount}
                                           onChange={e => setNewDraft({ ...newDraft, amount: e.target.value })} />
                                </div>
                                <div>
                                    <label className="label">Bank name *</label>
                                    <input required className="input" value={newDraft.bank_name}
                                           onChange={e => setNewDraft({ ...newDraft, bank_name: e.target.value })} />
                                </div>
                                <div>
                                    <label className="label">Branch</label>
                                    <input className="input" value={newDraft.bank_branch}
                                           onChange={e => setNewDraft({ ...newDraft, bank_branch: e.target.value })} />
                                </div>
                                <div>
                                    <label className="label">Currency</label>
                                    <input className="input uppercase" maxLength="3" value={newDraft.currency}
                                           onChange={e => setNewDraft({ ...newDraft, currency: e.target.value.toUpperCase() })} />
                                </div>
                                <div>
                                    <label className="label">Linked invoice ID (optional)</label>
                                    <input type="number" className="input" value={newDraft.invoice_id}
                                           onChange={e => setNewDraft({ ...newDraft, invoice_id: e.target.value })} />
                                </div>
                                <div>
                                    <label className="label">Linked patient ID (optional)</label>
                                    <input type="number" className="input" value={newDraft.patient_id}
                                           onChange={e => setNewDraft({ ...newDraft, patient_id: e.target.value })} />
                                </div>
                                <div className="col-span-2">
                                    <label className="label">Notes</label>
                                    <textarea rows="3" className="input resize-none" value={newDraft.notes}
                                              onChange={e => setNewDraft({ ...newDraft, notes: e.target.value })} />
                                </div>
                            </div>
                            <div className="flex justify-end gap-2 pt-3 border-t border-ink-100">
                                <button type="button" onClick={() => setIsNewOpen(false)} className="btn-secondary">Cancel</button>
                                <button type="submit" disabled={submitting} className="btn-primary">
                                    {submitting ? <Activity size={15} className="animate-spin" /> : <Save size={15} />} Record cheque
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Detail drawer ── */}
            {active && !actionPanel && (
                <div className="fixed inset-0 z-40 flex justify-end pointer-events-none">
                    <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm pointer-events-auto" onClick={() => setActive(null)} />
                    <div className="relative w-full max-w-md bg-white h-full shadow-elevated flex flex-col animate-slide-in-right pointer-events-auto">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 shrink-0">
                            <div>
                                <span className="section-eyebrow">Cheque</span>
                                <h2 className="text-lg font-semibold mt-1">#{active.cheque_number}</h2>
                                <p className="text-xs text-ink-500 mt-0.5">{active.drawer_name}</p>
                            </div>
                            <button onClick={() => setActive(null)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full">
                                <X size={18} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-5 space-y-3">
                            <div className="flex items-center gap-2">
                                <span className={STATUS_META[active.status]?.badge}>{active.status}</span>
                                <span className="font-mono text-sm text-ink-700">{active.currency} {Number(active.amount).toLocaleString()}</span>
                            </div>
                            <Field label="Bank" value={`${active.bank_name}${active.bank_branch ? ` · ${active.bank_branch}` : ''}`} />
                            <Field label="Drawer type" value={active.drawer_type} />
                            <Field label="Date on cheque" value={active.date_on_cheque ? new Date(active.date_on_cheque).toLocaleDateString() : '—'} />
                            <Field label="Received on" value={active.date_received ? new Date(active.date_received).toLocaleString() : '—'} />
                            {active.deposit_date && <Field label="Deposited" value={`${new Date(active.deposit_date).toLocaleString()}${active.deposit_account ? ` → ${active.deposit_account}` : ''}`} />}
                            {active.clearance_date && <Field label="Cleared" value={new Date(active.clearance_date).toLocaleString()} />}
                            {active.bounce_reason && <Field label="Bounce reason" value={active.bounce_reason} accent="rose" />}
                            {active.cancel_reason && <Field label="Cancellation reason" value={active.cancel_reason} accent="rose" />}
                            {active.invoice_id && <Field label="Linked invoice" value={`#${active.invoice_id}${active.invoice_total != null ? ` (KES ${active.invoice_total.toLocaleString()})` : ''}`} />}
                            {active.patient_name && <Field label="Linked patient" value={active.patient_name} />}
                            {active.notes && <Field label="Notes" value={active.notes} />}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Action panels ── */}
            {actionPanel && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/60 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl shadow-elevated w-full max-w-md p-6 animate-slide-up">
                        <h3 className="text-lg font-semibold text-ink-900 mb-1 capitalize">{actionPanel} cheque</h3>
                        <p className="text-xs text-ink-500 mb-4">#{active?.cheque_number} · KES {Number(active?.amount).toLocaleString()}</p>

                        {actionPanel === 'deposit' && (
                            <div className="space-y-3">
                                <div>
                                    <label className="label">Deposit account *</label>
                                    <input className="input" value={actionDraft.deposit_account || ''}
                                           onChange={e => setActionDraft({ ...actionDraft, deposit_account: e.target.value })}
                                           placeholder="e.g. KCB 1234567890" />
                                </div>
                                <div>
                                    <label className="label">Deposit date</label>
                                    <input type="date" className="input" value={actionDraft.deposit_date || ''}
                                           onChange={e => setActionDraft({ ...actionDraft, deposit_date: e.target.value })} />
                                </div>
                            </div>
                        )}
                        {actionPanel === 'clear' && (
                            <div className="space-y-3">
                                <p className="text-sm text-ink-600">Marking this cheque as cleared posts a <span className="font-semibold">Payment</span> against the linked invoice (if any). This action cannot be undone.</p>
                                <div>
                                    <label className="label">Clearance date</label>
                                    <input type="date" className="input" value={actionDraft.clearance_date || ''}
                                           onChange={e => setActionDraft({ ...actionDraft, clearance_date: e.target.value })} />
                                </div>
                            </div>
                        )}
                        {(actionPanel === 'bounce' || actionPanel === 'cancel') && (
                            <div>
                                <label className="label">Reason *</label>
                                <textarea rows="3" className="input resize-none" value={actionDraft.reason || ''}
                                          onChange={e => setActionDraft({ ...actionDraft, reason: e.target.value })}
                                          placeholder={actionPanel === 'bounce' ? 'e.g. Insufficient funds, signature mismatch…' : 'e.g. Issued in error, wrong amount…'} />
                            </div>
                        )}

                        <div className="flex justify-end gap-2 mt-5 pt-3 border-t border-ink-100">
                            <button onClick={() => { setActionPanel(null); }} className="btn-secondary">Cancel</button>
                            <button onClick={submitAction} className={actionPanel === 'bounce' || actionPanel === 'cancel' ? 'btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50' : 'btn-primary'}>
                                Confirm {actionPanel}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function Field({ label, value, accent }) {
    const tone = accent === 'rose' ? 'text-rose-700' : 'text-ink-800';
    return (
        <div className="text-sm">
            <div className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">{label}</div>
            <div className={`mt-0.5 ${tone}`}>{value}</div>
        </div>
    );
}
