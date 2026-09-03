import React, { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
    Smartphone, ShieldCheck, AlertCircle, AlertTriangle, CheckCircle2,
    Send, Hash, Key, Link2, RefreshCw, Copy, Undo2,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import {
    getConfig, saveConfig, getC2bReadiness, getCallbackUrls, registerC2b,
    rotateToken, testStk, newIdempotencyKey,
} from '../api/mpesa';

/* ────────────────────────────────────────────────────────────────────────── */
/*  M-Pesa payment settings: hospital-facing, against the Daraja config.      */
/*                                                                            */
/*  This is the ONE rail this app surfaces for collecting M-Pesa. Pay Hero    */
/*  still runs underneath until it is removed, but nothing here, and nothing  */
/*  on the Billing or Pharmacy checkout screens, ever offers it: showing      */
/*  both rails is how the same invoice gets paid twice on two independent    */
/*  prompts, and there is no cross-rail guard against that.                  */
/* ────────────────────────────────────────────────────────────────────────── */

const emptyForm = {
    shortcode: '',
    shortcode_type: 'paybill',
    environment: 'sandbox',
    consumer_key: '',
    consumer_secret: '',
    passkey: '',
    initiator_name: '',
    initiator_password: '',
    refunds_enabled: false,
    refund_max_amount: '10000.00',
    refund_daily_cap: '50000.00',
    refund_dual_approval_above: '5000.00',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
};

// Vite stamps this true only for a production build; a hospital running a
// production deployment on a sandbox till is a "forgot to flip the switch
// before go-live" state worth calling out, not a hard error.
const IS_PRODUCTION_DEPLOYMENT = import.meta.env.PROD;

// Module-scope, not rebuilt per render: every URL row (masked or revealed)
// copies through this one function.
const copyToClipboard = (text) => {
    navigator.clipboard?.writeText(text);
    toast.success('Copied.');
};

export default function MpesaSettings() {
    const [config, setConfig] = useState(null);
    const [form, setForm] = useState(emptyForm);
    const [readiness, setReadiness] = useState([]);
    const [callbackTills, setCallbackTills] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testPhone, setTestPhone] = useState('');
    const [testing, setTesting] = useState(false);
    const [rotateOpen, setRotateOpen] = useState(false);
    const [revealed, setRevealed] = useState(null); // rotate-token's once-only response

    const testKeyRef = useRef(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [cfg, ready, urls] = await Promise.all([
                getConfig(), getC2bReadiness(), getCallbackUrls(),
            ]);
            setConfig(cfg);
            setReadiness(Array.isArray(ready) ? ready : []);
            setCallbackTills(urls?.tills || []);
            if (cfg?.configured) {
                setForm((f) => ({
                    ...f,
                    shortcode: cfg.shortcode || '',
                    shortcode_type: cfg.shortcode_type || 'paybill',
                    environment: cfg.environment || 'sandbox',
                    initiator_name: cfg.initiator_name || '',
                    refunds_enabled: !!cfg.refunds_enabled,
                    refund_max_amount: cfg.refund_max_amount ?? f.refund_max_amount,
                    refund_daily_cap: cfg.refund_daily_cap ?? f.refund_daily_cap,
                    refund_dual_approval_above: cfg.refund_dual_approval_above ?? f.refund_dual_approval_above,
                    account_reference: cfg.account_reference || 'HMS-BILLING',
                    transaction_desc: cfg.transaction_desc || 'Hospital Bill Payment',
                    // Secrets are never round-tripped: leaving these blank on
                    // save means "keep what's already stored".
                    consumer_key: '', consumer_secret: '', passkey: '', initiator_password: '',
                }));
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load M-Pesa settings.');
        } finally { setLoading(false); }
    }, []);

    useEffect(() => { load(); }, [load]);

    const save = async () => {
        if (!form.shortcode) return toast.error('Shortcode is required.');
        setSaving(true);
        try {
            await saveConfig(form);
            toast.success('M-Pesa settings saved.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save.');
        } finally { setSaving(false); }
    };

    const runTestPush = async () => {
        if (!testPhone) return toast.error('Enter a phone number to send the test prompt to.');
        if (!testKeyRef.current) testKeyRef.current = newIdempotencyKey();
        setTesting(true);
        try {
            await testStk({ phone_number: testPhone, idempotency_key: testKeyRef.current });
            toast.success(`Test M-Pesa prompt sent to ${testPhone}.`);
            testKeyRef.current = null; // this attempt is done; the next click is a new one
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Test prompt failed.');
            testKeyRef.current = null;
            load();
        } finally { setTesting(false); }
    };

    const doRegisterC2b = async () => {
        try {
            await registerC2b();
            toast.success('C2B URLs registered with Safaricom.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not register C2B URLs.');
        }
    };

    const doRotate = async (alsoRegister) => {
        try {
            const result = await rotateToken();
            setRevealed(result);
            setRotateOpen(false);
            if (alsoRegister) {
                await registerC2b();
                toast.success('Token rotated and C2B URLs re-registered.');
            } else {
                toast.success('Token rotated.');
            }
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not rotate the token.');
        }
    };

    const brokenTills = readiness.filter((t) => t.c2b_urls_registered_at && !t.verification_ready);

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={Smartphone}
                title="M-Pesa Payments"
                subtitle="Connect this hospital's Safaricom till so you can collect M-Pesa at the till and pharmacy."
                tone="brand"
            />

            {brokenTills.length > 0 && <C2bBrokenBanner tills={brokenTills} />}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <ShortcodeSection form={form} setForm={setForm} />
                    <EnvironmentSection form={form} setForm={setForm} />
                    <CredentialsSection form={form} setForm={setForm} config={config} />
                    <CallbackUrlsSection
                        tills={callbackTills}
                        onRegisterC2b={doRegisterC2b}
                        onOpenRotate={() => setRotateOpen(true)}
                    />
                    <RefundControlsSection form={form} setForm={setForm} />

                    <div className="flex justify-end pt-2 border-t border-ink-100 dark:border-ink-800">
                        <button type="button" onClick={save} disabled={saving}
                                className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {saving ? 'Saving…' : 'Save settings'}
                        </button>
                    </div>
                </div>

                <div className="space-y-4">
                    <StatusCard config={config} loading={loading} />
                    <TestPushCard
                        testPhone={testPhone} setTestPhone={setTestPhone}
                        testing={testing} runTestPush={runTestPush} config={config}
                    />
                </div>
            </div>

            {rotateOpen && (
                <RotateConfirmDialog onCancel={() => setRotateOpen(false)} onConfirm={doRotate} />
            )}

            {revealed && (
                <RevealedTokenPanel result={revealed} onDismiss={() => setRevealed(null)} />
            )}
        </div>
    );
}

