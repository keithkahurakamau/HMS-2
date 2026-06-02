import React from 'react';
import { Smartphone, CheckCircle2, XCircle, RefreshCcw } from 'lucide-react';

/* ──────────────────────────────────────────────────────────────────────────
 * Shared M-Pesa STK-push progress panel.
 *
 * Presentational only — the parent owns the countdown + the DB-status poll
 * and just feeds this component the current state. Used by both the cashier
 * (Billing) and pharmacy checkout so the customer-facing wait/success/failure
 * experience is identical across the app.
 *
 * Props:
 *   status      'waiting' | 'success' | 'failed'
 *   phone       MSISDN the prompt was sent to (shown to the operator)
 *   secondsLeft remaining seconds on the visible countdown (waiting only)
 *   total       countdown length in seconds (for the ring sweep; default 60)
 *   receipt     M-Pesa receipt number (success)
 *   errorDesc   failure reason from Pay Hero / timeout (failed)
 *   onRetry     () => void  — re-show the payment form (failed)
 *   onCancel    () => void  — dismiss while waiting (optional)
 * ────────────────────────────────────────────────────────────────────────── */
export default function MpesaStkProgress({
    status = 'waiting',
    phone,
    secondsLeft = 0,
    total = 60,
    receipt,
    errorDesc,
    onRetry,
    onCancel,
}) {
    if (status === 'success') {
        return (
            <div className="text-center py-8 px-4">
                <div className="mx-auto size-16 rounded-full bg-emerald-100 flex items-center justify-center mb-4">
                    <CheckCircle2 className="text-emerald-600" size={34} />
                </div>
                <p className="text-base font-semibold text-ink-900">Payment received</p>
                {receipt && (
                    <p className="text-sm text-ink-500 mt-1">
                        M-Pesa receipt <span className="font-mono font-semibold text-ink-700">{receipt}</span>
                    </p>
                )}
            </div>
        );
    }

    if (status === 'failed') {
        return (
            <div className="text-center py-8 px-4">
                <div className="mx-auto size-16 rounded-full bg-rose-100 flex items-center justify-center mb-4">
                    <XCircle className="text-rose-600" size={34} />
                </div>
                <p className="text-base font-semibold text-ink-900">Payment failed. Please try again.</p>
                <p className="text-sm text-ink-500 mt-1">
                    {errorDesc || 'The customer cancelled the prompt, the PIN timed out, or funds were insufficient.'}
                </p>
                {onRetry && (
                    <button
                        onClick={onRetry}
                        className="mt-5 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700"
                    >
                        <RefreshCcw size={15} /> Try again
                    </button>
                )}
            </div>
        );
    }

    // status === 'waiting' — pulsing phone + circular countdown.
    const R = 30;
    const C = 2 * Math.PI * R;
    const clamped = Math.max(0, Math.min(secondsLeft, total));
    const offset = C * (1 - clamped / (total || 1));

    return (
        <div className="text-center py-8 px-4">
            <div className="relative mx-auto size-24 mb-4">
                <svg className="size-24 -rotate-90" viewBox="0 0 72 72">
                    <circle cx="36" cy="36" r={R} fill="none" stroke="currentColor"
                            className="text-ink-100" strokeWidth="5" />
                    <circle cx="36" cy="36" r={R} fill="none" stroke="currentColor"
                            className="text-brand-600 transition-[stroke-dashoffset] duration-1000 ease-linear"
                            strokeWidth="5" strokeLinecap="round"
                            strokeDasharray={C} strokeDashoffset={offset} />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <Smartphone className="text-brand-600 animate-pulse" size={22} />
                    <span className="text-xs font-mono font-semibold text-ink-700 mt-0.5">{clamped}s</span>
                </div>
            </div>
            <p className="text-base font-semibold text-ink-900">
                Prompt sent{phone ? <> to <span className="font-mono">{phone}</span></> : ''}
            </p>
            <p className="text-sm text-ink-500 mt-1">
                Ask the customer to enter their M-Pesa PIN on their phone.
            </p>
            {onCancel && (
                <button
                    onClick={onCancel}
                    className="mt-5 px-3 py-1.5 rounded-lg border border-ink-200 text-xs font-medium text-ink-600 hover:bg-ink-50"
                >
                    Cancel
                </button>
            )}
        </div>
    );
}
