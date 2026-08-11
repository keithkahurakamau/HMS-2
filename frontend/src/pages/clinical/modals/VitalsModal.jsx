import React, { useState } from 'react';
import { Activity, Save } from 'lucide-react';
import Modal from './Modal';
import { computeBmi } from '../../../utils/clinicalForms';

// Same shape the clinical-desk encounter holds, so the shell can pass its
// `vitals` object straight in and take the saved copy straight back.
const FIELDS = [
    { key: 'weight', label: 'Weight (kg)', placeholder: '70' },
    { key: 'height', label: 'Height (cm)', placeholder: '170' },
    { key: 'bp', label: 'Blood pressure', placeholder: '120/80' },
    { key: 'hr', label: 'Heart rate (bpm)', placeholder: '72' },
    { key: 'rr', label: 'Resp. rate (/min)', placeholder: '16' },
    { key: 'temp', label: 'Temperature (°C)', placeholder: '36.8' },
    { key: 'spo2', label: 'SpO₂ (%)', placeholder: '98' },
    { key: 'glucose', label: 'Blood glucose', placeholder: '5.5' },
];

/** Vitals grid with a live BMI readout. Edits a local copy and hands it back
 *  via `onSave` — the encounter stays the single source of truth in the shell. */
export default function VitalsModal({ vitals, onSave, onClose }) {
    const [form, setForm] = useState(() => ({ ...vitals }));
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
    const bmi = computeBmi(form.weight, form.height);

    const save = () => { onSave(form); onClose(); };

    return (
        <Modal title="Vitals" icon={Activity} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" onClick={save} className="btn-primary"><Save size={14} /> Save vitals</button>
            </>}>
            <div className="grid grid-cols-2 gap-3">
                {FIELDS.map((f) => (
                    <div key={f.key}>
                        <label htmlFor={`v-${f.key}`} className="label">{f.label}</label>
                        <input id={`v-${f.key}`} className="input" value={form[f.key] ?? ''}
                            onChange={(e) => set(f.key, e.target.value)} placeholder={f.placeholder} />
                    </div>
                ))}
            </div>
            <div className="rounded-xl bg-ink-50 dark:bg-ink-800/60 px-4 py-2.5 text-sm">
                <span className="text-ink-500 dark:text-ink-400">BMI: </span>
                <span className="font-semibold text-ink-800 dark:text-ink-200">{bmi ?? '—'}</span>
                {bmi && <span className="text-ink-400 dark:text-ink-500"> kg/m²</span>}
            </div>
        </Modal>
    );
}
