import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import {
    HeartPulse, ShieldCheck, CalendarDays, Receipt, ClipboardList,
    LogOut, Activity, ArrowLeft, AlertCircle,
} from 'lucide-react';

const TABS = [
    { key: 'profile', label: 'Profile', icon: HeartPulse },
    { key: 'appointments', label: 'Appointments', icon: CalendarDays },
    { key: 'billing', label: 'Billing', icon: Receipt },
    { key: 'history', label: 'History', icon: ClipboardList },
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
            toast.error('All three fields are required.');
            return;
        }
        if (!/^\d{4}$/.test(verifyForm.phone_last4)) {
            toast.error('Phone suffix must be exactly 4 digits.');
            return;
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

    // Try to resume an existing portal session on mount.
    useEffect(() => {
        (async () => {
            try {
                await apiClient.get('/portal/me');
                setAuthed(true);
                await loadAll();
            } catch {
                setAuthed(false);
            }
        })();
    }, []);

    if (!authed) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 dark:from-slate-950 dark:to-slate-900 flex flex-col items-center justify-center p-4">
                <div className="max-w-md w-full">
                    <div className="text-center mb-6">
                        <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-600 rounded-2xl shadow-lg mb-4">
                            <HeartPulse size={32} className="text-white" aria-hidden="true" />
                        </div>
                        <h1 className="text-2xl font-black text-slate-900 dark:text-white">Patient Portal</h1>
                        <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">{tenantName}</p>
                    </div>

                    <form
                        onSubmit={handleLookup}
                        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-soft p-6 space-y-4"
                    >
                        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/30 rounded-lg p-3 text-xs text-amber-900 dark:text-amber-200 flex gap-2">
                            <AlertCircle size={14} className="shrink-0 mt-0.5" aria-hidden="true" />
                            <p>This portal is read-only. To verify, enter the details on your patient card and the last 4 digits of your registered phone number.</p>
                        </div>

                        <div>
                            <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">OP Number</label>
                            <input
                                required
                                type="text"
                                value={verifyForm.outpatient_no}
                                onChange={(e) => setVerifyForm({ ...verifyForm, outpatient_no: e.target.value.toUpperCase() })}
                                placeholder="OP-2026-0001"
                                className="w-full px-3 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Date of Birth</label>
                            <input
                                required
                                type="date"
                                value={verifyForm.date_of_birth}
                                onChange={(e) => setVerifyForm({ ...verifyForm, date_of_birth: e.target.value })}
                                className="w-full px-3 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Last 4 digits of phone</label>
                            <input
                                required
                                type="text"
                                inputMode="numeric"
                                pattern="\d{4}"
                                maxLength={4}
                                value={verifyForm.phone_last4}
                                onChange={(e) => setVerifyForm({ ...verifyForm, phone_last4: e.target.value.replace(/\D/g, '') })}
                                placeholder="••••"
                                className="w-full px-3 py-2.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white font-mono tracking-[0.4em] text-center focus:outline-none focus:ring-2 focus:ring-brand-500"
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={submitting}
                            className="w-full py-3 bg-brand-600 hover:bg-brand-700 text-white rounded-lg font-bold text-sm shadow-sm disabled:opacity-50"
                        >
                            {submitting ? 'Verifying...' : 'Open my portal'}
                        </button>

                        <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
                            <button
                                type="button"
                                onClick={() => navigate('/')}
                                className="text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white flex items-center gap-1 font-bold"
                            >
                                <ArrowLeft size={12} /> Back
                            </button>
                            <span className="text-slate-400 flex items-center gap-1">
                                <ShieldCheck size={12} /> Read-only access
                            </span>
                        </div>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
            <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center shrink-0">
                            <HeartPulse size={20} className="text-white" aria-hidden="true" />
                        </div>
                        <div>
                            <p className="font-black text-slate-900 dark:text-white">{profile?.full_name || 'Loading...'}</p>
                            <p className="text-xs text-slate-500 font-mono">{profile?.outpatient_no}</p>
                        </div>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-rose-600 dark:text-slate-400 dark:hover:text-rose-400"
                    >
                        <LogOut size={16} aria-hidden="true" /> Sign out
                    </button>
                </div>
                <nav className="max-w-5xl mx-auto px-4 sm:px-6 flex gap-1 border-t border-slate-100 dark:border-slate-800 overflow-x-auto" aria-label="Portal sections">
                    {TABS.map(({ key, label, icon: Icon }) => (
                        <button
                            key={key}
                            onClick={() => setActiveTab(key)}
                            aria-current={activeTab === key ? 'page' : undefined}
                            className={`px-3 py-2.5 text-sm font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
                                activeTab === key
                                    ? 'border-brand-600 text-brand-700 dark:text-brand-400'
                                    : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                            }`}
                        >
                            <Icon size={14} aria-hidden="true" /> {label}
                        </button>
                    ))}
                </nav>
            </header>

            <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
                {!profile ? (
                    <div className="flex items-center gap-2 text-slate-400">
                        <Activity className="animate-spin" size={16} /> Loading...
                    </div>
                ) : activeTab === 'profile' ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {[
                            ['Full name', profile.full_name],
                            ['Outpatient number', profile.outpatient_no],
                            ['Date of birth', profile.date_of_birth],
                            ['Sex', profile.sex],
                            ['Blood group', profile.blood_group],
                            ['Allergies', profile.allergies],
                            ['Chronic conditions', profile.chronic_conditions],
                            ['Phone', profile.telephone_1_masked],
                        ].map(([k, v]) => (
                            <div key={k} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
                                <p className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">{k}</p>
                                <p className="text-sm font-bold text-slate-900 dark:text-white mt-1">{v || '—'}</p>
                            </div>
                        ))}
                    </div>
                ) : activeTab === 'appointments' ? (
                    appointments.length === 0 ? (
                        <p className="text-sm text-slate-400">No appointments on file.</p>
                    ) : (
                        <ul className="space-y-2">
                            {appointments.map(a => (
                                <li key={a.appointment_id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex justify-between items-center">
                                    <div>
                                        <p className="font-bold text-slate-900 dark:text-white text-sm">{new Date(a.appointment_date).toLocaleString()}</p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{a.doctor_name}</p>
                                        {a.notes && <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">{a.notes}</p>}
                                    </div>
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                                        {a.status}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )
                ) : activeTab === 'billing' ? (
                    invoices.length === 0 ? (
                        <p className="text-sm text-slate-400">No invoices on file.</p>
                    ) : (
                        <ul className="space-y-2">
                            {invoices.map(i => (
                                <li key={i.invoice_id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex justify-between items-center">
                                    <div>
                                        <p className="font-bold text-slate-900 dark:text-white text-sm">Invoice INV-{i.invoice_id}</p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{i.billing_date ? new Date(i.billing_date).toLocaleDateString() : '—'}</p>
                                    </div>
                                    <div className="text-right">
                                        <p className={`text-base font-black ${i.balance > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                                            KES {i.balance.toFixed(2)}
                                        </p>
                                        <p className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{i.status}</p>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )
                ) : activeTab === 'history' ? (
                    history.length === 0 ? (
                        <p className="text-sm text-slate-400">No history entries on file.</p>
                    ) : (
                        <ul className="space-y-2">
                            {history.map(h => (
                                <li key={h.entry_id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
                                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{h.type.replace(/_/g, ' ')}</p>
                                    <p className="font-bold text-slate-900 dark:text-white text-sm mt-1">{h.title}</p>
                                    {h.description && <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">{h.description}</p>}
                                    <p className="text-[10px] text-slate-400 mt-2">{h.event_date}</p>
                                </li>
                            ))}
                        </ul>
                    )
                ) : null}
            </main>
        </div>
    );
}
