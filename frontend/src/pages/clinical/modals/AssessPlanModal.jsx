import React, { useState } from 'react';
import { ClipboardList, Save } from 'lucide-react';
import Modal from './Modal';
import { serializeAssessPlan, parseAssessPlan } from '../../../utils/clinicalForms';

/** Two-pane Assessment & Plan editor. Serializes to a single string via
 *  `serializeAssessPlan` and hands it back through `onSave`. */
export default function AssessPlanModal({ value, onSave, onClose }) {
    const [form, setForm] = useState(() => parseAssessPlan(value));
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const save = () => { onSave(serializeAssessPlan(form)); onClose(); };

    return (
        <Modal title="Assessment & Plan" icon={ClipboardList} onClose={onClose} size="lg"
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" onClick={save} className="btn-primary"><Save size={14} /> Save</button>
            </>}>
            <div>
                <label htmlFor="ap-assessment" className="label">Assessment</label>
                <textarea id="ap-assessment" rows="5" className="input resize-none" value={form.assessment}
                    onChange={(e) => set('assessment', e.target.value)}
                    placeholder="Clinical impression, differential, staging…" />
            </div>
            <div>
                <label htmlFor="ap-plan" className="label">Plan</label>
                <textarea id="ap-plan" rows="5" className="input resize-none" value={form.plan}
                    onChange={(e) => set('plan', e.target.value)}
                    placeholder="Management, investigations, follow-up, patient education…" />
            </div>
        </Modal>
    );
}
