import React, { useState } from 'react';
import { Activity, Plus, X, Stethoscope, ClipboardList, AlertTriangle } from 'lucide-react';
import DraftRecoveryBanner from '../../components/DraftRecoveryBanner';

// Common pick-lists (free text still allowed via the datalists) — parity with
// MedicentreV3's Body System / Procedure dropdowns.
const BODY_SYSTEMS = ['CNS', 'CVS', 'Respiratory', 'GIT', 'Genitourinary', 'Musculoskeletal', 'Skin', 'ENT', 'Eyes', 'Endocrine'];
const PROCEDURES = ['Dressing', 'Injection', 'Nebulization', 'Cannulation', 'Catheterization', 'Suturing', 'Wound cleaning', 'Oxygen therapy', 'Blood transfusion'];

// Acuity scale shown to the nurse. 1 = most urgent; mirrors the 1–5 range the
// backend clamps to and the doctor's queue sorts by.
const ACUITY_LEVELS = [
    { level: 1, label: 'Emergency', hint: 'Immediate / resuscitation', tone: 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/20' },
    { level: 2, label: 'Urgent', hint: 'Very ill, cannot wait', tone: 'bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/20' },
    { level: 3, label: 'Standard', hint: 'Stable, routine', tone: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20' },
    { level: 4, label: 'Less urgent', hint: 'Minor complaint', tone: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20' },
    { level: 5, label: 'Non-urgent', hint: 'Could be seen later', tone: 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20' },
];

/**
 * Triage tab — the nurse's assessment for the active patient. Fully controlled:
 * `value` carries the state the Triage shell owns, `on` the handlers. Extracted
 * verbatim from the legacy Triage page so behaviour (draft safety-net, submit
 * gating, guided-tour anchors) is unchanged.
 */
export default function TriageTab({ value, on }) {
    const { vitals, bmi, complaints, complaintInput, triageNotes, acuity, hasNotesDraft, notesDraftSavedAt } = value;
    const systemicExam = value.systemicExam || [];
    const procedures = value.procedures || [];

    // Transient "new row" inputs for the two structured lists live here; the
    // committed rows live in the shell (via on.addSystemic / on.addProcedure).
    const [newSys, setNewSys] = useState({ body_system: '', remark: '', is_anomalous: false });
    const [newProc, setNewProc] = useState({ procedure: '', remark: '' });

    const addSystemic = () => {
        if (!newSys.body_system.trim()) return;
        on.addSystemic({ _uid: crypto.randomUUID(), ...newSys, body_system: newSys.body_system.trim(), remark: newSys.remark.trim() });
        setNewSys({ body_system: '', remark: '', is_anomalous: false });
    };
    const addProcedure = () => {
        if (!newProc.procedure.trim()) return;
        on.addProcedure({ _uid: crypto.randomUUID(), procedure: newProc.procedure.trim(), remark: newProc.remark.trim() });
        setNewProc({ procedure: '', remark: '' });
    };

    return (
        <div className="space-y-5">
            {/* Vitals */}
            <section data-tour="triage-vitals" className="card-flush p-6 border-l-4 border-l-brand-500">
                <div className="flex items-center justify-between mb-3 border-b border-ink-100 dark:border-ink-800 pb-3">
                    <h3 className="section-eyebrow flex items-center gap-2"><Activity size={16} className="text-brand-500" /> Vitals</h3>
                    <span className="text-xs text-ink-500 dark:text-ink-400">BMI: <span className="font-semibold text-ink-700 dark:text-ink-200">{bmi}</span></span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
                    <div><label htmlFor="triage-bp-mmhg" className="label">BP (mmHg)</label><input id="triage-bp-mmhg" type="text" value={vitals.bp} onChange={(e) => on.setVitals({ ...vitals, bp: e.target.value })} placeholder="120/80" className="input" /></div>
                    <div><label htmlFor="triage-hr-bpm" className="label">HR (bpm)</label><input id="triage-hr-bpm" type="number" value={vitals.hr} onChange={(e) => on.setVitals({ ...vitals, hr: e.target.value })} placeholder="72" className="input" /></div>
                    <div><label htmlFor="triage-resp-bpm" className="label">Resp (bpm)</label><input id="triage-resp-bpm" type="number" value={vitals.rr} onChange={(e) => on.setVitals({ ...vitals, rr: e.target.value })} placeholder="16" className="input" /></div>
                    <div><label htmlFor="triage-temp-c" className="label">Temp (°C)</label><input id="triage-temp-c" type="number" step="0.1" value={vitals.temp} onChange={(e) => on.setVitals({ ...vitals, temp: e.target.value })} placeholder="37.2" className="input" /></div>
                    <div><label htmlFor="triage-spo" className="label">SpO₂ (%)</label><input id="triage-spo" type="number" value={vitals.spo2} onChange={(e) => on.setVitals({ ...vitals, spo2: e.target.value })} placeholder="98" className="input" /></div>
                    <div><label htmlFor="triage-weight-kg" className="label">Weight (kg)</label><input id="triage-weight-kg" type="number" value={vitals.weight} onChange={(e) => on.setVitals({ ...vitals, weight: e.target.value })} placeholder="70" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                    <div><label htmlFor="triage-height-cm" className="label">Height (cm)</label><input id="triage-height-cm" type="number" value={vitals.height} onChange={(e) => on.setVitals({ ...vitals, height: e.target.value })} placeholder="175" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                    <div><label htmlFor="triage-pain-0-10" className="label">Pain (0–10)</label><input id="triage-pain-0-10" type="number" min="0" max="10" value={vitals.pain} onChange={(e) => on.setVitals({ ...vitals, pain: e.target.value })} placeholder="0" className="input" /></div>
                    <div><label htmlFor="triage-rbs-mmol-l" className="label">RBS (mmol/L)</label><input id="triage-rbs-mmol-l" type="number" step="0.1" value={vitals.glucose} onChange={(e) => on.setVitals({ ...vitals, glucose: e.target.value })} placeholder="5.5" className="input" /></div>
                </div>
            </section>

            {/* Presenting complaint + notes */}
            <section data-tour="triage-complaint" className="card-flush p-6 border-l-4 border-l-ink-700 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label htmlFor="triage-chief-complaint-s" className="label">Chief complaint(s)</label>
                    <div className="flex gap-2">
                        <input id="triage-chief-complaint-s" type="text" value={complaintInput}
                            onChange={(e) => on.setComplaintInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); on.addComplaint(); } }}
                            placeholder="What brought the patient in? Press Enter to add" className="input flex-1" />
                        <button type="button" onClick={on.addComplaint} className="btn-secondary shrink-0 px-3"><Plus size={15} /> Add</button>
                    </div>
                    {complaints.length > 0 && (
                        <ol className="mt-3 space-y-1.5">
                            {complaints.map((c, idx) => (
                                <li key={c} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                    <span className="font-mono text-2xs font-semibold text-ink-400 w-5 shrink-0">{idx + 1}.</span>
                                    <span className="flex-1 text-ink-800 dark:text-ink-200">{c}</span>
                                    <button type="button" onClick={() => on.removeComplaint(idx)} aria-label={`Remove complaint ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                </li>
                            ))}
                        </ol>
                    )}
                </div>
                <div>
                    <label htmlFor="triage-triage-notes" className="label">Triage notes</label>
                    {hasNotesDraft && (
                        <div className="mb-2">
                            <DraftRecoveryBanner savedAt={notesDraftSavedAt} label="triage notes"
                                onRestore={on.onRestoreDraft} onDiscard={on.onDiscardDraft} />
                        </div>
                    )}
                    <textarea id="triage-triage-notes" value={triageNotes} onChange={(e) => on.setTriageNotes(e.target.value)} rows={3}
                        placeholder="Observations, mobility, anything the doctor should know." className="input resize-none" />
                </div>
            </section>

            {/* Systemic Examination + Procedures (MedicentreV3 parity) */}
            <section data-tour="triage-systemic" className="card-flush p-6 border-l-4 border-l-accent-500 grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Systemic Examination */}
                <div>
                    <h3 className="section-eyebrow flex items-center gap-2 mb-3"><Stethoscope size={16} className="text-accent-600 dark:text-accent-400" /> Systemic Examination</h3>
                    <div className="space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                            <div>
                                <label htmlFor="tri-sys-system" className="label text-2xs">Body System</label>
                                <input id="tri-sys-system" list="tri-body-systems" className="input py-1.5 text-sm" value={newSys.body_system}
                                    onChange={(e) => setNewSys((p) => ({ ...p, body_system: e.target.value }))} placeholder="e.g. Respiratory" />
                                <datalist id="tri-body-systems">{BODY_SYSTEMS.map((b) => <option key={b} value={b} />)}</datalist>
                            </div>
                            <div>
                                <label htmlFor="tri-sys-remark" className="label text-2xs">Remark</label>
                                <input id="tri-sys-remark" className="input py-1.5 text-sm" value={newSys.remark}
                                    onChange={(e) => setNewSys((p) => ({ ...p, remark: e.target.value }))}
                                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addSystemic(); } }} placeholder="Findings" />
                            </div>
                        </div>
                        <div className="flex items-center justify-between">
                            <label htmlFor="tri-sys-anom" className="flex items-center gap-2 text-sm text-ink-700 dark:text-ink-300">
                                <input id="tri-sys-anom" type="checkbox" className="size-4 rounded" checked={newSys.is_anomalous}
                                    onChange={(e) => setNewSys((p) => ({ ...p, is_anomalous: e.target.checked }))} /> Is anomalous
                            </label>
                            <button type="button" onClick={addSystemic} className="btn-secondary px-3 py-1.5 text-xs"><Plus size={13} /> Add</button>
                        </div>
                        {systemicExam.length > 0 && (
                            <ul className="mt-2 space-y-1.5">
                                {systemicExam.map((s, idx) => (
                                    <li key={s._uid} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                        <span className="font-semibold text-ink-800 dark:text-ink-200">{s.body_system}</span>
                                        {s.remark && <span className="text-ink-600 dark:text-ink-400 truncate">— {s.remark}</span>}
                                        {s.is_anomalous && <span className="badge-danger text-2xs inline-flex items-center gap-1"><AlertTriangle size={10} /> Anomalous</span>}
                                        <button type="button" onClick={() => on.removeSystemic(idx)} aria-label={`Remove ${s.body_system} finding`} className="ml-auto text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>

                {/* Procedures */}
                <div>
                    <h3 className="section-eyebrow flex items-center gap-2 mb-3"><ClipboardList size={16} className="text-accent-600 dark:text-accent-400" /> Procedures</h3>
                    <div className="space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                            <div>
                                <label htmlFor="tri-proc-name" className="label text-2xs">Procedure</label>
                                <input id="tri-proc-name" list="tri-procedures" className="input py-1.5 text-sm" value={newProc.procedure}
                                    onChange={(e) => setNewProc((p) => ({ ...p, procedure: e.target.value }))} placeholder="e.g. Dressing" />
                                <datalist id="tri-procedures">{PROCEDURES.map((b) => <option key={b} value={b} />)}</datalist>
                            </div>
                            <div>
                                <label htmlFor="tri-proc-remark" className="label text-2xs">Remark</label>
                                <input id="tri-proc-remark" className="input py-1.5 text-sm" value={newProc.remark}
                                    onChange={(e) => setNewProc((p) => ({ ...p, remark: e.target.value }))}
                                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addProcedure(); } }} placeholder="Notes" />
                            </div>
                        </div>
                        <div className="flex justify-end">
                            <button type="button" onClick={addProcedure} className="btn-secondary px-3 py-1.5 text-xs"><Plus size={13} /> Add</button>
                        </div>
                        {procedures.length > 0 && (
                            <ul className="mt-2 space-y-1.5">
                                {procedures.map((pr, idx) => (
                                    <li key={pr._uid} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                        <span className="font-semibold text-ink-800 dark:text-ink-200">{pr.procedure}</span>
                                        {pr.remark && <span className="text-ink-600 dark:text-ink-400 truncate">— {pr.remark}</span>}
                                        <button type="button" onClick={() => on.removeProcedure(idx)} aria-label={`Remove ${pr.procedure}`} className="ml-auto text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            </section>

            {/* Acuity */}
            <section data-tour="triage-acuity" className="card-flush p-6 border-l-4 border-l-accent-500">
                <h3 className="section-eyebrow mb-3">Acuity</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                    {ACUITY_LEVELS.map((a) => (
                        <button key={a.level} type="button" onClick={() => on.setAcuity(a.level)}
                            className={`text-left p-3 rounded-xl border ring-1 transition-all ${acuity === a.level ? `${a.tone} border-transparent ring-2` : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 ring-transparent text-ink-600 dark:text-ink-400 hover:border-brand-300'}`}>
                            <div className="flex items-center gap-2 mb-0.5">
                                <span className="font-bold text-sm">{a.level}</span>
                                <span className="font-semibold text-sm">{a.label}</span>
                            </div>
                            <p className="text-2xs leading-tight opacity-80">{a.hint}</p>
                        </button>
                    ))}
                </div>
            </section>
        </div>
    );
}
