import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';
import {
    X, Building2, PauseCircle, PlayCircle, Receipt, Banknote, Ban,
} from 'lucide-react';
import {
    getTenantDetail, recordPayment, voidInvoice, setReminders, updateSubscription,
    formatKes, isZeroMoney,
} from '../../../api/receivables';
import { SkeletonTable } from '../../../components/ui/Skeleton';
import ErrorState from '../../../components/ui/ErrorState';

const todayIso = () => new Date().toISOString().slice(0, 10);

// Everything a focus trap needs to cycle through. Deliberately excludes
// tabindex="-1" targets: those are programmatic focus destinations, not
// stops in the tab order.
const FOCUSABLE_SELECTOR = [
    'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
    'input:not([disabled])', 'select:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(', ');

const PLAN_OPTIONS = ['standard', 'premium'];
const STATUS_OPTIONS = ['active', 'paused', 'cancelled'];
const METHOD_OPTIONS = ['mpesa', 'bank', 'cash', 'waiver'];

/**
 * TenantDrawer: the drill-down view for one tenant's receivables. Shows the
 * subscription terms (editable), every invoice with its running balance,
 * and every payment recorded against them. Every write action here calls
 * `onChanged()` afterwards so the ageing table and summary tiles behind it
 * stay in sync without the operator having to close and reopen the drawer.
 *
 * The body is split into three sections (SubscriptionSection, InvoicesSection,
 * PaymentsSection) further down this file so this component stays a thin
 * orchestrator: it owns the data fetch and the write handlers, the sections
 * own their own markup.
 */
export default function TenantDrawer({ tenantId, onClose, onChanged }) {
    const [detail, setDetail] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const [pauseSaving, setPauseSaving] = useState(false);
    const [subForm, setSubForm] = useState({ plan: '', price_kes: '', status: '' });
    const [subSaving, setSubSaving] = useState(false);

    // Which invoice row currently has its inline action form expanded, and
    // which of the two actions (record a payment / void) that form is for.
    const [openAction, setOpenAction] = useState(null); // { invoiceId, kind }
    const [paymentForm, setPaymentForm] = useState({ amount_kes: '', paid_on: todayIso(), method: 'mpesa', note: '' });
    const [voidReason, setVoidReason] = useState('');
    const [actionSaving, setActionSaving] = useState(false);

    // Focus management for this portal-based dialog (native <dialog> is
    // deferred project-wide, so none of this comes for free): dialogRef
    // scopes the Tab trap, closeButtonRef is where focus lands on open, and
    // previouslyFocusedRef is what focus returns to on close (whatever
    // triggered the drawer, normally the ageing table row).
    const dialogRef = useRef(null);
    const closeButtonRef = useRef(null);
    const previouslyFocusedRef = useRef(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getTenantDetail(tenantId);
            setDetail(data);
            if (data.subscription) {
                setSubForm({
                    plan: data.subscription.plan,
                    price_kes: data.subscription.price_kes,
                    status: data.subscription.status,
                });
            }
        } catch (err) {
            setError(err?.response?.data?.detail || 'Could not load this tenant\'s receivables.');
        } finally {
            setLoading(false);
        }
    }, [tenantId]);

    useEffect(() => { load(); }, [load]);

    // Escape closes the drawer, matching what a native <dialog> gives for free.
    useEffect(() => {
        const onKeyDown = (event) => { if (event.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [onClose]);

    // On open, move focus into the dialog rather than leaving it wherever it
    // was (or nowhere, if the trigger was a mouse click on a non-focusable
    // element). On close, give it back to whatever had focus before the
    // drawer opened, so a keyboard user lands back on the table row instead
    // of the top of the document. Runs once per mount: this component is
    // mounted/unmounted by the parent each time the drawer opens/closes, so
    // there is no separate "isOpen" prop to key off.
    useEffect(() => {
        previouslyFocusedRef.current = document.activeElement;
        closeButtonRef.current?.focus();
        return () => {
            const toRestore = previouslyFocusedRef.current;
            if (toRestore && typeof toRestore.focus === 'function' && document.contains(toRestore)) {
                toRestore.focus();
            }
        };
    }, []);

    // Keep Tab from escaping to the page behind the backdrop while the
    // drawer is open. Cycles within whatever is actually focusable right
    // now (a loading skeleton has nothing; a loaded drawer has several
    // buttons/inputs), so it stays correct as sections load in or fold away.
    const handleTrapKeyDown = (event) => {
        if (event.key !== 'Tab' || !dialogRef.current) return;
        const focusables = Array.from(dialogRef.current.querySelectorAll(FOCUSABLE_SELECTOR));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const isInside = dialogRef.current.contains(document.activeElement);
        if (event.shiftKey) {
            if (!isInside || document.activeElement === first) {
                event.preventDefault();
                last.focus();
            }
        } else if (!isInside || document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    };

    const notifyChanged = () => { if (onChanged) onChanged(); };

    const togglePause = async () => {
        if (!detail?.subscription) return;
        setPauseSaving(true);
        try {
            const next = !detail.subscription.reminders_paused;
            await setReminders(tenantId, next);
            setDetail((d) => ({ ...d, subscription: { ...d.subscription, reminders_paused: next } }));
            toast.success(next ? 'Reminders paused for this tenant.' : 'Reminders resumed for this tenant.');
            notifyChanged();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not update reminders.');
        } finally {
            setPauseSaving(false);
        }
    };

    const saveSubscription = async (event) => {
        event.preventDefault();
        setSubSaving(true);
        try {
            const updated = await updateSubscription(tenantId, {
                plan: subForm.plan,
                price_kes: subForm.price_kes,
                status: subForm.status,
            });
            setDetail((d) => ({ ...d, subscription: { ...d.subscription, ...updated } }));
            toast.success('Subscription terms updated.');
            notifyChanged();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not update the subscription.');
        } finally {
            setSubSaving(false);
        }
    };

    const openPaymentForm = (invoice) => {
        setOpenAction({ invoiceId: invoice.id, kind: 'payment' });
        setPaymentForm({ amount_kes: invoice.balance, paid_on: todayIso(), method: 'mpesa', note: '' });
    };
    const openVoidForm = (invoice) => {
        setOpenAction({ invoiceId: invoice.id, kind: 'void' });
        setVoidReason('');
    };
    const closeAction = () => setOpenAction(null);

    const submitPayment = async (event, invoiceId) => {
        event.preventDefault();
        setActionSaving(true);
        try {
            await recordPayment(invoiceId, {
                amount_kes: paymentForm.amount_kes,
                paid_on: paymentForm.paid_on,
                method: paymentForm.method,
                note: paymentForm.note || undefined,
            });
            toast.success('Payment recorded.');
            setOpenAction(null);
            await load();
            notifyChanged();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not record that payment.');
        } finally {
            setActionSaving(false);
        }
    };

    const submitVoid = async (event, invoiceId) => {
        event.preventDefault();
        if (!voidReason.trim()) { toast.error('A reason is required to void an invoice.'); return; }
        setActionSaving(true);
        try {
            await voidInvoice(invoiceId, voidReason.trim());
            toast.success('Invoice voided.');
            setOpenAction(null);
            await load();
            notifyChanged();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not void that invoice.');
        } finally {
            setActionSaving(false);
        }
    };

    return createPortal(
        <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/50 backdrop-blur-sm" onClick={onClose} role="presentation">
            <div
                ref={dialogRef}
                className="overlay-surface h-full w-full max-w-2xl flex flex-col rounded-none border-l"
                onClick={(event) => event.stopPropagation()}
                onKeyDown={handleTrapKeyDown}
                role="dialog"
                aria-modal="true"
                aria-label={detail ? `Receivables for ${detail.tenant_name}` : 'Tenant receivables'}
            >
                <div className="flex items-center justify-between p-4 border-b border-ink-200 dark:border-ink-800 shrink-0">
                    <h2 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2 min-w-0">
                        <Building2 size={16} className="text-brand-500 shrink-0" aria-hidden="true" />
                        <span className="truncate">{detail ? detail.tenant_name : 'Loading tenant…'}</span>
                    </h2>
                    <button
                        ref={closeButtonRef}
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-1.5 rounded-lg text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800 cursor-pointer"
                    >
                        <X size={16} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-6">
                    {loading && <SkeletonTable rows={6} cols={5} label="Loading tenant receivables" />}
                    {!loading && error && <ErrorState title="Could not load this tenant" message={error} onRetry={load} />}

                    {!loading && !error && detail && (
                        <>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="card p-4">
                                    <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500 dark:text-ink-400">Outstanding</p>
                                    <p className="tnum text-xl font-semibold text-ink-900 dark:text-white mt-1">{formatKes(detail.balances.outstanding)}</p>
                                </div>
                                <div className="card p-4">
                                    <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-ink-500 dark:text-ink-400">Overdue</p>
                                    <p className={`tnum text-xl font-semibold mt-1 ${isZeroMoney(detail.balances.overdue) ? 'text-ink-900 dark:text-white' : 'text-rose-700 dark:text-rose-400'}`}>
                                        {formatKes(detail.balances.overdue)}
                                    </p>
                                </div>
                            </div>

                            <SubscriptionSection
                                subscription={detail.subscription}
                                subForm={subForm}
                                setSubForm={setSubForm}
                                subSaving={subSaving}
                                pauseSaving={pauseSaving}
                                onTogglePause={togglePause}
                                onSaveSubscription={saveSubscription}
                            />

                            <InvoicesSection
                                invoices={detail.invoices}
                                openAction={openAction}
                                paymentForm={paymentForm}
                                setPaymentForm={setPaymentForm}
                                voidReason={voidReason}
                                setVoidReason={setVoidReason}
                                actionSaving={actionSaving}
                                onOpenPayment={openPaymentForm}
                                onOpenVoid={openVoidForm}
                                onCloseAction={closeAction}
                                onSubmitPayment={submitPayment}
                                onSubmitVoid={submitVoid}
                            />

                            <PaymentsSection payments={detail.payments} />
                        </>
                    )}
                </div>
            </div>
        </div>,
        document.body,
    );
}

function SubscriptionSection({
    subscription, subForm, setSubForm, subSaving, pauseSaving, onTogglePause, onSaveSubscription,
}) {
    return (
        <section className="card p-4 space-y-3">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Subscription terms</h3>
            {!subscription && (
                <p className="text-sm text-ink-500 dark:text-ink-400">No subscription configured for this tenant.</p>
            )}
            {subscription && (
                <>
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-xs text-ink-500 dark:text-ink-400 space-y-0.5">
                            <p>Cycle: <span className="font-medium text-ink-700 dark:text-ink-200">{subscription.cycle}</span></p>
                            <p>Started: <span className="tnum">{subscription.started_on}</span></p>
                            <p>Next invoice: <span className="tnum">{subscription.next_invoice_on}</span></p>
                        </div>
                        {subscription.reminders_paused && (
                            <span className="badge-warn inline-flex items-center gap-1">
                                <PauseCircle size={10} aria-hidden="true" /> Reminders paused
                            </span>
                        )}
                        <button type="button" onClick={onTogglePause} disabled={pauseSaving} className="btn btn-secondary btn-xs">
                            {subscription.reminders_paused
                                ? <><PlayCircle size={12} aria-hidden="true" /> Resume reminders</>
                                : <><PauseCircle size={12} aria-hidden="true" /> Pause reminders</>}
                        </button>
                    </div>

                    <form onSubmit={onSaveSubscription} className="grid grid-cols-3 gap-3 pt-2 border-t border-ink-100 dark:border-ink-800">
                        <Field label="Plan">
                            <select className="input" value={subForm.plan} onChange={(e) => setSubForm((f) => ({ ...f, plan: e.target.value }))}>
                                {PLAN_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
                            </select>
                        </Field>
                        <Field label="Price (KES)">
                            <input
                                aria-label="Price (KES)"
                                className="input tnum"
                                inputMode="decimal"
                                value={subForm.price_kes}
                                onChange={(e) => setSubForm((f) => ({ ...f, price_kes: e.target.value }))}
                            />
                        </Field>
                        <Field label="Status">
                            <select className="input" value={subForm.status} onChange={(e) => setSubForm((f) => ({ ...f, status: e.target.value }))}>
                                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                            </select>
                        </Field>
                        <div className="col-span-3 flex justify-end">
                            <button type="submit" disabled={subSaving} className="btn btn-primary btn-xs">
                                {subSaving ? 'Saving…' : 'Save subscription'}
                            </button>
                        </div>
                    </form>
                </>
            )}
        </section>
    );
}

const INVOICE_STATUS_TONE = {
    open: 'badge-info',
    paid: 'badge-success',
    void: 'badge-neutral',
};

function InvoicesSection({
    invoices, openAction, paymentForm, setPaymentForm, voidReason, setVoidReason,
    actionSaving, onOpenPayment, onOpenVoid, onCloseAction, onSubmitPayment, onSubmitVoid,
}) {
    return (
        <section className="space-y-2">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                <Receipt size={14} className="text-ink-400" aria-hidden="true" /> Invoices
            </h3>
            {invoices.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">No invoices raised yet.</p>
            ) : (
                <div className="card overflow-x-auto">
                    <table className="table-clean">
                        <thead>
                            <tr>
                                <th>Number</th><th>Period</th><th className="num">Amount</th>
                                <th className="num">Balance</th><th>Status</th><th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {invoices.map((inv) => (
                                <React.Fragment key={inv.id}>
                                    <tr>
                                        <td className="font-mono text-xs">{inv.number}</td>
                                        <td className="text-xs">{inv.period_start} – {inv.period_end}</td>
                                        <td className="num tnum">{formatKes(inv.amount_kes)}</td>
                                        <td className="num tnum">{formatKes(inv.balance)}</td>
                                        <td><span className={INVOICE_STATUS_TONE[inv.status] || 'badge-neutral'}>{inv.status}</span></td>
                                        <td>
                                            {inv.status === 'open' && (
                                                <div className="flex gap-1.5">
                                                    <button type="button" className="btn btn-secondary btn-xs" onClick={() => onOpenPayment(inv)}>
                                                        <Banknote size={12} aria-hidden="true" /> Payment
                                                    </button>
                                                    <button type="button" className="btn btn-danger-ghost btn-xs" onClick={() => onOpenVoid(inv)}>
                                                        <Ban size={12} aria-hidden="true" /> Void
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                    {openAction?.invoiceId === inv.id && openAction.kind === 'payment' && (
                                        <PaymentFormRow
                                            paymentForm={paymentForm}
                                            setPaymentForm={setPaymentForm}
                                            actionSaving={actionSaving}
                                            onSubmit={(e) => onSubmitPayment(e, inv.id)}
                                            onCancel={onCloseAction}
                                        />
                                    )}
                                    {openAction?.invoiceId === inv.id && openAction.kind === 'void' && (
                                        <VoidFormRow
                                            voidReason={voidReason}
                                            setVoidReason={setVoidReason}
                                            actionSaving={actionSaving}
                                            onSubmit={(e) => onSubmitVoid(e, inv.id)}
                                            onCancel={onCloseAction}
                                        />
                                    )}
                                </React.Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
}

function PaymentFormRow({ paymentForm, setPaymentForm, actionSaving, onSubmit, onCancel }) {
    return (
        <tr>
            <td colSpan={6} className="bg-ink-50 dark:bg-ink-800/40">
                <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2 py-2">
                    <Field label="Amount (KES)">
                        <input aria-label="Payment amount" className="input tnum" inputMode="decimal"
                            value={paymentForm.amount_kes}
                            onChange={(e) => setPaymentForm((f) => ({ ...f, amount_kes: e.target.value }))} />
                    </Field>
                    <Field label="Paid on">
                        <input aria-label="Paid on" type="date" className="input"
                            value={paymentForm.paid_on}
                            onChange={(e) => setPaymentForm((f) => ({ ...f, paid_on: e.target.value }))} />
                    </Field>
                    <Field label="Method">
                        <select aria-label="Payment method" className="input"
                            value={paymentForm.method}
                            onChange={(e) => setPaymentForm((f) => ({ ...f, method: e.target.value }))}>
                            {METHOD_OPTIONS.map((m) => <option key={m} value={m}>{m}</option>)}
                        </select>
                    </Field>
                    <Field label="Note" className="flex-1 min-w-[10rem]">
                        <input aria-label="Payment note" className="input"
                            value={paymentForm.note}
                            onChange={(e) => setPaymentForm((f) => ({ ...f, note: e.target.value }))} />
                    </Field>
                    <button type="submit" disabled={actionSaving} className="btn btn-primary btn-xs">
                        {actionSaving ? 'Saving…' : 'Record payment'}
                    </button>
                    <button type="button" className="btn btn-ghost btn-xs" onClick={onCancel}>Cancel</button>
                </form>
            </td>
        </tr>
    );
}

function VoidFormRow({ voidReason, setVoidReason, actionSaving, onSubmit, onCancel }) {
    return (
        <tr>
            <td colSpan={6} className="bg-ink-50 dark:bg-ink-800/40">
                <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2 py-2">
                    <Field label="Reason for voiding this invoice" className="flex-1 min-w-[14rem]">
                        <input aria-label="Void reason" className="input" value={voidReason} onChange={(e) => setVoidReason(e.target.value)} />
                    </Field>
                    <button type="submit" disabled={actionSaving} className="btn btn-danger btn-xs">
                        {actionSaving ? 'Voiding…' : 'Void invoice'}
                    </button>
                    <button type="button" className="btn btn-ghost btn-xs" onClick={onCancel}>Cancel</button>
                </form>
            </td>
        </tr>
    );
}

function PaymentsSection({ payments }) {
    return (
        <section className="space-y-2">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                <Banknote size={14} className="text-ink-400" aria-hidden="true" /> Payments
            </h3>
            {payments.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">No payments recorded yet.</p>
            ) : (
                <div className="card overflow-x-auto">
                    <table className="table-clean">
                        <thead>
                            <tr><th>Invoice</th><th className="num">Amount</th><th>Paid on</th><th>Method</th><th>Note</th></tr>
                        </thead>
                        <tbody>
                            {payments.map((p) => (
                                <tr key={p.id}>
                                    <td className="text-xs">#{p.invoice_id}</td>
                                    <td className="num tnum">{formatKes(p.amount_kes)}</td>
                                    <td className="text-xs tnum">{p.paid_on}</td>
                                    <td className="text-xs">{p.method}</td>
                                    <td className="text-xs text-ink-500 dark:text-ink-400">{p.note || '-'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    );
}

function Field({ label, children, className = '' }) {
    return (
        <label className={`block ${className}`.trim()}>
            <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">{label}</span>
            {children}
        </label>
    );
}
