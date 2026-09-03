import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../api/client';
import toast from 'react-hot-toast';
import {
    CreditCard, Wallet, Hash, Link2, Send, CheckCircle2, AlertCircle,
    Phone, Building2, Activity,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import PasswordInput from '../../components/PasswordInput';
import usePlatformPaymentSocket from '../../hooks/usePlatformPaymentSocket';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Superadmin: Subscription Billing (the platform's OWN Daraja rail).       */
/*                                                                            */
/*  This is the ONLY rail where MediFleet receives money. The operator       */
/*  provisions MediFleet's own Daraja (direct Safaricom) shortcode, charges  */
/*  a tenant's subscription via STK straight to that shortcode, and watches  */
/*  it settle live. The hospital rail (M-Pesa Provisioning) stays           */
/*  custody-free. Pay Hero, the aggregator this screen used to provision,   */
/*  was removed in the Daraja migration's Task 12: there is no aggregator   */
/*  settlement bank to nominate here any more, Safaricom pays MediFleet's   */
/*  own shortcode directly.                                                  */
/* ────────────────────────────────────────────────────────────────────────── */

const blankConfig = {
    shortcode: '', shortcode_type: 'paybill', environment: 'sandbox',
    consumer_key: '', consumer_secret: '', passkey: '',
    account_reference: 'MEDIFLEET', transaction_desc: 'MediFleet Subscription',
};

const numericId = (t) => String(t.id || t.tenant_id || '').replace(/^tenant_/, '');
const genKey = () => crypto.randomUUID();

export default function PlatformSubscriptions() {
    const [health, setHealth] = useState(null);
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
        try { const { data } = await apiClient.get('/public/superadmin/platform-mpesa/health'); setHealth(data); seedForm(data?.config); }
        catch (err) { toast.error(err?.response?.data?.detail || 'Could not load billing status.'); }
    };
    const loadTxns = async () => {
        try { const { data } = await apiClient.get('/public/superadmin/platform-mpesa/transactions?limit=50'); setTxns(data || []); }
        catch { /* non-fatal */ }
    };
    const seedForm = (cfg) => {
        if (!cfg?.configured) return;
        setForm(f => ({
            ...f,
            shortcode: cfg.shortcode || '', shortcode_type: cfg.shortcode_type || 'paybill',
            environment: cfg.environment || 'sandbox',
            consumer_key: '', consumer_secret: '', passkey: '',
            account_reference: cfg.account_reference || 'MEDIFLEET',
            transaction_desc: cfg.transaction_desc || 'MediFleet Subscription',
        }));
    };

    useEffect(() => {
        (async () => {
            try {
                const hosp = await apiClient.get('/public/hospitals?include_inactive=false');
                setTenants(hosp.data || []);
            } catch { /* noop */ }
            loadHealth();
            loadTxns();
        })();
    }, []);

    // Live settlement feed: merge incoming frames into the transactions list.
    usePlatformPaymentSocket(true, (evt) => {
        // A frame for a transaction we are not holding means our list is
        // stale, so refetch. That refetch must happen AFTER the updater, not
        // inside it: React runs updater functions twice under StrictMode, so
        // a fetch in there fires the request twice, and an updater that is
        // not pure is wrong even where the duplicate happens to be harmless.
        let listIsStale = false;
        setTxns(prev => {
            const idx = prev.findIndex(t => t.id === evt.transaction_id || t.external_reference === evt.external_reference);
            if (idx === -1) { listIsStale = true; return prev; }
            const next = [...prev];
            next[idx] = { ...next[idx], status: evt.status, receipt_number: evt.receipt_number, result_desc: evt.result_desc };
            return next;
        });
        if (listIsStale) loadTxns();
        if (evt.status === 'Success') toast.success(`Subscription settled, receipt ${evt.receipt_number || ''}`);
        else if (evt.status === 'Failed') toast.error(`Subscription charge failed: ${evt.result_desc || ''}`);
    });

    const saveConfig = async () => {
        if (!form.shortcode) {
            return toast.error('MediFleet’s shortcode is required.');
        }
        setSaving(true);
        try {
            await apiClient.post('/public/superadmin/platform-mpesa/config', form);
            toast.success('Subscription billing account saved.');
            setForm(f => ({ ...f, consumer_key: '', consumer_secret: '', passkey: '' }));
            loadHealth();
        } catch (err) { toast.error(err?.response?.data?.detail || 'Could not save.'); }
        finally { setSaving(false); }
    };

    const saveContact = async () => {
        if (!chargeTenant) return toast.error('Pick a tenant first.');
        setSavingContact(true);
        try {
            await apiClient.patch(`/public/hospitals/${chargeTenant}`, {
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
            await apiClient.post('/public/superadmin/platform-mpesa/charge', {
                tenant_id: Number(chargeTenant),
                amount: isTest ? 1 : Number(chargeAmount),
                phone_number: chargePhone || undefined,
                period_label: isTest ? 'Connectivity test' : (chargePeriod || undefined),
                idempotency_key: genKey(),
            });
            toast.success(isTest ? 'KES 1 test push sent. Approve on the phone.' : 'Subscription charge dispatched.');
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
                subtitle="Provision MediFleet's own Daraja shortcode and charge tenants their subscription. This is the only money you receive."
                tone="accent"
            />

            <SubsGuide />
            <HealthBanner health={health} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Config */}
                <div data-tour="sub-config" className="lg:col-span-2 bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-6 space-y-5">
                    <SectionHead icon={Wallet} title="Your MediFleet Daraja shortcode" />
                    <p className="text-xs text-ink-500 dark:text-ink-400 -mt-3">
                        These are MediFleet's OWN shortcode and Daraja API credentials. Safaricom pays this shortcode directly, there is no aggregator or settlement bank to configure.
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

                    <Field label="Daraja environment">
                        <select className="input max-w-xs" value={form.environment} onChange={set('environment')}>
                            <option value="sandbox">Sandbox</option>
                            <option value="production">Production</option>
                        </select>
                    </Field>

                    <SectionHead icon={Link2} title="Daraja API credentials" />
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Consumer key">
                            <PasswordInput autoComplete="new-password" value={form.consumer_key}
                                   onChange={set('consumer_key')}
                                   placeholder={health?.config?.has_credentials ? '•••••• (leave blank to keep)' : 'Consumer key'} />
                        </Field>
                        <Field label="Consumer secret">
                            <PasswordInput autoComplete="new-password" value={form.consumer_secret}
                                   onChange={set('consumer_secret')}
                                   placeholder={health?.config?.has_credentials ? '•••••• (leave blank to keep)' : 'Consumer secret'} />
                        </Field>
                    </div>
                    <Field label="Passkey">
                        <PasswordInput autoComplete="new-password" value={form.passkey}
                               onChange={set('passkey')}
                               placeholder={health?.config?.has_credentials ? '•••••• (leave blank to keep)' : 'Passkey'} />
                    </Field>

                    <SectionHead icon={Hash} title="Customisation" />
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
                    <div className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl p-5 space-y-3">
                        <SectionHead icon={Phone} title="Charge a tenant" />
                        <Field label="Tenant">
                            <select className="input" value={chargeTenant} onChange={e => setChargeTenant(e.target.value)}>
                                <option value="">, select tenant, </option>
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
                            <Field label="Period label"><input aria-label="Period label" className="input" value={chargePeriod} onChange={e => setChargePeriod(e.target.value)} placeholder="May 2026, Standard" /></Field>
                        </div>
                        <div className="flex gap-2 pt-1">
                            <button type="button" onClick={() => charge(false)} disabled={charging || !health?.ready}
                                    className="flex-1 px-3 py-2 rounded-lg bg-accent-600 text-white text-sm font-medium hover:bg-accent-700 disabled:opacity-60">
                                {charging ? 'Sending…' : 'Charge subscription'}
                            </button>
                            <button type="button" onClick={() => charge(true)} disabled={charging || !health?.ready}
                                    className="px-3 py-2 rounded-lg border border-accent-200 dark:border-accent-500/30 text-accent-700 dark:text-accent-300 text-sm font-medium hover:bg-accent-50 dark:hover:bg-accent-500/10 disabled:opacity-60 inline-flex items-center gap-1">
                                <Send size={14} /> Test (KES 1)
                            </button>
                        </div>
                        {!health?.ready && (
                            <p className="text-xs text-amber-700 dark:text-amber-400">Charging unlocks once your account is fully configured (see status above).</p>
                        )}
                    </div>
                </div>
            </div>

            {/* Live activity */}
            <div data-tour="sub-activity" className="bg-white dark:bg-ink-900 border border-ink-200/70 dark:border-ink-800 rounded-xl overflow-hidden">
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
        <div data-tour="sub-guide" className="bg-accent-50 dark:bg-accent-500/10 border border-accent-200 dark:border-accent-500/20 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-accent-900 dark:text-accent-200 mb-2 inline-flex items-center gap-2">
                <Wallet size={16} /> This is the only money you receive
            </h3>
            <p className="text-sm text-accent-900/90 dark:text-accent-200/90 leading-relaxed">
                Hospital patient payments never touch you, they settle to each hospital's own bank.
                <strong> Subscriptions are the one inbound rail:</strong> you charge a tenant's billing
                phone via M-Pesa and the money lands directly on <strong>MediFleet's own Daraja shortcode</strong>,
                on Safaricom's own settlement schedule. Configure your shortcode once below, set each tenant's
                billing phone, then charge them and watch it settle live.
            </p>
        </div>
    );
}

function HealthBanner({ health }) {
    if (!health) return null;
    if (health.ready) {
        return (
            <div data-tour="sub-health" className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-xl p-4 text-sm text-emerald-800 dark:text-emerald-300 inline-flex items-start gap-2 w-full">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                <div>
                    <span className="font-semibold">Ready to collect subscriptions.</span>
                    {health.callback_url && <span className="text-xs text-emerald-700 dark:text-emerald-400 block mt-0.5 font-mono break-all">callback: {health.callback_url}</span>}
                </div>
            </div>
        );
    }
    return (
        <div data-tour="sub-health" className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4 text-sm text-amber-900 dark:text-amber-200 w-full">
            <div className="font-semibold inline-flex items-center gap-2 mb-1"><AlertCircle size={16} /> Not ready yet, finish these first</div>
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
            <table className="table-clean table-sticky">
                <thead>
                    <tr>
                        <th>Tenant</th><th>Amount</th>
                        <th>Period</th><th>Status</th>
                        <th>Receipt</th><th>When</th>
                    </tr>
                </thead>
                <tbody>
                    {txns.map(t => (
                        <tr key={t.id} className="hover:bg-ink-50">
                            <td><span className="inline-flex items-center gap-1.5"><Building2 size={14} className="text-ink-400" />{nameFor(t.tenant_id)}</span></td>
                            <td className="font-mono text-xs">KES {Number(t.amount || 0).toLocaleString('en-KE')}</td>
                            <td className="text-xs">{t.period_label || '-'}</td>
                            <td className={`font-semibold text-xs ${STATUS_TONE[t.status] || 'text-ink-500'}`}>{t.status}</td>
                            <td className="font-mono text-xs">{t.receipt_number || '-'}</td>
                            <td className="text-xs text-ink-500">{t.initiated_at ? new Date(t.initiated_at).toLocaleString() : '-'}</td>
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
