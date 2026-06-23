import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import {
    HeartPulse, ShieldCheck, CalendarDays, Receipt, ClipboardList,
    LogOut, Activity, ArrowLeft, AlertCircle, Lock, CheckCircle2, Sparkles,
} from 'lucide-react';
import WebGLHero from '../components/WebGLHero';

const TABS = [
    { key: 'profile',      label: 'Profile',      icon: HeartPulse },
    { key: 'appointments', label: 'Appointments', icon: CalendarDays },
    { key: 'billing',      label: 'Billing',      icon: Receipt },
    { key: 'history',      label: 'History',      icon: ClipboardList },
];

export default function PatientPortal() {
    const navigate = useNavigate();
    const tenantName = localStorage.getItem('hms_tenant_name') || 'Hospital';

    const [authed, setAuthed] = useState(false);
    const [verifyForm, setVerifyForm] = useState({ outpatient_no: '', date_of_birth: '', phone_last4: '' });
    const [touched, setTouched] = useState({});
    const [submitting, setSubmitting] = useState(false);

    // Field-level validation drives the inline micro-interactions (red ring +
    // message when wrong, green tick when right). Pure functions of the value
    // so they can be called during render without extra state.
    const today = new Date().toISOString().slice(0, 10);
    const fieldError = (name, value) => {
        if (name === 'outpatient_no') {
            if (!value.trim()) return 'Enter the OP number from your card.';
            if (!/^OP[-/]?\d/i.test(value.trim())) return 'That does not look like an OP number.';
            return '';
        }
        if (name === 'date_of_birth') {
            if (!value) return 'Select your date of birth.';
            if (value > today) return 'Date of birth cannot be in the future.';
            return '';
        }
        if (name === 'phone_last4') {
            if (!value) return 'Enter the last 4 digits.';
            if (!/^\d{4}$/.test(value)) return 'Exactly 4 digits.';
            return '';
        }
        return '';
    };
    const markTouched = (name) => setTouched((t) => ({ ...t, [name]: true }));
    const isValid = (name) => !fieldError(name, verifyForm[name]);
    const showError = (name) => touched[name] && !isValid(name);
    const formValid = ['outpatient_no', 'date_of_birth', 'phone_last4'].every(isValid);
    const [activeTab, setActiveTab] = useState('profile');
    const [profile, setProfile] = useState(null);
    const [appointments, setAppointments] = useState([]);
    const [invoices, setInvoices] = useState([]);
    const [history, setHistory] = useState([]);

    const handleLookup = async (e) => {
        e.preventDefault();
        setTouched({ outpatient_no: true, date_of_birth: true, phone_last4: true });
        if (!formValid) {
            return toast.error('Please fix the highlighted fields.');
        }
        setSubmitting(true);
        try {
            const res = await apiClient.post('/portal/lookup', verifyForm);
            toast.success(`Welcome, ${res.data.patient.full_name}`);
            setAuthed(true);
            await loadAll();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Verification failed.');
        } finally {
            setSubmitting(false);
        }
    };

    const loadAll = async () => {
        try {
            const [meRes, apptRes, billRes, histRes] = await Promise.all([
                apiClient.get('/portal/me'),
                apiClient.get('/portal/appointments'),
                apiClient.get('/portal/billing'),
                apiClient.get('/portal/history'),
            ]);
            setProfile(meRes.data);
            setAppointments(apptRes.data);
            setInvoices(billRes.data);
            setHistory(histRes.data);
        } catch {
            setAuthed(false);
        }
    };

    const handleLogout = async () => {
        try { await apiClient.post('/portal/logout'); } catch {}
        setAuthed(false);
        setProfile(null);
        setAppointments([]);
        setInvoices([]);
        setHistory([]);
        setVerifyForm({ outpatient_no: '', date_of_birth: '', phone_last4: '' });
    };

    useEffect(() => {
        // Without a hospital pick, the API client has no X-Tenant-ID and every
        // portal call would 400. Bounce to the hospital picker with a `next`
        // param so the Portal returns the patient straight back here after
        // they choose their hospital, instead of dropping them on /login.
        if (!localStorage.getItem('hms_tenant_id')) {
            toast('Pick your hospital first.', { icon: 'ℹ️' });
            navigate('/portal?next=/patient', { replace: true });
            return;
        }
        (async () => {
            try {
                await apiClient.get('/portal/me');
                setAuthed(true);
                await loadAll();
            } catch {
                setAuthed(false);
            }
        })();
    }, [navigate]);

    if (!authed) {
        return (
            <div className="min-h-screen w-full grid lg:grid-cols-5 bg-white font-sans selection:bg-[#00ffff]/30">
                {/* ============== Immersive brand panel (left, lg+) ============== */}
                <aside className="hidden lg:flex lg:col-span-2 relative overflow-hidden lp-bg-hero text-white isolate">
                    <div className="absolute inset-0 pointer-events-none">
                        <WebGLHero className="absolute inset-0 opacity-70" />
                        <div className="absolute -top-24 -right-20 size-96 rounded-full bg-[#00ffff]/15 blur-[120px] animate-blob-breathe" />
                        <div className="absolute -bottom-32 -left-16 size-[28rem] rounded-full bg-[#008080]/40 blur-[120px] animate-blob-breathe" style={{ animationDelay: '5s' }} />
                    </div>

                    <div className="relative z-10 flex flex-col justify-between w-full p-12 xl:p-16">
                        <div className="flex items-center gap-3">
                            <span className="inline-flex items-center justify-center size-11 rounded-2xl bg-[#00ffff]/15 ring-1 ring-[#00ffff]/30 backdrop-blur-md">
                                <HeartPulse size={22} className="text-[#7dfdfd]" />
                            </span>
                            <div>
                                <p className="text-sm font-bold tracking-tight">{tenantName}</p>
                                <p className="text-2xs text-[#9fdede] uppercase tracking-[0.16em]">Patient portal</p>
                            </div>
                        </div>

                        <div className="max-w-md">
                            <span className="lp-chip-dark inline-flex"><Sparkles size={11} /> Your records, in one place</span>
                            <h1 className="mt-6 text-4xl xl:text-5xl font-extrabold leading-[1.05] tracking-tight">
                                Your care,{' '}
                                <span className="lp-text-gradient">on your side</span>.
                            </h1>
                            <p className="mt-5 text-[#cdeeee] text-base leading-relaxed">
                                Look up your appointments, lab results, prescriptions, and bills the
                                moment you verify. Everything here is read-only and private to you.
                            </p>
                        </div>

                        <div className="grid grid-cols-3 gap-3">
                            <PortalPreview icon={<CalendarDays size={16} />} label="Appointments" />
                            <PortalPreview icon={<Receipt size={16} />} label="Billing" />
                            <PortalPreview icon={<ClipboardList size={16} />} label="History" />
                        </div>
                    </div>
                </aside>

                {/* ============== Verification form (right) ============== */}
                <main className="lg:col-span-3 flex flex-col justify-center items-center px-5 py-12 sm:px-10 relative lp-bg-ice">
                    {/* Mobile brand bar */}
                    <div className="lg:hidden w-full max-w-md mb-8 flex items-center gap-3">
                        <span className="inline-flex items-center justify-center size-12 rounded-2xl bg-gradient-to-br from-[#00ffff] to-[#008080] lp-glow-ring">
                            <HeartPulse size={22} className="text-[#012626]" />
                        </span>
                        <div>
                            <p className="text-base font-extrabold text-[#012626] tracking-tight">Patient Portal</p>
                            <p className="text-xs text-ink-500">{tenantName}</p>
                        </div>
                    </div>

                    <div className="w-full max-w-md animate-slide-up">
                        <div className="mb-7">
                            <span className="lp-chip">Verify it's you</span>
                            <h2 className="mt-3 text-3xl font-extrabold text-[#012626] tracking-tight">Open your portal</h2>
                            <p className="mt-2 text-sm text-ink-600">
                                Enter the details from your patient card and the last 4 digits of your registered phone number.
                            </p>
                        </div>

                        <form onSubmit={handleLookup} noValidate className="lp-glass rounded-[1.4rem] p-6 space-y-4">
                            <div className="bg-[#e6fbfb] ring-1 ring-[#b2f0f0] rounded-xl p-3 text-xs text-[#015050] flex gap-2">
                                <AlertCircle size={14} className="shrink-0 mt-0.5 text-[#008080]" />
                                <p className="leading-relaxed">This portal is read-only. We use these three details only to confirm your identity.</p>
                            </div>

                            <ValidatedField
                                id="patien-op-number" label="OP Number"
                                value={verifyForm.outpatient_no}
                                onChange={(v) => setVerifyForm({ ...verifyForm, outpatient_no: v.toUpperCase() })}
                                onBlur={() => markTouched('outpatient_no')}
                                placeholder="OP-2026-0001" mono
                                valid={isValid('outpatient_no')} showError={showError('outpatient_no')}
                                error={fieldError('outpatient_no', verifyForm.outpatient_no)}
                                touched={touched.outpatient_no}
                            />
                            <ValidatedField
                                id="patien-date-of-birth" label="Date of birth" type="date"
                                value={verifyForm.date_of_birth} max={today}
                                onChange={(v) => setVerifyForm({ ...verifyForm, date_of_birth: v })}
                                onBlur={() => markTouched('date_of_birth')}
                                valid={isValid('date_of_birth')} showError={showError('date_of_birth')}
                                error={fieldError('date_of_birth', verifyForm.date_of_birth)}
                                touched={touched.date_of_birth}
                            />
                            <ValidatedField
                                id="patien-last-4-digits-of-phone" label="Last 4 digits of phone"
                                value={verifyForm.phone_last4} inputMode="numeric" maxLength={4} mono center
                                onChange={(v) => setVerifyForm({ ...verifyForm, phone_last4: v.replace(/\D/g, '') })}
                                onBlur={() => markTouched('phone_last4')}
                                placeholder="0000"
                                valid={isValid('phone_last4')} showError={showError('phone_last4')}
                                error={fieldError('phone_last4', verifyForm.phone_last4)}
                                touched={touched.phone_last4}
                            />

                            <button type="submit" disabled={submitting} className="lp-btn-glow w-full justify-center py-3 group disabled:opacity-60">
                                {submitting ? (
                                    <><Activity className="animate-spin" size={18} /> Verifying…</>
                                ) : (
                                    <>Open my portal <CheckCircle2 size={16} className="transition-transform duration-200 group-hover:scale-110" /></>
                                )}
                            </button>

                            <div className="pt-2 border-t border-[#b2f0f0] flex items-center justify-between text-xs">
                                <button type="button" onClick={() => navigate('/')} className="text-ink-500 hover:text-[#008080] flex items-center gap-1 font-semibold transition-colors duration-200">
                                    <ArrowLeft size={12} /> Back
                                </button>
                                <span className="text-ink-400 flex items-center gap-1">
                                    <Lock size={12} /> Read-only access
                                </span>
                            </div>
                        </form>

                        <p className="mt-6 text-center text-2xs text-ink-400 uppercase tracking-[0.16em] inline-flex items-center gap-1.5 w-full justify-center">
                            <ShieldCheck size={12} className="text-[#008080]" /> Secured and private to you
                        </p>
                    </div>
                </main>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-ink-50">
            <header className="bg-white/80 backdrop-blur-md border-b border-ink-200/70 sticky top-0 z-30">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="size-10 rounded-xl bg-brand-gradient flex items-center justify-center shrink-0 shadow-glow">
                            <HeartPulse size={18} className="text-white" />
                        </div>
                        <div>
                            <p className="font-semibold text-ink-900 tracking-tight">{profile?.full_name || 'Loading…'}</p>
                            <p className="text-xs text-ink-500 font-mono">{profile?.outpatient_no}</p>
                        </div>
                    </div>
                    <button type="button" onClick={handleLogout} className="flex items-center gap-2 text-sm font-semibold text-ink-500 hover:text-rose-600 px-3 py-2 rounded-lg hover:bg-rose-50 transition-colors">
                        <LogOut size={15} /> Sign out
                    </button>
                </div>
                <nav className="max-w-5xl mx-auto px-4 sm:px-6 flex gap-1 border-t border-ink-100 overflow-x-auto" aria-label="Portal sections">
                    {TABS.map(({ key, label, icon: Icon }) => (
                        <button type="button" key={key} onClick={() => setActiveTab(key)}
                            aria-current={activeTab === key ? 'page' : undefined}
                            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                                activeTab === key
                                    ? 'border-brand-600 text-brand-700'
                                    : 'border-transparent text-ink-500 hover:text-ink-900'
                            }`}
                        >
                            <Icon size={14} /> {label}
                        </button>
                    ))}
                </nav>
            </header>

            <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
                {!profile ? (
                    <div className="flex items-center gap-2 text-ink-400">
                        <Activity className="animate-spin" size={16} /> Loading…
                    </div>
                ) : activeTab === 'profile' ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 animate-fade-in">
                        {[
                            ['Full name',           profile.full_name],
                            ['Outpatient number',   profile.outpatient_no],
                            ['Date of birth',       profile.date_of_birth],
                            ['Sex',                 profile.sex],
                            ['Blood group',         profile.blood_group],
                            ['Allergies',           profile.allergies],
                            ['Chronic conditions',  profile.chronic_conditions],
                            ['Phone',               profile.telephone_1_masked],
                        ].map(([k, v]) => (
                            <div key={k} className="card p-4">
                                <p className="stat-label">{k}</p>
                                <p className="text-sm font-semibold text-ink-900 mt-1">{v || 'Not recorded'}</p>
                            </div>
                        ))}
                    </div>
                ) : activeTab === 'appointments' ? (
                    appointments.length === 0 ? (
                        <p className="text-sm text-ink-400">No appointments on file.</p>
                    ) : (
                        <ul className="space-y-2 animate-fade-in">
                            {appointments.map(a => (
                                <li key={a.appointment_id} className="card p-4 flex justify-between items-center">
                                    <div>
                                        <p className="font-semibold text-ink-900 text-sm">{new Date(a.appointment_date).toLocaleString()}</p>
                                        <p className="text-xs text-ink-500 mt-0.5">{a.doctor_name}</p>
                                        {a.notes && <p className="text-xs text-ink-600 mt-1">{a.notes}</p>}
                                    </div>
                                    <span className="badge-neutral">{a.status}</span>
                                </li>
                            ))}
                        </ul>
                    )
                ) : activeTab === 'billing' ? (
                    invoices.length === 0 ? (
                        <p className="text-sm text-ink-400">No invoices on file.</p>
                    ) : (
                        <ul className="space-y-2 animate-fade-in">
                            {invoices.map(i => (
                                <li key={i.invoice_id} className="card p-4 flex justify-between items-center">
                                    <div>
                                        <p className="font-semibold text-ink-900 text-sm">Invoice INV-{i.invoice_id}</p>
                                        <p className="text-xs text-ink-500 mt-0.5">{i.billing_date ? new Date(i.billing_date).toLocaleDateString() : 'No date'}</p>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-base font-semibold ${i.balance > 0 ? 'text-rose-600' : 'text-accent-600'}`}>
                                            KES {i.balance.toFixed(2)}
                                        </p>
                                        <p className="text-2xs uppercase tracking-wider font-semibold text-ink-400 mt-0.5">{i.status}</p>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )
                ) : activeTab === 'history' ? (
                    history.length === 0 ? (
                        <p className="text-sm text-ink-400">No history entries on file.</p>
                    ) : (
                        <ul className="space-y-2 animate-fade-in">
                            {history.map(h => (
                                <li key={h.entry_id} className="card p-4">
                                    <p className="text-2xs font-semibold uppercase tracking-wider text-ink-400">{h.type.replace(/_/g, ' ')}</p>
                                    <p className="font-semibold text-ink-900 text-sm mt-1">{h.title}</p>
                                    {h.description && <p className="text-xs text-ink-600 mt-1 leading-relaxed">{h.description}</p>}
                                    <p className="text-2xs text-ink-400 mt-2">{h.event_date}</p>
                                </li>
                            ))}
                        </ul>
                    )
                ) : null}
            </main>
        </div>
    );
}

