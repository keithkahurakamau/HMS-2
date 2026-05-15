import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Search, User, Activity, FileText, Pill, CheckCircle2, AlertCircle, Clock,
    ChevronDown, ChevronUp, Users, Send, Stethoscope, TestTube, ArrowRightLeft,
    History, Scissors, Cigarette, Dna, Syringe, CalendarPlus, FileSignature, Save, Receipt, Variable,
    X, Image as ImageIcon, Plus, Minus,
} from 'lucide-react';
import toast from 'react-hot-toast';
import PageHeader from '../components/PageHeader';
import { useActivePatient } from '../context/PatientContext';

export default function ClinicalDesk() {
    const navigate = useNavigate();
    // --- DYNAMIC QUEUE STATE ---
    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [activePatient, setActivePatient] = useState(null);
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);

    // --- FORM STATE ---
    const [vitals, setVitals] = useState({ weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '' });
    const [clinicalNotes, setClinicalNotes] = useState({ cc: '', hpi: '', objective: '', diagnosis: '', plan: '', internal_notes: '' });
    const [icdSearch, setIcdSearch] = useState('');
    const [showIcdDropdown, setShowIcdDropdown] = useState(false);
    const [chargeConsultation, setChargeConsultation] = useState(false);

    // --- LAB / IMAGING / FOLLOW-UP MODAL STATE ---
    const [isLabModalOpen, setIsLabModalOpen] = useState(false);
    const [isImagingModalOpen, setIsImagingModalOpen] = useState(false);
    const [isFollowUpOpen, setIsFollowUpOpen] = useState(false);
    // Holds the most recent appointment we booked from this consultation so
    // the doctor sees confirmation in-line and the button updates from
    // "Select date…" to the scheduled date/time.
    const [pendingFollowUp, setPendingFollowUp] = useState(null);

    // Cross-page active patient context (also drives the bar at the top of
    // every workspace page). We mirror the local `activePatient` state into
    // it so the rest of the system sees the doctor's current focus.
    const { setActivePatient: setGlobalActivePatient } = useActivePatient();

    const mockIcdDatabase = ["A09 - Infectious gastroenteritis", "E11.9 - Type 2 diabetes mellitus", "I10 - Essential hypertension", "B50.9 - Severe Malaria", "J03.90 - Acute tonsillitis", "R50.9 - Fever, unspecified"];
    const filteredIcd = mockIcdDatabase.filter(code => code.toLowerCase().includes(icdSearch.toLowerCase()));

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchQueue();
    }, []);

    const fetchQueue = async () => {
        setIsLoadingQueue(true);
        try {
            const response = await apiClient.get('/clinical/queue');
            setQueue(response.data || []);
        } catch (error) {
            toast.error("Failed to load active patient queue.");
        } finally {
            setIsLoadingQueue(false);
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

    const handlePatientSelect = (patientItem) => {
        setActivePatient(patientItem);
        // Make this patient the system-wide active context so the persistent
        // bar + cross-module navigation stays scoped to them, and the
        // KDPA S.26 access log captures the doctor's movement.
        setGlobalActivePatient(patientItem);
        setIsQueueOpen(false);
        // Reset all forms for the new patient
        setVitals({ weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '' });
        setClinicalNotes({ cc: '', hpi: '', objective: '', diagnosis: '', plan: '', internal_notes: '' });
        setIcdSearch('');
        setChargeConsultation(false);
    };

    // --- ACTION HANDLERS ---
    const handleNotImplemented = (moduleName) => {
        toast(`The ${moduleName} module is currently under development.`, { icon: '🚧' });
    };

    const handleClinicalSubmit = async (targetStatus) => {
        if (!activePatient) return;
        setIsSubmitting(true);

        // Build the payload matching the backend Pydantic schema
        const payload = {
            patient_id: activePatient.patient_id,
            queue_id: activePatient.queue_id,
            record_status: targetStatus, // "Draft", "Pharmacy", "Billed", or "Completed"
            
            // Vitals (Convert strings to numbers where appropriate, or leave null)
            blood_pressure: vitals.bp || null,
            heart_rate: vitals.hr ? parseInt(vitals.hr) : null,
            respiratory_rate: vitals.rr ? parseInt(vitals.rr) : null,
            temperature: vitals.temp ? parseFloat(vitals.temp) : null,
            spo2: vitals.spo2 ? parseInt(vitals.spo2) : null,
            weight_kg: vitals.weight ? parseFloat(vitals.weight) : null,
            height_cm: vitals.height ? parseFloat(vitals.height) : null,
            
            // Clinical Notes
            chief_complaint: clinicalNotes.cc,
            history_of_present_illness: clinicalNotes.hpi,
            physical_examination: clinicalNotes.objective,
            diagnosis: clinicalNotes.diagnosis || icdSearch,
            icd10_code: icdSearch,
            treatment_plan: clinicalNotes.plan, // This is what the Pharmacy reads!
            internal_notes: clinicalNotes.internal_notes
        };

        try {
            await apiClient.post('/clinical/submit', payload);
            
            // Generate Consultation Fee if checked
            if (chargeConsultation && targetStatus !== 'Draft') {
                await apiClient.post('/billing/consultation-fee', {
                    patient_id: activePatient.patient_id,
                    amount: 1000.0
                });
            }
            
            if (targetStatus === 'Pharmacy') toast.success("Record saved and routed to Pharmacy!");
            else if (targetStatus === 'Billed') toast.success("Record saved and sent to Billing!");
            else if (targetStatus === 'Draft') toast.success("Draft saved successfully.");
            else toast.success("Consultation finalized and closed.");

            // If not a draft, clear the workspace and refresh the queue
            if (targetStatus !== 'Draft') {
                setActivePatient(null);
                setIsQueueOpen(true);
                fetchQueue();
            }
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to save clinical record.");
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Consultation"
                icon={Stethoscope}
                title="Clinical Desk"
                subtitle="Run encounters end-to-end — vitals, diagnosis, prescriptions, and orders."
            />

            {/* TOP PANEL: Collapsible Queue */}
            <div className="card shrink-0 flex flex-col z-20">
                <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 hover:bg-brand-50/40 transition-colors rounded-t-2xl focus:outline-none">
                    <div className="flex items-center gap-3">
                        <Users className="text-brand-600" size={18} />
                        <h2 className="font-semibold text-ink-900 text-base tracking-tight">Active Queue</h2>
                        <span className="badge-brand">{queue.length} Waiting</span>
                    </div>
                    <span className="text-ink-500">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                </button>

                {isQueueOpen && (
                    <div className="border-t border-ink-100 p-4 bg-white rounded-b-2xl">
                        {isLoadingQueue ? (
                            <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading queue&hellip;</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-ink-400">No patients currently waiting in your queue.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((item) => (
                                    <button key={item.queue_id} type="button" onClick={() => handlePatientSelect(item)}
                                        className={`text-left p-3 rounded-xl border transition-all duration-150 ${activePatient?.queue_id === item.queue_id ? 'bg-brand-50/60 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white border-ink-200 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                        <div className="flex justify-between items-start mb-2">
                                            <h3 className="font-semibold text-sm text-ink-900">{item.patient_name}</h3>
                                            {item.priority === 'High' && <AlertCircle size={14} className="text-rose-500 animate-pulse-soft" />}
                                        </div>
                                        <div className="flex justify-between items-center text-xs text-ink-500">
                                            <span className="font-mono">{item.outpatient_no}</span>
                                            <span className="bg-ink-100 px-2 py-0.5 rounded-full text-ink-600 flex items-center gap-1"><Clock size={10} /> {item.triage_time}</span>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* BOTTOM PANEL: Consultation Workspace */}
            <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                {!activePatient ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40">
                        <Stethoscope size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-600 mb-1">Doctor's workspace</h3>
                        <p className="text-sm">Select a patient from the queue to begin charting.</p>
                    </div>
                ) : (
                    <>
                        <div className="shrink-0 flex flex-col">
                            <div className="p-4 border-b border-ink-100 bg-white flex justify-between items-center z-10">
                                <div className="flex items-center gap-3">
                                    <div className="w-11 h-11 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 text-white flex items-center justify-center font-semibold text-base shadow-glow">
                                        {activePatient.patient_name?.charAt(0) || 'P'}
                                    </div>
                                    <div>
                                        <h1 className="text-lg font-semibold text-ink-900 tracking-tight">{activePatient.patient_name}</h1>
                                        <p className="text-xs font-medium text-ink-500">{activePatient.outpatient_no} &middot; {activePatient.age} yrs &middot; {activePatient.gender}</p>
                                    </div>
                                </div>
                                {activePatient.allergies && activePatient.allergies.toLowerCase() !== 'none' && (
                                    <div className="bg-rose-50 ring-1 ring-rose-100 px-3 py-2 rounded-xl flex items-center gap-2">
                                        <AlertCircle size={16} className="text-rose-600" />
                                        <div>
                                            <p className="text-2xs font-semibold text-rose-700 uppercase tracking-[0.14em]">Allergies</p>
                                            <p className="text-xs font-semibold text-rose-700">{activePatient.allergies}</p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* History toolbar — each button deep-links to the
                                Medical History page with the active patient
                                pre-selected and the relevant section auto-expanded.
                                The first item lands on the full chart (no entry_type
                                filter) so the doctor sees everything at a glance. */}
                            <div className="bg-ink-50/40 border-b border-ink-100 p-2 flex gap-1.5 overflow-x-auto custom-scrollbar">
                                {[
                                    { icon: History,   label: 'Medical Hx',    entry_type: null },
                                    { icon: Scissors,  label: 'Surgical Hx',   entry_type: 'SURGICAL_HISTORY' },
                                    { icon: Cigarette, label: 'Social Hx',     entry_type: 'SOCIAL_HISTORY' },
                                    { icon: Dna,       label: 'Family Hx',     entry_type: 'FAMILY_HISTORY' },
                                    { icon: Syringe,   label: 'Immunizations', entry_type: 'IMMUNIZATION' },
                                ].map(({ icon: Icon, label, entry_type }) => (
                                    <button
                                        key={label}
                                        onClick={() => {
                                            const params = new URLSearchParams({ patient_id: String(activePatient.patient_id) });
                                            if (entry_type) params.set('entry_type', entry_type);
                                            navigate(`/app/medical-history?${params.toString()}`);
                                        }}
                                        className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-ink-200 text-ink-600 rounded-lg text-xs font-medium hover:border-brand-300 hover:text-brand-700 transition-colors"
                                    >
                                        <Icon size={13} /> {label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 custom-scrollbar">

                            {/* Vitals Entry */}
                            <div className="card-flush p-5 border-l-4 border-l-brand-500">
                                <div className="flex justify-between items-center mb-4 border-b border-ink-100 pb-3">
                                    <h3 className="section-eyebrow flex items-center gap-2"><Activity size={16} className="text-brand-500" /> Vital signs</h3>
                                    <button onClick={() => handleNotImplemented('Vitals Trends')} className="text-xs font-semibold text-brand-600 hover:text-brand-700 flex items-center gap-1"><Activity size={13} /> View trends</button>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
                                    <div><label className="label">BP (mmHg)</label><input type="text" value={vitals.bp} onChange={(e) => setVitals({...vitals, bp: e.target.value})} placeholder="120/80" className="input" /></div>
                                    <div><label className="label">HR (bpm)</label><input type="number" value={vitals.hr} onChange={(e) => setVitals({...vitals, hr: e.target.value})} placeholder="72" className="input" /></div>
                                    <div><label className="label">Resp (bpm)</label><input type="number" value={vitals.rr} onChange={(e) => setVitals({...vitals, rr: e.target.value})} placeholder="16" className="input" /></div>
                                    <div><label className="label">Temp (°C)</label><input type="number" step="0.1" value={vitals.temp} onChange={(e) => setVitals({...vitals, temp: e.target.value})} placeholder="37.2" className="input" /></div>
                                    <div><label className="label">SpO₂ (%)</label><input type="number" value={vitals.spo2} onChange={(e) => setVitals({...vitals, spo2: e.target.value})} placeholder="98" className="input" /></div>
                                    <div><label className="label">Weight (kg)</label><input type="number" value={vitals.weight} onChange={(e) => setVitals({...vitals, weight: e.target.value})} placeholder="70" className="input bg-brand-50/40" /></div>
                                    <div><label className="label">Height (cm)</label><input type="number" value={vitals.height} onChange={(e) => setVitals({...vitals, height: e.target.value})} placeholder="175" className="input bg-brand-50/40" /></div>
                                    <div><label className="label text-brand-700">BMI</label><div className="input bg-brand-50 ring-1 ring-brand-200 text-brand-800 font-semibold text-center">{calculateBMI()}</div></div>
                                </div>
                            </div>

                            {/* Clinical Documentation (SOAP) */}
                            <div className="card-flush p-5 border-l-4 border-l-ink-700 space-y-4">
                                <h3 className="section-eyebrow border-b border-ink-100 pb-3 flex items-center gap-2"><FileText size={16} className="text-ink-600" /> Clinical documentation</h3>
                                <div><label className="label">Chief complaint (CC)</label><input type="text" value={clinicalNotes.cc} onChange={(e) => setClinicalNotes({...clinicalNotes, cc: e.target.value})} className="input" placeholder="e.g. Severe headache for 3 days" /></div>
                                <div><label className="label">History of present illness (HPI)</label><textarea rows="3" value={clinicalNotes.hpi} onChange={(e) => setClinicalNotes({...clinicalNotes, hpi: e.target.value})} className="input resize-none" placeholder="Narrative of the patient's symptoms…"></textarea></div>
                                <div><label className="label">Physical examination (Objective)</label><textarea rows="3" value={clinicalNotes.objective} onChange={(e) => setClinicalNotes({...clinicalNotes, objective: e.target.value})} className="input resize-none" placeholder="Systematic findings…"></textarea></div>
                            </div>

                            {/* Orders & Prescriptions */}
                            <div className="card-flush p-5 border-l-4 border-l-accent-500 space-y-4">
                                <h3 className="section-eyebrow border-b border-ink-100 pb-3 flex items-center gap-2"><Pill size={16} className="text-accent-600" /> Diagnosis &amp; orders</h3>

                                <div className="relative">
                                    <label className="label">Final diagnosis (ICD-10)</label>
                                    <input type="text" value={icdSearch} onChange={(e) => { setIcdSearch(e.target.value); setShowIcdDropdown(true); }} onFocus={() => setShowIcdDropdown(true)} className="input" placeholder="Type to search ICD-10 codes…" />
                                    {showIcdDropdown && icdSearch.length > 0 && (
                                        <div className="absolute z-30 w-full mt-1 bg-white border border-ink-200 rounded-xl shadow-elevated max-h-48 overflow-y-auto custom-scrollbar">
                                            {filteredIcd.length > 0 ? filteredIcd.map((code, idx) => (<button type="button" key={idx} onClick={() => {setIcdSearch(code); setShowIcdDropdown(false);}} className="block w-full text-left px-4 py-2 hover:bg-brand-50 text-sm">{code}</button>)) : <div className="px-4 py-3 text-sm text-ink-500">No codes found.</div>}
                                        </div>
                                    )}
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="rounded-xl border border-ink-200 p-4">
                                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 mb-3 flex items-center gap-2"><TestTube size={13} /> Investigations</h4>
                                        <div className="flex gap-2">
                                            <button
                                                type="button"
                                                onClick={() => setIsLabModalOpen(true)}
                                                className="btn-secondary flex-1 py-2 text-xs cursor-pointer"
                                            >
                                                <TestTube size={13} aria-hidden="true" /> Order Lab Tests
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setIsImagingModalOpen(true)}
                                                className="btn-secondary flex-1 py-2 text-xs cursor-pointer"
                                            >
                                                <ImageIcon size={13} aria-hidden="true" /> Order Imaging
                                            </button>
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-accent-200 bg-accent-50/40 p-4">
                                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-accent-700 mb-3 flex items-center gap-2"><Pill size={13} /> Medications (routed to Pharmacy)</h4>
                                        <textarea rows="2" value={clinicalNotes.plan} onChange={(e) => setClinicalNotes({...clinicalNotes, plan: e.target.value})} className="input resize-none" placeholder="Enter prescription instructions to send to Pharmacy…"></textarea>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div><label className="label">Internal notes (nursing / ward)</label><input type="text" value={clinicalNotes.internal_notes} onChange={(e) => setClinicalNotes({...clinicalNotes, internal_notes: e.target.value})} className="input" placeholder="e.g. Please administer stat dose before discharge" /></div>
                                    <div>
                                        <label className="label flex items-center gap-1">
                                            <CalendarPlus size={13} aria-hidden="true" /> Next follow-up
                                        </label>
                                        <button
                                            type="button"
                                            onClick={() => setIsFollowUpOpen(true)}
                                            className={`input text-left flex items-center justify-between gap-2 cursor-pointer ${
                                                pendingFollowUp ? 'text-ink-900 border-brand-300 bg-brand-50/40' : 'text-ink-400'
                                            }`}
                                        >
                                            <span className="truncate">
                                                {pendingFollowUp
                                                    ? new Date(pendingFollowUp.appointment_date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
                                                    : 'Select date…'}
                                            </span>
                                            {pendingFollowUp
                                                ? <CheckCircle2 size={13} className="text-accent-600 shrink-0" aria-hidden="true" />
                                                : <CalendarPlus size={13} className="text-ink-400 shrink-0" aria-hidden="true" />}
                                        </button>
                                        {pendingFollowUp && (
                                            <p className="text-2xs text-ink-500 mt-1">
                                                With <span className="font-medium text-ink-700">{pendingFollowUp.doctor_name}</span>.{' '}
                                                <button
                                                    type="button"
                                                    onClick={() => setIsFollowUpOpen(true)}
                                                    className="text-brand-700 hover:text-brand-800 cursor-pointer underline"
                                                >
                                                    Change
                                                </button>
                                            </p>
                                        )}
                                    </div>
                                </div>

                                <label htmlFor="chargeFee" className="border border-brand-200 bg-brand-50/50 p-4 rounded-xl flex items-center justify-between cursor-pointer hover:bg-brand-50/80 transition-colors">
                                    <div className="flex items-center gap-3">
                                        <input type="checkbox" id="chargeFee" checked={chargeConsultation} onChange={(e) => setChargeConsultation(e.target.checked)} className="w-5 h-5 text-brand-600 rounded border-brand-300 focus:ring-brand-500" />
                                        <div>
                                            <span className="text-sm font-semibold text-brand-900 block">Authorize consultation fee</span>
                                            <span className="text-xs text-brand-700">Automatically generate a consultation invoice at the cashier.</span>
                                        </div>
                                    </div>
                                    <span className="text-base font-semibold text-brand-700">KES 1,000</span>
                                </label>
                            </div>
                        </div>

                        {/* Footer actions */}
                        <div className="p-4 border-t border-ink-100 bg-white flex flex-wrap justify-between items-center gap-3 shrink-0 z-10">
                            <div className="flex gap-2">
                                <button onClick={() => handleClinicalSubmit('Draft')} disabled={isSubmitting} className="btn-secondary"><Save size={15} /> Save draft</button>
                                <button onClick={() => handleNotImplemented('External Referrals')} className="btn-ghost"><ArrowRightLeft size={15} /> Refer patient</button>
                            </div>

                            <div className="flex gap-2">
                                <button onClick={() => handleClinicalSubmit('Billed')} disabled={isSubmitting} className="btn-secondary text-brand-700 border-brand-200 hover:bg-brand-50">
                                    <Receipt size={15} /> Send to billing
                                </button>
                                <button onClick={() => handleClinicalSubmit('Pharmacy')} disabled={isSubmitting} className="btn-success">
                                    <Pill size={15} /> Forward to pharmacy
                                </button>
                                <button onClick={() => handleClinicalSubmit('Completed')} disabled={isSubmitting} className="btn bg-ink-800 text-white hover:bg-ink-900 shadow-soft">
                                    <FileSignature size={15} /> Finalize &amp; sign
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Lab + imaging order modals — only rendered when a patient is
                active so the modals always have a target to POST against. */}
            {activePatient && isLabModalOpen && (
                <LabOrderModal
                    patient={activePatient}
                    onClose={() => setIsLabModalOpen(false)}
                />
            )}
            {activePatient && isImagingModalOpen && (
                <ImagingOrderModal
                    patient={activePatient}
                    onClose={() => setIsImagingModalOpen(false)}
                />
            )}
            {activePatient && isFollowUpOpen && (
                <FollowUpModal
                    patient={activePatient}
                    existing={pendingFollowUp}
                    onClose={() => setIsFollowUpOpen(false)}
                    onBooked={(appt) => { setPendingFollowUp(appt); setIsFollowUpOpen(false); }}
                />
            )}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Lab order modal.                                                          */
/*                                                                            */
/*  Fetches /laboratory/catalog (only active tests), lets the doctor pick     */
/*  one or more, attach per-test clinical notes + priority, and submits in    */
/*  a single transaction via /laboratory/orders.                              */
/* ────────────────────────────────────────────────────────────────────────── */
const PRIORITIES = ['Routine', 'Urgent', 'STAT'];

function LabOrderModal({ patient, onClose }) {
    const [catalog, setCatalog] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [search, setSearch] = useState('');
    // Map of catalog_id -> { selected, priority, clinical_notes }
    const [selection, setSelection] = useState({});
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get('/laboratory/catalog?active_only=true');
                setCatalog(res.data || []);
            } catch (e) {
                toast.error(e.response?.data?.detail || 'Failed to load lab catalog.');
            } finally {
                setIsLoading(false);
            }
        })();
    }, []);

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase();
        if (!needle) return catalog;
        return catalog.filter(c =>
            c.test_name?.toLowerCase().includes(needle)
            || c.specimen_type?.toLowerCase().includes(needle)
        );
    }, [catalog, search]);

    const selectedItems = useMemo(() =>
        Object.entries(selection).filter(([, v]) => v && v.selected)
    , [selection]);

    const toggle = (catalogId) => {
        setSelection(prev => ({
            ...prev,
            [catalogId]: prev[catalogId]?.selected
                ? { ...prev[catalogId], selected: false }
                : { selected: true, priority: 'Routine', clinical_notes: '' },
        }));
    };

    const updateField = (catalogId, field, value) => {
        setSelection(prev => ({
            ...prev,
            [catalogId]: { ...prev[catalogId], [field]: value },
        }));
    };

    const submit = async () => {
        if (selectedItems.length === 0) {
            toast.error('Pick at least one test.');
            return;
        }
        setSubmitting(true);
        try {
            const tests = selectedItems.map(([catalogId, v]) => ({
                catalog_id: Number(catalogId),
                clinical_notes: v.clinical_notes || null,
                priority: v.priority || 'Routine',
            }));
            await apiClient.post('/laboratory/orders', {
                patient_id: patient.patient_id,
                record_id: null,
                tests,
            });
            toast.success(`Ordered ${tests.length} lab test${tests.length === 1 ? '' : 's'}.`);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to create lab order.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lab-order-title"
        >
            <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-3xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 bg-ink-50 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">New lab order</p>
                        <h2 id="lab-order-title" className="text-base sm:text-lg font-semibold text-ink-900 tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {/* Search */}
                    <div className="px-4 sm:px-6 py-3 border-b border-ink-200 bg-white sticky top-0 z-10">
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                            <label htmlFor="lab-search" className="sr-only">Search tests</label>
                            <input
                                id="lab-search"
                                type="search"
                                placeholder="Search lab tests by name or specimen…"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full bg-white border border-ink-200 rounded-lg pl-9 pr-3 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                    </div>

                    {/* Catalog list */}
                    <div className="p-4 sm:p-6 space-y-1.5">
                        {isLoading ? (
                            <div className="text-center py-8 text-ink-500">
                                <Activity className="animate-spin inline mr-2 text-brand-600" size={18} aria-hidden="true" /> Loading catalog…
                            </div>
                        ) : filtered.length === 0 ? (
                            <p className="text-center py-8 text-ink-500 text-sm">No tests match your search.</p>
                        ) : filtered.map(item => {
                            const state = selection[item.catalog_id];
                            const isSelected = !!state?.selected;
                            return (
                                <div
                                    key={item.catalog_id}
                                    className={`rounded-lg border transition-colors ${
                                        isSelected
                                            ? 'bg-brand-50/60 border-brand-200'
                                            : 'bg-white border-ink-200 hover:bg-ink-50'
                                    }`}
                                >
                                    <label
                                        htmlFor={`lab-${item.catalog_id}`}
                                        className="flex items-start gap-3 px-3 py-2.5 cursor-pointer"
                                    >
                                        <input
                                            id={`lab-${item.catalog_id}`}
                                            type="checkbox"
                                            checked={isSelected}
                                            onChange={() => toggle(item.catalog_id)}
                                            aria-label={`Order ${item.test_name}`}
                                            className="mt-0.5 w-4 h-4 accent-brand-600 cursor-pointer"
                                        />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium text-ink-900 truncate">{item.test_name}</p>
                                            <p className="text-xs text-ink-500 mt-0.5 truncate">
                                                {item.specimen_type || 'Unknown specimen'}
                                                {item.base_price !== undefined && item.base_price !== null
                                                    ? ` · KES ${Number(item.base_price).toLocaleString('en-KE')}`
                                                    : ''}
                                            </p>
                                        </div>
                                    </label>
                                    {isSelected && (
                                        <div className="px-3 pb-3 grid grid-cols-1 sm:grid-cols-3 gap-2">
                                            <label className="sm:col-span-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600">
                                                Priority
                                                <select
                                                    value={state.priority}
                                                    onChange={e => updateField(item.catalog_id, 'priority', e.target.value)}
                                                    className="mt-1 w-full bg-white border border-ink-200 rounded-md px-2 py-1.5 text-xs text-ink-900 normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                                >
                                                    {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                                                </select>
                                            </label>
                                            <label className="sm:col-span-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600">
                                                Clinical notes (optional)
                                                <input
                                                    type="text"
                                                    value={state.clinical_notes}
                                                    onChange={e => updateField(item.catalog_id, 'clinical_notes', e.target.value)}
                                                    placeholder="e.g. fasting since 8pm yesterday"
                                                    className="mt-1 w-full bg-white border border-ink-200 rounded-md px-2 py-1.5 text-xs text-ink-900 normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                                />
                                            </label>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 bg-ink-50 flex flex-col-reverse sm:flex-row sm:justify-between sm:items-center gap-2 shrink-0">
                    <p className="text-xs text-ink-600">
                        <span className="font-semibold text-ink-900">{selectedItems.length}</span> test{selectedItems.length === 1 ? '' : 's'} selected
                    </p>
                    <div className="flex gap-2">
                        <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                        <button
                            type="button"
                            onClick={submit}
                            disabled={submitting || selectedItems.length === 0}
                            className="btn-primary disabled:opacity-50 cursor-pointer"
                        >
                            {submitting
                                ? <><Activity size={15} className="animate-spin" aria-hidden="true" /> Submitting…</>
                                : <><Send size={15} aria-hidden="true" /> Place order</>}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Imaging (radiology) order modal.                                          */
/*                                                                            */
/*  One exam per order. Doctor picks from the catalog (or types a free-text   */
/*  exam name when the catalog doesn't have it), supplies clinical notes      */
/*  and priority, then POST /radiology/.                                      */
/* ────────────────────────────────────────────────────────────────────────── */
function ImagingOrderModal({ patient, onClose }) {
    const [catalog, setCatalog] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [pickedId, setPickedId] = useState(null);   // catalog_id of selected exam
    const [customName, setCustomName] = useState(''); // free-text exam when no catalog
    const [clinicalNotes, setClinicalNotes] = useState('');
    const [priority, setPriority] = useState('Routine');
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get('/radiology/catalog?active_only=true');
                setCatalog(res.data || []);
            } catch (e) {
                toast.error(e.response?.data?.detail || 'Failed to load imaging catalog.');
            } finally {
                setIsLoading(false);
            }
        })();
    }, []);

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase();
        if (!needle) return catalog;
        return catalog.filter(c =>
            c.exam_name?.toLowerCase().includes(needle)
            || c.modality?.toLowerCase().includes(needle)
        );
    }, [catalog, search]);

    const submit = async () => {
        if (!pickedId && !customName.trim()) {
            toast.error('Pick an exam from the catalog or enter a custom exam name.');
            return;
        }
        setSubmitting(true);
        try {
            const body = {
                patient_id: patient.patient_id,
                catalog_id: pickedId,
                exam_type: pickedId ? null : customName.trim(),
                clinical_notes: clinicalNotes || null,
                priority,
            };
            await apiClient.post('/radiology/', body);
            toast.success('Imaging order placed.');
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to create imaging order.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="imaging-order-title"
        >
            <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-2xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 bg-ink-50 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">New imaging order</p>
                        <h2 id="imaging-order-title" className="text-base sm:text-lg font-semibold text-ink-900 tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
                    {/* Catalog picker */}
                    <div>
                        <label htmlFor="img-search" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">Catalogue</label>
                        <div className="relative mt-1.5">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                            <input
                                id="img-search"
                                type="search"
                                placeholder="Search by exam name or modality…"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full bg-white border border-ink-200 rounded-lg pl-9 pr-3 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                        <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-ink-200 custom-scrollbar">
                            {isLoading ? (
                                <div className="p-4 text-center text-ink-500 text-sm">
                                    <Activity className="animate-spin inline mr-2 text-brand-600" size={16} aria-hidden="true" /> Loading…
                                </div>
                            ) : filtered.length === 0 ? (
                                <p className="p-4 text-center text-ink-500 text-sm">No exams match.</p>
                            ) : (
                                <ul className="divide-y divide-ink-100">
                                    {filtered.map(item => {
                                        const isPicked = pickedId === item.catalog_id;
                                        return (
                                            <li key={item.catalog_id}>
                                                <button
                                                    type="button"
                                                    onClick={() => { setPickedId(item.catalog_id); setCustomName(''); }}
                                                    aria-pressed={isPicked}
                                                    className={`w-full text-left px-3 py-2 transition-colors cursor-pointer ${
                                                        isPicked ? 'bg-brand-50' : 'hover:bg-ink-50'
                                                    }`}
                                                >
                                                    <div className="flex items-center justify-between gap-2">
                                                        <span className="text-sm font-medium text-ink-900 truncate">{item.exam_name}</span>
                                                        {isPicked && <CheckCircle2 size={14} className="text-brand-700 shrink-0" aria-hidden="true" />}
                                                    </div>
                                                    <div className="text-xs text-ink-500 mt-0.5">
                                                        {item.modality || 'Unknown modality'}
                                                        {item.base_price !== undefined && item.base_price !== null
                                                            ? ` · KES ${Number(item.base_price).toLocaleString('en-KE')}`
                                                            : ''}
                                                    </div>
                                                </button>
                                            </li>
                                        );
                                    })}
                                </ul>
                            )}
                        </div>
                    </div>

                    {/* Custom exam fallback */}
                    <div>
                        <label htmlFor="img-custom" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">
                            Or custom exam (when not in catalog)
                        </label>
                        <input
                            id="img-custom"
                            type="text"
                            value={customName}
                            onChange={e => { setCustomName(e.target.value); if (e.target.value) setPickedId(null); }}
                            placeholder="e.g. X-Ray Right Wrist AP/Lat"
                            className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                        />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <label className="sm:col-span-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">
                            Priority
                            <select
                                value={priority}
                                onChange={e => setPriority(e.target.value)}
                                className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            >
                                {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                            </select>
                        </label>
                        <label className="sm:col-span-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">
                            Clinical notes
                            <textarea
                                value={clinicalNotes}
                                onChange={e => setClinicalNotes(e.target.value)}
                                rows="2"
                                placeholder="Clinical question, indication, or area of interest"
                                className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 resize-none"
                            />
                        </label>
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 bg-ink-50 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button
                        type="button"
                        onClick={submit}
                        disabled={submitting || (!pickedId && !customName.trim())}
                        className="btn-primary disabled:opacity-50 cursor-pointer"
                    >
                        {submitting
                            ? <><Activity size={15} className="animate-spin" aria-hidden="true" /> Submitting…</>
                            : <><Send size={15} aria-hidden="true" /> Place imaging order</>}
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Follow-up booking modal.                                                  */
/*                                                                            */
/*  POSTs to /appointments/. Pre-fills the doctor from /appointments/doctors. */
/*  Quick-pick chips for +1 week, +2 weeks, +1 month so the most common       */
/*  follow-up cadences are one click. Surfaces existing bookings for that     */
/*  doctor on the picked date so the user can avoid double-booking.           */
/* ────────────────────────────────────────────────────────────────────────── */

const QUICK_PICKS = [
    { label: '+1 week',   add: { weeks: 1 } },
    { label: '+2 weeks',  add: { weeks: 2 } },
    { label: '+1 month',  add: { months: 1 } },
    { label: '+3 months', add: { months: 3 } },
];

const addToDate = (base, { weeks = 0, months = 0 }) => {
    const d = new Date(base);
    if (weeks)  d.setDate(d.getDate() + weeks * 7);
    if (months) d.setMonth(d.getMonth() + months);
    return d;
};

const toDateInput = (d) => {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

function FollowUpModal({ patient, existing, onClose, onBooked }) {
    const [doctors, setDoctors] = useState([]);
    const [isLoadingDoctors, setIsLoadingDoctors] = useState(true);
    const [doctorId, setDoctorId] = useState(existing?.doctor_id ? String(existing.doctor_id) : '');
    const initial = existing?.appointment_date
        ? new Date(existing.appointment_date)
        : addToDate(new Date(), { weeks: 1 });
    const [date, setDate] = useState(toDateInput(initial));
    const [time, setTime] = useState(() => {
        const pad = (n) => String(n).padStart(2, '0');
        const hours = initial.getHours() || 9;
        const minutes = Math.floor((initial.getMinutes() || 0) / 30) * 30;
        return `${pad(hours)}:${pad(minutes)}`;
    });
    const [notes, setNotes] = useState(existing?.notes || 'Follow-up consultation');
    const [bookings, setBookings] = useState([]);
    const [busy, setBusy] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const res = await apiClient.get('/appointments/doctors');
                setDoctors(res.data || []);
                if (!doctorId && res.data?.length) {
                    setDoctorId(String(res.data[0].user_id));
                }
            } catch (e) {
                toast.error(e.response?.data?.detail || 'Failed to load doctors.');
            } finally {
                setIsLoadingDoctors(false);
            }
        })();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (!doctorId || !date) return;
        let cancelled = false;
        setBusy(true);
        apiClient.get('/appointments/availability', { params: { doctor_id: doctorId, date } })
            .then(res => { if (!cancelled) setBookings(res.data?.bookings || []); })
            .catch(() => { if (!cancelled) setBookings([]); })
            .finally(() => { if (!cancelled) setBusy(false); });
        return () => { cancelled = true; };
    }, [doctorId, date]);

    const bookingTimes = useMemo(() => new Set(
        bookings.map(b => {
            if (!b.appointment_date) return null;
            const d = new Date(b.appointment_date);
            const pad = (n) => String(n).padStart(2, '0');
            return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
        }).filter(Boolean)
    ), [bookings]);

    const applyQuickPick = (offset) => {
        const next = addToDate(new Date(), offset);
        setDate(toDateInput(next));
    };

    const submit = async () => {
        if (!doctorId) { toast.error('Pick a doctor.'); return; }
        if (!date || !time) { toast.error('Pick a date and time.'); return; }
        if (bookingTimes.has(time)) {
            toast.error('That slot is already booked for the selected doctor.');
            return;
        }
        setSubmitting(true);
        try {
            const iso = new Date(`${date}T${time}:00`).toISOString();
            const res = await apiClient.post('/appointments/', {
                patient_id: patient.patient_id,
                doctor_id:  parseInt(doctorId, 10),
                appointment_date: iso,
                notes: notes || null,
            });
            toast.success(`Follow-up booked for ${new Date(res.data.appointment_date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}.`);
            onBooked(res.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to book follow-up.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="followup-title"
        >
            <div className="bg-white border border-ink-200 rounded-2xl shadow-elevated w-full max-w-xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 bg-ink-50 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Schedule follow-up</p>
                        <h2 id="followup-title" className="text-base sm:text-lg font-semibold text-ink-900 tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 mb-1.5">Common cadences</p>
                        <div className="flex flex-wrap gap-1.5">
                            {QUICK_PICKS.map(q => (
                                <button
                                    key={q.label}
                                    type="button"
                                    onClick={() => applyQuickPick(q.add)}
                                    className="inline-flex items-center px-2.5 py-1.5 rounded-md text-2xs font-semibold bg-brand-50 text-brand-700 border border-brand-200 hover:bg-brand-100 cursor-pointer"
                                >
                                    {q.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label htmlFor="fu-doctor" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">Doctor</label>
                        <select
                            id="fu-doctor"
                            value={doctorId}
                            onChange={e => setDoctorId(e.target.value)}
                            disabled={isLoadingDoctors}
                            className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                        >
                            {isLoadingDoctors ? (
                                <option>Loading doctors…</option>
                            ) : doctors.length === 0 ? (
                                <option value="">No doctors available</option>
                            ) : (
                                doctors.map(d => (
                                    <option key={d.user_id} value={d.user_id}>
                                        {d.full_name}{d.specialization ? ` — ${d.specialization}` : ''}
                                    </option>
                                ))
                            )}
                        </select>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="fu-date" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">Date</label>
                            <input
                                id="fu-date"
                                type="date"
                                value={date}
                                onChange={e => setDate(e.target.value)}
                                min={toDateInput(new Date())}
                                className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                        <div>
                            <label htmlFor="fu-time" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">Time</label>
                            <input
                                id="fu-time"
                                type="time"
                                value={time}
                                onChange={e => setTime(e.target.value)}
                                step={60 * 30}
                                className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                    </div>

                    <div className="rounded-lg border border-ink-200 bg-ink-50/40">
                        <div className="px-3 py-2 border-b border-ink-200 flex items-center justify-between text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600">
                            <span>Doctor's bookings on {date || '—'}</span>
                            {busy && <Activity size={12} className="animate-spin text-brand-600" aria-hidden="true" />}
                        </div>
                        {bookings.length === 0 ? (
                            <p className="px-3 py-3 text-xs text-ink-500">No appointments yet for this day.</p>
                        ) : (
                            <ul className="divide-y divide-ink-100 max-h-32 overflow-y-auto">
                                {bookings.map(b => {
                                    const d = b.appointment_date ? new Date(b.appointment_date) : null;
                                    const pad = (n) => String(n).padStart(2, '0');
                                    const slot = d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : '—';
                                    const isYou = b.patient_id === patient.patient_id;
                                    return (
                                        <li key={b.appointment_id} className="px-3 py-1.5 flex items-center justify-between gap-2 text-xs">
                                            <span className={`font-mono ${time === slot ? 'text-rose-700 font-semibold' : 'text-ink-700'}`}>{slot}</span>
                                            <span className={isYou ? 'text-brand-700 italic' : 'text-ink-500'}>
                                                {isYou ? 'this patient' : `patient #${b.patient_id}`} · {b.status}
                                            </span>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>

                    <div>
                        <label htmlFor="fu-notes" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700">Notes</label>
                        <textarea
                            id="fu-notes"
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            rows="2"
                            placeholder="What should this follow-up review?"
                            className="mt-1.5 w-full bg-white border border-ink-200 rounded-lg px-3 py-2 text-sm text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 resize-none"
                        />
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 bg-ink-50 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button
                        type="button"
                        onClick={submit}
                        disabled={submitting}
                        className="btn-primary disabled:opacity-50 cursor-pointer"
                    >
                        {submitting
                            ? <><Activity size={15} className="animate-spin" aria-hidden="true" /> Booking…</>
                            : <><CalendarPlus size={15} aria-hidden="true" /> Book follow-up</>}
                    </button>
                </div>
            </div>
        </div>
    );
}