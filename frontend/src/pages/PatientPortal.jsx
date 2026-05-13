import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import {
    HeartPulse, ShieldCheck, CalendarDays, Receipt, ClipboardList,
    LogOut, Activity, ArrowLeft, AlertCircle,
} from 'lucide-react';

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
    const [submitting, setSubmitting] = useState(false);
    const [activeTab, setActiveTab] = useState('profile');
    const [profile, setProfile] = useState(null);
    const [appointments, setAppointments] = useState([]);
    const [invoices, setInvoices] = useState([]);
    const [history, setHistory] = useState([]);

    const handleLookup = async (e) => {
        e.preventDefault();
        if (!verifyForm.outpatient_no || !verifyForm.date_of_birth || !verifyForm.phone_last4) {
            return toast.error('All three fields are required.');
        }
        if (!/^\d{4}$/.test(verifyForm.phone_last4)) {
            return toast.error('Phone suffix must be exactly 4 digits.');
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
        // they choose their hospital — instead of dropping them on /login.
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
            <div className="min-h-screen bg-ink-50 bg-mesh flex flex-col items-center justify-center p-4">
                <div className="max-w-md w-full animate-slide-up">
                    <div className="text-center mb-6">
                        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-gradient shadow-glow">
                            <HeartPulse size={26} className="text-white" />
                        </div>
                        <h1 className="mt-5 text-2xl font-semibold text-ink-900 tracking-tight">Patient Portal</h1>
                        <p className="text-sm text-ink-500 mt-1">{tenantName}</p>
                    </div>

                    <form onSubmit={handleLookup} className="card p-6 space-y-4">
                        <div className="bg-amber-50 ring-1 ring-amber-100 rounded-xl p-3 text-xs text-amber-900 flex gap-2">
                            <AlertCircle size={14} className="shrink-0 mt-0.5" />
                            <p className="leading-relaxed">This portal is read-only. To verify, enter the details on your patient card and the last 4 digits of your registered phone number.</p>
                        </div>

                        <div>
                            <label className="label">OP Number</label>
                            <input
                                required type="text"
                                value={verifyForm.outpatient_no}
                                onChange={(e) => setVerifyForm({ ...verifyForm, outpatient_no: e.target.value.toUpperCase() })}
                                placeholder="OP-2026-0001"
                                className="input font-mono"
                            />
                        </div>
                        <div>
                            <label className="label">Date of birth</label>
                            <input required type="date" value={verifyForm.date_of_birth}
                                onChange={(e) => setVerifyForm({ ...verifyForm, date_of_birth: e.target.value })}
                                className="input" />
                        </div>
                        <div>
                            <label className="label">Last 4 digits of phone</label>
                            <input
                                required type="text" inputMode="numeric" pattern="\d{4}" maxLength={4}
                                value={verifyForm.phone_last4}
                                onChange={(e) => setVerifyForm({ ...verifyForm, phone_last4: e.target.value.replace(/\D/g, '') })}
                                placeholder="••••"
                                className="input font-mono tracking-[0.4em] text-center"
                            />
                        </div>
                        <button type="submit" disabled={submitting} className="btn-primary w-full py-3">
                            {submitting ? 'Verifying…' : 'Open my portal'}
                        </button>

                        <div className="pt-2 border-t border-ink-100 flex items-center justify-between text-xs">
                            <button type="button" onClick={() => navigate('/')} className="text-ink-500 hover:text-ink-900 flex items-center gap-1 font-semibold">
                                <ArrowLeft size={12} /> Back
                            </button>
                            <span className="text-ink-400 flex items-center gap-1">
                                <ShieldCheck size={12} /> Read-only access
                            </span>
                        </div>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-ink-50">
            <header className="bg-white/80 backdrop-blur-md border-b border-ink-200/70 sticky top-0 z-30">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-brand-gradient flex items-center justify-center shrink-0 shadow-glow">
                            <HeartPulse size={18} className="text-white" />
                        </div>
                        <div>
                            <p className="font-semibold text-ink-900 tracking-tight">{profile?.full_name || 'Loading…'}</p>
                            <p className="text-xs text-ink-500 font-mono">{profile?.outpatient_no}</p>
                        </div>
                    </div>
                    <button onClick={handleLogout} className="flex items-center gap-2 text-sm font-semibold text-ink-500 hover:text-rose-600 px-3 py-2 rounded-lg hover:bg-rose-50 transition-colors">
                        <LogOut size={15} /> Sign out
                    </button>
                </div>
                <nav className="max-w-5xl mx-auto px-4 sm:px-6 flex gap-1 border-t border-ink-100 overflow-x-auto" aria-label="Portal sections">
                    {TABS.map(({ key, label, icon: Icon }) => (
                        <button key={key} onClick={() => setActiveTab(key)}
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
                                <p className="text-sm font-semibold text-ink-900 mt-1">{v || '—'}</p>
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
                                        <p className="text-xs text-ink-500 mt-0.5">{i.billing_date ? new Date(i.billing_date).toLocaleDateString() : '—'}</p>
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