function PortalPreview({ icon, label }) {
    return (
        <div className="flex flex-col items-start gap-2 p-3 rounded-xl bg-[#00ffff]/[0.06] ring-1 ring-[#00ffff]/15 backdrop-blur-sm">
            <span className="size-8 rounded-lg bg-[#00ffff]/10 flex items-center justify-center text-[#7dfdfd]">
                {icon}
            </span>
            <span className="text-2xs font-semibold text-white/85">{label}</span>
        </div>
    );
}

/*
 * ValidatedField — text/date input with inline validation micro-interactions.
 * The ring shifts green when the value is valid (after the field is touched)
 * and red with a message when it is wrong, so a patient gets immediate, calm
 * feedback while typing rather than a single error on submit.
 */
function ValidatedField({
    id, label, value, onChange, onBlur, placeholder, type = 'text',
    mono, center, inputMode, maxLength, max, valid, showError, error, touched,
}) {
    const ring = showError
        ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-200/60'
        : touched && valid
            ? 'border-[#00d4d4] focus:border-[#008080] focus:ring-[#00ffff]/30'
            : 'border-[#b2f0f0] focus:border-[#008080] focus:ring-[#00ffff]/30';
    return (
        <div>
            <label htmlFor={id} className="block text-xs font-bold text-[#015050] mb-1.5">{label}</label>
            <div className="relative">
                <input
                    id={id}
                    type={type}
                    value={value}
                    inputMode={inputMode}
                    maxLength={maxLength}
                    max={max}
                    placeholder={placeholder}
                    onChange={(e) => onChange(e.target.value)}
                    onBlur={onBlur}
                    aria-invalid={showError || undefined}
                    className={`w-full rounded-xl bg-white px-3.5 py-2.5 text-sm text-[#012626] border ${ring} pr-10 shadow-sm outline-none transition-all duration-200 ease-in-out focus:ring-4 ${mono ? 'font-mono' : ''} ${center ? 'text-center tracking-[0.4em]' : ''}`}
                />
                {/* Status icon micro-interaction */}
                {touched && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
                        {showError
                            ? <AlertCircle size={16} className="text-rose-400 animate-fade-in" />
                            : valid
                                ? <CheckCircle2 size={16} className="text-[#00d4d4] animate-fade-in" />
                                : null}
                    </span>
                )}
            </div>
            {showError && (
                <p className="mt-1.5 text-2xs font-semibold text-rose-500 flex items-center gap-1 animate-slide-up">
                    <AlertCircle size={11} /> {error}
                </p>
            )}
        </div>
    );
}
