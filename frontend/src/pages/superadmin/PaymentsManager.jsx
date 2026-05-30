import React, { useEffect, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    Smartphone, Building2, Hash, Building, Banknote, KeyRound,
    Send, CheckCircle2, AlertCircle, Link2, ShieldCheck, Wallet,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin — M-Pesa / Pay Hero provisioning.                              */
/*                                                                            */
/*  Only the platform operator is linked with Pay Hero. Here the operator     */
/*  wires each hospital's Pay Hero channel + credentials (and can set the     */
/*  till + bank during onboarding). Hospitals never see any of this — their   */
/*  own page only shows whether M-Pesa is live.                               */
/* ────────────────────────────────────────────────────────────────────────── */

const blankForm = {
    shortcode: '',
    shortcode_type: 'paybill',
    payhero_channel_id: '',
    payhero_username: '',
    payhero_password: '',
    payhero_webhook_secret: '',
    settlement_bank_code: '',
    settlement_account_number: '',
    settlement_account_name: '',
    account_reference: 'HMS-BILLING',
    transaction_desc: 'Hospital Bill Payment',
};

const numericId = (t) => String(t.id || t.tenant_id || '').replace(/^tenant_/, '');

export default function PaymentsManager() {
    const [tenants, setTenants] = useState([]);
    const [banks, setBanks] = useState([]);
    const [selected, setSelected] = useState(null);   // numeric tenant id (string)
    const [config, setConfig] = useState(null);
    const [form, setForm] = useState(blankForm);
    const [loadingCfg, setLoadingCfg] = useState(false);
    const [saving, setSaving] = useState(false);
    const [testPhone, setTestPhone] = useState('');
    const [testing, setTesting] = useState(false);

    // Load the tenant list + bank catalogue once.
    useEffect(() => {
        (async () => {
            try {
                const [hosp, bnk] = await Promise.all([
                    apiClient.get('/public/hospitals?include_inactive=false'),
                    apiClient.get('/public/superadmin/payhero/banks'),
                ]);
                setTenants(hosp.data || []);
                setBanks(bnk.data?.banks || []);
            } catch (err) {
                toast.error(err?.response?.data?.detail || 'Could not load tenants.');
            }
        })();
    }, []);

    const loadConfig = async (tenantId) => {
        setSelected(tenantId);
        setConfig(null);
        setForm(blankForm);
        if (!tenantId) return;
        setLoadingCfg(true);
        try {
            const { data } = await apiClient.get(`/public/superadmin/payhero/${tenantId}/config`);
            setConfig(data);
            if (data?.configured) {
                setForm(f => ({
                    ...f,
                    shortcode: data.shortcode || '',
                    shortcode_type: data.shortcode_type || 'paybill',
                    payhero_channel_id: data.payhero_channel_id || '',
                    payhero_username: '',
                    payhero_password: '',
                    payhero_webhook_secret: '',
                    settlement_bank_code: data.settlement_bank_code || '',
                    settlement_account_number: data.settlement_account_number || '',
                    settlement_account_name: data.settlement_account_name || '',
                    account_reference: data.account_reference || 'HMS-BILLING',
                    transaction_desc: data.transaction_desc || 'Hospital Bill Payment',
                }));
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load tenant config.');
        } finally { setLoadingCfg(false); }
    };

    const save = async () => {
        if (!selected) return toast.error('Select a hospital first.');
        setSaving(true);
        try {
            const { data } = await apiClient.post(`/public/superadmin/payhero/${selected}/config`, form);
            setConfig(data);
            setForm(f => ({ ...f, payhero_username: '', payhero_password: '', payhero_webhook_secret: '' }));
            toast.success('Pay Hero wiring saved for this hospital.');
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not save.');
        } finally { setSaving(false); }
    };

    const testStk = async () => {
        if (!testPhone) return toast.error('Enter a phone number for the test prompt.');
        setTesting(true);
        try {
            await apiClient.post(`/public/superadmin/payhero/${selected}/test-stk`, { phone_number: testPhone });
            toast.success(`Test KES 1 prompt sent to ${testPhone}.`);
            loadConfig(selected);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Test prompt failed.');
            loadConfig(selected);
        } finally { setTesting(false); }
    };

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Platform"
                icon={Smartphone}
                title="M-Pesa Provisioning"
                subtitle="Wire each hospital's Pay Hero channel + credentials. Hospitals never see this — only whether their M-Pesa is live."
                tone="brand"
            />

            <ProvisioningGuide />

            <div data-tour="prov-hospital" className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5">
                <label className="block text-xs font-semibold text-ink-600 mb-1.5 inline-flex items-center gap-1.5">
                    <Building2 size={14} className="text-brand-600" /> Hospital
                </label>
                <select
                    className="input max-w-md"
                    value={selected || ''}
                    onChange={(e) => loadConfig(e.target.value)}
                >
                    <option value="">— select a hospital —</option>
                    {tenants.map((t) => (
                        <option key={t.id || t.tenant_id} value={numericId(t)}>{t.name}</option>
                    ))}
                </select>
            </div>

            {!selected ? (
                <div className="bg-white border border-dashed border-ink-200 rounded-2xl p-12 text-center text-ink-400">
                    <Smartphone size={40} className="mx-auto mb-3 text-ink-300" />
                    <p className="text-sm font-medium text-ink-500">Select a hospital to manage its M-Pesa wiring.</p>
                </div>
            ) : loadingCfg ? (
                <div className="bg-white border border-ink-200/70 rounded-2xl p-8 text-sm text-ink-500">Loading…</div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Editor */}
                    <div className="lg:col-span-2 bg-white border border-ink-200/70 rounded-2xl shadow-soft p-6 space-y-5">
                        <SectionHead icon={Hash} title="Hospital Safaricom shortcode" />
                        <div className="grid grid-cols-2 gap-3">
                            <Field label="Shortcode (PayBill / Till)">
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

                        <div data-tour="prov-payhero">
                        <SectionHead icon={Link2} title="Pay Hero wiring (operator-only)" />
                        <p className="text-xs text-ink-500 mt-2 mb-3">
                            These come from <strong>this hospital's own Pay Hero account</strong> (each
                            hospital owns its account so funds settle to their bank, never yours). Paste
                            the values from their Pay Hero dashboard.
                        </p>
                        <Field label="Pay Hero channel id">
                            <input className="input" value={form.payhero_channel_id}
                                   onChange={e => setForm({ ...form, payhero_channel_id: e.target.value })}
                                   placeholder="copied from the Pay Hero dashboard" />
                        </Field>
                        <p className="text-xs text-ink-500 -mt-2 mt-1">
                            M-Pesa goes live for the hospital the moment a channel id is saved here.
                        </p>
                        <div className="grid grid-cols-2 gap-3 mt-3">
                            <Field label="Pay Hero username">
                                <input className="input" type="password" autoComplete="new-password"
                                       value={form.payhero_username}
                                       onChange={e => setForm({ ...form, payhero_username: e.target.value })}
                                       placeholder={config?.uses_per_tenant_creds ? '•••••• (leave blank to keep)' : 'platform default if blank'} />
                            </Field>
                            <Field label="Pay Hero password">
                                <input className="input" type="password" autoComplete="new-password"
                                       value={form.payhero_password}
                                       onChange={e => setForm({ ...form, payhero_password: e.target.value })}
                                       placeholder={config?.uses_per_tenant_creds ? '•••••• (leave blank to keep)' : 'platform default if blank'} />
                            </Field>
                        </div>
                        <Field label="Webhook signing secret">
                            <input className="input" type="password" autoComplete="new-password"
                                   value={form.payhero_webhook_secret}
                                   onChange={e => setForm({ ...form, payhero_webhook_secret: e.target.value })}
                                   placeholder={config?.uses_per_tenant_webhook_secret ? '•••••• (leave blank to keep)' : "this hospital's own webhook secret"} />
                        </Field>
                        <p className="text-xs text-ink-500 -mt-2 mt-1 inline-flex items-start gap-1.5">
                            <ShieldCheck size={13} className="mt-0.5 text-brand-600 shrink-0" />
                            Each hospital signs its M-Pesa callbacks with its own secret. Leave blank to
                            fall back to the platform default secret.
                        </p>
                        </div>

                        <SectionHead icon={Building} title="Settlement bank" />
                        <div className="grid grid-cols-2 gap-3">
                            <Field label="Bank">
                                <select className="input" value={form.settlement_bank_code}
                                        onChange={e => setForm({ ...form, settlement_bank_code: e.target.value })}>
                                    <option value="">— select bank —</option>
                                    {banks.map(b => (<option key={b.code} value={b.code}>{b.name}</option>))}
                                </select>
                            </Field>
                            <Field label="Account number">
                                <input className="input" value={form.settlement_account_number}
                                       onChange={e => setForm({ ...form, settlement_account_number: e.target.value })} />
                            </Field>
                            <Field label="Account name">
                                <input className="input" value={form.settlement_account_name}
                                       onChange={e => setForm({ ...form, settlement_account_name: e.target.value })} />
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

                        <div className="flex justify-end pt-2 border-t border-ink-100">
                            <button onClick={save} disabled={saving}
                                    className="px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                                {saving ? 'Saving…' : 'Save wiring'}
                            </button>
                        </div>
                    </div>

                    {/* Sidebar */}
                    <div className="space-y-4">
                        <StatusCard config={config} />

                        <div data-tour="prov-test" className="bg-white border border-ink-200/70 rounded-2xl shadow-soft p-5 space-y-3">
                            <SectionHead icon={Send} title="Send a test prompt" />
                            <p className="text-xs text-ink-500">
                                Real KES&nbsp;1 STK push using this hospital's saved wiring.
                            </p>
                            <input className="input" value={testPhone}
                                   onChange={e => setTestPhone(e.target.value)}
                                   placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                            <button onClick={testStk} disabled={testing || !config?.mpesa_active}
                                    className="w-full px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                                {testing ? 'Sending…' : 'Send test'}
                            </button>
                            {config?.configured && !config?.mpesa_active && (
                                <p className="text-xs text-amber-700">Save a channel id first to enable the test.</p>
                            )}
                            {config?.last_test_at && (
                                <div className="text-xs text-ink-600 pt-2 border-t border-ink-100">
                                    <div>Last: <span className="font-mono">{new Date(config.last_test_at).toLocaleString()}</span></div>
                                    <div>Status: <strong>{config.last_test_status}</strong></div>
                                    {config.last_test_message && (<div className="text-ink-500 mt-1">{config.last_test_message}</div>)}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function ProvisioningGuide() {
    return (
        <div data-tour="prov-guide" className="bg-brand-50 border border-brand-200 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-brand-900 mb-2 inline-flex items-center gap-2">
                <Wallet size={16} /> How hospital payments are wired (the operator model)
            </h3>
            <p className="text-sm text-brand-900/90 leading-relaxed mb-2">
                Each hospital owns its <strong>own Pay Hero account</strong>. Patient money flows
                patient → that hospital's Pay Hero account → that hospital's bank. <strong>MediFleet
                never holds hospital money</strong> — the platform only triggers the STK push (using
                the hospital's credentials) and relays the live status back to their screens.
            </p>
            <ol className="list-decimal pl-5 text-sm text-brand-900/90 space-y-1">
                <li>Get the hospital's <strong>Channel ID, API username/password, and webhook secret</strong> from their Pay Hero account.</li>
                <li>Pick the hospital below, paste those values, set their till + settlement bank, and save.</li>
                <li>Saving a channel id flips their M-Pesa to live. Send a KES 1 test to confirm end-to-end.</li>
            </ol>
            <p className="text-xs text-brand-700 mt-2">
                Your own MediFleet account (for collecting subscriptions) is configured separately under <strong>Subscription Billing</strong> — that's the only money you receive.
            </p>
        </div>
    );
}

function StatusCard({ config }) {
    if (!config?.configured) {
        return (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 text-sm text-amber-800 inline-flex items-start gap-2">
                <AlertCircle size={16} className="mt-0.5" />
                <div>
                    <div className="font-semibold">Nothing saved yet</div>
                    <div className="text-xs mt-1">Enter the wiring below and save to provision this hospital.</div>
                </div>
            </div>
        );
    }
    return (
        <div className="bg-white border border-ink-200/70 rounded-2xl p-5 text-sm space-y-2">
            {config.mpesa_active ? (
                <div className="flex items-center gap-2 font-semibold text-emerald-700"><CheckCircle2 size={16} /> M-Pesa live</div>
            ) : (
                <div className="flex items-center gap-2 font-semibold text-amber-700"><AlertCircle size={16} /> Channel not set</div>
            )}
            <div className="text-ink-700">
                {config.shortcode && <div><span className="text-ink-500">Shortcode:</span> <span className="font-mono">{config.shortcode}</span> ({config.shortcode_type})</div>}
                {config.payhero_channel_id && <div><span className="text-ink-500">Channel:</span> <span className="font-mono">{config.payhero_channel_id}</span></div>}
                {config.settlement_bank_name && <div><span className="text-ink-500">Settles to:</span> <span className="font-mono">{config.settlement_bank_name} · {config.settlement_account_number}</span></div>}
                <div className="text-xs inline-flex items-center gap-1.5 text-ink-500 pt-1">
                    <KeyRound size={12} /> {config.uses_per_tenant_creds ? 'Per-tenant credentials' : 'Platform default credentials'}
                </div>
                <div className="text-xs inline-flex items-center gap-1.5 text-ink-500">
                    <ShieldCheck size={12} /> {config.uses_per_tenant_webhook_secret ? 'Own webhook secret' : 'Platform default webhook secret'}
                </div>
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
