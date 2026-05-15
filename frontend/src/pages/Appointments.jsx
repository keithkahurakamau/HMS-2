import React, { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    CalendarDays, Plus, X, Filter, CheckCircle2, XCircle,
    UserRound, Stethoscope, Activity, RefreshCw,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { useActivePatient } from '../context/PatientContext';

const STATUS_BADGES = {
    Scheduled:  'badge-info',
    Confirmed:  'badge-success',
    Completed:  'badge-neutral',
    Cancelled:  'badge-danger',
    'No-Show':  'badge-warn',
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
    // Cross-page active patient — when present, "New appointment" pre-fills.
    const { activePatient } = useActivePatient();

    const fetchAppointments = async () => {
        setIsLoading(true);
        try {
            const params = {};
            if (filter.status) params.status = filter.status;
            if (filter.from)   params.date_from = `${filter.from}T00:00:00`;
            if (filter.to)     params.date_to   = `${filter.to}T23:59:59`;
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
            // /appointments/doctors is gated only by patients:write so receptionists
            // can populate the form. /admin/users would 403 for non-admins.
            const [doctorsRes, patientsRes] = await Promise.all([
                apiClient.get('/appointments/doctors').catch(() => ({ data: [] })),
                apiClient.get('/patients/').catch(() => ({ data: [] })),
            ]);
            setDoctors(doctorsRes.data || []);
            setPatients(patientsRes.data || []);
        } catch (error) { /* non-fatal */ }
    };

    useEffect(() => { fetchDirectory(); }, []);

    // When an active patient is open and the user clicks "New appointment",
    // pre-select them. This is what makes the Calendar feel connected to
    // the rest of the system — open patient → book → done.
    useEffect(() => {
        if (isFormOpen && activePatient?.patient_id && !form.patient_id) {
            setForm(f => ({ ...f, patient_id: String(activePatient.patient_id) }));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isFormOpen, activePatient]);

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
                doctor_id:  parseInt(form.doctor_id, 10),
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
            <PageHeader
                eyebrow="Calendar"
                icon={CalendarDays}
                title="Appointments"
                subtitle="Schedule, confirm, and manage clinic appointments."
                actions={
                    <>
                        <button onClick={fetchAppointments} className="btn-secondary cursor-pointer" aria-label="Reload appointments">
                            <RefreshCw size={15} /> Refresh
                        </button>
                        <button onClick={() => setIsFormOpen(true)} className="btn-primary cursor-pointer">
                            <Plus size={15} /> New appointment
                        </button>
                    </>
                }
            />

            <div className="card p-4 flex flex-wrap gap-4 items-end">
                <div className="flex flex-col gap-1">
                    <label className="label flex items-center gap-1"><Filter size={11} /> Status</label>
                    <select
                        value={filter.status}
                        onChange={(e) => setFilter({ ...filter, status: e.target.value })}
                        className="input"
                    >
                        <option value="">Any status</option>
                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>
                <div className="flex flex-col gap-1">
                    <label className="label">From</label>
                    <input type="date" value={filter.from} onChange={(e) => setFilter({ ...filter, from: e.target.value })} className="input" />
                </div>
                <div className="flex flex-col gap-1">
                    <label className="label">To</label>
                    <input type="date" value={filter.to} onChange={(e) => setFilter({ ...filter, to: e.target.value })} className="input" />
                </div>
            </div>

            {isLoading ? (
                <div className="flex items-center justify-center h-64 text-ink-400">
                    <Activity className="animate-spin mr-2" size={20} /> Loading…
                </div>
            ) : grouped.length === 0 ? (
                <div className="card p-12 text-center text-ink-400 border-dashed">
                    <CalendarDays size={44} className="mx-auto mb-3 text-ink-300" />
                    <p className="text-sm font-semibold">No appointments in this window.</p>
                    <p className="text-xs mt-1">Adjust your filters or book a new appointment.</p>
                </div>
            ) : (
                <div className="space-y-6">
                    {grouped.map(([day, list]) => (
                        <section key={day}>
                            <h2 className="section-eyebrow mb-3 sticky top-0 bg-ink-50/95 backdrop-blur-sm py-2 z-[1] flex items-center gap-2">
                                {new Date(day).toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                                <span className="text-ink-400 normal-case tracking-normal font-medium">&middot; {list.length}</span>
                            </h2>
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                {list.map(appt => (
                                    <article key={appt.appointment_id} className="card p-4 flex gap-4 items-start hover:shadow-elevated transition-shadow">
                                        <div className="w-16 shrink-0 text-center bg-ink-50 ring-1 ring-ink-100 rounded-xl py-2.5">
                                            <div className="text-lg font-semibold text-ink-900 leading-none">
                                                {new Date(appt.appointment_date).toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit', hour12: false })}
                                            </div>
                                            <div className="text-2xs font-semibold text-ink-400 uppercase tracking-wider mt-1">
                                                {new Date(appt.appointment_date).toLocaleDateString('en-KE', { month: 'short', day: 'numeric' })}
                                            </div>
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <h3 className="font-semibold text-ink-900 truncate flex items-center gap-1.5">
                                                    <UserRound size={14} className="text-ink-400" />
                                                    {appt.patient_name}
                                                </h3>
                                                {appt.patient_opd && <span className="text-2xs font-mono text-ink-400">{appt.patient_opd}</span>}
                                                <span className={STATUS_BADGES[appt.status] || 'badge-neutral'}>
                                                    {appt.status}
                                                </span>
                                            </div>
                                            <p className="text-xs text-ink-500 mt-1 flex items-center gap-1.5">
                                                <Stethoscope size={12} /> {appt.doctor_name}
                                            </p>
                                            {appt.notes && <p className="text-xs text-ink-600 mt-2 line-clamp-2 leading-relaxed">{appt.notes}</p>}

                                            {appt.status !== 'Completed' && appt.status !== 'Cancelled' && (
                                                <div className="flex flex-wrap gap-1.5 mt-3">
                                                    {appt.status === 'Scheduled' && (
                                                        <button onClick={() => updateStatus(appt.appointment_id, 'Confirmed')} className="text-xs font-semibold px-2.5 py-1 bg-accent-50 text-accent-700 rounded-lg ring-1 ring-accent-100 hover:bg-accent-100 transition-colors">
                                                            <CheckCircle2 size={12} className="inline mr-1" /> Confirm
                                                        </button>
                                                    )}
                                                    <button onClick={() => updateStatus(appt.appointment_id, 'Completed')} className="text-xs font-semibold px-2.5 py-1 bg-ink-100 text-ink-700 rounded-lg ring-1 ring-ink-200 hover:bg-ink-200 transition-colors">
                                                        Mark completed
                                                    </button>
                                                    <button onClick={() => updateStatus(appt.appointment_id, 'No-Show')} className="text-xs font-semibold px-2.5 py-1 bg-amber-50 text-amber-700 rounded-lg ring-1 ring-amber-100 hover:bg-amber-100 transition-colors">
                                                        No-show
                                                    </button>
                                                    <button onClick={() => cancel(appt.appointment_id)} className="text-xs font-semibold px-2.5 py-1 bg-rose-50 text-rose-700 rounded-lg ring-1 ring-rose-100 hover:bg-rose-100 transition-colors">
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
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/60 backdrop-blur-sm animate-fade-in" role="dialog" aria-modal="true">
                    <div className="card-elevated w-full max-w-lg overflow-hidden animate-slide-up">
                        <div className="px-5 py-4 border-b border-ink-100 flex justify-between items-center bg-ink-50/60">
                            <h2 className="font-semibold text-ink-900 flex items-center gap-2 tracking-tight">
                                <CalendarDays size={18} className="text-brand-600" /> New appointment
                            </h2>
                            <button onClick={() => setIsFormOpen(false)} aria-label="Close dialog" className="p-2 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-ink-100 transition-colors">
                                <X size={18} />
                            </button>
                        </div>
                        <form onSubmit={handleCreate} className="p-5 space-y-4">
                            <div>
                                <label className="label">Patient</label>
                                <select required value={form.patient_id} onChange={(e) => setForm({ ...form, patient_id: e.target.value })} className="input">
                                    <option value="">Select patient…</option>
                                    {patients.map(p => (
                                        <option key={p.patient_id} value={p.patient_id}>{p.surname}, {p.other_names} ({p.outpatient_no})</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Doctor</label>
                                <select required value={form.doctor_id} onChange={(e) => setForm({ ...form, doctor_id: e.target.value })} className="input">
                                    <option value="">Select doctor…</option>
                                    {doctors.map(d => (
                                        <option key={d.user_id} value={d.user_id}>{d.full_name}{d.specialization ? ` · ${d.specialization}` : ''}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="label">Date &amp; time</label>
                                <input type="datetime-local" required value={form.appointment_date} onChange={(e) => setForm({ ...form, appointment_date: e.target.value })} className="input" />
                            </div>
                            <div>
                                <label className="label">Notes (optional)</label>
                                <textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="input resize-none" placeholder="Reason for visit, prep instructions…" />
                            </div>
                            <div className="flex justify-end gap-2 pt-2">
                                <button type="button" onClick={() => setIsFormOpen(false)} className="btn-secondary">Cancel</button>
                                <button type="submit" disabled={submitting} className="btn-primary">
                                    {submitting ? 'Booking…' : 'Book appointment'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
