/* Bulk-allocate one client deposit across many claim-schedule items in a
 * single all-or-nothing transaction. Backed by
 * POST /api/accounting/debtors/deposits/{id}/allocate-bulk. */
import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import { ModalShell, ModalActions, Field } from './ui';
import { formatAmount } from './format';

export default function BulkAllocateModal({ deposit, onClose, onSaved }) {
    const available = Number(deposit.amount) - Number(deposit.amount_applied || 0);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [amounts, setAmounts] = useState({}); // item_id → string
    const [notes, setNotes] = useState('');
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        (async () => {
            setLoading(true);
            try {
                const r = await apiClient.get('/accounting/debtors/claims');
                const flat = [];
                for (const claim of r.data || []) {
                    for (const it of claim.items || []) {
                        const remaining = Number(it.amount_claimed) - Number(it.amount_allocated || 0);
                        if (remaining > 0) {
                            flat.push({
                                ...it,
                                schedule_number: claim.schedule_number,
                                remaining,
                            });
                        }
                    }
                }
                setItems(flat);
            } catch { toast.error('Could not load claim items.'); }
            finally { setLoading(false); }
        })();
    }, []);

    const total = useMemo(
        () => Object.values(amounts).reduce((s, v) => s + Number(v || 0), 0),
        [amounts],
    );
    const remainingDeposit = available - total;

    const setAmount = (id, val) => setAmounts(prev => ({ ...prev, [id]: val }));

    const submit = async () => {
        const allocations = Object.entries(amounts)
            .filter(([, v]) => Number(v) > 0)
            .map(([id, v]) => ({ item_id: Number(id), amount: Number(v) }));
        if (allocations.length === 0) { toast.error('Enter at least one allocation.'); return; }
        if (total > available + 1e-9) {
            toast.error(`Allocations exceed available ${formatAmount(available)}.`); return;
        }
        // Per-item over-allocation guard (server enforces too).
        for (const a of allocations) {
            const item = items.find(i => i.item_id === a.item_id);
            if (item && a.amount > item.remaining + 1e-9) {
                toast.error(`Item ${item.schedule_number} #${item.item_id}: max ${formatAmount(item.remaining)}.`);
                return;
            }
        }
        setSaving(true);
        try {
            await apiClient.post(`/accounting/debtors/deposits/${deposit.deposit_id}/allocate-bulk`, {
                allocations,
                notes: notes || null,
            });
            toast.success('Deposit allocated.');
            onSaved();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not allocate.'); }
        finally { setSaving(false); }
    };

    return (
        <ModalShell title={`Bulk-allocate deposit ${deposit.deposit_number}`} onClose={onClose} wide>
            <div className="flex items-center justify-between text-sm mb-3">
                <span className="text-ink-600 dark:text-ink-400">
                    Patient #{deposit.patient_id} · Available:{' '}
                    <span className="font-mono font-semibold">{formatAmount(available)}</span>
                </span>
                <span className={'font-mono ' + (remainingDeposit < 0 ? 'text-rose-600' : 'text-ink-600 dark:text-ink-400')}>
                    Allocated {formatAmount(total)} · Remaining {formatAmount(remainingDeposit)}
                </span>
            </div>

            {loading ? (
                <div className="p-6 text-sm text-ink-500 dark:text-ink-400">Loading claim items...</div>
            ) : items.length === 0 ? (
                <div className="p-6 text-sm text-ink-500 dark:text-ink-400">No claim items with an unallocated balance.</div>
            ) : (
                <div className="border border-ink-200 dark:border-ink-800 rounded-lg overflow-hidden max-h-[50vh] overflow-y-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-ink-50 dark:bg-ink-800/40 text-ink-600 dark:text-ink-400 sticky top-0">
                            <tr>
                                <th className="text-left px-3 py-2 font-medium">Claim</th>
                                <th className="text-left px-3 py-2 font-medium">Patient</th>
                                <th className="text-left px-3 py-2 font-medium">Invoice ref</th>
                                <th className="text-right px-3 py-2 font-medium">Remaining</th>
                                <th className="text-right px-3 py-2 font-medium w-36">Allocate</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                            {items.map(it => (
                                <tr key={it.item_id}>
                                    <td className="px-3 py-1.5 font-mono text-xs">{it.schedule_number}</td>
                                    <td className="px-3 py-1.5">{it.patient_name || '—'}</td>
                                    <td className="px-3 py-1.5">{it.invoice_reference || (it.invoice_id ? `#${it.invoice_id}` : '—')}</td>
                                    <td className="px-3 py-1.5 text-right font-mono">{formatAmount(it.remaining)}</td>
                                    <td className="px-2 py-1">
                                        <input type="number" step="0.01" min="0" max={it.remaining}
                                               className="input text-right py-1 px-2 w-32"
                                               value={amounts[it.item_id] ?? ''}
                                               onChange={(e) => setAmount(it.item_id, e.target.value)} />
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            <div className="mt-3">
                <Field label="Notes">
                    <textarea className="input min-h-[50px]" value={notes}
                              onChange={(e) => setNotes(e.target.value)} />
                </Field>
            </div>
            <ModalActions onClose={onClose} onSubmit={submit} saving={saving} submitLabel="Allocate" />
        </ModalShell>
    );
}