/* ─── C2B readiness blocker ──────────────────────────────────────────────── */

function C2bBrokenBanner({ tills }) {
    return (
        <div role="alert" className="bg-rose-50 dark:bg-rose-500/10 border-2 border-rose-300 dark:border-rose-500/40 rounded-xl p-5">
            <h3 className="text-sm font-bold text-rose-900 dark:text-rose-300 mb-2 inline-flex items-center gap-2">
                <AlertTriangle size={18} /> Walk-in payments cannot be verified
            </h3>
            <p className="text-sm text-rose-900 dark:text-rose-200 leading-relaxed">
                {tills.length === 1 ? 'This till has' : `${tills.length} tills have`} C2B registered
                with Safaricom but no initiator credentials. A payment made directly to{' '}
                {tills.map((t) => t.shortcode).join(', ')} will be taken from the patient and will
                never verify or settle: it sits on the unmatched-receipt queue forever. Add the
                initiator name and password under Credentials below, then save.
            </p>
        </div>
    );
}

/* ─── Shortcode ──────────────────────────────────────────────────────────── */

function ShortcodeSection({ form, setForm }) {
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-3">
            <SectionHead icon={Hash} title="Your Safaricom shortcode" />
            <div className="grid grid-cols-2 gap-3">
                <Field label="Shortcode (PayBill / Till) *">
                    <input aria-label="Shortcode (PayBill / Till) *" className="input" value={form.shortcode}
                           onChange={(e) => setForm({ ...form, shortcode: e.target.value })}
                           placeholder="e.g. 247247 or 5123456" />
                </Field>
                <Field label="Shortcode type">
                    <select className="input" value={form.shortcode_type}
                            onChange={(e) => setForm({ ...form, shortcode_type: e.target.value })}>
                        <option value="paybill">PayBill (account # required)</option>
                        <option value="till">Buy Goods / Till (no account #)</option>
                    </select>
                </Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
                <Field label="Account reference">
                    <input aria-label="Account reference" className="input" value={form.account_reference}
                           onChange={(e) => setForm({ ...form, account_reference: e.target.value })} />
                </Field>
                <Field label="Transaction description">
                    <input aria-label="Transaction description" className="input" value={form.transaction_desc}
                           onChange={(e) => setForm({ ...form, transaction_desc: e.target.value })} />
                </Field>
            </div>
        </div>
    );
}

/* ─── Environment ────────────────────────────────────────────────────────── */

function EnvironmentSection({ form, setForm }) {
    const warn = IS_PRODUCTION_DEPLOYMENT && form.environment === 'sandbox';
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-3">
            <SectionHead icon={ShieldCheck} title="Environment" />
            <Field label="Daraja environment">
                <select className="input max-w-xs" value={form.environment}
                        onChange={(e) => setForm({ ...form, environment: e.target.value })}>
                    <option value="sandbox">Sandbox (testing)</option>
                    <option value="production">Production (real money)</option>
                </select>
            </Field>
            {warn && (
                <p role="alert" className="text-xs inline-flex items-start gap-1.5 text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg p-2.5">
                    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                    This is a production MediFleet deployment, but this till is set to Sandbox.
                    No real money moves on a sandbox till. Switch to Production once this
                    hospital has completed Safaricom Go-Live.
                </p>
            )}
        </div>
    );
}

