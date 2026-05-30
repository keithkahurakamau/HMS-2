import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Smartphone, ShieldCheck, AlertCircle, CheckCircle2,
    Send, Banknote, Building2, Hash, Wallet,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  M-Pesa payment settings — hospital-facing.                                */
/*                                                                            */
/*  The hospital enters only its OWN Safaricom till (PayBill / Buy-Goods)     */
/*  and the bank account where proceeds settle. The payment aggregator that   */
/*  MediFleet uses behind the scenes is never surfaced here — activation is   */
/*  handled by the MediFleet team, and this page simply reflects whether      */
/*  M-Pesa is live for the hospital.                                          */
/* ────────────────────────────────────────────────────────────────────────── */

const empty = {
    shortcode: '',
    shortcode_type: 'paybill',
    settlement_bank_code: '',
    settlement_account_number: '',
    settlement_account_name: '',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
};

export default function MpesaSettings() {
    const [config, setConfig] = useState(null); // server-side public view
    const [form, setForm] = useState(empty);     // editor state
    const [banks, setBanks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testPhone, setTestPhone] = useState('');
    const [testing, setTesting] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [cfg, bnk] = await Promise.all([
                apiClient.get('/admin/payhero/config'),
                apiClient.get('/admin/payhero/banks'),
            ]);
            setConfig(cfg.data);
            setBanks(bnk.data?.banks || []);
            if (cfg.data?.configured) {
                setForm(f => ({
                    ...f,
                    shortcode: cfg.data.shortcode || '',
                    shortcode_type: cfg.data.shortcode_type || 'paybill',
                    settlement_bank_code: cfg.data.settlement_bank_code || '',
                    settlement_account_number: cfg.data.settlement_account_number || '',
                    settlement_account_name: cfg.data.settlement_account_name || '',
                    account_reference: cfg.data.account_reference || 'HMS-BILLING',
                    transaction_desc: cfg.data.transaction_desc || 'Hospital Bill Payment',
                }));
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load M-Pesa settings.');
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const save = async () => {
        if (!form.shortcode || !form.settlement_bank_code || !form.settlement_account_number) {
            return toast.error('Shortcode, settlement bank, and account number are required.');
        }
        setSaving(true);
        try {
            await apiClient.post('/admin/payhero/config', form);
            toast.success('M-Pesa settings saved.');
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save.');
        } finally { setSaving(false); }
    };

    const testStk = async () => {
        if (!testPhone) return toast.error('Enter a phone number to send the test prompt to.');
        setTesting(true);
        try {
            await apiClient.post('/admin/payhero/test-stk', { phone_number: testPhone });
            toast.success(`Test M-Pesa prompt sent to ${testPhone}.`);
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Test prompt failed.');
            load();
        } finally { setTesting(false); }
    };

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={Smartphone}
                title="M-Pesa Payments"
                subtitle="Connect this hospital's Safaricom till so you can collect M-Pesa at the till and pharmacy."
                tone="brand"
            />

            <MpesaChecklist />
            <MoneyFlowNote />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Editor */}
                <div data-tour="mpesa-editor" className="lg:col-span-2 bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
                    <div data-tour="mpesa-shortcode">
                    <SectionHead icon={Hash} title="Your Safaricom shortcode" />
                    <p className="text-xs text-ink-500 -mt-3">
                        Enter the PayBill or Buy-Goods Till you already own. Payments made
                        to this shortcode are routed into MediFleet.
                    </p>

                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Shortcode (PayBill / Till) *">
                            <input className="input" value={form.shortcode}
                                   onChange={e => setForm({ ...form, shortcode: e.target.value })}
                                   placeholder="e.g. 247247 or 5123456" />
                        </Field>
                        <Field label="Shortcode type">
                            <select className="input" value={form.shortcode_type}
                                    onChange={e => setForm({ ...form, shortcode_type: e.target.value })}>
                                <option value="paybill">PayBill (account # required)</option>
                                <option value="till">Buy Goods / Till (no account #)</option>
                            </select>
                        </Field>
                    </div>
                    <p className="text-xs text-ink-500 -mt-2 inline-flex items-start gap-1.5">
                        <ShieldCheck size={13} className="mt-0.5 text-brand-600 shrink-0" />
                        MediFleet activates M-Pesa for your till on its end — there's nothing
                        else for you to set up or copy from anywhere.
                    </p>
                    </div>

                    <div data-tour="mpesa-settlement">
                    <SectionHead icon={Building2} title="Settlement bank" />
                    <p className="text-xs text-ink-500 -mt-3">
                        Proceeds are deposited into <strong>your hospital's own bank account</strong> on the
                        settlement schedule agreed at onboarding. MediFleet never holds your money —
                        it routes the payment and settles straight to you.
                    </p>

                    <div className="grid grid-cols-2 gap-3 mt-3">
                        <Field label="Bank *">
                            <select className="input" value={form.settlement_bank_code}
                                    onChange={e => setForm({ ...form, settlement_bank_code: e.target.value })}>
                                <option value="">— select bank —</option>
                                {banks.map(b => (
                                    <option key={b.code} value={b.code}>{b.name}</option>
                                ))}
                            </select>
                        </Field>
                        <Field label="Account number *">
                            <input className="input" value={form.settlement_account_number}
                                   onChange={e => setForm({ ...form, settlement_account_number: e.target.value })} />
                        </Field>
                        <Field label="Account name">
                            <input className="input" value={form.settlement_account_name}
                                   onChange={e => setForm({ ...form, settlement_account_name: e.target.value })}
                                   placeholder="as it appears on the bank statement" />
                        </Field>
                    </div>
                    </div>

                    <SectionHead icon={Banknote} title="Customisation" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Account reference">
                            <input className="input" value={form.account_reference}
                                   onChange={e => setForm({ ...form, account_reference: e.target.value })} />
                        </Field>
                        <Field label="Transaction description">
                            <input className="input" value={form.transaction_desc}
                                   onChange={e => setForm({ ...form, transaction_desc: e.target.value })} />
                        </Field>
                    </div>

                    <div className="flex justify-end pt-2 border-t border-ink-100">
                        <button onClick={save} disabled={saving}
                                className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {saving ? 'Saving…' : 'Save settings'}
                        </button>
                    </div>
                </div>

                {/* Sidebar: status + test */}
                <div className="space-y-4">
                    <div data-tour="mpesa-status"><StatusCard config={config} loading={loading} /></div>

                    <div data-tour="mpesa-test" className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5 space-y-3">
                        <SectionHead icon={Send} title="Send a test M-Pesa prompt" />
                        <p className="text-xs text-ink-500">
                            Sends a real KES&nbsp;1 prompt to the phone below. It doesn't
                            actually charge — the customer can decline.
                        </p>
                        <input className="input" value={testPhone}
                               onChange={e => setTestPhone(e.target.value)}
                               placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                        <button onClick={testStk} disabled={testing || !config?.mpesa_active}
                                className="w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {testing ? 'Sending…' : 'Send test'}
                        </button>
                        {config?.configured && !config?.mpesa_active && (
                            <p className="text-xs text-amber-700">
                                The test prompt unlocks once MediFleet activates M-Pesa for your till.
                            </p>
                        )}
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
                </div>
            </div>
        </div>
    );
}


function MoneyFlowNote() {
    return (
        <div data-tour="mpesa-flow" className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-emerald-900 mb-2 inline-flex items-center gap-2">
                <Wallet size={16} /> How your money flows
            </h3>
            <p className="text-sm text-emerald-900 leading-relaxed">
                When a patient pays by M-Pesa, the money goes through your own Safaricom
                shortcode and settles directly into <strong>your hospital's bank account</strong> on
                your settlement schedule. <strong>MediFleet never holds or touches your money</strong> —
                the platform only triggers the payment prompt and shows you a live status as it
                completes. The only thing MediFleet bills you for is your subscription.
            </p>
        </div>
    );
}

function MpesaChecklist() {
    return (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-amber-900 mb-2 inline-flex items-center gap-2">
                <ShieldCheck size={16} /> Before you start
            </h3>
            <ol className="list-decimal pl-5 text-sm text-amber-900 space-y-1">
                <li>You must already have a Safaricom <strong>PayBill or Buy Goods Till</strong>. Tills are issued via Safaricom Business support and require business registration + KRA PIN.</li>
                <li>Enter that shortcode and your settlement bank below, then save. <strong>MediFleet</strong> takes care of activating M-Pesa for your till on its end.</li>
                <li>The settlement schedule (daily / weekly) is agreed during onboarding and managed by MediFleet.</li>
                <li>Once MediFleet confirms M-Pesa is active, send a test KES&nbsp;1 prompt to your own number to verify end-to-end.</li>
            </ol>
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
                    <div className="text-xs mt-1">Fill out the form and click Save to start setting up M-Pesa payments.</div>
                </div>
            </div>
        );
    }
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl p-5 text-sm space-y-2">
            <div className="flex items-center gap-2 font-semibold text-emerald-700">
                <CheckCircle2 size={16} /> Saved
            </div>
            <div className="text-ink-700">
                <div><span className="text-ink-500">Shortcode:</span> <span className="font-mono">{config.shortcode}</span> ({config.shortcode_type})</div>
                <div><span className="text-ink-500">Settles to:</span> <span className="font-mono">{config.settlement_bank_name} · {config.settlement_account_number}</span></div>
            </div>
            {config.mpesa_active ? (
                <div className="text-xs inline-flex items-center gap-1.5 text-emerald-700 pt-2 border-t border-ink-100 w-full">
                    <CheckCircle2 size={14} /> M-Pesa is live — you can collect payments at the till and pharmacy.
                </div>
            ) : (
                <div className="text-xs inline-flex items-start gap-1.5 text-amber-700 pt-2 border-t border-ink-100 w-full">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    Awaiting MediFleet to activate M-Pesa for your till. Collection stays disabled until then.
                </div>
            )}
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
