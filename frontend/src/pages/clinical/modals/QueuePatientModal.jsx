import React, { useState } from 'react';
import { UserPlus, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import Modal from './Modal';
import PatientSearch from '../../../components/PatientSearch';
import { apiClient } from '../../../api/client';

const ACUITY = [
    { value: 1, label: '1: Emergency' },
    { value: 2, label: '2: Urgent' },
    { value: 3, label: '3: Standard' },
    { value: 4, label: '4: Non-urgent' },
    { value: 5, label: '5: Routine' },
];
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

/** Add a patient to the consultation queue. `onQueued` lets the shell refresh
 *  its queue after a successful add. */
export default function QueuePatientModal({ onQueued, onClose }) {
    const [patient, setPatient] = useState(null);
    const [acuity, setAcuity] = useState(3);
    const [notes, setNotes] = useState('');
    const [saving, setSaving] = useState(false);

    const submit = () => {
        if (!patient) { toast.error('Pick a patient first.'); return; }
        setSaving(true);
        apiClient.post('/queue/', {
            patient_id: patient.patient_id, department: 'Consultation',
            acuity_level: acuity, notes: notes || null,
        })
            .then(() => { toast.success('Added to the consultation queue.'); onQueued?.(); onClose(); })
            .catch((e) => err(e, 'Could not add to queue.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Add to queue" icon={UserPlus} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={submit} className="btn-primary"><Save size={14} /> Add to queue</button>
            </>}>
            <div>
                <p className="label">Patient</p>
                {patient ? (
                    <div className="flex items-center justify-between rounded-xl border border-ink-200 dark:border-ink-800 px-3 py-2">
                        <span className="text-sm font-medium text-ink-800 dark:text-ink-200">
                            {patient.surname}, {patient.other_names}
                        </span>
                        <button type="button" onClick={() => setPatient(null)} className="btn-ghost text-xs">Change</button>
                    </div>
                ) : (
                    <PatientSearch onSelect={setPatient} autoFocus />
                )}
            </div>
            <div>
                <label htmlFor="q-acuity" className="label">Acuity</label>
                <select id="q-acuity" className="input" value={acuity} onChange={(e) => setAcuity(Number(e.target.value))}>
                    {ACUITY.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
                </select>
            </div>
            <div>
                <label htmlFor="q-notes" className="label">Notes</label>
                <textarea id="q-notes" rows="2" className="input resize-none" value={notes}
                    onChange={(e) => setNotes(e.target.value)} placeholder="Reason for visit (optional)" />
            </div>
        </Modal>
    );
}