/* ─── Credentials ────────────────────────────────────────────────────────── */

function CredentialsSection({ form, setForm, config }) {
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-3">
            <SectionHead icon={Key} title="Daraja credentials" />
            <p className="text-xs text-ink-500 dark:text-ink-400 -mt-2">
                From the Safaricom developer portal for this till. Leave a field blank to keep
                what is already stored, values are never shown back once saved.
            </p>
            <div className="grid grid-cols-2 gap-3">
                <SecretField label="Consumer key" isSet={config?.has_consumer_key} value={form.consumer_key}
                             onChange={(v) => setForm({ ...form, consumer_key: v })} />
                <SecretField label="Consumer secret" isSet={config?.has_consumer_secret} value={form.consumer_secret}
                             onChange={(v) => setForm({ ...form, consumer_secret: v })} />
                <SecretField label="Passkey" isSet={config?.has_passkey} value={form.passkey}
                             onChange={(v) => setForm({ ...form, passkey: v })} />
                <Field label="Initiator name">
                    <input aria-label="Initiator name" className="input" value={form.initiator_name}
                           onChange={(e) => setForm({ ...form, initiator_name: e.target.value })} />
                </Field>
                <SecretField label="Initiator password" isSet={config?.has_initiator_password} value={form.initiator_password}
                             onChange={(v) => setForm({ ...form, initiator_password: v })} />
            </div>
            <p className="text-xs text-ink-500 dark:text-ink-400">
                The initiator name and password are required to verify a walk-in (C2B) payment.
                Without them, a payment made directly to this till can never settle.
            </p>
        </div>
    );
}

function SecretField({ label, isSet, value, onChange }) {
    return (
        <Field label={label}>
            <div className="relative">
                <input type="password" aria-label={label} className="input pr-16" value={value}
                       onChange={(e) => onChange(e.target.value)}
                       placeholder={isSet ? 'Leave blank to keep the saved value' : 'Not set'} />
                <span className={`absolute right-2 top-1/2 -translate-y-1/2 text-2xs font-semibold uppercase tracking-wide ${isSet ? 'text-emerald-600' : 'text-ink-400'}`}>
                    {isSet ? 'Set' : 'Not set'}
                </span>
            </div>
        </Field>
    );
}

