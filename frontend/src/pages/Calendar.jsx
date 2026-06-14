import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    CalendarDays, ChevronLeft, ChevronRight, Plus, X, Activity,
    Stethoscope, CalendarPlus, Trash2, RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import PageHeader from '../components/PageHeader';
import { useAuth } from '../context/AuthContext';

// ── date helpers (local time; the calendar grid is a local-time artifact) ──
const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
const endOfMonth = (d) => new Date(d.getFullYear(), d.getMonth() + 1, 0);
const addMonths = (d, n) => new Date(d.getFullYear(), d.getMonth() + n, 1);
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Personal-event category → swatch.
const CATEGORY_TONE = {
    personal: 'bg-brand-500',
    leave:    'bg-rose-500',
    meeting:  'bg-amber-500',
    'on-call':'bg-violet-500',
    reminder: 'bg-teal-500',
    other:    'bg-ink-400',
};
const CATEGORIES = ['personal', 'leave', 'meeting', 'on-call', 'reminder', 'other'];

// Build the 6×7 grid of dates covering the month (leading/trailing days from
// adjacent months so weeks are always whole).
function monthGrid(cursor) {
    const first = startOfMonth(cursor);
    const gridStart = new Date(first);
    gridStart.setDate(first.getDate() - first.getDay());
    return Array.from({ length: 42 }, (_, i) => {
        const d = new Date(gridStart);
        d.setDate(gridStart.getDate() + i);
        return d;
    });
}

const STATUS_TONE = {
    Scheduled: 'text-sky-700 dark:text-sky-300',
    Confirmed: 'text-accent-700 dark:text-accent-300',
    Completed: 'text-ink-400 line-through',
    Cancelled: 'text-rose-600 dark:text-rose-400 line-through',
    'No-Show': 'text-amber-700 dark:text-amber-400',
};

