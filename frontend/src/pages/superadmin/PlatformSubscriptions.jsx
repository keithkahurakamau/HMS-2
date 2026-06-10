import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    CreditCard, Wallet, Hash, Link2, KeyRound, Building, Banknote,
    Send, CheckCircle2, AlertCircle, Phone, Building2, Activity, ShieldCheck,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import PasswordInput from '../../components/PasswordInput';
import usePlatformPaymentSocket from '../../hooks/usePlatformPaymentSocket';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin — Subscription Billing (the platform's OWN Pay Hero rail).     */
/*                                                                            */
/*  This is the ONLY rail where MediFleet receives money. The operator        */
/*  provisions MediFleet's own Pay Hero account, charges a tenant's           */
/*  subscription via STK into that account, and watches it settle live.       */
/*  The hospital rail (M-Pesa Provisioning) stays custody-free.               */
/* ────────────────────────────────────────────────────────────────────────── */

const blankConfig = {
    shortcode: '', shortcode_type: 'paybill', payhero_channel_id: '',
    payhero_username: '', payhero_password: '', payhero_webhook_secret: '',
    settlement_bank_code: '', settlement_account_number: '', settlement_account_name: '',
    account_reference: 'MEDIFLEET', transaction_desc: 'MediFleet Subscription',
};

const numericId = (t) => String(t.id || t.tenant_id || '').replace(/^tenant_/, '');

export default function PlatformSubscriptions() {
    const [health, setHealth] = useState(null);
    const [banks, setBanks] = useState([]);
    const [form, setForm] = useState(blankConfig);
    const [saving, setSaving] = useState(false);

    const [tenants, setTenants] = useState([]);
    const [chargeTenant, setChargeTenant] = useState('');
    const [chargePhone, setChargePhone] = useState('');
    const [chargeAmount, setChargeAmount] = useState('');
    const [chargePeriod, setChargePeriod] = useState('');
    const [charging, setCharging] = useState(false);
    const [savingContact, setSavingContact] = useState(false);

    const [txns, setTxns] = useState([]);

    const loadHealth = async () => {
        try { const { data } = await apiClient.get('/public/superadmin/platform-payhero/health'); setHealth(data); seedForm(data?.config); }
        catch (err) { toast.error(err?.response?.data?.detail || 'Could not load billing status.'); }
    };
    const loadTxns = async () => {
        try { const { data } = await apiClient.get('/public/superadmin/platform-payhero/transactions?limit=50'); setTxns(data || []); }
        catch { /* non-fatal */ }
    };
    const seedForm = (cfg) => {
        if (!cfg?.configured) return;
        setForm(f => ({
            ...f,
            shortcode: cfg.shortcode || '', shortcode_type: cfg.shortcode_type || 'paybill',
            payhero_channel_id: cfg.payhero_channel_id || '',
            payhero_username: '', payhero_password: '', payhero_webhook_secret: '',
            settlement_bank_code: cfg.settlement_bank_code || '',
            settlement_account_number: cfg.settlement_account_number || '',
            settlement_account_name: cfg.settlement_account_name || '',
            account_reference: cfg.account_reference || 'MEDIFLEET',
            transaction_desc: cfg.transaction_desc || 'MediFleet Subscription',
        }));
    };

    useEffect(() => {
        (async () => {
            try {
                const [bnk, hosp] = await Promise.all([
                    apiClient.get('/public/superadmin/platform-payhero/banks'),
                    apiClient.get('/public/hospitals?include_inactive=false'),
                ]);
                setBanks(bnk.data?.banks || []);
                setTenants(hosp.data || []);
            } catch { /* noop */ }
            loadHealth();
            loadTxns();
        })();
    }, []);

    // Live settlement feed — merge incoming frames into the transactions list.
    usePlatformPaymentSocket(true, (evt) => {
        setTxns(prev => {
            const idx = prev.findIndex(t => t.id === evt.transaction_id || t.external_reference === evt.external_reference);
            if (idx === -1) { loadTxns(); return prev; }
            const next = [...prev];
            next[idx] = { ...next[idx], status: evt.status, receipt_number: evt.receipt_number, result_desc: evt.result_desc };
            return next;
        });
        if (evt.status === 'Success') toast.success(`Subscription settled — receipt ${evt.receipt_number || ''}`);
        else if (evt.status === 'Failed') toast.error(`Subscription charge failed: ${evt.result_desc || ''}`);
    });

    const saveConfig = async () => {
        if (!form.settlement_bank_code || !form.payhero_channel_id) {
            return toast.error('Channel id and settlement bank are required.');
        }
        setSaving(true);
        try {
            await apiClient.post('/public/superadmin/platform-payhero/config', form);
            toast.success('Subscription billing account saved.');
            setForm(f => ({ ...f, payhero_username: '', payhero_password: '', payhero_webhook_secret: '' }));
            loadHealth();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    const saveContact = async () => {
        if (!chargeTenant) return toast.error('Pick a tenant first.');
        setSavingContact(true);
        try {
            await apiClient.patch(`/public/superadmin/platform-payhero/tenant/${chargeTenant}/billing-contact`, {
                billing_contact_msisdn: chargePhone,
            });
            toast.success('Billing contact saved for this tenant.');
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save contact.'); }
        finally { setSavingContact(false); }
    };

    const charge = async (isTest) => {
        if (!chargeTenant) return toast.error('Pick a tenant to charge.');
        if (!isTest && !chargeAmount) return toast.error('Enter an amount.');
        setCharging(true);
        try {
            if (isTest) {
                await apiClient.post('/public/superadmin/platform-payhero/test-stk', {
                    tenant_id: Number(chargeTenant), phone_number: chargePhone,
                });
                toast.success('KES 1 test push sent. Approve on the phone.');
            } else {
                await apiClient.post('/public/superadmin/platform-payhero/charge', {
                    tenant_id: Number(chargeTenant), amount: Number(chargeAmount),
                    phone_number: chargePhone || undefined, period_label: chargePeriod || undefined,
                });
                toast.success('Subscription charge dispatched.');
            }
            loadTxns();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Charge failed.'); }
        finally { setCharging(false); }
    };

    const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Console"
                icon={CreditCard}
                title="Subscription Billing"
                subtitle="Provision MediFleet's own Pay Hero account and charge tenants their subscription. This is the only money you receive."
                tone="accent"
            />

            <SubsGuide />
            <HealthBanner health={health} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Config */}
                <div data-tour="sub-config" className="lg:col-span-2 bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-2xl shadow-soft p-6 space-y-5">
                    <SectionHead icon={Wallet} title="Your MediFleet Pay Hero account" />
                    <p className="text-xs text-ink-500 dark:text-ink-400 -mt-3">
                        These are MediFleet's OWN account values — subscription proceeds settle to MediFleet's bank.
                    </p>

                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Your shortcode (PayBill / Till)">
                            <input aria-label="Your shortcode (PayBill / Till)" className="input" value={form.shortcode} onChange={set('shortcode')} placeholder="MediFleet PayBill / Till" />
                        </Field>
                        <Field label="Shortcode type">
                            <select className="input" value={form.shortcode_type} onChange={set('shortcode_type')}>
                                <option value="paybill">PayBill</option>
                                <option value="till">Buy Goods / Till</option>
                            </select>
                        </Field>
                    </div>

                    <SectionHead icon={Link2} title="Pay Hero credentials" />
                    <Field label="Channel id">
                        <input aria-label="Channel id" className="input" value={form.payhero_channel_id} onChange={set('payhero_channel_id')} placeholder="from your Pay Hero dashboard" />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="API username">
                            <PasswordInput autoComplete="new-password" value={form.payhero_username}
                                   onChange={set('payhero_username')}
                                   placeholder={health?.config?.uses_credentials ? '•••••• (leave blank to keep)' : 'API username'} />
                        </Field>
                        <Field label="API password">
                            <PasswordInput autoComplete="new-password" value={form.payhero_password}
                                   onChange={set('payhero_password')}
                                   placeholder={health?.config?.uses_credentials ? '•••••• (leave blank to keep)' : 'API password'} />
                        </Field>
                    </div>
                    <Field label="Webhook signing secret">
                        <PasswordInput autoComplete="new-password" value={form.payhero_webhook_secret}
                               onChange={set('payhero_webhook_secret')}
                               placeholder={health?.config?.uses_webhook_secret ? '•••••• (leave blank to keep)' : 'your account webhook secret'} />
                    </Field>

                    <SectionHead icon={Building} title="Settlement bank (where MediFleet is paid)" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Bank">
                            <select className="input" value={form.settlement_bank_code} onChange={set('settlement_bank_code')}>
                                <option value="">— select bank —</option>
                                {banks.map(b => <option key={b.code} value={b.code}>{b.name}</option>)}
                            </select>
                        </Field>
                        <Field label="Account number">
                            <input aria-label="Account number" className="input" value={form.settlement_account_number} onChange={set('settlement_account_number')} />
                        </Field>
                        <Field label="Account name">
                            <input aria-label="Account name" className="input" value={form.settlement_account_name} onChange={set('settlement_account_name')} />
                        </Field>
                    </div>

                    <SectionHead icon={Banknote} title="Customisation" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Account reference"><input aria-label="Account reference" className="input" value={form.account_reference} onChange={set('account_reference')} /></Field>
                        <Field label="Transaction description"><input aria-label="Transaction description" className="input" value={form.transaction_desc} onChange={set('transaction_desc')} /></Field>
                    </div>

                    <div className="flex justify-end pt-2 border-t border-ink-100 dark:border-ink-800">
                        <button type="button" onClick={saveConfig} disabled={saving}
                                className="px-4 py-2 rounded-lg bg-accent-600 text-white text-sm font-medium hover:bg-accent-700 disabled:opacity-60">
                            {saving ? 'Saving…' : 'Save account'}
                        </button>
                    </div>
                </div>

                {/* Charge a tenant */}
                <div data-tour="sub-charge" className="space-y-4">
                    <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-2xl shadow-soft p-5 space-y-3">
                        <SectionHead icon={Phone} title="Charge a tenant" />
                        <Field label="Tenant">
                            <select className="input" value={chargeTenant} onChange={e => setChargeTenant(e.target.value)}>
                                <option value="">— select tenant —</option>
                                {tenants.map(t => <option key={t.id || t.tenant_id} value={numericId(t)}>{t.name}</option>)}
                            </select>
                        </Field>
                        <Field label="Billing phone (M-Pesa)">
                            <input aria-label="Billing phone (M-Pesa)" className="input" value={chargePhone} onChange={e => setChargePhone(e.target.value)} placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                        </Field>
                        <button type="button" onClick={saveContact} disabled={savingContact || !chargeTenant}
                                className="text-xs text-accent-700 dark:text-accent-300 font-medium hover:underline disabled:opacity-50">
                            {savingContact ? 'Saving…' : 'Save as this tenant’s default billing phone'}
                        </button>
                        <div className="grid grid-cols-2 gap-3 pt-1">
                            <Field label="Amount (KES)"><input aria-label="Amount (KES)" className="input" type="number" value={chargeAmount} onChange={e => setChargeAmount(e.target.value)} placeholder="18500" /></Field>
                            <Field label="Period label"><input aria-label="Period label" className="input" value={chargePeriod} onChange={e => setChargePeriod(e.target.value)} placeholder="May 2026 — Standard" /></Field>
                        </div>
                        <div className="flex gap-2 pt-1">
                            <button type="button" onClick={() => charge(false)} disabled={charging || !health?.ready}
                                    className="flex-1 px-3 py-2 rounded-lg bg-accent-600 text-white text-sm font-medium hover:bg-accent-700 disabled:opacity-60">
                                {charging ? 'Sending…' : 'Charge subscription'}
                            </button>
                            <button type="button" onClick={() => charge(true)} disabled={charging || !health?.ready}
                                    className="px-3 py-2 rounded-lg border border-accent-200 dark:border-accent-500/30 text-accent-700 dark:text-accent-300 text-sm font-medium hover:bg-accent-50 dark:hover:bg-accent-500/10 disabled:opacity-60 inline-flex items-center gap-1">
                                <Send size={14} /> Test
                            </button>
                        </div>
                        {!health?.ready && (
                            <p className="text-xs text-amber-700 dark:text-amber-400">Charging unlocks once your account is fully configured (see status above).</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Live activity */}
            <div data-tour="sub-activity" className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-2xl shadow-soft overflow-hidden">
                <div className="p-4 border-b border-ink-100 dark:border-ink-800 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-ink-900 dark:text-white inline-flex items-center gap-2">
                        <Activity size={16} className="text-accent-600 dark:text-accent-400" /> Subscription activity
                    </h3>
                    <span className="text-2xs uppercase tracking-wider text-accent-700 dark:text-accent-300 inline-flex items-center gap-1.5">
                        <span className="size-1.5 rounded-full bg-accent-500 animate-pulse-soft" /> live
                    </span>
                </div>
                <TxnTable txns={txns} tenants={tenants} />
            </div>
        </div>
    );
}

function SubsGuide() {
    return (
        <div data-tour="sub-guide" className="bg-accent-50 dark:bg-accent-500/10 border border-accent-200 dark:border-accent-500/20 rounded-2xl p-5">
            <h3 className="text-sm font-semibold text-accent-900 dark:text-accent-200 mb-2 inline-flex items-center gap-2">
                <Wallet size={16} /> This is the only money you receive
            </h3>
            <p className="text-sm text-accent-900/90 dark:text-accent-200/90 leading-relaxed">
                Hospital patient payments never touch you — they settle to each hospital's own bank.
                <strong> Subscriptions are the one inbound rail:</strong> you charge a tenant's billing
                phone via M-Pesa and the money lands in <strong>MediFleet's own Pay Hero account</strong>,
                then your settlement bank. Configure your account once below, set each tenant's billing
                phone, then charge them and watch it settle live.
            </p>
        </div>
    );
}

function HealthBanner({ health }) {
    if (!health) return null;
    if (health.ready) {
        return (
            <div data-tour="sub-health" className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-2xl p-4 text-sm text-emerald-800 dark:text-emerald-300 inline-flex items-start gap-2 w-full">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                <div>
                    <span className="font-semibold">Ready to collect subscriptions.</span>
                    {health.callback_url && <span className="text-xs text-emerald-700 dark:text-emerald-400 block mt-0.5 font-mono break-all">callback: {health.callback_url}</span>}
                </div>
            </div>
        );
    }
    return (
        <div data-tour="sub-health" className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-2xl p-4 text-sm text-amber-900 dark:text-amber-200 w-full">
            <div className="font-semibold inline-flex items-center gap-2 mb-1"><AlertCircle size={16} /> Not ready yet — finish these first</div>
            <ul className="list-disc pl-5 text-xs space-y-0.5">
                {(health.blockers || []).map((b) => <li key={b}>{b}</li>)}
            </ul>
        </div>
    );
}

const STATUS_TONE = {
    Success: 'text-emerald-700 dark:text-emerald-400', Failed: 'text-rose-700 dark:text-rose-400', Pending: 'text-amber-700 dark:text-amber-400',
};

function TxnTable({ txns, tenants }) {
    const nameFor = useMemo(() => {
        const m = {};
        tenants.forEach(t => { m[numericId(t)] = t.name; });
        return (id) => m[String(id)] || `Tenant ${id}`;
    }, [tenants]);

    if (!txns.length) {
        return <div className="p-8 text-center text-sm text-ink-400">No subscription charges yet.</div>;
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
                <thead className="bg-ink-50 text-ink-600 text-2xs uppercase tracking-[0.14em]">
                    <tr>
                        <th className="px-5 py-3">Tenant</th><th className="px-5 py-3">Amount</th>
                        <th className="px-5 py-3">Period</th><th className="px-5 py-3">Status</th>
                        <th className="px-5 py-3">Receipt</th><th className="px-5 py-3">When</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-ink-100 text-ink-700">
                    {txns.map(t => (
                        <tr key={t.id} className="hover:bg-ink-50">
                            <td className="px-5 py-3"><span className="inline-flex items-center gap-1.5"><Building2 size={14} className="text-ink-400" />{nameFor(t.tenant_id)}</span></td>
                            <td className="px-5 py-3 font-mono text-xs">KES {(t.amount || 0).toLocaleString('en-KE')}</td>
                            <td className="px-5 py-3 text-xs">{t.period_label || '—'}</td>
                            <td className={`px-5 py-3 font-semibold text-xs ${STATUS_TONE[t.status] || 'text-ink-500'}`}>{t.status}</td>
                            <td className="px-5 py-3 font-mono text-xs">{t.receipt_number || '—'}</td>
                            <td className="px-5 py-3 text-xs text-ink-500">{t.initiated_at ? new Date(t.initiated_at).toLocaleString() : '—'}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function SectionHead({ icon: Icon, title }) {
    return (
        <h3 className="text-sm font-semibold text-ink-900 inline-flex items-center gap-2 border-b border-ink-100 pb-2 w-full">
            <Icon size={16} className="text-accent-600" /> {title}
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
