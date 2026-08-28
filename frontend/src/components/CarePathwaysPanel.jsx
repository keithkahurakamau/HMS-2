import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X, Save, Stethoscope, BedDouble, Scissors } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';

const PRIORITIES = ['Elective', 'Emergency'];
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

/** Shared modal shell: portaled to <body> so it escapes the workspace card's
 *  stacking context and always sits above the queue bar and page chrome. */
function Modal({ title, icon: Icon, onClose, children, footer }) {
    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 backdrop-blur-sm p-4"
            onClick={onClose} role="presentation">
            <div className="bg-white dark:bg-ink-900 rounded-2xl shadow-overlay w-full max-w-lg max-h-[90vh] flex flex-col"
                onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <h3 className="text-sm font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                        {Icon && <Icon size={16} className="text-brand-500" />} {title}
                    </h3>
                    <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-lg text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800"><X size={16} /></button>
                </div>
                <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">{children}</div>
                {footer && <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2">{footer}</div>}
            </div>
        </div>,
        document.body,
    );
}

/* ── Theatre request ───────────────────────────────────────────────────── */
function TheatreModal({ patient, diagnosis, onClose }) {
    const [form, setForm] = useState({ procedure_name: '', priority: 'Elective', scheduled_at: '', diagnosis: diagnosis || '' });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const submit = () => {
        if (!form.procedure_name.trim()) { toast.error('Enter the procedure.'); return; }
        setSaving(true);
        const payload = {
            patient_id: patient.patient_id,
            procedure_name: form.procedure_name,
            priority: form.priority,
            diagnosis: form.diagnosis || null,
            ...(form.scheduled_at ? { scheduled_at: new Date(form.scheduled_at).toISOString() } : {}),
        };
        apiClient.post('/theatre/cases', payload)
            .then(() => { toast.success('Theatre case requested.'); onClose(); })
            .catch((e) => err(e, 'Could not request theatre case.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Request theatre" icon={Scissors} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={submit} className="btn-primary"><Save size={14} /> Request</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">Book a surgical case for <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span>. The theatre team schedules and runs the WHO checklist.</p>
            <div><label htmlFor="th-proc" className="label">Procedure</label><input id="th-proc" className="input" value={form.procedure_name} onChange={(e) => set('procedure_name', e.target.value)} placeholder="e.g. Appendectomy" /></div>
            <div className="grid grid-cols-2 gap-3">
                <div><label htmlFor="th-pri" className="label">Priority</label>
                    <select id="th-pri" className="input" value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                        {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                </div>
                <div><label htmlFor="th-when" className="label">Preferred time (optional)</label><input id="th-when" type="datetime-local" className="input" value={form.scheduled_at} onChange={(e) => set('scheduled_at', e.target.value)} /></div>
            </div>
            <div><label htmlFor="th-dx" className="label">Diagnosis</label><input id="th-dx" className="input" value={form.diagnosis} onChange={(e) => set('diagnosis', e.target.value)} placeholder="Pre-operative diagnosis" /></div>
        </Modal>
    );
}

/* ── Admit patient ─────────────────────────────────────────────────────── */
function AdmitModal({ patient, diagnosis, onClose }) {
    const [board, setBoard] = useState([]);
    const [loading, setLoading] = useState(true);
    const [wardId, setWardId] = useState('');
    const [bedId, setBedId] = useState('');
    const [dx, setDx] = useState(diagnosis || '');
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        apiClient.get('/wards/board')
            .then((r) => setBoard(r.data || []))
            .catch((e) => err(e, 'Could not load the bed board.'))
            .finally(() => setLoading(false));
    }, []);

    const ward = board.find((w) => String(w.id) === String(wardId));
    const availableBeds = (ward?.beds || []).filter((b) => b.status === 'Available');

    const submit = () => {
        if (!bedId) { toast.error('Pick an available bed.'); return; }
        if (!dx.trim()) { toast.error('Enter an admitting diagnosis.'); return; }
        setSaving(true);
        apiClient.post('/wards/admit', { patient_id: patient.patient_id, bed_id: Number(bedId), diagnosis: dx })
            .then(() => { toast.success('Patient admitted.'); onClose(); })
            .catch((e) => err(e, 'Could not admit patient.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Admit patient" icon={BedDouble} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving || loading} onClick={submit} className="btn-primary"><Save size={14} /> Admit</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">Admit <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span> to an available bed.</p>
            {loading ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">Loading bed board…</p>
            ) : (
                <>
                    <div className="grid grid-cols-2 gap-3">
                        <div><label htmlFor="ad-ward" className="label">Ward</label>
                            <select id="ad-ward" className="input" value={wardId} onChange={(e) => { setWardId(e.target.value); setBedId(''); }}>
                                <option value="">Select ward…</option>
                                {board.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                        </div>
                        <div><label htmlFor="ad-bed" className="label">Bed</label>
                            <select id="ad-bed" className="input" value={bedId} onChange={(e) => setBedId(e.target.value)} disabled={!wardId}>
                                <option value="">{wardId ? (availableBeds.length ? 'Select bed…' : 'No available beds') : 'Pick a ward first'}</option>
                                {availableBeds.map((b) => <option key={b.id} value={b.id}>{b.number}</option>)}
                            </select>
                        </div>
                    </div>
                    <div><label htmlFor="ad-dx" className="label">Admitting diagnosis</label><input id="ad-dx" className="input" value={dx} onChange={(e) => setDx(e.target.value)} placeholder="Reason for admission" /></div>
                </>
            )}
        </Modal>
    );
}

/**
 * Care pathways from the Clinical Desk, request a surgical case (theatre) or
 * admit the patient to a ward. Reuses the theatre and wards modules; each
 * button is gated on the viewer's permission so it only appears when actionable.
 */
export default function CarePathwaysPanel({ patient, perms = [], diagnosis = '' }) {
    const [active, setActive] = useState(null); // 'theatre' | 'admit'
    if (!patient) return null;
    const canTheatre = perms.includes('theatre:manage');
    const canAdmit = perms.includes('wards:read') || perms.includes('wards:manage');
    if (!canTheatre && !canAdmit) return null;
    const btn = 'btn-secondary flex-1 py-2 text-xs cursor-pointer whitespace-nowrap';

    return (
        <div className="rounded-xl border border-ink-200 dark:border-ink-800 p-4">
            <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 mb-3 flex items-center gap-2"><Stethoscope size={13} /> Care pathways</h4>
            <div className="grid grid-cols-2 gap-2">
                {canTheatre && <button type="button" onClick={() => setActive('theatre')} className={btn}><Scissors size={13} /> Request theatre</button>}
                {canAdmit && <button type="button" onClick={() => setActive('admit')} className={btn}><BedDouble size={13} /> Admit patient</button>}
            </div>

            {active === 'theatre' && <TheatreModal patient={patient} diagnosis={diagnosis} onClose={() => setActive(null)} />}
            {active === 'admit' && <AdmitModal patient={patient} diagnosis={diagnosis} onClose={() => setActive(null)} />}
        </div>
    );
}
