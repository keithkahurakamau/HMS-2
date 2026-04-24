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
        <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
            
            {/* TOP PANEL: Collapsible Queue (Unchanged) */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm shrink-0 flex flex-col z-30">
                <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-slate-50 hover:bg-brand-50 transition-colors rounded-t-xl focus:outline-none">
                    <div className="flex items-center gap-3">
                        <Users className="text-brand-600" size={20} />
                        <h2 className="font-bold text-slate-800 text-lg">Active Queue</h2>
                        <span className="bg-brand-100 text-brand-700 text-xs font-bold px-2.5 py-1 rounded-full">{queue.length} Waiting</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                        {isQueueOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                    </div>
                </button>

                {isQueueOpen && (
                    <div className="border-t border-slate-100 p-4 bg-white rounded-b-xl">
                        {isLoadingQueue ? (
                            <div className="text-center py-6 text-slate-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={24} /> Loading queue...</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-slate-400">No patients currently waiting in your queue.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((item) => (
                                    <div key={item.queue_id} onClick={() => handlePatientSelect(item)} className={`p-3 rounded-lg border cursor-pointer transition-all ${activePatient?.queue_id === item.queue_id ? 'bg-brand-50 border-brand-500 shadow-sm ring-1 ring-brand-500' : 'bg-white hover:border-brand-300'}`}>
                                        <div className="flex justify-between items-start mb-2">
                                            <h3 className="font-semibold text-sm text-slate-900">{item.patient_name}</h3>
                                            {item.priority === 'High' && <AlertCircle size={14} className="text-red-500 animate-pulse" />}
                                        </div>
                                        <div className="flex justify-between items-center text-xs text-slate-500">
                                            <span className="font-medium">{item.outpatient_no}</span>
                                            <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600 flex items-center gap-1"><Clock size={10} /> {item.triage_time}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* BOTTOM PANEL: Consultation Workspace */}
            <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col z-10 relative">
                {!activePatient ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 bg-slate-50/50">
                        <Stethoscope size={64} className="mb-4 text-slate-300" strokeWidth={1.5} />
                        <h3 className="text-lg font-semibold text-slate-600 mb-1">Doctor's Workspace</h3>
                        <p className="text-sm">Select a patient from the queue to begin charting.</p>
                    </div>
                ) : (
                    <>
                        <div className="shrink-0 flex flex-col">
                            <div className="p-4 border-b border-slate-200 bg-white flex justify-between items-center shadow-[0_2px_4px_rgba(0,0,0,0.02)] z-10">
                                <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 bg-brand-100 text-brand-700 rounded-full flex items-center justify-center font-bold text-lg border border-brand-200">
                                        {activePatient.patient_name?.charAt(0) || 'P'}
                                    </div>
                                    <div>
                                        <h1 className="text-xl font-bold text-slate-900">{activePatient.patient_name}</h1>
                                        <p className="text-sm font-medium text-slate-500">{activePatient.outpatient_no} • {activePatient.age} yrs • {activePatient.gender}</p>
                                    </div>
                                </div>
                                {activePatient.allergies && activePatient.allergies.toLowerCase() !== 'none' && (
                                    <div className="bg-red-50 border border-red-200 px-4 py-2 rounded-lg flex items-center gap-2">
                                        <AlertCircle size={18} className="text-red-600" />
                                        <div>
                                            <p className="text-xs font-bold text-red-800 uppercase tracking-wider">Known Allergies</p>
                                            <p className="text-sm font-medium text-red-600">{activePatient.allergies}</p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Unimplemented Modules Toolbar */}
                            <div className="bg-slate-50 border-b border-slate-200 p-2 flex gap-2 overflow-x-auto custom-scrollbar">
                                <button onClick={() => handleNotImplemented('Medical History')} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-md text-xs font-semibold hover:border-brand-300 hover:text-brand-600 transition-colors"><History size={14}/> Medical Hx</button>
                                <button onClick={() => handleNotImplemented('Surgical History')} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-md text-xs font-semibold hover:border-brand-300 hover:text-brand-600 transition-colors"><Scissors size={14}/> Surgical Hx</button>
                                <button onClick={() => handleNotImplemented('Social History')} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-md text-xs font-semibold hover:border-brand-300 hover:text-brand-600 transition-colors"><Cigarette size={14}/> Social Hx</button>
                                <button onClick={() => handleNotImplemented('Family History')} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-md text-xs font-semibold hover:border-brand-300 hover:text-brand-600 transition-colors"><Dna size={14}/> Family Hx</button>
                                <button onClick={() => handleNotImplemented('Immunizations')} className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-600 rounded-md text-xs font-semibold hover:border-brand-300 hover:text-brand-600 transition-colors"><Syringe size={14}/> Immunizations</button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/50">
                            
                            {/* Vitals Entry */}
                            <div className="bg-white border-l-4 border-brand-500 rounded-r-xl border-y border-r border-slate-200 p-5 shadow-sm">
                                <div className="flex justify-between items-center mb-4 border-b border-slate-100 pb-2">
                                    <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2"><Activity size={18} className="text-brand-500"/> Vital Signs</h3>
                                    <button onClick={() => handleNotImplemented('Vitals Trends')} className="text-xs font-bold text-brand-600 hover:text-brand-800 flex items-center gap-1"><Activity size={14}/> View Trends</button>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">BP (mmHg)</label><input type="text" value={vitals.bp} onChange={(e) => setVitals({...vitals, bp: e.target.value})} placeholder="120/80" className="w-full px-3 py-2 border rounded-md text-sm" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">HR (bpm)</label><input type="number" value={vitals.hr} onChange={(e) => setVitals({...vitals, hr: e.target.value})} placeholder="72" className="w-full px-3 py-2 border rounded-md text-sm" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">Resp (bpm)</label><input type="number" value={vitals.rr} onChange={(e) => setVitals({...vitals, rr: e.target.value})} placeholder="16" className="w-full px-3 py-2 border rounded-md text-sm" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">Temp (°C)</label><input type="number" step="0.1" value={vitals.temp} onChange={(e) => setVitals({...vitals, temp: e.target.value})} placeholder="37.2" className="w-full px-3 py-2 border rounded-md text-sm" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">SpO2 (%)</label><input type="number" value={vitals.spo2} onChange={(e) => setVitals({...vitals, spo2: e.target.value})} placeholder="98" className="w-full px-3 py-2 border rounded-md text-sm" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">Weight (kg)</label><input type="number" value={vitals.weight} onChange={(e) => setVitals({...vitals, weight: e.target.value})} placeholder="70" className="w-full px-3 py-2 border rounded-md text-sm bg-brand-50" /></div>
                                    <div><label className="block text-xs font-semibold text-slate-500 mb-1">Height (cm)</label><input type="number" value={vitals.height} onChange={(e) => setVitals({...vitals, height: e.target.value})} placeholder="175" className="w-full px-3 py-2 border rounded-md text-sm bg-brand-50" /></div>
                                    <div><label className="block text-xs font-bold text-brand-600 mb-1">BMI</label><div className="w-full px-3 py-2 border border-brand-200 bg-brand-50 text-brand-800 font-bold rounded-md text-sm text-center">{calculateBMI()}</div></div>
                                </div>
                            </div>

                            {/* Clinical Documentation (SOAP) */}
                            <div className="bg-white border-l-4 border-slate-800 rounded-r-xl border-y border-r border-slate-200 p-5 shadow-sm space-y-5">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2 flex items-center gap-2"><FileText size={18} className="text-slate-600"/> Clinical Documentation</h3>
                                
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Chief Complaint (CC)</label><input type="text" value={clinicalNotes.cc} onChange={(e) => setClinicalNotes({...clinicalNotes, cc: e.target.value})} className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500" placeholder="e.g. Severe headache for 3 days" /></div>
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">History of Present Illness (HPI)</label><textarea rows="3" value={clinicalNotes.hpi} onChange={(e) => setClinicalNotes({...clinicalNotes, hpi: e.target.value})} className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500" placeholder="Narrative of the patient's symptoms..."></textarea></div>
                                <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Physical Examination (Objective)</label><textarea rows="3" value={clinicalNotes.objective} onChange={(e) => setClinicalNotes({...clinicalNotes, objective: e.target.value})} className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500" placeholder="Systematic findings..."></textarea></div>
                            </div>

                            {/* Orders & Prescriptions */}
                            <div className="bg-white border-l-4 border-brand-300 rounded-r-xl border-y border-r border-slate-200 p-5 shadow-sm space-y-5">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider border-b border-slate-100 pb-2 flex items-center gap-2"><Pill size={18} className="text-brand-500"/> Diagnosis & Orders</h3>
                                
                                <div className="relative">
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Final Diagnosis (ICD-10)</label>
                                    <input type="text" value={icdSearch} onChange={(e) => { setIcdSearch(e.target.value); setShowIcdDropdown(true); }} onFocus={() => setShowIcdDropdown(true)} className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500" placeholder="Type to search ICD-10 codes..." />
                                    {showIcdDropdown && icdSearch.length > 0 && (
                                        <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-xl max-h-48 overflow-y-auto">
                                            {filteredIcd.length > 0 ? filteredIcd.map((code, idx) => (<div key={idx} onClick={() => {setIcdSearch(code); setShowIcdDropdown(false);}} className="px-4 py-2 hover:bg-brand-50 text-sm cursor-pointer">{code}</div>)) : <div className="px-4 py-3 text-sm text-slate-500">No codes found.</div>}
                                        </div>
                                    )}
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="border border-slate-200 rounded-lg p-4">
                                        <h4 className="text-xs font-bold text-slate-700 mb-3 flex items-center gap-2"><TestTube size={14}/> Investigations</h4>
                                        <div className="flex gap-2">
                                            <button onClick={() => handleNotImplemented('Lab Ordering Modal')} className="flex-1 text-xs font-bold py-2 bg-slate-50 border border-slate-200 rounded hover:bg-brand-50 hover:text-brand-700 hover:border-brand-300 transition-colors">+ Order Lab Tests</button>
                                            <button onClick={() => handleNotImplemented('Radiology Ordering')} className="flex-1 text-xs font-bold py-2 bg-slate-50 border border-slate-200 rounded hover:bg-brand-50 hover:text-brand-700 hover:border-brand-300 transition-colors">+ Order Imaging</button>
                                        </div>
                                    </div>
                                    <div className="border border-slate-200 rounded-lg p-4 bg-brand-50/30">
                                        <h4 className="text-xs font-bold text-brand-800 mb-3 flex items-center justify-between">
                                            <span className="flex items-center gap-2"><Pill size={14}/> Medications</span>
                                        </h4>
                                        {/* What is typed here is routed directly to the Pharmacy queue! */}
                                        <textarea rows="2" value={clinicalNotes.plan} onChange={(e) => setClinicalNotes({...clinicalNotes, plan: e.target.value})} className="w-full px-3 py-2 border border-slate-200 rounded text-sm focus:ring-2 focus:ring-brand-500" placeholder="Enter prescription instructions to send to Pharmacy..."></textarea>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div><label className="block text-xs font-bold text-slate-700 mb-1.5">Internal Notes (Nursing/Ward)</label><input type="text" value={clinicalNotes.internal_notes} onChange={(e) => setClinicalNotes({...clinicalNotes, internal_notes: e.target.value})} className="w-full px-4 py-2 border border-slate-200 rounded-lg text-sm" placeholder="e.g. Please administer stat dose before discharge" /></div>
                                    <div><label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center gap-1"><CalendarPlus size={14}/> Next Follow-Up</label><button onClick={() => handleNotImplemented('Scheduling')} className="w-full px-4 py-2 text-left bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-400">Select date...</button></div>
                                </div>
                            </div>
                        </div>

                        {/* WIRED FOOTER ACTIONS */}
                        <div className="p-4 border-t border-slate-200 bg-slate-50 flex flex-wrap justify-between items-center shrink-0 z-10 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)]">
                            <div className="flex gap-2">
                                <button onClick={() => handleClinicalSubmit('Draft')} disabled={isSubmitting} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-semibold hover:bg-slate-100 flex items-center gap-2"><Save size={16}/> Save Draft</button>
                                <button onClick={() => handleNotImplemented('External Referrals')} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg text-sm font-semibold hover:bg-brand-50 hover:text-brand-700 hover:border-brand-300 flex items-center gap-2"><ArrowRightLeft size={16}/> Refer Patient</button>
                            </div>
                            
                            <div className="flex gap-2 mt-2 sm:mt-0">
                                <button onClick={() => handleNotImplemented('Billing Integration')} className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                    <Receipt size={16}/> Send to Billing
                                </button>
                                {/* 🚨 Crucial Action: This routes the record directly to the Pharmacy Component! */}
                                <button onClick={() => handleClinicalSubmit('Pharmacy')} disabled={isSubmitting} className="px-4 py-2 bg-accent-600 hover:bg-accent-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                    <Pill size={16}/> Forward to Pharmacy
                                </button>
                                <button onClick={() => handleClinicalSubmit('Completed')} disabled={isSubmitting} className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                    <FileSignature size={16}/> Finalize & Sign
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}