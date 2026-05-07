import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    CalendarDays, Plus, X, Filter, Clock, CheckCircle2, XCircle,
    UserRound, Stethoscope, Activity, RefreshCw,
} from 'lucide-react';

const STATUS_BADGES = {
    Scheduled: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    Confirmed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    Completed: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    Cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
    'No-Show': 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
};

const STATUS_OPTIONS = ['Scheduled', 'Confirmed', 'Completed', 'Cancelled', 'No-Show'];

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function Appointments() {
    const [appointments, setAppointments] = useState([]);
    const [doctors, setDoctors] = useState([]);
    const [patients, setPatients] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [filter, setFilter] = useState({ status: '', from: todayISO(), to: '' });
    const [isFormOpen, setIsFormOpen] = useState(false);
    const [form, setForm] = useState({ patient_id: '', doctor_id: '', appointment_date: '', notes: '' });
    const [submitting, setSubmitting] = useState(false);

    const fetchAppointments = async () => {
        setIsLoading(true);
        try {
            const params = {};
            if (filter.status) params.status = filter.status;
            if (filter.from) params.date_from = `${filter.from}T00:00:00`;
            if (filter.to) params.date_to = `${filter.to}T23:59:59`;
            const res = await apiClient.get('/appointments/', { params });
            setAppointments(res.data || []);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to load appointments');
        } finally {
            setIsLoading(false);
        }
    };

    const fetchDirectory = async () => {
        try {
            const [doctorsRes, patientsRes] = await Promise.all([
                apiClient.get('/admin/users').catch(() => ({ data: [] })),
                apiClient.get('/patients/').catch(() => ({ data: [] })),
            ]);
            setDoctors((doctorsRes.data || []).filter(u => u.role === 'Doctor' && u.is_active));
            setPatients(patientsRes.data || []);
        } catch (error) {
            // non-fatal — the form just shows empty selects.
        }
    };

    useEffect(() => {
        fetchDirectory();
    }, []);

    useEffect(() => {
        fetchAppointments();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filter.status, filter.from, filter.to]);

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!form.patient_id || !form.doctor_id || !form.appointment_date) {
            toast.error('Patient, doctor, and date/time are required.');
            return;
        }
        setSubmitting(true);
        try {
            await apiClient.post('/appointments/', {
                patient_id: parseInt(form.patient_id, 10),
                doctor_id: parseInt(form.doctor_id, 10),
                appointment_date: form.appointment_date,
                notes: form.notes || null,
            });
            toast.success('Appointment booked.');
            setIsFormOpen(false);
            setForm({ patient_id: '', doctor_id: '', appointment_date: '', notes: '' });
            fetchAppointments();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to book appointment.');
        } finally {
            setSubmitting(false);
        }
    };

    const updateStatus = async (id, status) => {
        try {
            await apiClient.patch(`/appointments/${id}/status`, { status });
            toast.success(`Marked as ${status}.`);
            fetchAppointments();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Status update failed.');
        }
    };

    const cancel = async (id) => {
        if (!window.confirm('Cancel this appointment?')) return;
        try {
            await apiClient.delete(`/appointments/${id}`);
            toast.success('Appointment cancelled.');
            fetchAppointments();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Cancel failed.');
        }
    };

    // Group by day for the calendar-ish layout.
    const grouped = useMemo(() => {
        const map = {};
        for (const a of appointments) {
            if (!a.appointment_date) continue;
            const day = a.appointment_date.slice(0, 10);
            (map[day] = map[day] || []).push(a);
        }
        return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
    }, [appointments]);

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
                        <CalendarDays className="text-brand-600" /> Appointments
                    </h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Schedule, confirm, and manage clinic appointments.
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={fetchAppointments}
                        className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-lg text-sm font-bold hover:bg-slate-50 dark:hover:bg-slate-700"
                        aria-label="Reload appointments"
                    >
                        <RefreshCw size={16} aria-hidden="true" /> Refresh
                    </button>
                    <button
                        onClick={() => setIsFormOpen(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-bold shadow-sm"
                    >
                        <Plus size={16} aria-hidden="true" /> New Appointment
                    </button>
                </div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex flex-wrap gap-3 items-end">
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1">
                        <Filter size={12} aria-hidden="true" /> Status
                    </label>
                    <select
                        value={filter.status}
                        onChange={(e) => setFilter({ ...filter, status: e.target.value })}
                        className="px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                        <option value="">Any status</option>
                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">From</label>
                    <input
                        type="date"
                        value={filter.from}
                        onChange={(e) => setFilter({ ...filter, from: e.target.value })}
                        className="px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                </div>
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">To</label>
                    <input
                        type="date"
                        value={filter.to}
                        onChange={(e) => setFilter({ ...filter, to: e.target.value })}
                        className="px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                </div>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center h-64 text-slate-400 dark:text-slate-500">
                    <Activity className="animate-spin mr-2" /> Loading...
                </div>
            ) : grouped.length === 0 ? (
                <div className="bg-white dark:bg-slate-900 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl p-12 text-center text-slate-400 dark:text-slate-500">
                    <CalendarDays size={48} className="mx-auto mb-3 text-slate-300 dark:text-slate-700" />
                    <p className="text-sm font-bold">No appointments in this window.</p>
                </div>
            ) : (
                <div className="space-y-6">
                    {grouped.map(([day, list]) => (
                        <section key={day}>
                            <h2 className="text-sm font-black text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3 sticky top-0 bg-slate-50/95 dark:bg-slate-950/95 py-2 backdrop-blur-sm z-[1]">
                                {new Date(day).toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                                <span className="ml-2 text-xs font-bold text-slate-400">· {list.length}</span>
                            </h2>
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                {list.map(appt => (
                                    <article key={appt.appointment_id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 flex gap-4 items-start">
                                        <div className="w-14 shrink-0 text-center">
                                            <div className="text-2xl font-black text-slate-900 dark:text-white">
                                                {new Date(appt.appointment_date).toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit', hour12: false })}
                                            </div>
                                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                                                <Clock size={10} className="inline -mt-0.5" /> {new Date(appt.appointment_date).toLocaleTimeString('en-KE', { hour12: true, hour: 'numeric' }).split(' ')[1]}
                                            </div>
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <h3 className="font-bold text-slate-900 dark:text-white truncate flex items-center gap-1.5">
                                                    <UserRound size={14} aria-hidden="true" className="text-slate-400" />
                                                    {appt.patient_name}
                                                </h3>
                                                {appt.patient_opd && <span className="text-xs font-mono text-slate-400">{appt.patient_opd}</span>}
                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${STATUS_BADGES[appt.status] || 'bg-slate-100 text-slate-600'}`}>
                                                    {appt.status}
                                                </span>
                                            </div>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1.5">
                                                <Stethoscope size={12} aria-hidden="true" /> {appt.doctor_name}
                                            </p>
                                            {appt.notes && <p className="text-xs text-slate-600 dark:text-slate-300 mt-2 line-clamp-2">{appt.notes}</p>}

                                            {appt.status !== 'Completed' && appt.status !== 'Cancelled' && (
                                                <div className="flex flex-wrap gap-2 mt-3">
                                                    {appt.status === 'Scheduled' && (
                                                        <button
                                                            onClick={() => updateStatus(appt.appointment_id, 'Confirmed')}
                                                            className="text-xs font-bold px-2.5 py-1 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 rounded hover:bg-emerald-100 dark:hover:bg-emerald-900/30"
                                                        >
                                                            <CheckCircle2 size={12} className="inline mr-1" /> Confirm
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => updateStatus(appt.appointment_id, 'Completed')}
                                                        className="text-xs font-bold px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded hover:bg-slate-200 dark:hover:bg-slate-700"
                                                    >
                                                        Mark Completed
                                                    </button>
                                                    <button
                                                        onClick={() => updateStatus(appt.appointment_id, 'No-Show')}
                                                        className="text-xs font-bold px-2.5 py-1 bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 rounded hover:bg-amber-100 dark:hover:bg-amber-900/30"
                                                    >
                                                        No-Show
                                                    </button>
                                                    <button
                                                        onClick={() => cancel(appt.appointment_id)}
                                                        className="text-xs font-bold px-2.5 py-1 bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-300 rounded hover:bg-rose-100 dark:hover:bg-rose-900/30"
                                                    >
                                                        <XCircle size={12} className="inline mr-1" /> Cancel
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    </article>
                                ))}
                            </div>
                        </section>
                    ))}
                </div>
            )}

            {isFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="New appointment">
                    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
                        <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-950/50">
                            <h2 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                <CalendarDays size={18} className="text-brand-600" /> New Appointment
                            </h2>
                            <button onClick={() => setIsFormOpen(false)} aria-label="Close dialog" className="text-slate-500 hover:text-slate-900 dark:hover:text-white">
                                <X size={20} aria-hidden="true" />
                            </button>
                        </div>
                        <form onSubmit={handleCreate} className="p-5 space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Patient</label>
                                <select
                                    required
                                    value={form.patient_id}
                                    onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                                >
                                    <option value="">Select patient...</option>
                                    {patients.map(p => (
                                        <option key={p.patient_id} value={p.patient_id}>
                                            {p.surname}, {p.other_names} ({p.outpatient_no})
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Doctor</label>
                                <select
                                    required
                                    value={form.doctor_id}
                                    onChange={(e) => setForm({ ...form, doctor_id: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                                >
                                    <option value="">Select doctor...</option>
                                    {doctors.map(d => (
                                        <option key={d.user_id} value={d.user_id}>
                                            {d.full_name} {d.specialization ? `· ${d.specialization}` : ''}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Date & Time</label>
                                <input
                                    type="datetime-local"
                                    required
                                    value={form.appointment_date}
                                    onChange={(e) => setForm({ ...form, appointment_date: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1.5">Notes (optional)</label>
                                <textarea
                                    rows={3}
                                    value={form.notes}
                                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500"
                                    placeholder="Reason for visit, prep instructions..."
                                />
                            </div>
                            <div className="flex justify-end gap-2 pt-2">
                                <button
                                    type="button"
                                    onClick={() => setIsFormOpen(false)}
                                    className="px-4 py-2 text-sm font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={submitting}
                                    className="px-5 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-bold disabled:opacity-50"
                                >
                                    {submitting ? 'Booking...' : 'Book appointment'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
