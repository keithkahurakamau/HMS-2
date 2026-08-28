import React, { useState } from 'react';
import { Pill, Plus, Trash2, Save } from 'lucide-react';
import Modal from './Modal';
import { FORMULATIONS, FREQUENCIES, blankMed } from '../../../utils/clinicalForms';

/** Medication rows for the encounter. Edits a local copy; `onSave` hands the
 *  rows back to the shell (which persists them in treatment_plan). */
export default function PrescriptionModal({ medications, onSave, onClose }) {
    const [meds, setMeds] = useState(() => (medications?.length
        ? medications.map((m) => ({ _uid: m._uid || crypto.randomUUID(), ...m }))
        : [blankMed()]));

    const update = (uid, k, v) => setMeds((p) => p.map((m) => m._uid === uid ? { ...m, [k]: v } : m));
    const add = () => setMeds((p) => [...p, blankMed()]);
    const remove = (uid) => setMeds((p) => (p.length === 1 ? p : p.filter((m) => m._uid !== uid)));

    const save = () => { onSave(meds.filter((m) => m.drug.trim())); onClose(); };

    return (
        <Modal title="Prescription" icon={Pill} onClose={onClose} size="xl"
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" onClick={save} className="btn-primary"><Save size={14} /> Save prescription</button>
            </>}>
            <div className="space-y-2">
                {meds.map((m) => (
                    <div key={m._uid} className="grid grid-cols-12 gap-2 items-end">
                        <div className="col-span-3">
                            <label htmlFor={`rx-drug-${m._uid}`} className="label text-2xs">Drug</label>
                            <input id={`rx-drug-${m._uid}`} className="input py-1.5 text-sm" value={m.drug}
                                onChange={(e) => update(m._uid, 'drug', e.target.value)} placeholder="e.g. Amoxicillin" />
                        </div>
                        <div className="col-span-2">
                            <label htmlFor={`rx-form-${m._uid}`} className="label text-2xs">Form</label>
                            <select id={`rx-form-${m._uid}`} className="input py-1.5 text-sm" value={m.formulation}
                                onChange={(e) => update(m._uid, 'formulation', e.target.value)}>
                                {FORMULATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
                            </select>
                        </div>
                        <div className="col-span-2">
                            <label htmlFor={`rx-dose-${m._uid}`} className="label text-2xs">Dosage</label>
                            <input id={`rx-dose-${m._uid}`} className="input py-1.5 text-sm" value={m.dosage}
                                onChange={(e) => update(m._uid, 'dosage', e.target.value)} placeholder="500 mg" />
                        </div>
                        <div className="col-span-2">
                            <label htmlFor={`rx-freq-${m._uid}`} className="label text-2xs">Frequency</label>
                            <select id={`rx-freq-${m._uid}`} className="input py-1.5 text-sm" value={m.frequency}
                                onChange={(e) => update(m._uid, 'frequency', e.target.value)}>
                                <option value="">, </option>
                                {FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}
                            </select>
                        </div>
                        <div className="col-span-2">
                            <label htmlFor={`rx-dur-${m._uid}`} className="label text-2xs">Duration</label>
                            <input id={`rx-dur-${m._uid}`} className="input py-1.5 text-sm" value={m.duration}
                                onChange={(e) => update(m._uid, 'duration', e.target.value)} placeholder="5 days" />
                        </div>
                        <button type="button" onClick={() => remove(m._uid)} aria-label="Remove medication"
                            className="col-span-1 text-ink-400 hover:text-rose-600 pb-2 justify-self-center"><Trash2 size={15} /></button>
                    </div>
                ))}
                <button type="button" onClick={add} className="btn-ghost text-xs"><Plus size={13} /> Add medication</button>
            </div>
        </Modal>
    );
}
