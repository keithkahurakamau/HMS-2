import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Activity, Users, Clock, AlertCircle, HeartPulse, Save, ChevronDown, ChevronUp,
    Stethoscope, ArrowRight,
} from 'lucide-react';
import toast from 'react-hot-toast';
import PageHeader from '../components/PageHeader';
import { useActivePatient } from '../context/PatientContext';

// Acuity scale shown to the nurse. 1 = most urgent. Mirrors the 1–5 range the
// backend clamps to and the doctor's queue sorts by.
const DISPOSITIONS = ['Consultation', 'Laboratory', 'Pharmacy', 'Radiology', 'Billing', 'Wards'];

const ACUITY_LEVELS = [
    { level: 1, label: 'Emergency',  hint: 'Immediate / resuscitation', tone: 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/20' },
    { level: 2, label: 'Urgent',     hint: 'Very ill, cannot wait',     tone: 'bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/20' },
    { level: 3, label: 'Standard',   hint: 'Stable, routine',           tone: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20' },
    { level: 4, label: 'Less urgent',hint: 'Minor complaint',           tone: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20' },
    { level: 5, label: 'Non-urgent', hint: 'Could be seen later',       tone: 'bg-blue-50 text-blue-700 ring-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20' },
];

const EMPTY_VITALS = {
    weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', pain: '', glucose: '',
};

export default function Triage() {
    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [activePatient, setActivePatient] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);

    const [vitals, setVitals] = useState(EMPTY_VITALS);
    // Chief complaint is a list — a patient can present with several.
    const [complaints, setComplaints] = useState([]);
    const [complaintInput, setComplaintInput] = useState('');
    const [triageNotes, setTriageNotes] = useState('');
    const [acuity, setAcuity] = useState(3);
    const [disposition, setDisposition] = useState('Consultation');

    const { setActivePatient: setGlobalActivePatient } = useActivePatient();

    useEffect(() => { fetchQueue(); }, []);

    const fetchQueue = async () => {
        setIsLoadingQueue(true);
        try {
            const res = await apiClient.get('/triage/queue');
            setQueue(res.data || []);
        } catch (err) {
            toast.error('Failed to load the triage queue.');
        } finally {
            setIsLoadingQueue(false);
        }
    };

    const removeFromTriage = async (e, queueId) => {
        e.stopPropagation();
        try {
            await apiClient.patch(`/queue/${queueId}/checkout`);
            toast.success('Removed from triage queue.');
            fetchQueue();
        } catch {
            toast.error('Could not remove from the queue.');
        }
    };

    const cancelFromTriage = async (e, queueId) => {
        e.stopPropagation();
        const reason = window.prompt('Cancel reason (optional):') ?? null;
        try {
            await apiClient.patch(`/queue/${queueId}/cancel`, { reason });
            toast.success('Patient cancelled.');
            fetchQueue();
        } catch {
            toast.error('Could not cancel.');
        }
    };

    const calculateBMI = () => {
        if (vitals.weight && vitals.height) {
            const h = parseFloat(vitals.height) / 100;
            const w = parseFloat(vitals.weight);
            if (h > 0 && w > 0) return (w / (h * h)).toFixed(1);
        }
        return '--';
    };

    const handlePatientSelect = (item) => {
        setActivePatient(item);
        setGlobalActivePatient(item);
        setIsQueueOpen(false);
        setVitals(EMPTY_VITALS);
        setComplaints([]);
        setComplaintInput('');
        setTriageNotes('');
        setAcuity(item.acuity_level || 3);
        setDisposition('Consultation');
    };

    const addComplaint = () => {
        const value = complaintInput.trim();
        if (!value) return;
        if (complaints.some((c) => c.toLowerCase() === value.toLowerCase())) {
            setComplaintInput('');
            return;
        }
        setComplaints((prev) => [...prev, value]);
        setComplaintInput('');
    };
    const removeComplaint = (idx) => setComplaints((prev) => prev.filter((_, i) => i !== idx));

    const handleSubmit = async () => {
        if (!activePatient) {
            toast.error('Select a patient from the queue first.');
            return;
        }
        // At least one vital or a chief complaint — otherwise there's nothing
        // to hand to the doctor and we'd just be advancing an empty record.
        const hasAnyVital = Object.values(vitals).some((v) => String(v).trim() !== '');
        // Fold any text left unsubmitted in the input into the list so a nurse
        // who typed but didn't press Enter doesn't lose it.
        const pending = complaintInput.trim();
        const allComplaints = pending && !complaints.some((c) => c.toLowerCase() === pending.toLowerCase())
            ? [...complaints, pending]
            : complaints;
        if (!hasAnyVital && allComplaints.length === 0) {
            toast.error('Record at least one vital or the chief complaint.');
            return;
        }

        setIsSubmitting(true);
        const bmi = calculateBMI();
        const payload = {
            patient_id: activePatient.patient_id,
            queue_id: activePatient.queue_id,
            blood_pressure: vitals.bp || null,
            heart_rate: vitals.hr ? parseInt(vitals.hr, 10) : null,
            respiratory_rate: vitals.rr ? parseInt(vitals.rr, 10) : null,
            temperature: vitals.temp ? parseFloat(vitals.temp) : null,
            spo2: vitals.spo2 ? parseInt(vitals.spo2, 10) : null,
            weight_kg: vitals.weight ? parseFloat(vitals.weight) : null,
            height_cm: vitals.height ? parseFloat(vitals.height) : null,
            calculated_bmi: bmi !== '--' ? parseFloat(bmi) : null,
            pain_score: vitals.pain !== '' ? parseInt(vitals.pain, 10) : null,
            blood_glucose: vitals.glucose ? parseFloat(vitals.glucose) : null,
            chief_complaint: allComplaints.length ? allComplaints.join('; ') : null,
            acuity_level: acuity,
            triage_notes: triageNotes || null,
            disposition,
        };

        try {
            const res = await apiClient.post('/triage/submit', payload);
            toast.success(res.data?.message || 'Triage saved — patient sent to the doctor.');
            setActivePatient(null);
            setIsQueueOpen(true);
            fetchQueue();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to save triage.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Nursing"
                icon={HeartPulse}
                title="Triage"
                subtitle="Capture vitals and acuity before the consultation — the doctor's desk arrives pre-filled."
            />

            {/* Triage queue */}
            <div data-tour="triage-queue" className="card shrink-0 flex flex-col z-20">
                <button type="button" onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 dark:bg-ink-800/40 hover:bg-brand-50/40 dark:hover:bg-ink-800/50 transition-colors rounded-t-2xl focus:outline-none">
                    <div className="flex items-center gap-3">
                        <Users className="text-brand-600" size={18} />
                        <h2 className="font-semibold text-ink-900 dark:text-white text-base tracking-tight">Awaiting Triage</h2>
                        <span className="badge-brand">{queue.length} Waiting</span>
                    </div>
                    <span className="text-ink-500">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                </button>

                {isQueueOpen && (
                    <div className="border-t border-ink-100 dark:border-ink-800 p-4 bg-white dark:bg-ink-900 rounded-b-2xl">
                        {isLoadingQueue ? (
                            <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading queue&hellip;</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-ink-400">No patients are currently waiting for triage.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((item) => (
                                    <div key={item.queue_id} className="flex flex-col">
                                        <button type="button" onClick={() => handlePatientSelect(item)}
                                            className={`text-left p-3 rounded-xl border transition-all duration-150 ${activePatient?.queue_id === item.queue_id ? 'bg-brand-50/60 dark:bg-brand-500/10 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                            <div className="flex justify-between items-start mb-2">
                                                <h3 className="font-semibold text-sm text-ink-900 dark:text-white">{item.patient_name}</h3>
                                                {item.allergies && item.allergies.toLowerCase() !== 'none' && <AlertCircle size={14} className="text-rose-500" />}
                                            </div>
                                            <div className="flex justify-between items-center text-xs text-ink-500 dark:text-ink-400">
                                                <span className="font-mono">{item.outpatient_no}</span>
                                                <span className="bg-ink-100 dark:bg-ink-800/40 px-2 py-0.5 rounded-full text-ink-600 dark:text-ink-400 flex items-center gap-1"><Clock size={10} /> {item.joined_time}</span>
                                            </div>
                                        </button>
                                        <div className="mt-1 flex items-center justify-end gap-1">
                                            <button type="button" onClick={(e) => removeFromTriage(e, item.queue_id)}
                                                className="text-xs px-2 py-0.5 rounded-md text-ink-500 hover:text-brand-700 hover:bg-brand-50 dark:hover:bg-ink-800">
                                                Remove
                                            </button>
                                            <button type="button" onClick={(e) => cancelFromTriage(e, item.queue_id)}
                                                className="text-xs px-2 py-0.5 rounded-md text-ink-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10">
                                                Cancel
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Triage workspace */}
            <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                {!activePatient ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/40">
                        <HeartPulse size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-600 dark:text-ink-400 mb-1">Triage station</h3>
                        <p className="text-sm">Select a patient from the queue to record their vitals.</p>
                    </div>
                ) : (
                    <div className="flex flex-col h-full">
                        {/* Patient header */}
                        <div className="p-4 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex justify-between items-center">
                            <div className="flex items-center gap-3">
                                <div className="size-11 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 text-white flex items-center justify-center font-semibold text-base shadow-glow">
                                    {activePatient.patient_name?.charAt(0) || 'P'}
                                </div>
                                <div>
                                    <h1 className="text-lg font-semibold text-ink-900 dark:text-white tracking-tight">{activePatient.patient_name}</h1>
                                    <p className="text-xs font-medium text-ink-500 dark:text-ink-400">{activePatient.outpatient_no} &middot; {activePatient.age} yrs &middot; {activePatient.gender}</p>
                                </div>
                            </div>
                            {activePatient.allergies && activePatient.allergies.toLowerCase() !== 'none' && (
                                <div className="bg-rose-50 dark:bg-rose-500/10 ring-1 ring-rose-100 dark:ring-rose-500/20 px-3 py-2 rounded-xl flex items-center gap-2">
                                    <AlertCircle size={16} className="text-rose-600" />
                                    <div>
                                        <p className="text-2xs font-semibold text-rose-700 dark:text-rose-300 uppercase tracking-[0.14em]">Allergies</p>
                                        <p className="text-xs font-semibold text-rose-700 dark:text-rose-300">{activePatient.allergies}</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Scrollable body */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-5 custom-scrollbar">
                            {/* Vitals */}
                            <section data-tour="triage-vitals">
                                <div className="flex items-center justify-between mb-3">
                                    <h3 className="font-semibold text-ink-800 dark:text-ink-200 flex items-center gap-2"><Activity size={16} className="text-brand-600" /> Vitals</h3>
                                    <span className="text-xs text-ink-500 dark:text-ink-400">BMI: <span className="font-semibold text-ink-700 dark:text-ink-200">{calculateBMI()}</span></span>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-3">
                                    <div><label htmlFor="triage-bp-mmhg" className="label">BP (mmHg)</label><input id="triage-bp-mmhg" type="text" value={vitals.bp} onChange={(e) => setVitals({ ...vitals, bp: e.target.value })} placeholder="120/80" className="input" /></div>
                                    <div><label htmlFor="triage-hr-bpm" className="label">HR (bpm)</label><input id="triage-hr-bpm" type="number" value={vitals.hr} onChange={(e) => setVitals({ ...vitals, hr: e.target.value })} placeholder="72" className="input" /></div>
                                    <div><label htmlFor="triage-resp-bpm" className="label">Resp (bpm)</label><input id="triage-resp-bpm" type="number" value={vitals.rr} onChange={(e) => setVitals({ ...vitals, rr: e.target.value })} placeholder="16" className="input" /></div>
                                    <div><label htmlFor="triage-temp-c" className="label">Temp (°C)</label><input id="triage-temp-c" type="number" step="0.1" value={vitals.temp} onChange={(e) => setVitals({ ...vitals, temp: e.target.value })} placeholder="37.2" className="input" /></div>
                                    <div><label htmlFor="triage-spo" className="label">SpO₂ (%)</label><input id="triage-spo" type="number" value={vitals.spo2} onChange={(e) => setVitals({ ...vitals, spo2: e.target.value })} placeholder="98" className="input" /></div>
                                    <div><label htmlFor="triage-weight-kg" className="label">Weight (kg)</label><input id="triage-weight-kg" type="number" value={vitals.weight} onChange={(e) => setVitals({ ...vitals, weight: e.target.value })} placeholder="70" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                                    <div><label htmlFor="triage-height-cm" className="label">Height (cm)</label><input id="triage-height-cm" type="number" value={vitals.height} onChange={(e) => setVitals({ ...vitals, height: e.target.value })} placeholder="175" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                                    <div><label htmlFor="triage-pain-0-10" className="label">Pain (0–10)</label><input id="triage-pain-0-10" type="number" min="0" max="10" value={vitals.pain} onChange={(e) => setVitals({ ...vitals, pain: e.target.value })} placeholder="0" className="input" /></div>
                                    <div><label htmlFor="triage-rbs-mmol-l" className="label">RBS (mmol/L)</label><input id="triage-rbs-mmol-l" type="number" step="0.1" value={vitals.glucose} onChange={(e) => setVitals({ ...vitals, glucose: e.target.value })} placeholder="5.5" className="input" /></div>
                                </div>
                            </section>

                            {/* Presenting complaint */}
                            <section data-tour="triage-complaint" className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="triage-chief-complaint-s" className="label">Chief complaint(s)</label>
                                    <div className="flex gap-2">
                                        <input id="triage-chief-complaint-s"
                                            type="text"
                                            value={complaintInput}
                                            onChange={(e) => setComplaintInput(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addComplaint(); } }}
                                            placeholder="What brought the patient in? Press Enter to add"
                                            className="input flex-1"
                                        />
                                        <button type="button" onClick={addComplaint} className="btn-secondary shrink-0 px-3">Add</button>
                                    </div>
                                    {complaints.length > 0 && (
                                        <ol className="mt-3 space-y-1.5">
                                            {complaints.map((c, idx) => (
                                                <li key={c} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                                    <span className="font-mono text-2xs font-semibold text-ink-400 w-5 shrink-0">{idx + 1}.</span>
                                                    <span className="flex-1 text-ink-800 dark:text-ink-200">{c}</span>
                                                    <button type="button" onClick={() => removeComplaint(idx)} aria-label={`Remove complaint ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0">✕</button>
                                                </li>
                                            ))}
                                        </ol>
                                    )}
                                </div>
                                <div>
                                    <label htmlFor="triage-triage-notes" className="label">Triage notes</label>
                                    <textarea id="triage-triage-notes" value={triageNotes} onChange={(e) => setTriageNotes(e.target.value)} rows={3} placeholder="Observations, mobility, anything the doctor should know." className="input" />
                                </div>
                            </section>

                            {/* Acuity */}
                            <section data-tour="triage-acuity">
                                <h3 className="font-semibold text-ink-800 dark:text-ink-200 mb-3">Acuity</h3>
                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                                    {ACUITY_LEVELS.map((a) => (
                                        <button key={a.level} type="button" onClick={() => setAcuity(a.level)}
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

                        {/* Footer actions */}
                        <div className="shrink-0 p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex flex-wrap items-center justify-between gap-3">
                            <div className="flex flex-wrap items-center gap-4">
                                <p className="text-xs text-ink-500 dark:text-ink-400 flex items-center gap-1.5">
                                    <Stethoscope size={13} /> On save, the patient is routed to {disposition}.
                                </p>
                                <div className="flex items-center gap-2">
                                    <label htmlFor="triage-disposition" className="label mb-0">Route to</label>
                                    <select id="triage-disposition" value={disposition}
                                        onChange={(e) => setDisposition(e.target.value)} className="input w-auto">
                                        {DISPOSITIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                                    </select>
                                </div>
                            </div>
                            <button type="button" data-tour="triage-save" onClick={handleSubmit} disabled={isSubmitting} className="btn-primary">
                                {isSubmitting ? <Activity size={15} className="animate-spin" /> : <Save size={15} />}
                                Save &amp; send to doctor <ArrowRight size={15} />
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
