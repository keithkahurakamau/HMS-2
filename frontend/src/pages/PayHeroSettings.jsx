import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Smartphone, ShieldCheck, AlertCircle, CheckCircle2,
    Send, Banknote, Building2, Hash,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Pay Hero settings — per-tenant admin.                                    */
/*  Each tenant pastes the Safaricom shortcode (their existing PayBill or    */
/*  Buy-Goods till), the Pay Hero channel id assigned to that shortcode,    */
/*  and picks the settlement bank + account number where Pay Hero deposits  */
/*  proceeds. Optional per-tenant Pay Hero API creds override the platform  */
/*  default.                                                                 */
/* ────────────────────────────────────────────────────────────────────────── */

const empty = {
    shortcode: '',
    shortcode_type: 'paybill',
    payhero_username: '',
    payhero_password: '',
    settlement_bank_code: '',
    settlement_account_number: '',
    settlement_account_name: '',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
};

export default function PayHeroSettings() {
    const [config, setConfig] = useState(null); // server-side public view
    const [form, setForm] = useState(empty);    // editor state (with secrets)
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
            toast.error(err?.response?.data?.detail || 'Could not load Pay Hero config.');
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
            toast.success('Pay Hero configuration saved.');
            // Clear creds from the editor — they're encrypted server-side and
            // we deliberately don't echo them back.
            setForm(f => ({ ...f, payhero_username: '', payhero_password: '' }));
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save.');
        } finally { setSaving(false); }
    };

    const testStk = async () => {
        if (!testPhone) return toast.error('Enter a phone number to send the test STK to.');
        setTesting(true);
        try {
            const r = await apiClient.post('/admin/payhero/test-stk', { phone_number: testPhone });
            toast.success(`STK push sent. reference: ${r.data?.reference || r.data?.external_reference || '—'}`);
            load();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Test STK push failed.');
            load();
        } finally { setTesting(false); }
    };

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Finance"
                icon={Smartphone}
                title="Pay Hero Settings"
                subtitle="Wire this hospital's Safaricom till to MediFleet through the Pay Hero aggregator."
                tone="brand"
            />

            <PayHeroChecklist />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Editor */}
                <div className="lg:col-span-2 bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
                    <SectionHead icon={Hash} title="Your Safaricom shortcode" />
                    <p className="text-xs text-ink-500 -mt-3">
                        Enter the PayBill or Buy-Goods Till you already own. Pay Hero will
                        route payments made to this shortcode into MediFleet.
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
                        MediFleet links your till to Pay Hero and provisions the channel for
                        you — you don't need a Pay Hero channel id here.
                    </p>

                    <SectionHead icon={Building2} title="Settlement bank" />
                    <p className="text-xs text-ink-500 -mt-3">
                        Pay Hero deposits till proceeds into this bank account on the
                        settlement schedule you agreed at onboarding.
                    </p>

                    <div className="grid grid-cols-2 gap-3">
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

                    <SectionHead icon={ShieldCheck} title="Per-tenant Pay Hero credentials (optional)" />
                    <p className="text-xs text-ink-500 -mt-3">
                        Leave blank to use MediFleet's platform Pay Hero account. Fill in
                        only if you have your own Pay Hero merchant credentials — they're
                        encrypted at rest and never echoed back.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Pay Hero username">
                            <input className="input" type="password" value={form.payhero_username}
                                   onChange={e => setForm({ ...form, payhero_username: e.target.value })} />
                        </Field>
                        <Field label="Pay Hero password">
                            <input className="input" type="password" value={form.payhero_password}
                                   onChange={e => setForm({ ...form, payhero_password: e.target.value })} />
                        </Field>
                    </div>

                    <div className="flex justify-end pt-2 border-t border-ink-100">
                        <button onClick={save} disabled={saving}
                                className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {saving ? 'Saving…' : 'Save configuration'}
                        </button>
                    </div>
                </div>

                {/* Sidebar: test + status */}
                <div className="space-y-4">
                    <StatusCard config={config} loading={loading} />

                    <div className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5 space-y-3">
                        <SectionHead icon={Send} title="Send a test STK push" />
                        <p className="text-xs text-ink-500">
                            Sends a real KES&nbsp;1 prompt to the phone below using the saved
                            credentials. Doesn't actually charge — the customer can decline.
                        </p>
                        <input className="input" value={testPhone}
                               onChange={e => setTestPhone(e.target.value)}
                               placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                        <button onClick={testStk} disabled={testing || !config?.configured || !config?.payhero_channel_id}
                                className="w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                            {testing ? 'Sending…' : 'Send test'}
                        </button>
                        {config?.configured && !config?.payhero_channel_id && (
                            <p className="text-xs text-amber-700">
                                The test push unlocks once MediFleet links your Pay Hero channel.
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


function PayHeroChecklist() {
    return (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-amber-900 mb-2 inline-flex items-center gap-2">
                <ShieldCheck size={16} /> Before you start
            </h3>
            <ol className="list-decimal pl-5 text-sm text-amber-900 space-y-1">
                <li>You must already have a Safaricom <strong>PayBill or Buy Goods Till</strong>. Tills are issued via Safaricom Business support and require business registration + KRA PIN.</li>
                <li>Enter that shortcode and your settlement bank below, then save. <strong>MediFleet</strong> links your till to Pay Hero and provisions the channel on its end — there's nothing for you to copy from the Pay Hero dashboard.</li>
                <li>The settlement schedule (daily / weekly) is agreed during onboarding and managed by MediFleet.</li>
                <li>Once MediFleet confirms your channel is linked, send a test KES&nbsp;1 STK push to your own number to verify end-to-end.</li>
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
                    <div className="text-xs mt-1">Fill out the form and click Save to enable M-Pesa payments via Pay Hero.</div>
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
                <div><span className="text-ink-500">Shortcode:</span> <span className="font-mono">{config.shortcode}</span> ({config.shortcode_type})</div>
                <div><span className="text-ink-500">Settles to:</span> <span className="font-mono">{config.settlement_bank_name} · {config.settlement_account_number}</span></div>
                {config.uses_per_tenant_creds && (
                    <div className="text-xs text-emerald-700">Using per-tenant Pay Hero credentials.</div>
                )}
            </div>
            {config.payhero_channel_id ? (
                <div className="text-xs inline-flex items-center gap-1.5 text-emerald-700 pt-2 border-t border-ink-100 w-full">
                    <CheckCircle2 size={14} /> Pay Hero channel linked by MediFleet — M-Pesa is live.
                </div>
            ) : (
                <div className="text-xs inline-flex items-start gap-1.5 text-amber-700 pt-2 border-t border-ink-100 w-full">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    Awaiting MediFleet to link your Pay Hero channel. M-Pesa stays disabled until then.
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
