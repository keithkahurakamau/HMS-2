import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
    X, Save, Printer, FileText, Eye, ExternalLink, ListChecks, Plus, Trash2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';

const EXTERNAL_TYPES = ['Lab', 'Radiology', 'Referral', 'Other'];
const ITEM_TYPES = ['Lab', 'Radiology', 'Drug'];
const today = () => new Date().toISOString().slice(0, 10);
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

/** Shared modal shell — portaled to <body> so it escapes the workspace card's
 *  stacking context and always sits above the queue bar and page chrome. */
function Modal({ title, icon: Icon, onClose, children, footer, wide = false }) {
    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 backdrop-blur-sm p-4"
            onClick={onClose} role="presentation">
            <div className={`bg-white dark:bg-ink-900 rounded-2xl shadow-xl w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[90vh] flex flex-col`}
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

/* ── Sick note ─────────────────────────────────────────────────────────── */
function SickNoteModal({ patient, onClose }) {
    const [form, setForm] = useState({ diagnosis: '', start_date: today(), end_date: today(), recommendation: '', fit_for_duty: false });
    const [saving, setSaving] = useState(false);
    const days = Math.max(1, Math.round((new Date(form.end_date) - new Date(form.start_date)) / 86400000) + 1);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const submit = (print) => {
        if (new Date(form.end_date) < new Date(form.start_date)) { toast.error('End date is before start date.'); return; }
        setSaving(true);
        apiClient.post('/clinical-extras/sick-notes', { patient_id: patient.patient_id, ...form })
            .then(() => { toast.success('Sick note saved.'); if (print) window.print(); onClose(); })
            .catch((e) => err(e, 'Could not save sick note.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Sick note" icon={FileText} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={() => submit(true)} className="btn-secondary"><Printer size={14} /> Save &amp; print</button>
                <button type="button" disabled={saving} onClick={() => submit(false)} className="btn-primary"><Save size={14} /> Save</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">For <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span></p>
            <div><label htmlFor="sn-dx" className="label">Diagnosis</label><input id="sn-dx" className="input" value={form.diagnosis} onChange={(e) => set('diagnosis', e.target.value)} placeholder="e.g. Acute bronchitis" /></div>
            <div className="grid grid-cols-2 gap-3">
                <div><label htmlFor="sn-start" className="label">From</label><input id="sn-start" type="date" className="input" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
                <div><label htmlFor="sn-end" className="label">To</label><input id="sn-end" type="date" className="input" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} /></div>
            </div>
            <p className="text-xs text-ink-500 dark:text-ink-400">Duration: <span className="font-semibold text-ink-800 dark:text-ink-200">{days} day{days === 1 ? '' : 's'}</span></p>
            <div><label htmlFor="sn-rec" className="label">Recommendation</label><textarea id="sn-rec" rows="2" className="input resize-none" value={form.recommendation} onChange={(e) => set('recommendation', e.target.value)} placeholder="e.g. Bed rest and adequate fluids" /></div>
            <label htmlFor="sn-fit" className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-300"><input id="sn-fit" type="checkbox" className="size-4 rounded" checked={form.fit_for_duty} onChange={(e) => set('fit_for_duty', e.target.checked)} /> Fit to resume duty at end of period</label>
        </Modal>
    );
}

/* ── Optical prescription ──────────────────────────────────────────────── */
const OPTICAL_FIELDS = ['sphere', 'cylinder', 'axis', 'add'];
function OpticalModal({ patient, onClose }) {
    const [form, setForm] = useState({
        right_sphere: '', right_cylinder: '', right_axis: '', right_add: '',
        left_sphere: '', left_cylinder: '', left_axis: '', left_add: '', pd: '', notes: '',
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const submit = () => {
        setSaving(true);
        apiClient.post('/clinical-extras/optical-prescriptions', { patient_id: patient.patient_id, ...form })
            .then(() => { toast.success('Optical prescription saved.'); onClose(); })
            .catch((e) => err(e, 'Could not save prescription.'))
            .finally(() => setSaving(false));
    };

    const eyeRow = (eye) => (
        <div className="grid grid-cols-5 gap-2 items-end">
            <div className="text-xs font-semibold text-ink-600 dark:text-ink-400 pb-2">{eye === 'right' ? 'Right (OD)' : 'Left (OS)'}</div>
            {OPTICAL_FIELDS.map((f) => (
                <div key={f}>
                    <label htmlFor={`opt-${eye}-${f}`} className="label text-2xs capitalize">{f}</label>
                    <input id={`opt-${eye}-${f}`} className="input py-1.5 text-sm" value={form[`${eye}_${f}`]} onChange={(e) => set(`${eye}_${f}`, e.target.value)} />
                </div>
            ))}
        </div>
    );

    return (
        <Modal title="Optical prescription" icon={Eye} onClose={onClose} wide
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={submit} className="btn-primary"><Save size={14} /> Save</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">For <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span></p>
            {eyeRow('right')}
            {eyeRow('left')}
            <div className="grid grid-cols-2 gap-3">
                <div><label htmlFor="opt-pd" className="label">PD (mm)</label><input id="opt-pd" className="input" value={form.pd} onChange={(e) => set('pd', e.target.value)} placeholder="62" /></div>
            </div>
            <div><label htmlFor="opt-notes" className="label">Notes</label><textarea id="opt-notes" rows="2" className="input resize-none" value={form.notes} onChange={(e) => set('notes', e.target.value)} placeholder="e.g. Distance vision, anti-glare coating" /></div>
        </Modal>
    );
}

/* ── External request ──────────────────────────────────────────────────── */
function ExternalModal({ patient, onClose }) {
    const [form, setForm] = useState({ request_type: 'Lab', facility: '', details: '', reason: '' });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    const submit = () => {
        setSaving(true);
        apiClient.post('/clinical-extras/external-requests', { patient_id: patient.patient_id, ...form })
            .then(() => { toast.success('External request saved.'); onClose(); })
            .catch((e) => err(e, 'Could not save request.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="External request" icon={ExternalLink} onClose={onClose}
            footer={<>
                <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                <button type="button" disabled={saving} onClick={submit} className="btn-primary"><Save size={14} /> Save</button>
            </>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">Out-of-facility order for <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span></p>
            <div className="grid grid-cols-2 gap-3">
                <div><label htmlFor="ext-type" className="label">Type</label>
                    <select id="ext-type" className="input" value={form.request_type} onChange={(e) => set('request_type', e.target.value)}>
                        {EXTERNAL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                </div>
                <div><label htmlFor="ext-fac" className="label">Facility</label><input id="ext-fac" className="input" value={form.facility} onChange={(e) => set('facility', e.target.value)} placeholder="e.g. Lancet Labs" /></div>
            </div>
            <div><label htmlFor="ext-details" className="label">Details</label><textarea id="ext-details" rows="2" className="input resize-none" value={form.details} onChange={(e) => set('details', e.target.value)} placeholder="What is being requested (tests, imaging, service)" /></div>
            <div><label htmlFor="ext-reason" className="label">Clinical reason</label><textarea id="ext-reason" rows="2" className="input resize-none" value={form.reason} onChange={(e) => set('reason', e.target.value)} placeholder="Indication / clinical justification" /></div>
        </Modal>
    );
}

/* ── Order sets ────────────────────────────────────────────────────────── */
const blankItem = () => ({ _uid: crypto.randomUUID(), item_type: 'Lab', name: '', ref_code: '' });
function OrderSetsModal({ onApply, onClose }) {
    const [sets, setSets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [draft, setDraft] = useState({ name: '', description: '', items: [blankItem()] });
    const [saving, setSaving] = useState(false);

    // No synchronous setState here — initial `loading` is already true, and the
    // reload after a save just refreshes the list in place.
    const load = () => {
        apiClient.get('/clinical-extras/order-sets')
            .then((r) => setSets(r.data || []))
            .catch((e) => err(e, 'Could not load order sets.'))
            .finally(() => setLoading(false));
    };
    useEffect(() => { load(); }, []);

    const updateItem = (uid, k, v) => setDraft((p) => ({ ...p, items: p.items.map((it) => it._uid === uid ? { ...it, [k]: v } : it) }));
    const addItem = () => setDraft((p) => ({ ...p, items: [...p.items, blankItem()] }));
    const removeItem = (uid) => setDraft((p) => ({ ...p, items: p.items.filter((it) => it._uid !== uid) }));

    const save = () => {
        const items = draft.items.filter((it) => it.name.trim()).map(({ item_type, name, ref_code }) => ({ item_type, name, ref_code: ref_code || null }));
        if (!draft.name.trim() || items.length === 0) { toast.error('Give the set a name and at least one item.'); return; }
        setSaving(true);
        apiClient.post('/clinical-extras/order-sets', { name: draft.name, description: draft.description, items })
            .then(() => { toast.success('Order set created.'); setCreating(false); setDraft({ name: '', description: '', items: [blankItem()] }); load(); })
            .catch((e) => err(e, 'Could not create order set.'))
            .finally(() => setSaving(false));
    };

    return (
        <Modal title="Order sets" icon={ListChecks} onClose={onClose} wide
            footer={<button type="button" onClick={onClose} className="btn-secondary">Close</button>}>
            {!creating && (
                <button type="button" onClick={() => setCreating(true)} className="btn-secondary text-xs"><Plus size={13} /> New order set</button>
            )}
            {creating && (
                <div className="rounded-xl border border-ink-200 dark:border-ink-800 p-4 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div><label htmlFor="os-name" className="label">Name</label><input id="os-name" className="input" value={draft.name} onChange={(e) => setDraft((p) => ({ ...p, name: e.target.value }))} placeholder="e.g. Diabetes work-up" /></div>
                        <div><label htmlFor="os-desc" className="label">Description</label><input id="os-desc" className="input" value={draft.description} onChange={(e) => setDraft((p) => ({ ...p, description: e.target.value }))} /></div>
                    </div>
                    <div className="space-y-2">
                        {draft.items.map((it) => (
                            <div key={it._uid} className="flex gap-2 items-end">
                                <div className="w-32"><label htmlFor={`os-it-${it._uid}`} className="label text-2xs">Type</label>
                                    <select id={`os-it-${it._uid}`} className="input py-1.5 text-sm" value={it.item_type} onChange={(e) => updateItem(it._uid, 'item_type', e.target.value)}>
                                        {ITEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                                    </select>
                                </div>
                                <div className="flex-1"><label htmlFor={`os-nm-${it._uid}`} className="label text-2xs">Name</label><input id={`os-nm-${it._uid}`} className="input py-1.5 text-sm" value={it.name} onChange={(e) => updateItem(it._uid, 'name', e.target.value)} placeholder="e.g. HbA1c" /></div>
                                <button type="button" onClick={() => removeItem(it._uid)} aria-label="Remove item" className="text-ink-400 hover:text-rose-600 pb-2"><Trash2 size={15} /></button>
                            </div>
                        ))}
                        <button type="button" onClick={addItem} className="btn-ghost text-xs"><Plus size={13} /> Add item</button>
                    </div>
                    <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => setCreating(false)} className="btn-secondary text-xs">Cancel</button>
                        <button type="button" disabled={saving} onClick={save} className="btn-primary text-xs"><Save size={13} /> Save set</button>
                    </div>
                </div>
            )}

            {loading ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">Loading…</p>
            ) : sets.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400 italic">No order sets yet. Create one to reuse it at the point of care.</p>
            ) : (
                <ul className="space-y-2">
                    {sets.map((s) => (
                        <li key={s.order_set_id} className="rounded-xl border border-ink-200 dark:border-ink-800 p-3 flex items-start justify-between gap-3">
                            <div className="min-w-0">
                                <p className="text-sm font-semibold text-ink-800 dark:text-ink-200">{s.name}</p>
                                {s.description && <p className="text-xs text-ink-500 dark:text-ink-400">{s.description}</p>}
                                <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">{s.items.map((i) => `${i.name} (${i.item_type})`).join(' · ') || 'No items'}</p>
                            </div>
                            <button type="button" onClick={() => { onApply(s); onClose(); }} className="btn-primary py-1.5 px-3 text-xs shrink-0">Apply</button>
                        </li>
                    ))}
                </ul>
            )}
        </Modal>
    );
}

/**
 * Clinical-desk extras — the Doctor's-panel outputs (sick notes, optical Rx,
 * external requests, reusable order sets). `onApplyOrderSet` receives the
 * chosen set so the parent can pre-fill orders (Drug items → medications).
 */
export default function ClinicalExtrasPanel({ patient, onApplyOrderSet }) {
    const [active, setActive] = useState(null); // 'sick' | 'optical' | 'external' | 'orderset'
    if (!patient) return null;
    const btn = 'btn-secondary flex-1 py-2 text-xs cursor-pointer whitespace-nowrap';

    return (
        <div className="rounded-xl border border-ink-200 dark:border-ink-800 p-4">
            <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 mb-3 flex items-center gap-2"><FileText size={13} /> Documents &amp; order sets</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <button type="button" onClick={() => setActive('sick')} className={btn}><FileText size={13} /> Sick note</button>
                <button type="button" onClick={() => setActive('optical')} className={btn}><Eye size={13} /> Optical Rx</button>
                <button type="button" onClick={() => setActive('external')} className={btn}><ExternalLink size={13} /> External request</button>
                <button type="button" onClick={() => setActive('orderset')} className={btn}><ListChecks size={13} /> Order sets</button>
            </div>

            {active === 'sick' && <SickNoteModal patient={patient} onClose={() => setActive(null)} />}
            {active === 'optical' && <OpticalModal patient={patient} onClose={() => setActive(null)} />}
            {active === 'external' && <ExternalModal patient={patient} onClose={() => setActive(null)} />}
            {active === 'orderset' && <OrderSetsModal onApply={onApplyOrderSet} onClose={() => setActive(null)} />}
        </div>
    );
}
