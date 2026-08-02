import React from 'react';
import {
    Activity, FileText, Pill, TestTube, Image as ImageIcon, Plus, X, Trash2,
    CalendarPlus, CheckCircle2, ClipboardList,
} from 'lucide-react';
import IcdDiagnosisPicker from '../../components/IcdDiagnosisPicker';
import { FORMULATIONS, FREQUENCIES, parseAssessPlan, serializeAssessPlan } from '../../utils/clinicalForms';

/**
 * Encounter Notes tab — the SOAP chart for the active encounter. Fully
 * controlled: `value` carries the encounter state the shell owns, `on` carries
 * the handlers. Extracted verbatim from the legacy Clinical Desk so behaviour
 * (submit targets, draft safety-net, guided-tour anchors) is unchanged.
 */
export default function EncounterNotesTab({ value, on }) {
    const {
        vitals, bmi, complaints, complaintInput, clinicalNotes, physicalExams, examInput,
        icdCodes, medications, assessPlan, pendingFollowUp, chargeConsultation, myFee,
    } = value;
    const ap = parseAssessPlan(assessPlan);
    const setAp = (patch) => on.setAssessPlan(serializeAssessPlan({ ...ap, ...patch }));

    return (
        <div className="space-y-6">
            {/* Vitals */}
            <div data-tour="clinical-vitals" className="card-flush p-6 border-l-4 border-l-brand-500">
                <div className="flex justify-between items-center mb-4 border-b border-ink-100 dark:border-ink-800 pb-3">
                    <h3 className="section-eyebrow flex items-center gap-2"><Activity size={16} className="text-brand-500" /> Vital signs</h3>
                    <button type="button" onClick={on.onViewTrends} className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 flex items-center gap-1"><Activity size={13} /> View trends</button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-4">
                    <div><label htmlFor="clinic-bp-mmhg" className="label">BP (mmHg)</label><input id="clinic-bp-mmhg" type="text" value={vitals.bp} onChange={(e) => on.setVitals({ ...vitals, bp: e.target.value })} placeholder="120/80" className="input" /></div>
                    <div><label htmlFor="clinic-hr-bpm" className="label">HR (bpm)</label><input id="clinic-hr-bpm" type="number" value={vitals.hr} onChange={(e) => on.setVitals({ ...vitals, hr: e.target.value })} placeholder="72" className="input" /></div>
                    <div><label htmlFor="clinic-resp-bpm" className="label">Resp (bpm)</label><input id="clinic-resp-bpm" type="number" value={vitals.rr} onChange={(e) => on.setVitals({ ...vitals, rr: e.target.value })} placeholder="16" className="input" /></div>
                    <div><label htmlFor="clinic-temp-c" className="label">Temp (°C)</label><input id="clinic-temp-c" type="number" step="0.1" value={vitals.temp} onChange={(e) => on.setVitals({ ...vitals, temp: e.target.value })} placeholder="37.2" className="input" /></div>
                    <div><label htmlFor="clinic-spo" className="label">SpO₂ (%)</label><input id="clinic-spo" type="number" value={vitals.spo2} onChange={(e) => on.setVitals({ ...vitals, spo2: e.target.value })} placeholder="98" className="input" /></div>
                    <div><label htmlFor="clinical-rbs" className="label">RBS (mmol/L)</label><input id="clinical-rbs" type="number" step="0.1" value={vitals.glucose} onChange={(e) => on.setVitals({ ...vitals, glucose: e.target.value })} placeholder="5.5" className="input" /></div>
                    <div><label htmlFor="clinic-weight-kg" className="label">Weight (kg)</label><input id="clinic-weight-kg" type="number" value={vitals.weight} onChange={(e) => on.setVitals({ ...vitals, weight: e.target.value })} placeholder="70" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                    <div><label htmlFor="clinic-height-cm" className="label">Height (cm)</label><input id="clinic-height-cm" type="number" value={vitals.height} onChange={(e) => on.setVitals({ ...vitals, height: e.target.value })} placeholder="175" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                    <div><span className="label text-brand-700 dark:text-brand-300 block">BMI</span><div className="input bg-brand-50 dark:bg-brand-500/10 ring-1 ring-brand-200 dark:ring-brand-500/20 text-brand-800 dark:text-brand-300 font-semibold text-center">{bmi}</div></div>
                </div>
            </div>

            {/* Clinical documentation (SOAP) */}
            <div className="card-flush p-6 border-l-4 border-l-ink-700 space-y-5">
                <h3 className="section-eyebrow border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2"><FileText size={16} className="text-ink-600 dark:text-ink-400" /> Clinical documentation</h3>
                <div>
                    <label htmlFor="clinic-cc" className="label">Chief complaint(s) (CC)</label>
                    <div className="flex gap-2">
                        <input id="clinic-cc" type="text" value={complaintInput}
                            onChange={(e) => on.setComplaintInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); on.addComplaint(); } }}
                            className="input flex-1" placeholder="e.g. Severe headache for 3 days — press Enter to add" />
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
                <div><label htmlFor="clinic-hpi" className="label">History of present illness (HPI)</label><textarea id="clinic-hpi" rows="3" value={clinicalNotes.hpi} onChange={(e) => on.setClinicalNotes({ ...clinicalNotes, hpi: e.target.value })} className="input resize-none" placeholder="Narrative of the patient's symptoms…" /></div>
                <div>
                    <label htmlFor="clinic-exam" className="label">Physical examination(s) (Objective)</label>
                    <div className="flex gap-2">
                        <input id="clinic-exam" type="text" value={examInput}
                            onChange={(e) => on.setExamInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); on.addExam(); } }}
                            className="input flex-1" placeholder="e.g. Chest: clear air entry bilaterally — press Enter to add" />
                        <button type="button" onClick={on.addExam} className="btn-secondary shrink-0 px-3"><Plus size={15} /> Add</button>
                    </div>
                    {physicalExams.length > 0 && (
                        <ol className="mt-3 space-y-1.5">
                            {physicalExams.map((c, idx) => (
                                <li key={c} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                    <span className="font-mono text-2xs font-semibold text-ink-400 w-5 shrink-0">{idx + 1}.</span>
                                    <span className="flex-1 text-ink-800 dark:text-ink-200">{c}</span>
                                    <button type="button" onClick={() => on.removeExam(idx)} aria-label={`Remove examination finding ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                </li>
                            ))}
                        </ol>
                    )}
                </div>
            </div>

            {/* Diagnosis & orders */}
            <div data-tour="clinical-diagnoses" className="card-flush p-6 border-l-4 border-l-accent-500 space-y-5">
                <h3 className="section-eyebrow border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2"><Pill size={16} className="text-accent-600 dark:text-accent-400" /> Diagnosis &amp; orders</h3>

                <IcdDiagnosisPicker codes={icdCodes} onChange={on.setIcdCodes} />

                <div>
                    <label htmlFor="clinic-dx" className="label">Diagnosis notes (free text)</label>
                    <input id="clinic-dx" type="text" value={clinicalNotes.diagnosis} onChange={(e) => on.setClinicalNotes({ ...clinicalNotes, diagnosis: e.target.value })} className="input" placeholder="Working / descriptive diagnosis if not using ICD-10 codes…" />
                </div>

                {/* Assessment & Plan → persisted in assessment_plan */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label htmlFor="clinic-assessment" className="label flex items-center gap-1"><ClipboardList size={13} /> Assessment</label><textarea id="clinic-assessment" rows="3" value={ap.assessment} onChange={(e) => setAp({ assessment: e.target.value })} className="input resize-none" placeholder="Clinical impression / differential…" /></div>
                    <div><label htmlFor="clinic-plan" className="label">Plan</label><textarea id="clinic-plan" rows="3" value={ap.plan} onChange={(e) => setAp({ plan: e.target.value })} className="input resize-none" placeholder="Management, investigations, follow-up…" /></div>
                </div>

                <div className="rounded-xl border border-ink-200 dark:border-ink-800 p-4">
                    <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 mb-3 flex items-center gap-2"><TestTube size={13} /> Investigations</h4>
                    <div className="flex gap-2">
                        <button type="button" onClick={on.onOrderLabs} className="btn-secondary flex-1 py-2 text-xs cursor-pointer"><TestTube size={13} aria-hidden="true" /> Order Lab Tests</button>
                        <button type="button" onClick={on.onOrderImaging} className="btn-secondary flex-1 py-2 text-xs cursor-pointer"><ImageIcon size={13} aria-hidden="true" /> Order Imaging</button>
                    </div>
                </div>

                {/* Medications */}
                <div data-tour="clinical-prescriptions" className="rounded-xl border border-accent-200 dark:border-accent-500/20 bg-accent-50/40 dark:bg-accent-500/10 p-4">
                    <div className="flex items-center justify-between mb-3">
                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-accent-700 dark:text-accent-300 flex items-center gap-2"><Pill size={13} /> Medications (routed to Pharmacy)</h4>
                        <button type="button" onClick={on.addMedication} className="btn-secondary px-3 py-1.5 text-xs shrink-0"><Plus size={13} /> Add medication</button>
                    </div>
                    {medications.length === 0 ? (
                        <p className="text-xs text-ink-500 dark:text-ink-400 italic">No medications yet — click “Add medication” to start prescribing.</p>
                    ) : (
                        <div className="space-y-2">
                            {medications.map((med, idx) => (
                                <div key={med._uid} className="rounded-lg border border-accent-200/70 dark:border-accent-500/20 bg-white dark:bg-ink-900 p-3">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="size-5 shrink-0 rounded-full bg-accent-100 dark:bg-accent-500/20 text-accent-700 dark:text-accent-300 text-2xs font-bold flex items-center justify-center">{idx + 1}</span>
                                        <input aria-label="Drug name (e.g. Amoxicillin)" value={med.drug} onChange={(e) => on.updateMedication(idx, 'drug', e.target.value)} className="input flex-1 py-1.5" placeholder="Drug name (e.g. Amoxicillin)" />
                                        <button type="button" onClick={() => on.removeMedication(idx)} aria-label={`Remove medication ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><Trash2 size={15} /></button>
                                    </div>
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                        <div>
                                            <label htmlFor={`clinic-formulation-${med._uid}`} className="label text-2xs">Formulation</label>
                                            <select id={`clinic-formulation-${med._uid}`} value={med.formulation} onChange={(e) => on.updateMedication(idx, 'formulation', e.target.value)} className="input py-1.5 text-sm">
                                                {FORMULATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label htmlFor={`clinic-dosage-${med._uid}`} className="label text-2xs">Dosage</label>
                                            <input id={`clinic-dosage-${med._uid}`} value={med.dosage} onChange={(e) => on.updateMedication(idx, 'dosage', e.target.value)} className="input py-1.5 text-sm" placeholder="500 mg" />
                                        </div>
                                        <div>
                                            <label htmlFor={`clinic-frequency-${med._uid}`} className="label text-2xs">Frequency</label>
                                            <input id={`clinic-frequency-${med._uid}`} list="rx-frequencies" value={med.frequency} onChange={(e) => on.updateMedication(idx, 'frequency', e.target.value)} className="input py-1.5 text-sm" placeholder="TDS" />
                                        </div>
                                        <div>
                                            <label htmlFor={`clinic-duration-${med._uid}`} className="label text-2xs">Duration</label>
                                            <input id={`clinic-duration-${med._uid}`} value={med.duration} onChange={(e) => on.updateMedication(idx, 'duration', e.target.value)} className="input py-1.5 text-sm" placeholder="5 days" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                            <datalist id="rx-frequencies">{FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}</datalist>
                        </div>
                    )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label htmlFor="clinic-internal" className="label">Internal notes (nursing / ward)</label><input id="clinic-internal" type="text" value={clinicalNotes.internal_notes} onChange={(e) => on.setClinicalNotes({ ...clinicalNotes, internal_notes: e.target.value })} className="input" placeholder="e.g. Please administer stat dose before discharge" /></div>
                    <div>
                        <span className="label flex items-center gap-1"><CalendarPlus size={13} aria-hidden="true" /> Next follow-up</span>
                        <button type="button" onClick={on.onPickFollowUp}
                            className={`input text-left flex items-center justify-between gap-2 cursor-pointer ${pendingFollowUp ? 'text-ink-900 dark:text-white border-brand-300 dark:border-brand-500/40 bg-brand-50/40 dark:bg-brand-500/10' : 'text-ink-400'}`}>
                            <span className="truncate">{pendingFollowUp ? new Date(pendingFollowUp.appointment_date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : 'Select date…'}</span>
                            {pendingFollowUp ? <CheckCircle2 size={13} className="text-accent-600 dark:text-accent-400 shrink-0" aria-hidden="true" /> : <CalendarPlus size={13} className="text-ink-400 shrink-0" aria-hidden="true" />}
                        </button>
                        {pendingFollowUp && (
                            <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">
                                With <span className="font-medium text-ink-700 dark:text-ink-200">{pendingFollowUp.doctor_name}</span>.{' '}
                                <button type="button" onClick={on.onPickFollowUp} className="text-brand-700 dark:text-brand-300 hover:text-brand-800 dark:hover:text-brand-200 cursor-pointer underline">Change</button>
                            </p>
                        )}
                    </div>
                </div>

                <div className="border border-brand-200 dark:border-brand-500/20 bg-brand-50/50 dark:bg-brand-500/10 p-4 rounded-xl flex items-center justify-between hover:bg-brand-50/80 dark:hover:bg-brand-500/15 transition-colors">
                    <label htmlFor="chargeFee" className="flex items-center gap-3 cursor-pointer">
                        <input type="checkbox" id="chargeFee" checked={chargeConsultation} onChange={(e) => on.setChargeConsultation(e.target.checked)} className="size-5 text-brand-600 rounded border-brand-300 focus:ring-brand-500" />
                        <span>
                            <span className="text-sm font-semibold text-brand-900 dark:text-brand-200 block">Authorize consultation fee</span>
                            <span className="text-xs text-brand-700 dark:text-brand-300">Automatically generate a consultation invoice at the cashier.</span>
                        </span>
                    </label>
                    <div className="text-right">
                        <span className="text-base font-semibold text-brand-700 dark:text-brand-300 block">KES {Number(myFee?.amount ?? 1000).toLocaleString()}</span>
                        <button type="button" onClick={on.onChangeFee} className="text-xs text-brand-700 dark:text-brand-300 underline hover:text-brand-800 dark:hover:text-brand-200 cursor-pointer">Change my fee</button>
                    </div>
                </div>
            </div>
        </div>
    );
}
