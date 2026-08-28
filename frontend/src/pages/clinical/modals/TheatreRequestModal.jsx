import React, { useState } from 'react';
import { Scissors, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import Modal from './Modal';
import { apiClient } from '../../../api/client';

const PRIORITIES = ['Elective', 'Emergency'];
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

/**
 * Theatre request: books a surgical case for the patient via POST /theatre/cases.
 * Minimal request form (procedure, diagnosis, priority, optional schedule); the
 * theatre team fills in room/surgeon later. Shared by the Clinical Desk + Triage.
 */
export default function TheatreRequestModal({ patient, onClose, onCreated }) {
    const [form, setForm] = useState({ procedure_name: '', procedure_code: '', diagnosis: '', priority: 'Elective', scheduled_at: '' });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const submit = () => {
        if (!form.procedure_name.trim()) { toast.error('Enter the procedure name.'); return; }
        setSaving(true);
        apiClient.post('/theatre/cases', {
            patient_id: patient.patient_id,
            procedure_name: form.procedure_name.trim(),
            procedure_code: form.procedure_code.trim() || null,
            diagnosis: form.diagnosis.trim() || null,
            priority: form.priority,
            scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
        })
            .then(() => { toast.success('Theatre request created.'); onCreated?.(); onClose(); })
            .catch((e) => err(e, 'Could not create the theatre request.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Theatre request" icon={Scissors} onClose={onClose} size="lg"
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={submit} className="btn-primary"><Save size={14} /> Create request</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">For <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span></p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="md:col-span-2"><label htmlFor="th-proc" className="label">Procedure</label><input id="th-proc" className="input" value={form.procedure_name} onChange={(e) => set('procedure_name', e.target.value)} placeholder="e.g. Appendectomy" /></div>
                <div><label htmlFor="th-code" className="label">Procedure code</label><input id="th-code" className="input" value={form.procedure_code} onChange={(e) => set('procedure_code', e.target.value)} placeholder="Optional" /></div>
                <div>
                    <label htmlFor="th-priority" className="label">Priority</label>
                    <select id="th-priority" className="input" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                        {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                </div>
                <div className="md:col-span-2"><label htmlFor="th-dx" className="label">Diagnosis</label><input id="th-dx" className="input" value={form.diagnosis} onChange={(e) => set('diagnosis', e.target.value)} placeholder="Working diagnosis / indication" /></div>
                <div><label htmlFor="th-when" className="label">Scheduled for</label><input id="th-when" type="datetime-local" className="input" value={form.scheduled_at} onChange={(e) => set('scheduled_at', e.target.value)} /></div>
            </div>
        </Modal>
    );
}