export default function Calendar() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const isDoctor = user?.role === 'Doctor';

    const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
    const [appointments, setAppointments] = useState([]);
    const [events, setEvents] = useState([]);
    const [doctors, setDoctors] = useState([]);
    // Doctors default to their own calendar; everyone else sees all doctors.
    const [doctorFilter, setDoctorFilter] = useState('');
    const [loading, setLoading] = useState(true);
    const [selectedDay, setSelectedDay] = useState(() => ymd(new Date()));
    const [eventModal, setEventModal] = useState(null); // {date} (new) or {event} (edit)

    const rangeFrom = useMemo(() => `${ymd(startOfMonth(cursor))}T00:00:00`, [cursor]);
    const rangeTo = useMemo(() => `${ymd(endOfMonth(cursor))}T23:59:59`, [cursor]);

    // Resolve the doctor filter once we know the role + directory. Doctors are
    // pinned to themselves; the dropdown is hidden for them.
    useEffect(() => {
        apiClient.get('/appointments/doctors').then((r) => {
            setDoctors(r.data || []);
            if (isDoctor && user?.user_id) setDoctorFilter(String(user.user_id));
        }).catch(() => {});
    }, [isDoctor, user?.user_id]);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const apptParams = { date_from: rangeFrom, date_to: rangeTo };
            if (doctorFilter) apptParams.doctor_id = doctorFilter;
            const [apptRes, evtRes] = await Promise.all([
                apiClient.get('/appointments/', { params: apptParams }).catch(() => ({ data: [] })),
                apiClient.get('/calendar/events', { params: { date_from: rangeFrom, date_to: rangeTo } }).catch(() => ({ data: [] })),
            ]);
            setAppointments(apptRes.data || []);
            setEvents(evtRes.data || []);
        } finally {
            setLoading(false);
        }
    }, [rangeFrom, rangeTo, doctorFilter]);

    useEffect(() => { load(); }, [load]);

    // Stay in sync: refetch when the tab regains focus (e.g. after booking in
    // another tab) and on a gentle interval so a teammate's change shows up.
    useEffect(() => {
        const onFocus = () => load();
        window.addEventListener('focus', onFocus);
        const id = setInterval(load, 60000);
        return () => { window.removeEventListener('focus', onFocus); clearInterval(id); };
    }, [load]);

    // Index appointments + events by day for the grid.
    const byDay = useMemo(() => {
        const map = {};
        const push = (day, item) => { (map[day] = map[day] || []).push(item); };
        for (const a of appointments) {
            if (!a.appointment_date) continue;
            push(a.appointment_date.slice(0, 10), { kind: 'appt', ...a });
        }
        for (const e of events) {
            if (!e.start_at) continue;
            push(e.start_at.slice(0, 10), { kind: 'event', ...e });
        }
        return map;
    }, [appointments, events]);

    const grid = useMemo(() => monthGrid(cursor), [cursor]);
    const todayStr = ymd(new Date());
    const selectedItems = byDay[selectedDay] || [];

    const deleteEvent = async (id) => {
        if (!window.confirm('Delete this event?')) return;
        try {
            await apiClient.delete(`/calendar/events/${id}`);
            toast.success('Event deleted.');
            load();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not delete event.');
        }
    };

    return (
        <div className="space-y-6 pb-8">
            <PageHeader
                eyebrow="Schedule"
                icon={CalendarDays}
                title="Calendar"
                subtitle="Appointments and your personal events in one synced view."
                actions={
                    <div className="flex flex-wrap items-center gap-2">
                        {!isDoctor && (
                            <select
                                aria-label="Filter by doctor"
                                className="input max-w-[12rem]"
                                value={doctorFilter}
                                onChange={(e) => setDoctorFilter(e.target.value)}
                            >
                                <option value="">All doctors</option>
                                {doctors.map((d) => (
                                    <option key={d.user_id} value={d.user_id}>{d.full_name}</option>
                                ))}
                            </select>
                        )}
                        <button type="button" onClick={load} className="btn-secondary" title="Refresh">
                            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Sync
                        </button>
                        <button type="button" onClick={() => setEventModal({ date: selectedDay })} className="btn-secondary">
                            <CalendarPlus size={15} /> Add event
                        </button>
                        <button type="button" onClick={() => navigate('/app/appointments')} className="btn-primary">
                            <Plus size={15} /> Book appointment
                        </button>
                    </div>
                }
            />

            {/* Month navigation */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <button type="button" onClick={() => setCursor(addMonths(cursor, -1))}
                        aria-label="Previous month" className="btn-ghost p-2"><ChevronLeft size={18} /></button>
                    <h2 className="text-lg font-semibold text-ink-900 dark:text-white tracking-tight min-w-[12rem] text-center">
                        {MONTHS[cursor.getMonth()]} {cursor.getFullYear()}
                    </h2>
                    <button type="button" onClick={() => setCursor(addMonths(cursor, 1))}
                        aria-label="Next month" className="btn-ghost p-2"><ChevronRight size={18} /></button>
                </div>
                <button type="button" onClick={() => { setCursor(startOfMonth(new Date())); setSelectedDay(todayStr); }}
                    className="btn-ghost text-sm">Today</button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Month grid */}
                <div className="lg:col-span-2 card overflow-hidden">
                    <div className="grid grid-cols-7 bg-ink-50/60 dark:bg-ink-800/40 border-b border-ink-100 dark:border-ink-800">
                        {WEEKDAYS.map((w) => (
                            <div key={w} className="px-2 py-2 text-2xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400 text-center">{w}</div>
                        ))}
                    </div>
                    <div className="grid grid-cols-7">
                        {grid.map((d) => {
                            const key = ymd(d);
                            const inMonth = d.getMonth() === cursor.getMonth();
                            const items = byDay[key] || [];
                            const isToday = key === todayStr;
                            const isSelected = key === selectedDay;
                            return (
                                <button
                                    key={key}
                                    type="button"
                                    onClick={() => setSelectedDay(key)}
                                    className={`min-h-[84px] border-b border-r border-ink-100 dark:border-ink-800 p-1.5 text-left align-top transition-colors
                                        ${inMonth ? 'bg-white dark:bg-ink-900' : 'bg-ink-50/40 dark:bg-ink-950/40'}
                                        ${isSelected ? 'ring-2 ring-inset ring-brand-500' : 'hover:bg-brand-50/40 dark:hover:bg-brand-500/10'}`}
                                >
                                    <div className="flex items-center justify-between">
                                        <span className={`text-xs font-semibold size-6 flex items-center justify-center rounded-full
                                            ${isToday ? 'bg-brand-600 text-white' : inMonth ? 'text-ink-700 dark:text-ink-200' : 'text-ink-400'}`}>
                                            {d.getDate()}
                                        </span>
                                        {items.length > 0 && (
                                            <span className="text-2xs font-medium text-ink-400">{items.length}</span>
                                        )}
                                    </div>
                                    <div className="mt-1 space-y-0.5">
                                        {items.slice(0, 3).map((it) => (
                                            <div key={it.kind === 'appt' ? `a${it.appointment_id}` : `e${it.event_id}`} className="flex items-center gap-1 truncate">
                                                <span className={`size-1.5 rounded-full shrink-0 ${it.kind === 'appt' ? 'bg-sky-500' : (CATEGORY_TONE[it.category] || 'bg-ink-400')}`} />
                                                <span className="text-2xs text-ink-600 dark:text-ink-300 truncate">
                                                    {it.kind === 'appt' ? (it.patient_name || 'Appointment') : it.title}
                                                </span>
                                            </div>
                                        ))}
                                        {items.length > 3 && (
                                            <div className="text-2xs text-ink-400 pl-2.5">+{items.length - 3} more</div>
                                        )}
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Day detail */}
                <div className="card p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">
                            {new Date(`${selectedDay}T00:00:00`).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}
                        </h3>
                        <button type="button" onClick={() => setEventModal({ date: selectedDay })}
                            className="text-brand-700 dark:text-brand-300 hover:underline text-sm inline-flex items-center gap-1">
                            <Plus size={14} /> Event
                        </button>
                    </div>

                    {loading ? (
                        <div className="text-center py-8 text-ink-400"><Activity className="animate-spin mx-auto mb-2" size={18} /> Loading…</div>
                    ) : selectedItems.length === 0 ? (
                        <p className="text-sm text-ink-500 dark:text-ink-400 py-6 text-center">Nothing scheduled.</p>
                    ) : (
                        <ul className="space-y-2">
                            {selectedItems
                                .slice()
                                .sort((a, b) => (a.kind === 'appt' ? a.appointment_date : a.start_at).localeCompare(b.kind === 'appt' ? b.appointment_date : b.start_at))
                                .map((it) => it.kind === 'appt' ? (
                                    <li key={`a${it.appointment_id}`} className="flex items-start gap-2 p-2.5 rounded-lg bg-sky-50/60 dark:bg-sky-500/10 border border-sky-100 dark:border-sky-500/20">
                                        <Stethoscope size={15} className="text-sky-600 dark:text-sky-400 mt-0.5 shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-ink-900 dark:text-ink-100 truncate">{it.patient_name}</p>
                                            <p className="text-2xs text-ink-500 dark:text-ink-400">
                                                {it.appointment_date ? new Date(it.appointment_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                                                {' · '}{it.doctor_name}
                                            </p>
                                        </div>
                                        <span className={`text-2xs font-semibold ${STATUS_TONE[it.status] || ''}`}>{it.status}</span>
                                    </li>
                                ) : (
                                    <li key={`e${it.event_id}`} className="flex items-start gap-2 p-2.5 rounded-lg bg-ink-50 dark:bg-ink-800/50 border border-ink-100 dark:border-ink-800">
                                        <span className={`size-2.5 rounded-full mt-1.5 shrink-0 ${CATEGORY_TONE[it.category] || 'bg-ink-400'}`} />
                                        <button type="button" onClick={() => setEventModal({ event: it })} className="flex-1 min-w-0 text-left">
                                            <p className="text-sm font-medium text-ink-900 dark:text-ink-100 truncate">{it.title}</p>
                                            <p className="text-2xs text-ink-500 dark:text-ink-400 capitalize">
                                                {it.all_day ? 'All day' : (it.start_at ? new Date(it.start_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '')}
                                                {' · '}{it.category}
                                            </p>
                                        </button>
                                        <button type="button" onClick={() => deleteEvent(it.event_id)} aria-label="Delete event"
                                            className="text-ink-400 hover:text-rose-600 shrink-0"><Trash2 size={14} /></button>
                                    </li>
                                ))}
                        </ul>
                    )}
                </div>
            </div>

            {eventModal && (
                <EventModal
                    initial={eventModal.event}
                    defaultDate={eventModal.date}
                    onClose={() => setEventModal(null)}
                    onSaved={() => { setEventModal(null); load(); }}
                />
            )}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Personal event create/edit modal.                                         */
/* ────────────────────────────────────────────────────────────────────────── */
function EventModal({ initial, defaultDate, onClose, onSaved }) {
    const isEdit = !!initial;
    const toLocalInput = (iso) => {
        if (!iso) return '';
        const d = new Date(iso);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    };
    const [form, setForm] = useState(() => ({
        title: initial?.title || '',
        category: initial?.category || 'personal',
        all_day: initial?.all_day || false,
        start_at: initial ? toLocalInput(initial.start_at) : `${defaultDate}T09:00`,
        end_at: initial?.end_at ? toLocalInput(initial.end_at) : '',
        notes: initial?.notes || '',
    }));
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.title.trim()) { toast.error('Give the event a title.'); return; }
        if (!form.start_at) { toast.error('Pick a start date/time.'); return; }
        setSaving(true);
        try {
            const payload = {
                title: form.title.trim(),
                category: form.category,
                all_day: form.all_day,
                start_at: new Date(form.start_at).toISOString(),
                end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
                notes: form.notes || null,
            };
            if (isEdit) {
                await apiClient.patch(`/calendar/events/${initial.event_id}`, payload);
                toast.success('Event updated.');
            } else {
                await apiClient.post('/calendar/events', payload);
                toast.success('Event added.');
            }
            onSaved();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not save event.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-md overflow-hidden flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800">
                    <div className="flex items-center gap-3">
                        <div className="size-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-500 text-white flex items-center justify-center shadow-soft">
                            <CalendarPlus size={17} />
                        </div>
                        <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">
                            {isEdit ? 'Edit event' : 'New personal event'}
                        </h3>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-3">
                    <div>
                        <label htmlFor="cal-evt-title" className="label">Title</label>
                        <input id="cal-evt-title" type="text" className="input" value={form.title}
                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                            placeholder="e.g. Annual leave, Team meeting" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="cal-evt-category" className="label">Category</label>
                            <select id="cal-evt-category" className="input capitalize" value={form.category}
                                onChange={(e) => setForm({ ...form, category: e.target.value })}>
                                {CATEGORIES.map((c) => <option key={c} value={c} className="capitalize">{c}</option>)}
                            </select>
                        </div>
                        <div className="flex items-end">
                            <label htmlFor="cal-evt-allday" className="flex items-center gap-2 cursor-pointer pb-2">
                                <input id="cal-evt-allday" type="checkbox" checked={form.all_day}
                                    onChange={(e) => setForm({ ...form, all_day: e.target.checked })}
                                    className="size-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500" />
                                <span className="text-sm text-ink-700 dark:text-ink-200">All day</span>
                            </label>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="cal-evt-start" className="label">Start</label>
                            <input id="cal-evt-start" type="datetime-local" className="input" value={form.start_at}
                                onChange={(e) => setForm({ ...form, start_at: e.target.value })} />
                        </div>
                        <div>
                            <label htmlFor="cal-evt-end" className="label">End (optional)</label>
                            <input id="cal-evt-end" type="datetime-local" className="input" value={form.end_at}
                                onChange={(e) => setForm({ ...form, end_at: e.target.value })} />
                        </div>
                    </div>
                    <div>
                        <label htmlFor="cal-evt-notes" className="label">Notes (optional)</label>
                        <textarea id="cal-evt-notes" rows="2" className="input resize-none" value={form.notes}
                            onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                    </div>
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2 bg-ink-50/40 dark:bg-ink-800/40">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button type="button" onClick={submit} disabled={saving} className="btn-primary cursor-pointer">
                        {saving ? <><Activity size={14} className="animate-spin" /> Saving…</> : <><CalendarPlus size={14} /> {isEdit ? 'Save' : 'Add event'}</>}
                    </button>
                </div>
            </div>
        </div>
    );
}