/* ─── Callback URLs + rotation ───────────────────────────────────────────── */

function CallbackUrlsSection({ tills, onRegisterC2b, onOpenRotate }) {
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-3">
            <SectionHead icon={Link2} title="Callback URLs" />
            <p className="text-xs text-ink-500 dark:text-ink-400 -mt-2">
                Register these with Safaricom so payment results reach MediFleet. The token
                segment is masked here; it is shown once, in full, right after a rotation.
            </p>
            <div className="flex gap-2">
                <button type="button" onClick={onRegisterC2b} className="btn-secondary btn-xs">
                    Register C2B URLs with Safaricom
                </button>
                <button type="button" onClick={onOpenRotate} className="btn-danger-ghost btn-xs">
                    <RefreshCw size={13} /> Rotate callback token
                </button>
            </div>
            {tills.length === 0 ? (
                <p className="text-xs text-ink-500 dark:text-ink-400">Save the shortcode above to generate callback URLs.</p>
            ) : (
                <div className="space-y-4">
                    {tills.map((t) => (
                        <div key={t.config_id} className="rounded-lg border border-ink-100 dark:border-ink-800 p-3 space-y-1.5">
                            <div className="flex items-center justify-between text-xs">
                                <span className="font-semibold text-ink-700 dark:text-ink-200">
                                    {t.shortcode}{t.department_id ? ` (department till)` : ' (hospital default)'}
                                </span>
                                <span className="text-ink-400 tnum">
                                    Token last rotated: {t.callback_token_rotated_at
                                        ? new Date(t.callback_token_rotated_at).toLocaleString()
                                        : 'never'}
                                </span>
                            </div>
                            {t.error ? (
                                <p className="text-xs text-rose-600">{t.error}</p>
                            ) : (
                                [
                                    ['STK callback', t.stk_callback_url],
                                    ['C2B validation', t.c2b_validation_url],
                                    ['C2B confirmation', t.c2b_confirmation_url],
                                    ['Status result', t.status_result_url],
                                    ['Status timeout', t.status_timeout_url],
                                ].map(([label, url]) => (
                                    <div key={label} className="flex items-center gap-2">
                                        <span className="text-2xs w-28 shrink-0 text-ink-500 dark:text-ink-400">{label}</span>
                                        <code className="flex-1 text-2xs font-mono truncate text-ink-600 dark:text-ink-300">{url}</code>
                                        <button type="button" onClick={() => copyToClipboard(url)} aria-label={`Copy ${label} URL`}
                                                className="text-ink-400 hover:text-brand-600 shrink-0">
                                            <Copy size={13} />
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function RotateConfirmDialog({ onCancel, onConfirm }) {
    const dialogRef = useRef(null);
    const confirmRef = useRef(null);
    const previouslyFocused = useRef(null);
    const [alsoRegister, setAlsoRegister] = useState(true);

    useEffect(() => {
        previouslyFocused.current = document.activeElement;
        confirmRef.current?.focus();
        const onKeyDown = (e) => { if (e.key === 'Escape') onCancel(); };
        document.addEventListener('keydown', onKeyDown);
        return () => {
            document.removeEventListener('keydown', onKeyDown);
            const toRestore = previouslyFocused.current;
            if (toRestore && typeof toRestore.focus === 'function' && document.contains(toRestore)) {
                toRestore.focus();
            }
        };
    }, [onCancel]);

    const handleTrap = (e) => {
        if (e.key !== 'Tab' || !dialogRef.current) return;
        const focusables = Array.from(dialogRef.current.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled])',
        ));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const inside = dialogRef.current.contains(document.activeElement);
        if (e.shiftKey) {
            if (!inside || document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else if (!inside || document.activeElement === last) { e.preventDefault(); first.focus(); }
    };

    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby="rotate-title"
                 onKeyDown={handleTrap}
                 className="bg-white dark:bg-ink-900 rounded-xl shadow-overlay w-full max-w-md p-6 space-y-4">
                <h3 id="rotate-title" className="text-base font-semibold text-ink-900 dark:text-white inline-flex items-center gap-2">
                    <AlertTriangle size={18} className="text-amber-600" /> Rotate the callback token?
                </h3>
                <p className="text-sm text-ink-600 dark:text-ink-300">
                    Rotating invalidates every callback URL currently registered with Safaricom
                    for this till: STK, C2B, and status URLs all stop working the moment this
                    completes. Safaricom will not be able to reach MediFleet again until the
                    C2B URLs are re-registered.
                </p>
                <label className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-200">
                    <input type="checkbox" checked={alsoRegister} onChange={(e) => setAlsoRegister(e.target.checked)} />
                    Re-register C2B URLs with Safaricom right after rotating
                </label>
                <div className="flex justify-end gap-2 pt-2">
                    <button type="button" onClick={onCancel}
                            className="px-3 py-2 rounded-lg border border-ink-200 dark:border-ink-800 text-sm font-medium hover:bg-ink-50 dark:hover:bg-ink-800/50">
                        Cancel
                    </button>
                    <button ref={confirmRef} type="button" onClick={() => onConfirm(alsoRegister)}
                            className="px-3 py-2 rounded-lg bg-rose-600 text-white text-sm font-medium hover:bg-rose-700">
                        Rotate token
                    </button>
                </div>
            </div>
        </div>
    );
}

function RevealedTokenPanel({ result, onDismiss }) {
    const urls = result?.urls;
    return (
        <div role="alert" className="bg-emerald-50 dark:bg-emerald-500/10 border-2 border-emerald-300 dark:border-emerald-500/30 rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-emerald-900 dark:text-emerald-300 inline-flex items-center gap-2">
                <ShieldCheck size={16} /> New token, shown once
            </h3>
            <p className="text-sm text-emerald-900 dark:text-emerald-200">{result?.message}</p>
            {urls && !urls.error && (
                <div className="space-y-1.5">
                    {[
                        ['STK callback', urls.stk_callback_url],
                        ['C2B validation', urls.c2b_validation_url],
                        ['C2B confirmation', urls.c2b_confirmation_url],
                        ['Status result', urls.status_result_url],
                        ['Status timeout', urls.status_timeout_url],
                    ].map(([label, url]) => (
                        <div key={label} className="flex items-center gap-2">
                            <span className="text-2xs w-28 shrink-0 text-emerald-800 dark:text-emerald-300">{label}</span>
                            <code className="flex-1 text-2xs font-mono truncate text-emerald-900 dark:text-emerald-100">{url}</code>
                            <button type="button" onClick={() => copyToClipboard(url)} aria-label={`Copy ${label} URL`}
                                    className="text-emerald-700 hover:text-emerald-900 shrink-0">
                                <Copy size={13} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
            <div className="flex justify-end">
                <button type="button" onClick={onDismiss} className="btn-secondary btn-xs">I've copied this, dismiss</button>
            </div>
        </div>
    );
}

/* ─── Refund controls ────────────────────────────────────────────────────── */

function RefundControlsSection({ form, setForm }) {
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-3">
            <SectionHead icon={Undo2} title="Refund controls" />
            <label className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-200">
                <input type="checkbox" checked={form.refunds_enabled}
                       onChange={(e) => setForm({ ...form, refunds_enabled: e.target.checked })} />
                Allow refunds from this till
            </label>
            <div className="grid grid-cols-3 gap-3">
                <Field label="Max amount per refund (KES)">
                    <input type="number" min="0" step="0.01" className="input tnum" value={form.refund_max_amount}
                           onChange={(e) => setForm({ ...form, refund_max_amount: e.target.value })} />
                </Field>
                <Field label="Daily cap (KES)">
                    <input type="number" min="0" step="0.01" className="input tnum" value={form.refund_daily_cap}
                           onChange={(e) => setForm({ ...form, refund_daily_cap: e.target.value })} />
                </Field>
                <Field label="Requires a second approver above (KES)">
                    <input type="number" min="0" step="0.01" className="input tnum" value={form.refund_dual_approval_above}
                           onChange={(e) => setForm({ ...form, refund_dual_approval_above: e.target.value })} />
                </Field>
            </div>
        </div>
    );
}

/* ─── Sidebar ────────────────────────────────────────────────────────────── */

function StatusCard({ config, loading }) {
    if (loading) return <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-5 text-sm text-ink-500 dark:text-ink-400">Loading…</div>;
    if (!config?.configured) {
        return (
            <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-xl p-5 text-sm text-rose-800 dark:text-rose-300 inline-flex items-start gap-2">
                <AlertCircle size={16} className="mt-0.5" />
                <div>
                    <div className="font-semibold">Not configured</div>
                    <div className="text-xs mt-1">Fill out the form and click Save to start setting up M-Pesa payments.</div>
                </div>
            </div>
        );
    }
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-5 text-sm space-y-2">
            <div className="flex items-center gap-2 font-semibold text-emerald-700 dark:text-emerald-300">
                <CheckCircle2 size={16} /> Saved
            </div>
            <div className="text-ink-700 dark:text-ink-200">
                <div><span className="text-ink-500 dark:text-ink-400">Shortcode:</span> <span className="font-mono">{config.shortcode}</span> ({config.shortcode_type})</div>
                <div><span className="text-ink-500 dark:text-ink-400">Environment:</span> {config.environment}</div>
            </div>
            {config.mpesa_active ? (
                <div className="text-xs inline-flex items-center gap-1.5 text-emerald-700 dark:text-emerald-300 pt-2 border-t border-ink-100 dark:border-ink-800 w-full">
                    <CheckCircle2 size={14} /> M-Pesa is live, you can collect payments at the till and pharmacy.
                </div>
            ) : (
                <div className="text-xs inline-flex items-start gap-1.5 text-amber-700 dark:text-amber-300 pt-2 border-t border-ink-100 dark:border-ink-800 w-full">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    Consumer key, consumer secret, and passkey are all required before collection goes live.
                </div>
            )}
        </div>
    );
}

function TestPushCard({ testPhone, setTestPhone, testing, runTestPush, config }) {
    return (
        <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-5 space-y-3">
            <SectionHead icon={Send} title="Send a test M-Pesa prompt" />
            <p className="text-xs text-ink-500 dark:text-ink-400">
                Sends a real KES&nbsp;1 prompt to the phone below, with no invoice attached. It
                doesn't actually charge anything of consequence: the customer can decline.
            </p>
            <input aria-label="07XXXXXXXX or 2547XXXXXXXX" className="input" value={testPhone}
                   onChange={(e) => setTestPhone(e.target.value)}
                   placeholder="07XXXXXXXX or 2547XXXXXXXX" />
            <button type="button" onClick={runTestPush} disabled={testing || !config?.mpesa_active}
                    className="w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                {testing ? 'Sending…' : 'Send test'}
            </button>
            {config?.configured && !config?.mpesa_active && (
                <p className="text-xs text-amber-700 dark:text-amber-300">
                    The test prompt unlocks once all three Daraja credentials are saved.
                </p>
            )}
            {config?.last_test_at && (
                <div className="text-xs text-ink-600 dark:text-ink-400 pt-2 border-t border-ink-100 dark:border-ink-800">
                    <div>Last: <span className="font-mono">{new Date(config.last_test_at).toLocaleString()}</span></div>
                    <div>Status: <strong>{config.last_test_status}</strong></div>
                    {config.last_test_message && (
                        <div className="text-ink-500 dark:text-ink-400 mt-1">{config.last_test_message}</div>
                    )}
                </div>
            )}
        </div>
    );
}

/* ─── Shared bits ────────────────────────────────────────────────────────── */

function SectionHead({ icon: Icon, title }) {
    return (
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white inline-flex items-center gap-2 border-b border-ink-100 dark:border-ink-800 pb-2 w-full">
            <Icon size={16} className="text-brand-600" /> {title}
        </h3>
    );
}

function Field({ label, children }) {
    return (
        <label className="block">
            <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">{label}</span>
            {children}
        </label>
    );
}
