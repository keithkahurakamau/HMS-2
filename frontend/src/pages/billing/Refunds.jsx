import React, { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Undo2, Plus, X, CheckCircle2 } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import { useAuth } from '../../context/AuthContext';
import {
    listRefunds, requestRefund, approveRefund, getRefundableAmount, getConfig,
    formatKes,
} from '../../api/mpesa';

/* ────────────────────────────────────────────────────────────────────────── */
/*  M-Pesa refunds: the only path by which money leaves the hospital's own    */
/*  till back to a patient.                                                   */
/*                                                                            */
/*  Dual approval is enforced by the server (app/services/daraja/b2c.py's    */
/*  approve_refund rejects a requester approving their own refund above      */
/*  refund_dual_approval_above). Hiding the button here below the threshold  */
/*  is a courtesy so nobody clicks into a 403 — it is not the control.       */
/* ────────────────────────────────────────────────────────────────────────── */

const STATUS_BADGE = {
    Requested: 'badge-warn',
    Approved: 'badge-info',
    Processing: 'badge-info',
    Completed: 'badge-success',
    Failed: 'badge-danger',
    Reversed: 'badge-neutral',
};

export default function Refunds() {
    const { user } = useAuth();
    const [refunds, setRefunds] = useState([]);
    const [dualApprovalAbove, setDualApprovalAbove] = useState(null);
    const [loading, setLoading] = useState(true);
    const [requestOpen, setRequestOpen] = useState(false);
    const [approvingId, setApprovingId] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [rows, config] = await Promise.all([listRefunds(), getConfig()]);
            setRefunds(Array.isArray(rows) ? rows : []);
            setDualApprovalAbove(config?.refund_dual_approval_above ?? null);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load refunds.');
        } finally { setLoading(false); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const doApprove = async (refundId) => {
        setApprovingId(refundId);
        try {
            await approveRefund(refundId);
            toast.success('Refund approved and submitted to M-Pesa.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not approve this refund.');
        } finally { setApprovingId(null); }
    };

    // Server-enforced rule: a requester cannot approve their own refund
    // above refund_dual_approval_above. This mirrors that rule only to hide
    // a button that would otherwise 403; it changes nothing about who is
    // actually allowed to approve.
    const canOfferApprove = (refund) => {
        if (refund.status !== 'Requested') return false;
        if (dualApprovalAbove == null) return true;
        const aboveThreshold = Number(refund.amount) > Number(dualApprovalAbove);
        const isRequester = user?.user_id === refund.requested_by;
        return !(aboveThreshold && isRequester);
    };

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={Undo2}
                title="M-Pesa Refunds"
                subtitle="Every refund reverses a specific M-Pesa receipt, requested by one person and, above the threshold, approved by another."
                tone="brand"
                actions={
                    <button type="button" onClick={() => setRequestOpen(true)} className="btn-primary btn-xs">
                        <Plus size={14} /> Request a refund
                    </button>
                }
            />

            <div className="card-flush overflow-hidden overflow-x-auto">
                <table className="table-clean table-sticky min-w-[880px]">
                    <thead>
                        <tr>
                            <th>Requested</th>
                            <th>Invoice</th>
                            <th>Phone</th>
                            <th className="text-right">Amount</th>
                            <th>Reason</th>
                            <th>Status</th>
                            <th>Receipt</th>
                            <th className="text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan="8" className="px-6 py-12 text-center text-ink-400">Loading…</td></tr>
                        ) : refunds.length === 0 ? (
                            <tr><td colSpan="8" className="px-6 py-12 text-center text-ink-400">No refunds recorded yet.</td></tr>
                        ) : (
                            refunds.map((r) => (
                                <tr key={r.id}>
                                    <td className="text-ink-500 tnum">{r.requested_at ? new Date(r.requested_at).toLocaleString() : '-'}</td>
                                    <td className="font-mono">{r.invoice_id ? `INV-${r.invoice_id}` : '-'}</td>
                                    <td className="font-mono">{r.phone_number}</td>
                                    <td className="text-right font-semibold tnum">{formatKes(r.amount)}</td>
                                    <td className="max-w-xs truncate" title={r.reason}>{r.reason}</td>
                                    <td><span className={STATUS_BADGE[r.status] || 'badge-neutral'}>{r.status}</span></td>
                                    <td className="font-mono text-xs">{r.transaction_receipt || '-'}</td>
                                    <td className="text-right">
                                        {canOfferApprove(r) ? (
                                            <button type="button" onClick={() => doApprove(r.id)} disabled={approvingId === r.id}
                                                    className="btn-secondary btn-xs">
                                                {approvingId === r.id ? 'Approving…' : 'Approve'}
                                            </button>
                                        ) : r.status === 'Requested' ? (
                                            <span className="text-2xs text-ink-400" title="Above the dual-approval threshold: needs a different approver">
                                                Awaiting a second approver
                                            </span>
                                        ) : null}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {requestOpen && (
                <RequestRefundDialog
                    onClose={() => setRequestOpen(false)}
                    onRequested={() => { setRequestOpen(false); load(); }}
                />
            )}
        </div>
    );
}

/* ─── Request-refund dialog ──────────────────────────────────────────────── */

function RequestRefundDialog({ onClose, onRequested }) {
    const [sourceTransactionId, setSourceTransactionId] = useState('');
    const [refundable, setRefundable] = useState(null);
    const [checking, setChecking] = useState(false);
    const [amount, setAmount] = useState('');
    const [reason, setReason] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const dialogRef = useRef(null);
    const firstFieldRef = useRef(null);
    const previouslyFocused = useRef(null);

    useEffect(() => {
        previouslyFocused.current = document.activeElement;
        firstFieldRef.current?.focus();
        const onKeyDown = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKeyDown);
        return () => {
            document.removeEventListener('keydown', onKeyDown);
            const toRestore = previouslyFocused.current;
            if (toRestore && typeof toRestore.focus === 'function' && document.contains(toRestore)) {
                toRestore.focus();
            }
        };
    }, [onClose]);

    const handleTrap = (e) => {
        if (e.key !== 'Tab' || !dialogRef.current) return;
        const focusables = Array.from(dialogRef.current.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled])',
        ));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const inside = dialogRef.current.contains(document.activeElement);
        if (e.shiftKey) {
            if (!inside || document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else if (!inside || document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    const checkRefundable = async () => {
        if (!sourceTransactionId) return;
        setChecking(true);
        setRefundable(null);
        try {
            const { refundable_amount } = await getRefundableAmount(sourceTransactionId);
            setRefundable(refundable_amount);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not look up that transaction.');
        } finally { setChecking(false); }
    };

    const submit = async () => {
        if (!sourceTransactionId || !amount || !reason.trim()) {
            return toast.error('Transaction, amount, and reason are all required.');
        }
        setSubmitting(true);
        try {
            await requestRefund({
                source_transaction_id: Number(sourceTransactionId),
                amount,
                reason: reason.trim(),
            });
            toast.success('Refund requested.');
            onRequested();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not request this refund.');
        } finally { setSubmitting(false); }
    };

    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="request-refund-title"
                 onKeyDown={handleTrap}
                 className="bg-white dark:bg-ink-900 rounded-xl shadow-overlay w-full max-w-md">
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <h3 id="request-refund-title" className="text-sm font-semibold text-ink-900 dark:text-ink-100">Request a refund</h3>
                    <button type="button" onClick={onClose} className="text-ink-400 hover:text-ink-700" aria-label="Close">
                        <X size={18} />
                    </button>
                </div>
                <div className="p-5 space-y-4">
                    <div className="block">
                        <label htmlFor="refund-source-transaction-id" className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">
                            M-Pesa transaction ID (the receipt to refund)
                        </label>
                        <div className="flex gap-2">
                            <input id="refund-source-transaction-id" ref={firstFieldRef} className="input" value={sourceTransactionId}
                                   onChange={(e) => { setSourceTransactionId(e.target.value); setRefundable(null); }}
                                   inputMode="numeric" placeholder="e.g. 482" />
                            <button type="button" onClick={checkRefundable} disabled={checking || !sourceTransactionId}
                                    className="btn-secondary btn-xs shrink-0">
                                {checking ? 'Checking…' : 'Check'}
                            </button>
                        </div>
                        {refundable != null && (
                            <p className="text-xs text-emerald-700 dark:text-emerald-300 mt-1 inline-flex items-center gap-1">
                                <CheckCircle2 size={12} /> Refundable up to {formatKes(refundable)}
                            </p>
                        )}
                    </div>
                    <label className="block">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Amount to refund (KES)</span>
                        <input type="number" min="0" step="0.01" className="input tnum" value={amount}
                               onChange={(e) => setAmount(e.target.value)} />
                    </label>
                    <label className="block">
                        <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Reason</span>
                        <textarea className="input" rows={2} value={reason}
                                  onChange={(e) => setReason(e.target.value)}
                                  placeholder="Why this refund is being requested" />
                    </label>
                    <div className="flex justify-end gap-2 pt-2">
                        <button type="button" onClick={onClose}
                                className="px-3 py-2 rounded-lg border border-ink-200 dark:border-ink-800 text-sm font-medium hover:bg-ink-50 dark:hover:bg-ink-800/50">
                            Cancel
                        </button>
                        <button type="button" onClick={submit} disabled={submitting}
                                className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {submitting ? 'Requesting…' : 'Request refund'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
