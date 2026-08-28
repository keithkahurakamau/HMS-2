import React, { useState, useEffect } from 'react';
import { BedDouble, ChevronRight } from 'lucide-react';
import toast from 'react-hot-toast';
import Modal from './Modal';
import { apiClient } from '../../../api/client';

const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

// Flatten the ward board into a flat list of occupied beds (the only ones that
// carry an admitted patient the doctor can round on). Single pass per ward: // flatMap both filters (empty array) and maps in one iteration.
const occupiedBeds = (board) => (board || []).flatMap((ward) =>
    (ward.beds || []).flatMap((b) =>
        (b.status === 'Occupied' && b.patient_id) ? [{ ...b, ward_name: ward.name }] : []));

/** Pick an admitted inpatient to round on. `onPick(bed)` hands the shell a bed
 *  row carrying `patient_id`, patient name, ward and diagnosis. */
export default function PickAdmissionModal({ onPick, onClose }) {
    const [beds, setBeds] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        apiClient.get('/wards/board')
            .then((r) => setBeds(occupiedBeds(r.data)))
            .catch((e) => err(e, 'Could not load the ward board.'))
            .finally(() => setLoading(false));
    }, []);

    return (
        <Modal title="Admitted patients" icon={BedDouble} onClose={onClose} size="lg"
            footer={<button type="button" onClick={onClose} className="btn-secondary">Close</button>}>
            {loading ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">Loading…</p>
            ) : beds.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400 italic">No admitted patients right now.</p>
            ) : (
                <ul className="space-y-2">
                    {beds.map((b) => (
                        <li key={b.id}>
                            <button type="button" onClick={() => { onPick?.(b); onClose(); }}
                                className="w-full flex items-center justify-between gap-3 rounded-xl border border-ink-200 dark:border-ink-800 px-3 py-2.5 text-left hover:bg-ink-50 dark:hover:bg-ink-800/60">
                                <div className="min-w-0">
                                    <p className="text-sm font-medium text-ink-800 dark:text-ink-200 truncate">{b.patient}</p>
                                    <p className="text-2xs text-ink-500 dark:text-ink-400 truncate">
                                        {b.ward_name} · Bed {b.number}{b.diagnosis ? ` · ${b.diagnosis}` : ''}
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
