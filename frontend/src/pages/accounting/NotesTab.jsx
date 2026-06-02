/* Debit / credit notes — post-invoice receivable adjustments that post
 * through the normal journal pipeline. Backed by /api/accounting/notes. */
import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { CheckCircle2, Slash, Trash2 } from 'lucide-react';
import {
    SectionHeader, DataCard, ModalShell, ModalActions, Field,
} from './ui';
import { formatAmount, todayISO } from './format';

const NOTE_STATUS_BADGE = {
    draft:  'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
    posted: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
    void:   'bg-ink-50 text-ink-500 ring-1 ring-ink-200',
};

const TYPE_BADGE = {
    debit:  'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
    credit: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
};

export default function NotesTab() {
    const [notes, setNotes] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openNew, setOpenNew] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [n, a] = await Promise.all([
                apiClient.get('/accounting/notes'),
                apiClient.get('/accounting/accounts?include_inactive=false'),
            ]);
            setNotes(n.data || []);
            setAccounts((a.data || []).filter(x => x.is_postable));
        } catch { toast.error('Could not load notes.'); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const accLabel = (id) => {
        const a = accounts.find(x => x.account_id === id);
        return a ? `${a.code} ${a.name}` : `#${id}`;
    };

    const post = async (id) => {
        try {
            await apiClient.post(`/accounting/notes/${id}/post`);
            toast.success('Note posted.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not post note.'); }
    };

    const voidNote = async (id) => {
        const reason = window.prompt('Void reason (optional):') || '';
        try {
            await apiClient.post(`/accounting/notes/${id}/void`, { reason: reason || null });
            toast.success('Note voided (entry reversed).');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not void note.'); }
    };

    const del = async (id) => {
        if (!window.confirm('Delete this draft note?')) return;
        try {
            await apiClient.delete(`/accounting/notes/${id}`);
            toast.success('Draft deleted.');
            load();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not delete.'); }
    };

    return (
        <div className="space-y-4">
            <SectionHeader title="Debit / Credit Notes"
                           subtitle="Adjust a receivable after invoicing. Credit notes reduce the balance; debit notes increase it."
                           onNew={() => setOpenNew(true)}
                           disabled={accounts.length === 0}
                           disabledMsg="Set up a chart of accounts first." />

            <DataCard loading={loading} empty={notes.length === 0} emptyMsg="No notes yet.">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-4 py-2 font-medium">Number</th>
                            <th className="text-left px-4 py-2 font-medium">Type</th>
                            <th className="text-left px-4 py-2 font-medium">Date</th>
                            <th className="text-left px-4 py-2 font-medium">Dr / Cr</th>
                            <th className="text-right px-4 py-2 font-medium">Amount</th>
                            <th className="text-left px-4 py-2 font-medium">Status</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {notes.map(n => (
                            <tr key={n.note_id} className="hover:bg-ink-50/40">
                                <td className="px-4 py-2 font-mono text-xs">{n.note_number}</td>
                                <td className="px-4 py-2">
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${TYPE_BADGE[n.note_type]}`}>
                                        {n.note_type}
                                    </span>
                                </td>
                                <td className="px-4 py-2">{n.note_date}</td>
                                <td className="px-4 py-2 text-xs text-ink-600">
                                    <div>Dr {accLabel(n.debit_account_id)}</div>
                                    <div>Cr {accLabel(n.credit_account_id)}</div>
                                </td>
                                <td className="px-4 py-2 text-right font-mono">{formatAmount(n.amount)}</td>
                                <td className="px-4 py-2">
                                    <span className={`text-xs px-2 py-0.5 rounded-md ${NOTE_STATUS_BADGE[n.status]}`}>
                                        {n.status}
                                    </span>
                                </td>
                                <td className="px-4 py-2 text-right space-x-2 whitespace-nowrap">
                                    {n.status === 'draft' && (
                                        <>
                                            <button onClick={() => post(n.note_id)}
                                                    className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline">
                                                <CheckCircle2 size={12} /> Post
                                            </button>
                                            <button onClick={() => del(n.note_id)}
                                                    className="inline-flex items-center gap-1 text-xs text-rose-600 hover:underline">
                                                <Trash2 size={12} /> Delete
                                            </button>
                                        </>
                                    )}
                                    {n.status === 'posted' && (
                                        <button onClick={() => voidNote(n.note_id)}
                                                className="inline-flex items-center gap-1 text-xs text-rose-700 hover:underline">
                                            <Slash size={12} /> Void
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </DataCard>

            {openNew && <NoteModal accounts={accounts}
                                   onClose={() => setOpenNew(false)}
                                   onSaved={() => { setOpenNew(false); load(); }} />}
        </div>
    );
}

function NoteModal({ accounts, onClose, onSaved }) {
    const [form, setForm] = useState({
        note_type: 'credit',
        note_date: todayISO(),
        amount: '',
        debit_account_id: '',
        credit_account_id: '',
        invoice_id: '',
        reason: '',
    });
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.amount || Number(form.amount) <= 0) { toast.error('Amount must be positive.'); return; }
        if (!form.debit_account_id || !form.credit_account_id) { toast.error('Pick both accounts.'); return; }
        if (form.debit_account_id === form.credit_account_id) { toast.error('Debit and credit accounts must differ.'); return; }
        setSaving(true);
        try {
            await apiClient.post('/accounting/notes', {
                note_type: form.note_type,
                note_date: form.note_date,
                amount: Number(form.amount),
                debit_account_id: Number(form.debit_account_id),
                credit_account_id: Number(form.credit_account_id),
                invoice_id: form.invoice_id ? Number(form.invoice_id) : null,
                reason: form.reason || null,
            });
            toast.success('Note created (draft).');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not create note.'); }
        finally { setSaving(false); }
    };

    const AccountSelect = ({ value, onChange }) => (
        <select className="input" value={value} onChange={onChange}>
            <option value="">— select account —</option>
            {accounts.map(a => (
                <option key={a.account_id} value={a.account_id}>{a.code} {a.name}</option>
            ))}
        </select>
    );

    return (
        <ModalShell title="New debit/credit note" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Type *">
                    <select className="input" value={form.note_type}
                            onChange={(e) => setForm({ ...form, note_type: e.target.value })}>
                        <option value="credit">Credit note (reduce balance)</option>
                        <option value="debit">Debit note (increase balance)</option>
                    </select>
                </Field>
                <Field label="Date *">
                    <input type="date" className="input" value={form.note_date}
                           onChange={(e) => setForm({ ...form, note_date: e.target.value })} />
                </Field>
                <Field label="Amount *">
                    <input type="number" step="0.01" min="0" className="input" value={form.amount}
                           onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                </Field>
                <Field label="Invoice ID">
                    <input type="number" className="input" value={form.invoice_id}
                           onChange={(e) => setForm({ ...form, invoice_id: e.target.value })}
                           placeholder="optional" />
                </Field>
                <Field label="Debit account *">
                    <AccountSelect value={form.debit_account_id}
                                   onChange={(e) => setForm({ ...form, debit_account_id: e.target.value })} />
                </Field>
                <Field label="Credit account *">
                    <AccountSelect value={form.credit_account_id}
                                   onChange={(e) => setForm({ ...form, credit_account_id: e.target.value })} />
                </Field>
            </div>
            <div className="mt-3">
                <Field label="Reason">
                    <textarea className="input min-h-[60px]" value={form.reason}
                              onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} submitLabel="Create draft" />
        </ModalShell>
    );
}
