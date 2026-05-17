import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Smartphone, ShieldCheck, AlertCircle, CheckCircle2, Link2,
    Send, Banknote, KeyRound, Globe,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  M-Pesa till administration — admin-only.                                 */
/*  Configures the hospital's own Safaricom till/paybill + Daraja creds.    */
/*  Adds: env (sandbox/prod), shortcode type (paybill/till), test STK, and  */
/*  the C2B URL registration that wires direct-to-till payments to us.     */
/* ────────────────────────────────────────────────────────────────────────── */

const empty = {
    paybill_number: '',
    consumer_key: '',
    consumer_secret: '',
    passkey: '',
    environment: 'sandbox',
    shortcode_type: 'paybill',
    c2b_short_code: '',
    c2b_response_type: 'Completed',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
    kcb_account_number: '',
};

export default function MpesaSettings() {
    const [config, setConfig] = useState(null); // server-side public view
    const [form, setForm] = useState(empty);    // editor state (with secrets)
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testPhone, setTestPhone] = useState('');
    const [testing, setTesting] = useState(false);
    const [registering, setRegistering] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const r = await apiClient.get('/admin/mpesa/config');
            setConfig(r.data);
            // Pre-fill non-secret fields so admins don't have to retype them.
            if (r.data?.configured) {
                setForm(f => ({
                    ...f,
                    paybill_number: r.data.paybill_number || '',
                    environment: r.data.environment || 'sandbox',
                    shortcode_type: r.data.shortcode_type || 'paybill',
                    c2b_short_code: r.data.c2b_short_code || '',
                    c2b_response_type: r.data.c2b_response_type || 'Completed',
                    account_reference: r.data.account_reference || 'HMS-BILLING',
                    transaction_desc: r.data.transaction_desc || 'Hospital Bill Payment',
                    kcb_account_number: r.data.kcb_account_number || '',
                }));
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load M-Pesa config.');
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const save = async () => {
        if (!form.paybill_number || !form.consumer_key || !form.consumer_secret || !form.passkey) {
            return toast.error('Paybill, consumer key, secret and passkey are all required.');
        }
        setSaving(true);
        try {
            await apiClient.post('/admin/mpesa/config', form);
            toast.success('M-Pesa configuration saved.');
            // Clear secrets from the editor — they're encrypted server-side and
            // we deliberately don't echo them back.
            setForm(f => ({ ...f, consumer_key: '', consumer_secret: '', passkey: '' }));
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save.');
        } finally { setSaving(false); }
    };

    const testStk = async () => {
        if (!testPhone) return toast.error('Enter a phone number to send the test STK to.');
        setTesting(true);
        try {
            const r = await apiClient.post('/admin/mpesa/test-stk', { phone_number: testPhone });
            toast.success(`STK push sent. checkout_request_id: ${r.data?.checkout_request_id || '—'}`);
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Test STK push failed.');
            load();
        } finally { setTesting(false); }
    };

    const registerC2B = async () => {
        if (!window.confirm('Push the C2B URLs to Safaricom now? Run this after going live and any time the public URL changes.')) return;
        setRegistering(true);
        try {
            await apiClient.post('/admin/mpesa/register-c2b');
            toast.success('C2B URLs registered with Safaricom.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Daraja registration failed.');
        } finally { setRegistering(false); }
    };

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={Smartphone}
                title="M-Pesa Settings"
                subtitle="Wire this hospital's Safaricom till to MediFleet — Lipa na M-Pesa Online + direct-to-till."
                tone="brand"
            />

            <SafaricomChecklist config={config} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Editor */}
                <div className="lg:col-span-2 bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
                    <SectionHead icon={KeyRound} title="Daraja credentials" />
                    <p className="text-xs text-ink-500 -mt-3">
                        These come from your Safaricom <em>Daraja</em> portal app. Secrets are encrypted at rest;
                        leave the secret fields blank to keep what's already saved.
                    </p>

                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Paybill / Till number *">
                            <input className="input" value={form.paybill_number}
                                   onChange={e => setForm({ ...form, paybill_number: e.target.value })} />
                        </Field>
                        <Field label="Shortcode type">
                            <select className="input" value={form.shortcode_type}
                                    onChange={e => setForm({ ...form, shortcode_type: e.target.value })}>
                                <option value="paybill">PayBill (account # required)</option>
                                <option value="till">Buy Goods / Till (no account #)</option>
                            </select>
                        </Field>
                        <Field label="Consumer key *">
                            <input className="input" value={form.consumer_key} type="password"
                                   onChange={e => setForm({ ...form, consumer_key: e.target.value })} />
                        </Field>
                        <Field label="Consumer secret *">
                            <input className="input" value={form.consumer_secret} type="password"
                                   onChange={e => setForm({ ...form, consumer_secret: e.target.value })} />
                        </Field>
                        <Field label="Passkey *">
                            <input className="input" value={form.passkey} type="password"
                                   onChange={e => setForm({ ...form, passkey: e.target.value })} />
                        </Field>
                        <Field label="Environment">
                            <select className="input" value={form.environment}
                                    onChange={e => setForm({ ...form, environment: e.target.value })}>
                                <option value="sandbox">Sandbox (Daraja test)</option>
                                <option value="production">Production (live)</option>
                            </select>
                        </Field>
                    </div>

                    <SectionHead icon={Link2} title="Direct-to-till routing (C2B)" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="C2B shortcode (optional)">
                            <input className="input" value={form.c2b_short_code}
                                   onChange={e => setForm({ ...form, c2b_short_code: e.target.value })}
                                   placeholder="leave blank to reuse paybill" />
                        </Field>
                        <Field label="Default response">
                            <select className="input" value={form.c2b_response_type}
                                    onChange={e => setForm({ ...form, c2b_response_type: e.target.value })}>
                                <option value="Completed">Completed — accept all payments</option>
                                <option value="Cancelled">Cancelled — validate each one</option>
                            </select>
                        </Field>
                    </div>

                    <SectionHead icon={Banknote} title="Customisation + settlement" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Account reference">
                            <input className="input" value={form.account_reference}
                                   onChange={e => setForm({ ...form, account_reference: e.target.value })} />
                        </Field>
                        <Field label="Transaction description">
                            <input className="input" value={form.transaction_desc}
                                   onChange={e => setForm({ ...form, transaction_desc: e.target.value })} />
                        </Field>
                        <Field label="Settlement bank account #">
                            <input className="input" value={form.kcb_account_number}
                                   onChange={e => setForm({ ...form, kcb_account_number: e.target.value })}
                                   placeholder="reference only — not API-configurable" />
                            <p className="text-xs text-ink-500 mt-1">
                                Stored for receipts and operator reference. Safaricom auto-settles
                                till proceeds to this account on the schedule you set up when applying
                                for the till — that linkage is configured by Safaricom Customer Care,
                                not through this UI.
                            </p>
                        </Field>
                    </div>

                    <div className="flex justify-end pt-2 border-t border-ink-100">
                        <button onClick={save} disabled={saving}
                                className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {saving ? 'Saving…' : 'Save configuration'}
                        </button>
                    </div>
                </div>

                {/* Sidebar: test + register + status */}
                <div className="space-y-4">
                    <StatusCard config={config} loading={loading} />

                    <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5 space-y-3">
                        <SectionHead icon={Send} title="Send a test STK push" />
                        <p className="text-xs text-ink-500">
                            Sends a real KES&nbsp;1 prompt to the phone below using the saved credentials.
                            Doesn't actually charge — the customer can decline.
                        </p>
                        <input className="input" value={testPhone}
                               onChange={e => setTestPhone(e.target.value)}
                               placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                        <button onClick={testStk} disabled={testing}
                                className="w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {testing ? 'Sending…' : 'Send test'}
                        </button>
                        {config?.last_test_at && (
                            <div className="text-xs text-ink-600 pt-2 border-t border-ink-100">
                                <div>Last: <span className="font-mono">{new Date(config.last_test_at).toLocaleString()}</span></div>
                                <div>Status: <strong>{config.last_test_status}</strong></div>
                                {config.last_test_message && (
                                    <div className="text-ink-500 mt-1">{config.last_test_message}</div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5 space-y-3">
                        <SectionHead icon={Link2} title="Register C2B URLs" />
                        <p className="text-xs text-ink-500">
                            Tells Safaricom where to POST direct-to-till payments. Re-run this
                            any time the public callback URL changes.
                        </p>
                        <div className="text-xs text-ink-500">
                            {config?.c2b_registered_at ? (
                                <span className="text-emerald-700 inline-flex items-center gap-1">
                                    <CheckCircle2 size={12} /> Registered {new Date(config.c2b_registered_at).toLocaleString()}
                                </span>
                            ) : (
                                <span className="text-amber-700 inline-flex items-center gap-1">
                                    <AlertCircle size={12} /> Not yet registered
                                </span>
                            )}
                        </div>
                        <button onClick={registerC2B} disabled={registering || !config?.configured}
                                className="w-full px-3 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50 disabled:opacity-60">
                            {registering ? 'Pushing…' : 'Register / Re-register'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}


function SafaricomChecklist({ config }) {
    return (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-amber-900 mb-2 inline-flex items-center gap-2">
                <ShieldCheck size={16} /> Before you start
            </h3>
            <ol className="list-decimal pl-5 text-sm text-amber-900 space-y-1">
                <li>You must already have a Safaricom <strong>PayBill or Buy Goods Till</strong>. Tills are issued via Safaricom Business support and require business registration + KRA PIN — they cannot be created via API.</li>
                <li>Create a <strong>Daraja</strong> app at <code className="bg-amber-100 px-1">developer.safaricom.co.ke</code> linked to your till. Copy the Consumer Key, Consumer Secret, and Lipa-na-M-Pesa Online <strong>Passkey</strong>.</li>
                <li>Your MediFleet deployment must serve <strong>HTTPS publicly</strong> — Safaricom rejects localhost / private callbacks. Set <code className="bg-amber-100 px-1">PUBLIC_BASE_URL</code> in your environment.</li>
                <li>After saving + the test STK works, click <strong>Register / Re-register C2B URLs</strong> to wire direct-to-till payments to us.</li>
            </ol>
            {config?.environment === 'production' && (
                <p className="mt-3 text-xs text-amber-900">
                    ⚠️ You're configured for <strong>production</strong>. Test STKs will charge the customer if accepted (refund manually).
                </p>
            )}
        </div>
    );
}

function StatusCard({ config, loading }) {
    if (loading) return <div className="bg-white border border-ink-200/70 rounded-2xl p-5 text-sm text-ink-500">Loading…</div>;
    if (!config?.configured) {
        return (
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-5 text-sm text-rose-800 inline-flex items-start gap-2">
                <AlertCircle size={16} className="mt-0.5" />
                <div>
                    <div className="font-semibold">Not configured</div>
                    <div className="text-xs mt-1">Fill out the form and click Save to enable M-Pesa payments.</div>
                </div>
            </div>
        );
    }
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl p-5 text-sm space-y-2">
            <div className="flex items-center gap-2 font-semibold text-emerald-700">
                <CheckCircle2 size={16} /> Configured
            </div>
            <div className="text-ink-700">
                <div><span className="text-ink-500">Shortcode:</span> <span className="font-mono">{config.paybill_number}</span> ({config.shortcode_type})</div>
                <div><span className="text-ink-500">Env:</span> <span className="font-mono">{config.environment}</span></div>
                {config.kcb_account_number && (
                    <div><span className="text-ink-500">Settles to:</span> <span className="font-mono">{config.kcb_account_number}</span></div>
                )}
            </div>
            <div className="text-xs text-ink-500 pt-2 border-t border-ink-100 inline-flex items-center gap-1">
                <Globe size={12} /> {config.environment === 'production'
                    ? 'Live Safaricom — payments are real.'
                    : 'Sandbox — no real money moves.'}
            </div>
        </div>
    );
}

function SectionHead({ icon: Icon, title }) {
    return (
        <h3 className="text-sm font-semibold text-ink-900 inline-flex items-center gap-2 border-b border-ink-100 pb-2 w-full">
            <Icon size={16} className="text-brand-600" /> {title}
        </h3>
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
