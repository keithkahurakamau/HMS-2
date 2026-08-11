import React, { useState, useEffect } from 'react';
import { CalendarDays, ChevronRight } from 'lucide-react';
import toast from 'react-hot-toast';
import Modal from './Modal';
import { apiClient } from '../../../api/client';

const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);
const dayBounds = () => {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const end = new Date(); end.setHours(23, 59, 59, 999);
    return { from: start.toISOString(), to: end.toISOString() };
};
const timeOf = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—');

/** Today's appointments for the signed-in doctor. `onPick(appt)` lets the shell
 *  pull the chosen patient into the encounter. */
export default function MyAppointmentsModal({ doctorId, onPick, onClose }) {
    const [appts, setAppts] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const { from, to } = dayBounds();
        apiClient.get('/appointments/', { params: { doctor_id: doctorId, date_from: from, date_to: to } })
            .then((r) => setAppts(r.data || []))
            .catch((e) => err(e, 'Could not load appointments.'))
            .finally(() => setLoading(false));
    }, [doctorId]);

    return (
        <Modal title="My appointments — today" icon={CalendarDays} onClose={onClose} size="lg"
            footer={<button type="button" onClick={onClose} className="btn-secondary">Close</button>}>
            {loading ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">Loading…</p>
            ) : appts.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400 italic">No appointments scheduled for today.</p>
            ) : (
                <ul className="space-y-2">
                    {appts.map((a) => (
                        <li key={a.appointment_id}>
                            <button type="button" onClick={() => { onPick?.(a); onClose(); }}
                                className="w-full flex items-center justify-between gap-3 rounded-xl border border-ink-200 dark:border-ink-800 px-3 py-2.5 text-left hover:bg-ink-50 dark:hover:bg-ink-800/60">
                                <div className="min-w-0">
                                    <p className="text-sm font-medium text-ink-800 dark:text-ink-200 truncate">{a.patient_name}</p>
                                    <p className="text-2xs text-ink-500 dark:text-ink-400">
                                        {timeOf(a.appointment_date)} · {a.status}{a.patient_opd ? ` · ${a.patient_opd}` : ''}
                                    </p>
                                </div>
                                <ChevronRight size={16} className="text-ink-400 shrink-0" />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </Modal>
    );
}
