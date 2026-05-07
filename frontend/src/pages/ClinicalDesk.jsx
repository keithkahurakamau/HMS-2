import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
    Search, User, Activity, FileText, Pill, CheckCircle2, AlertCircle, Clock, 
    ChevronDown, ChevronUp, Users, Send, Stethoscope, TestTube, ArrowRightLeft,
    History, Scissors, Cigarette, Dna, Syringe, CalendarPlus, FileSignature, Save, Receipt, Variable
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function ClinicalDesk() {
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

                            {/* History toolbar */}
                            <div className="bg-ink-50/40 border-b border-ink-100 p-2 flex gap-1.5 overflow-x-auto custom-scrollbar">
                                {[
                                    { icon: History, label: 'Medical Hx',    name: 'Medical History' },
                                    { icon: Scissors, label: 'Surgical Hx',  name: 'Surgical History' },
                                    { icon: Cigarette, label: 'Social Hx',   name: 'Social History' },
                                    { icon: Dna, label: 'Family Hx',         name: 'Family History' },
                                    { icon: Syringe, label: 'Immunizations', name: 'Immunizations' },
                                ].map(({ icon: Icon, label, name }) => (
                                    <button key={label} onClick={() => handleNotImplemented(name)} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-ink-200 text-ink-600 rounded-lg text-xs font-medium hover:border-brand-300 hover:text-brand-700 transition-colors">
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
                                            <button onClick={() => handleNotImplemented('Lab Ordering Modal')} className="btn-secondary flex-1 py-2 text-xs">+ Order Lab Tests</button>
                                            <button onClick={() => handleNotImplemented('Radiology Ordering')} className="btn-secondary flex-1 py-2 text-xs">+ Order Imaging</button>
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-accent-200 bg-accent-50/40 p-4">
                                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-accent-700 mb-3 flex items-center gap-2"><Pill size={13} /> Medications (routed to Pharmacy)</h4>
                                        <textarea rows="2" value={clinicalNotes.plan} onChange={(e) => setClinicalNotes({...clinicalNotes, plan: e.target.value})} className="input resize-none" placeholder="Enter prescription instructions to send to Pharmacy…"></textarea>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div><label className="label">Internal notes (nursing / ward)</label><input type="text" value={clinicalNotes.internal_notes} onChange={(e) => setClinicalNotes({...clinicalNotes, internal_notes: e.target.value})} className="input" placeholder="e.g. Please administer stat dose before discharge" /></div>
                                    <div><label className="label flex items-center gap-1"><CalendarPlus size={13} /> Next follow-up</label><button onClick={() => handleNotImplemented('Scheduling')} className="input text-left text-ink-400">Select date…</button></div>
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
                                <button onClick={() => handleNotImplemented('Billing Integration')} className="btn-secondary text-brand-700 border-brand-200 hover:bg-brand-50">
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
        </div>
    );
}