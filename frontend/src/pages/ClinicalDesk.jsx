import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Search, User, Activity, FileText, Pill, CheckCircle2, AlertCircle, Clock,
    ChevronDown, ChevronUp, Users, Send, Stethoscope, TestTube, ArrowRightLeft,
    History, Scissors, Cigarette, Dna, Syringe, CalendarPlus, FileSignature, Save, Receipt, Variable,
    X, Image as ImageIcon, Plus, Minus, ShieldCheck, CalendarX, UserMinus, Trash2,
} from 'lucide-react';
import toast from 'react-hot-toast';
import PageHeader from '../components/PageHeader';
import IcdDiagnosisPicker from '../components/IcdDiagnosisPicker';
import ReferralModal from '../components/ReferralModal';
import VitalsTrendsModal from '../components/VitalsTrendsModal';
import { buildDiagnosisFields } from '../utils/diagnosisMapping';
import { useActivePatient } from '../context/PatientContext';

// Prescription pick-lists — kept at module scope so the dropdowns are stable.
const FORMULATIONS = ["Tablet", "Capsule", "Syrup", "Suspension", "Injection", "Cream / Ointment", "Drops", "Inhaler", "Suppository", "Other"];
const FREQUENCIES = ["OD (once daily)", "BD (twice daily)", "TDS (three times daily)", "QDS (four times daily)", "PRN (as needed)", "STAT (immediately)", "Nocte (at night)"];
const blankMed = () => ({ _uid: crypto.randomUUID(), drug: '', formulation: 'Tablet', dosage: '', frequency: '', duration: '' });

// Split a stored chief-complaint string back into discrete complaints. Newer
// records join with "; "; older free-text ones become a single complaint.
const splitComplaints = (s) => (s || '').split(/\s*;\s*|\n+/).flatMap((c) => { const t = c.trim(); return t ? [t] : []; });

export default function ClinicalDesk() {
    const navigate = useNavigate();
    // --- DYNAMIC QUEUE STATE ---
    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [activePatient, setActivePatient] = useState(null);
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isClosingClinic, setIsClosingClinic] = useState(false);

    // --- FORM STATE ---
    const [vitals, setVitals] = useState({ weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', glucose: '' });
    const [clinicalNotes, setClinicalNotes] = useState({ hpi: '', diagnosis: '', internal_notes: '' });
    // Chief complaint is now a list — a patient can present with several.
    const [complaints, setComplaints] = useState([]);
    const [complaintInput, setComplaintInput] = useState('');
    // Physical examination is a list too — one entry per system/finding
    // (e.g. "Chest: clear air entry bilaterally"). Persists "; "-joined in
    // physical_examination, same convention as chief complaints.
    const [physicalExams, setPhysicalExams] = useState([]);
    const [examInput, setExamInput] = useState('');
    // Structured, numbered prescription rows routed to Pharmacy.
    const [medications, setMedications] = useState([]);
    // Multi-diagnosis chips — [{code, description}] for catalogue picks or
    // {code: null, description, custom: true} for custom (note) diagnoses;
    // first entry is primary. Type-ahead against the ~74k-row CMS ICD-10-CM
    // catalogue lives in IcdDiagnosisPicker, which owns its own state.
    const [icdCodes, setIcdCodes] = useState([]);
    const [chargeConsultation, setChargeConsultation] = useState(false);
    // The logged-in doctor's own consultation fee (per-doctor price-list row
    // server-side). Null until loaded; the charge endpoint resolves the fee
    // server-side either way, so this only drives the display + editor.
    const [myFee, setMyFee] = useState(null);
    const [isFeeModalOpen, setIsFeeModalOpen] = useState(false);

    // --- LAB / IMAGING / FOLLOW-UP MODAL STATE ---
    const [isLabModalOpen, setIsLabModalOpen] = useState(false);
    const [isImagingModalOpen, setIsImagingModalOpen] = useState(false);
    const [isFollowUpOpen, setIsFollowUpOpen] = useState(false);
    const [isReferModalOpen, setIsReferModalOpen] = useState(false);
    const [isTrendsOpen, setIsTrendsOpen] = useState(false);
    // Holds the most recent appointment we booked from this consultation so
    // the doctor sees confirmation in-line and the button updates from
    // "Select date…" to the scheduled date/time.
    const [pendingFollowUp, setPendingFollowUp] = useState(null);

    // --- KDPA TREATMENT CONSENT MODAL ---
    // Doctors can record consent without leaving the desk, so the clinical
    // submit never trips the S.30 gate mid-encounter. Modal is local rather
    // than reused from Medical History because the flow here is one-shot
    // (Treatment type, current patient) and we want zero context switching.
    const [isConsentOpen, setIsConsentOpen] = useState(false);
    const [consentDraft, setConsentDraft] = useState({
        consent_method: 'Verbal',
        notes: '',
    });
    const [consentSubmitting, setConsentSubmitting] = useState(false);
    const [hasRecordedConsent, setHasRecordedConsent] = useState(false);

    // Cross-page active patient context (also drives the bar at the top of
    // every workspace page). We mirror the local `activePatient` state into
    // it so the rest of the system sees the doctor's current focus.
    const { setActivePatient: setGlobalActivePatient } = useActivePatient();

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchQueue();
        fetchMyFee();
    }, []);

    const fetchMyFee = async () => {
        try {
            const response = await apiClient.get('/billing/consultation-fee/me');
            setMyFee(response.data);
        } catch {
            // Non-blocking — the server still resolves the right fee at charge time.
        }
    };

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

    // Clears the doctor's workspace back to the empty state. Used when the
    // patient currently being charted is taken out of the queue.
    const clearWorkspace = () => {
        setActivePatient(null);
        setGlobalActivePatient(null);
    };

    // Remove a single patient from the queue without charting them — e.g. they
    // left before being seen. Soft-completes the queue entry server-side so the
    // visit stays in history but stops showing as "waiting".
    const handleRemoveFromQueue = async (item) => {
        if (!window.confirm(`Remove ${item.patient_name} from the queue? They will no longer appear as waiting.`)) return;
        try {
            await apiClient.patch(`/queue/${item.queue_id}/checkout`);
            toast.success(`${item.patient_name} removed from the queue.`);
            if (activePatient?.queue_id === item.queue_id) clearWorkspace();
            fetchQueue();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not remove patient from the queue.');
        }
    };

    // End-of-clinic-day checkout — clears every patient still waiting in the
    // Consultation queue so leftover, never-seen patients don't roll into
    // tomorrow's list.
    const handleEndClinicDay = async () => {
        if (!window.confirm(`End the clinic day? This checks out all ${queue.length} patient(s) still waiting in the consultation queue.`)) return;
        setIsClosingClinic(true);
        try {
            const res = await apiClient.post('/queue/end-of-day', { department: 'Consultation' });
            const n = res.data?.checked_out ?? 0;
            toast.success(n > 0
                ? `Clinic closed — ${n} patient(s) checked out of the queue.`
                : 'Clinic closed — the queue was already empty.');
            clearWorkspace();
            setIsQueueOpen(true);
            fetchQueue();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not close the clinic day.');
        } finally {
            setIsClosingClinic(false);
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
        setVitals({ weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', glucose: '' });
        setClinicalNotes({ hpi: '', diagnosis: '', internal_notes: '' });
        setComplaints([]);
        setComplaintInput('');
        setPhysicalExams([]);
        setExamInput('');
        setMedications([]);
        setIcdCodes([]);
        // Pre-fill from the nurse's triage so the doctor doesn't re-key vitals.
        // Fire-and-forget — a missing/absent triage just leaves the form blank.
        prefillFromTriage(patientItem.patient_id);
        // Default to ON — a consultation that ends at "Send to billing" with
        // no fee posts no invoice and the patient never surfaces in the
        // cashier's queue, which is the most common bug report from
        // receptionists. Doctors who need to waive the fee can uncheck.
        setChargeConsultation(true);
        setPendingFollowUp(null);
        setHasRecordedConsent(false);
        setConsentDraft({ consent_method: 'Verbal', notes: '' });
    };

    // Pulls the most recent nurse triage for this patient and drops the vitals
    // straight into the encounter form. This is the payoff of the triage
    // module — the doctor opens the chart and the numbers are already there.
    const prefillFromTriage = async (patientId) => {
        if (!patientId) return;
        try {
            const res = await apiClient.get(`/triage/patients/${patientId}/latest`);
            const t = res.data;
            if (!t) return; // never triaged — leave the form blank
            setVitals({
                weight: t.weight_kg ?? '',
                height: t.height_cm ?? '',
                bp: t.blood_pressure ?? '',
                hr: t.heart_rate ?? '',
                rr: t.respiratory_rate ?? '',
                temp: t.temperature ?? '',
                spo2: t.spo2 ?? '',
                glucose: t.blood_glucose ?? '',
            });
            if (t.chief_complaint) {
                setComplaints(splitComplaints(t.chief_complaint));
            }
            toast.success('Vitals pre-filled from triage.', { icon: '🩺' });
        } catch (err) {
            // Triage is a convenience prefill, not a hard dependency — stay quiet
            // on failure (e.g. doctor's role lacks triage:read on an old tenant).
        }
    };

    // --- ACTION HANDLERS ---
    // --- CHIEF COMPLAINT (multi-entry) ---
    const addComplaint = () => {
        const value = complaintInput.trim();
        if (!value) return;
        // Skip case-insensitive duplicates so the list stays clean.
        if (complaints.some((c) => c.toLowerCase() === value.toLowerCase())) {
            setComplaintInput('');
            return;
        }
        setComplaints((prev) => [...prev, value]);
        setComplaintInput('');
    };
    const removeComplaint = (idx) => setComplaints((prev) => prev.filter((_, i) => i !== idx));

    // --- PHYSICAL EXAMINATION (multi-entry) ---
    const addExam = () => {
        const value = examInput.trim();
        if (!value) return;
        if (physicalExams.some((c) => c.toLowerCase() === value.toLowerCase())) {
            setExamInput('');
            return;
        }
        setPhysicalExams((prev) => [...prev, value]);
        setExamInput('');
    };
    const removeExam = (idx) => setPhysicalExams((prev) => prev.filter((_, i) => i !== idx));

    // --- MEDICATIONS (structured, numbered) ---
    const addMedication = () => setMedications((prev) => [...prev, blankMed()]);
    const updateMedication = (idx, field, value) =>
        setMedications((prev) => prev.map((m, i) => (i === idx ? { ...m, [field]: value } : m)));
    const removeMedication = (idx) => setMedications((prev) => prev.filter((_, i) => i !== idx));

    // Per-target validation. Returns an error message or null. We branch on
    // targetStatus so a doctor doesn't accidentally:
    //   - finalize an empty encounter (no diagnosis / no chief complaint)
    //   - forward a blank prescription to Pharmacy
    //   - send a patient to Billing with no charges and no consultation fee,
    //     which would leave them invisible in the cashier's queue
    const validateForSubmit = (targetStatus) => {
        if (!activePatient) return 'Select a patient from the queue first.';
        if (targetStatus === 'Draft') return null;                    // drafts are intentionally permissive
        const hasDx = ((clinicalNotes.diagnosis || '').trim().length > 0) || icdCodes.length > 0;
        const hasCc = complaints.length > 0;
        if (targetStatus === 'Pharmacy') {
            if (!medications.some((m) => m.drug.trim())) {
                return 'Add at least one medication (with a drug name) before forwarding to Pharmacy.';
            }
            if (!hasDx && !hasCc) {
                return 'Record at least a chief complaint or diagnosis before forwarding to Pharmacy.';
            }
        }
        if (targetStatus === 'Billed') {
            // Billing queue is populated by Pending invoices. With no
            // consultation fee and no other line items, the patient would
            // never surface there. Require either the fee or an explicit
            // ack the doctor knows another bill already exists.
            if (!chargeConsultation) {
                return 'Re-enable the consultation fee, or charge a service from Billing — otherwise the cashier won\'t see this patient.';
            }
            if (!hasDx && !hasCc) {
                return 'Record at least a chief complaint or diagnosis before billing.';
            }
        }
        if (targetStatus === 'Completed') {
            if (!hasDx && !hasCc) {
                return 'Finalising requires at least a chief complaint or diagnosis.';
            }
        }
        return null;
    };

    const handleClinicalSubmit = async (targetStatus) => {
        const validationError = validateForSubmit(targetStatus);
        if (validationError) {
            toast.error(validationError);
            return;
        }
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
            blood_glucose: vitals.glucose ? parseFloat(vitals.glucose) : null,

            // Clinical Notes — multiple complaints persist as a single
            // "; "-joined string (no schema change); splitComplaints() reverses it.
            chief_complaint: complaints.join('; '),
            history_of_present_illness: clinicalNotes.hpi,
            physical_examination: physicalExams.join('; '),
            // Catalogue codes → icd10_code; custom (note) entries + the
            // free-text field → diagnosis. See utils/diagnosisMapping.js.
            ...buildDiagnosisFields(icdCodes, clinicalNotes.diagnosis),
            // Structured prescriptions serialise to JSON in treatment_plan —
            // this is what the Pharmacy queue parses back into rows.
            treatment_plan: medications.some((m) => m.drug.trim())
                ? JSON.stringify(medications.filter((m) => m.drug.trim()).map(({ _uid, ...m }) => m))
                : null,
            internal_notes: clinicalNotes.internal_notes
        };

        try {
            await apiClient.post('/clinical/submit', payload);

            // Consultation fee posts on Billed/Pharmacy/Completed only — never
            // on Draft. For Pharmacy + Completed the checkbox still gates it
            // (a follow-up encounter might not warrant a new fee). For Billed
            // the validator already forced the checkbox on, so this branch
            // posts unconditionally for that path.
            if (chargeConsultation && targetStatus !== 'Draft') {
                // No amount sent — the server bills the doctor's own saved fee.
                await apiClient.post('/billing/consultation-fee', {
                    patient_id: activePatient.patient_id
                });
            }

            if (targetStatus === 'Pharmacy') toast.success('Record saved and routed to Pharmacy.');
            else if (targetStatus === 'Billed') toast.success('Record saved — patient is now in the Billing queue.');
            else if (targetStatus === 'Draft') toast.success('Draft saved.');
            else toast.success('Consultation finalised and signed.');

            // If not a draft, clear the workspace and refresh the queue
            if (targetStatus !== 'Draft') {
                setActivePatient(null);
                setIsQueueOpen(true);
                fetchQueue();
            }
        } catch (error) {
            const detail = error.response?.data?.detail || 'Failed to save clinical record.';
            // Friendlier message when the KDPA S.30 gate fires server-side
            // (means no active Treatment consent on file for the patient).
            if (typeof detail === 'string' && /consent/i.test(detail)) {
                toast.error('No active Treatment consent on file — click "Record consent" first.');
            } else {
                toast.error(detail);
            }
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleConsentSubmit = async () => {
        if (!activePatient) return;
        setConsentSubmitting(true);
        try {
            await apiClient.post('/medical-history/consent', {
                patient_id: activePatient.patient_id,
                consent_type: 'Treatment',
                consent_given: true,
                consent_method: consentDraft.consent_method,
                notes: consentDraft.notes || null,
            });
            toast.success('Treatment consent recorded.');
            setHasRecordedConsent(true);
            setIsConsentOpen(false);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to record consent.');
        } finally {
            setConsentSubmitting(false);
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
            <div data-tour="clinical-queue" className="card shrink-0 flex flex-col z-20">
                <div className="w-full p-4 flex justify-between items-center gap-3 bg-ink-50/60 dark:bg-ink-800/40 rounded-t-2xl">
                    <button type="button" onClick={() => setIsQueueOpen(!isQueueOpen)} className="flex items-center gap-3 min-w-0 hover:opacity-80 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/30 rounded-lg">
                        <Users className="text-brand-600 dark:text-brand-400 shrink-0" size={18} />
                        <h2 className="font-semibold text-ink-900 dark:text-white text-base tracking-tight">Active Queue</h2>
                        <span className="badge-brand">{queue.length} Waiting</span>
                        <span className="text-ink-500 dark:text-ink-400">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                    </button>
                    {queue.length > 0 && (
                        <button
                            type="button"
                            onClick={handleEndClinicDay}
                            disabled={isClosingClinic}
                            title="Check out every patient still waiting in the consultation queue"
                            className="btn-secondary btn-xs gap-1.5 shrink-0"
                        >
                            {isClosingClinic ? <Activity className="animate-spin" size={13} /> : <CalendarX size={13} />}
                            <span className="hidden sm:inline">End clinic day</span>
                        </button>
                    )}
                </div>

                {isQueueOpen && (
                    <div className="border-t border-ink-100 dark:border-ink-800 p-4 bg-white dark:bg-ink-900 rounded-b-2xl">
                        {isLoadingQueue ? (
                            <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading queue&hellip;</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-ink-400">No patients currently waiting in your queue.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((item) => (
                                    <div key={item.queue_id} className="relative group">
                                        <button type="button" onClick={() => handlePatientSelect(item)}
                                            className={`w-full text-left p-3 pr-8 rounded-xl border transition-all duration-150 ${activePatient?.queue_id === item.queue_id ? 'bg-brand-50/60 dark:bg-brand-500/15 border-brand-400 dark:border-brand-500/40 ring-2 ring-brand-500/15' : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:border-brand-300 dark:hover:border-brand-500/40 hover:-translate-y-0.5'}`}>
                                            <div className="flex justify-between items-start mb-2">
                                                <h3 className="font-semibold text-sm text-ink-900 dark:text-white">{item.patient_name}</h3>
                                                {item.priority === 'High' && <AlertCircle size={14} className="text-rose-500 animate-pulse-soft" />}
                                            </div>
                                            <div className="flex justify-between items-center text-xs text-ink-500 dark:text-ink-400">
                                                <span className="font-mono">{item.outpatient_no}</span>
                                                <span className="bg-ink-100 dark:bg-ink-800 px-2 py-0.5 rounded-full text-ink-600 dark:text-ink-300 flex items-center gap-1"><Clock size={10} /> {item.triage_time}</span>
                                            </div>
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveFromQueue(item)}
                                            aria-label={`Remove ${item.patient_name} from queue`}
                                            title="Remove from queue"
                                            className="absolute top-2 right-2 p-1 rounded-md text-ink-400 hover:text-rose-600 hover:bg-rose-50 dark:text-ink-500 dark:hover:text-rose-400 dark:hover:bg-rose-500/15 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity cursor-pointer"
                                        >
                                            <UserMinus size={14} />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* BOTTOM PANEL: Consultation Workspace */}
            <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                {!activePatient ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/40">
                        <Stethoscope size={56} className="mb-4 text-ink-300 dark:text-ink-600" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-600 dark:text-ink-400 mb-1">Doctor's workspace</h3>
                        <p className="text-sm">Select a patient from the queue to begin charting.</p>
                    </div>
                ) : (
                    <>
                        <div className="shrink-0 flex flex-col">
                            <div className="p-4 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex justify-between items-center z-10">
                                <div className="flex items-center gap-3">
                                    <div className="size-11 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 text-white flex items-center justify-center font-semibold text-base shadow-glow">
                                        {activePatient.patient_name?.charAt(0) || 'P'}
                                    </div>
                                    <div>
                                        <h1 className="text-lg font-semibold text-ink-900 dark:text-white tracking-tight">{activePatient.patient_name}</h1>
                                        <p className="text-xs font-medium text-ink-500 dark:text-ink-400">{activePatient.outpatient_no} &middot; {activePatient.age} yrs &middot; {activePatient.gender}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {activePatient.allergies && activePatient.allergies.toLowerCase() !== 'none' && (
                                        <div className="bg-rose-50 dark:bg-rose-500/10 ring-1 ring-rose-100 dark:ring-rose-500/20 px-3 py-2 rounded-xl flex items-center gap-2">
                                            <AlertCircle size={16} className="text-rose-600 dark:text-rose-400" />
                                            <div>
                                                <p className="text-2xs font-semibold text-rose-700 dark:text-rose-300 uppercase tracking-[0.14em]">Allergies</p>
                                                <p className="text-xs font-semibold text-rose-700 dark:text-rose-300">{activePatient.allergies}</p>
                                            </div>
                                        </div>
                                    )}
                                    {/* KDPA S.30 consent capture — visible at all times so the
                                        doctor can record verbal/written consent without leaving
                                        the desk. Turns into a confirmed pill once recorded for
                                        the active encounter. */}
                                    <button
                                        type="button"
                                        data-tour="clinical-consent"
                                        onClick={() => setIsConsentOpen(true)}
                                        title={hasRecordedConsent
                                            ? 'Consent recorded for this encounter — click to re-record'
                                            : 'Record KDPA Section 30 treatment consent'}
                                        className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold transition-colors cursor-pointer ring-1 ${
                                            hasRecordedConsent
                                                ? 'bg-emerald-50 dark:bg-emerald-500/10 ring-emerald-200 dark:ring-emerald-500/20 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-500/15'
                                                : 'bg-brand-50 dark:bg-brand-500/10 ring-brand-200 dark:ring-brand-500/20 text-brand-700 dark:text-brand-300 hover:bg-brand-100 dark:hover:bg-brand-500/15'
                                        }`}
                                    >
                                        <ShieldCheck size={14} />
                                        {hasRecordedConsent ? 'Consent recorded' : 'Record consent'}
                                    </button>
                                </div>
                            </div>

                            {/* History toolbar — each button deep-links to the
                                Medical History page with the active patient
                                pre-selected and the relevant section auto-expanded.
                                The first item lands on the full chart (no entry_type
                                filter) so the doctor sees everything at a glance. */}
                            <div className="bg-ink-50/40 dark:bg-ink-800/40 border-b border-ink-100 dark:border-ink-800 p-2 flex gap-1.5 overflow-x-auto custom-scrollbar">
                                {[
                                    { icon: History,   label: 'Medical Hx',    entry_type: null },
                                    { icon: Scissors,  label: 'Surgical Hx',   entry_type: 'SURGICAL_HISTORY' },
                                    { icon: Cigarette, label: 'Social Hx',     entry_type: 'SOCIAL_HISTORY' },
                                    { icon: Dna,       label: 'Family Hx',     entry_type: 'FAMILY_HISTORY' },
                                    { icon: Syringe,   label: 'Immunizations', entry_type: 'IMMUNIZATION' },
                                ].map(({ icon: Icon, label, entry_type }) => (
                                    <button type="button"
                                        key={label}
                                        onClick={() => {
                                            const params = new URLSearchParams({ patient_id: String(activePatient.patient_id) });
                                            if (entry_type) params.set('entry_type', entry_type);
                                            navigate(`/app/medical-history?${params.toString()}`);
                                        }}
                                        className="whitespace-nowrap flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 text-ink-600 dark:text-ink-400 rounded-lg text-xs font-medium hover:border-brand-300 dark:hover:border-brand-500/40 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
                                    >
                                        <Icon size={13} /> {label}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 dark:bg-ink-800/40 custom-scrollbar">

                            {/* Vitals Entry */}
                            <div data-tour="clinical-vitals" className="card-flush p-5 border-l-4 border-l-brand-500">
                                <div className="flex justify-between items-center mb-4 border-b border-ink-100 dark:border-ink-800 pb-3">
                                    <h3 className="section-eyebrow flex items-center gap-2"><Activity size={16} className="text-brand-500" /> Vital signs</h3>
                                    <button type="button" onClick={() => setIsTrendsOpen(true)} className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 flex items-center gap-1"><Activity size={13} /> View trends</button>
                                </div>
                                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
                                    <div><label htmlFor="clinic-bp-mmhg" className="label">BP (mmHg)</label><input id="clinic-bp-mmhg" type="text" value={vitals.bp} onChange={(e) => setVitals({...vitals, bp: e.target.value})} placeholder="120/80" className="input" /></div>
                                    <div><label htmlFor="clinic-hr-bpm" className="label">HR (bpm)</label><input id="clinic-hr-bpm" type="number" value={vitals.hr} onChange={(e) => setVitals({...vitals, hr: e.target.value})} placeholder="72" className="input" /></div>
                                    <div><label htmlFor="clinic-resp-bpm" className="label">Resp (bpm)</label><input id="clinic-resp-bpm" type="number" value={vitals.rr} onChange={(e) => setVitals({...vitals, rr: e.target.value})} placeholder="16" className="input" /></div>
                                    <div><label htmlFor="clinic-temp-c" className="label">Temp (°C)</label><input id="clinic-temp-c" type="number" step="0.1" value={vitals.temp} onChange={(e) => setVitals({...vitals, temp: e.target.value})} placeholder="37.2" className="input" /></div>
                                    <div><label htmlFor="clinic-spo" className="label">SpO₂ (%)</label><input id="clinic-spo" type="number" value={vitals.spo2} onChange={(e) => setVitals({...vitals, spo2: e.target.value})} placeholder="98" className="input" /></div>
                                    <div><label htmlFor="clinical-rbs" className="label">RBS (mmol/L)</label><input id="clinical-rbs" type="number" step="0.1" value={vitals.glucose} onChange={(e) => setVitals({...vitals, glucose: e.target.value})} placeholder="5.5" className="input" /></div>
                                    <div><label htmlFor="clinic-weight-kg" className="label">Weight (kg)</label><input id="clinic-weight-kg" type="number" value={vitals.weight} onChange={(e) => setVitals({...vitals, weight: e.target.value})} placeholder="70" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                                    <div><label htmlFor="clinic-height-cm" className="label">Height (cm)</label><input id="clinic-height-cm" type="number" value={vitals.height} onChange={(e) => setVitals({...vitals, height: e.target.value})} placeholder="175" className="input bg-brand-50/40 dark:bg-brand-500/10" /></div>
                                    <div><span className="label text-brand-700 dark:text-brand-300 block">BMI</span><div className="input bg-brand-50 dark:bg-brand-500/10 ring-1 ring-brand-200 dark:ring-brand-500/20 text-brand-800 dark:text-brand-300 font-semibold text-center">{calculateBMI()}</div></div>
                                </div>
                            </div>

                            {/* Clinical Documentation (SOAP) */}
                            <div className="card-flush p-5 border-l-4 border-l-ink-700 space-y-4">
                                <h3 className="section-eyebrow border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2"><FileText size={16} className="text-ink-600 dark:text-ink-400" /> Clinical documentation</h3>
                                <div>
                                    <label htmlFor="clinic-chief-complaint-s-cc" className="label">Chief complaint(s) (CC)</label>
                                    <div className="flex gap-2">
                                        <input id="clinic-chief-complaint-s-cc"
                                            type="text"
                                            value={complaintInput}
                                            onChange={(e) => setComplaintInput(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addComplaint(); } }}
                                            className="input flex-1"
                                            placeholder="e.g. Severe headache for 3 days — press Enter to add"
                                        />
                                        <button type="button" onClick={addComplaint} className="btn-secondary shrink-0 px-3"><Plus size={15} /> Add</button>
                                    </div>
                                    {complaints.length > 0 && (
                                        <ol className="mt-3 space-y-1.5">
                                            {complaints.map((c, idx) => (
                                                <li key={c} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                                    <span className="font-mono text-2xs font-semibold text-ink-400 w-5 shrink-0">{idx + 1}.</span>
                                                    <span className="flex-1 text-ink-800 dark:text-ink-200">{c}</span>
                                                    <button type="button" onClick={() => removeComplaint(idx)} aria-label={`Remove complaint ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                                </li>
                                            ))}
                                        </ol>
                                    )}
                                </div>
                                <div><label htmlFor="clinic-history-of-present-illness-hpi" className="label">History of present illness (HPI)</label><textarea id="clinic-history-of-present-illness-hpi" rows="3" value={clinicalNotes.hpi} onChange={(e) => setClinicalNotes({...clinicalNotes, hpi: e.target.value})} className="input resize-none" placeholder="Narrative of the patient's symptoms…"></textarea></div>
                                <div>
                                    <label htmlFor="clinic-physical-examination-objective" className="label">Physical examination(s) (Objective)</label>
                                    <div className="flex gap-2">
                                        <input id="clinic-physical-examination-objective"
                                            type="text"
                                            value={examInput}
                                            onChange={(e) => setExamInput(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addExam(); } }}
                                            className="input flex-1"
                                            placeholder="e.g. Chest: clear air entry bilaterally — press Enter to add"
                                        />
                                        <button type="button" onClick={addExam} className="btn-secondary shrink-0 px-3"><Plus size={15} /> Add</button>
                                    </div>
                                    {physicalExams.length > 0 && (
                                        <ol className="mt-3 space-y-1.5">
                                            {physicalExams.map((c, idx) => (
                                                <li key={c} className="flex items-center gap-2 text-sm bg-ink-50 dark:bg-ink-800/60 rounded-lg px-3 py-1.5">
                                                    <span className="font-mono text-2xs font-semibold text-ink-400 w-5 shrink-0">{idx + 1}.</span>
                                                    <span className="flex-1 text-ink-800 dark:text-ink-200">{c}</span>
                                                    <button type="button" onClick={() => removeExam(idx)} aria-label={`Remove examination finding ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><X size={14} /></button>
                                                </li>
                                            ))}
                                        </ol>
                                    )}
                                </div>
                            </div>

                            {/* Orders & Prescriptions */}
                            <div data-tour="clinical-diagnoses" className="card-flush p-5 border-l-4 border-l-accent-500 space-y-4">
                                <h3 className="section-eyebrow border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2"><Pill size={16} className="text-accent-600 dark:text-accent-400" /> Diagnosis &amp; orders</h3>

                                <IcdDiagnosisPicker codes={icdCodes} onChange={setIcdCodes} />

                                <div>
                                    <label htmlFor="clinic-diagnosis-free-text" className="label">Diagnosis notes (free text)</label>
                                    <input id="clinic-diagnosis-free-text" type="text" value={clinicalNotes.diagnosis} onChange={(e) => setClinicalNotes({ ...clinicalNotes, diagnosis: e.target.value })} className="input" placeholder="Working / descriptive diagnosis if not using ICD-10 codes…" />
                                </div>

                                <div className="rounded-xl border border-ink-200 dark:border-ink-800 p-4">
                                    <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400 mb-3 flex items-center gap-2"><TestTube size={13} /> Investigations</h4>
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

                                {/* Medications — structured, numbered rows routed to Pharmacy */}
                                <div data-tour="clinical-prescriptions" className="rounded-xl border border-accent-200 dark:border-accent-500/20 bg-accent-50/40 dark:bg-accent-500/10 p-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="text-2xs font-semibold uppercase tracking-[0.14em] text-accent-700 dark:text-accent-300 flex items-center gap-2"><Pill size={13} /> Medications (routed to Pharmacy)</h4>
                                        <button type="button" onClick={addMedication} className="btn-secondary px-3 py-1.5 text-xs shrink-0"><Plus size={13} /> Add medication</button>
                                    </div>
                                    {medications.length === 0 ? (
                                        <p className="text-xs text-ink-500 dark:text-ink-400 italic">No medications yet — click “Add medication” to start prescribing.</p>
                                    ) : (
                                        <div className="space-y-2">
                                            {medications.map((med, idx) => (
                                                <div key={med._uid} className="rounded-lg border border-accent-200/70 dark:border-accent-500/20 bg-white dark:bg-ink-900 p-3">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <span className="size-5 shrink-0 rounded-full bg-accent-100 dark:bg-accent-500/20 text-accent-700 dark:text-accent-300 text-2xs font-bold flex items-center justify-center">{idx + 1}</span>
                                                        <input aria-label="Drug name (e.g. Amoxicillin)" value={med.drug} onChange={(e) => updateMedication(idx, 'drug', e.target.value)} className="input flex-1 py-1.5" placeholder="Drug name (e.g. Amoxicillin)" />
                                                        <button type="button" onClick={() => removeMedication(idx)} aria-label={`Remove medication ${idx + 1}`} className="text-ink-400 hover:text-rose-600 shrink-0"><Trash2 size={15} /></button>
                                                    </div>
                                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                                        <div>
                                                            <label htmlFor="clinic-formulation" className="label text-2xs">Formulation</label>
                                                            <select id="clinic-formulation" value={med.formulation} onChange={(e) => updateMedication(idx, 'formulation', e.target.value)} className="input py-1.5 text-sm">
                                                                {FORMULATIONS.map((f) => <option key={f} value={f}>{f}</option>)}
                                                            </select>
                                                        </div>
                                                        <div>
                                                            <label htmlFor="clinic-dosage" className="label text-2xs">Dosage</label>
                                                            <input id="clinic-dosage" value={med.dosage} onChange={(e) => updateMedication(idx, 'dosage', e.target.value)} className="input py-1.5 text-sm" placeholder="500 mg" />
                                                        </div>
                                                        <div>
                                                            <label htmlFor="clinic-frequency" className="label text-2xs">Frequency</label>
                                                            <input id="clinic-frequency" list="rx-frequencies" value={med.frequency} onChange={(e) => updateMedication(idx, 'frequency', e.target.value)} className="input py-1.5 text-sm" placeholder="TDS" />
                                                        </div>
                                                        <div>
                                                            <label htmlFor="clinic-duration" className="label text-2xs">Duration</label>
                                                            <input id="clinic-duration" value={med.duration} onChange={(e) => updateMedication(idx, 'duration', e.target.value)} className="input py-1.5 text-sm" placeholder="5 days" />
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                            <datalist id="rx-frequencies">{FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}</datalist>
                                        </div>
                                    )}
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div><label htmlFor="clinic-internal-notes-nursing-ward" className="label">Internal notes (nursing / ward)</label><input id="clinic-internal-notes-nursing-ward" type="text" value={clinicalNotes.internal_notes} onChange={(e) => setClinicalNotes({...clinicalNotes, internal_notes: e.target.value})} className="input" placeholder="e.g. Please administer stat dose before discharge" /></div>
                                    <div>
                                        <span className="label flex items-center gap-1">
                                            <CalendarPlus size={13} aria-hidden="true" /> Next follow-up
                                        </span>
                                        <button
                                            type="button"
                                            onClick={() => setIsFollowUpOpen(true)}
                                            className={`input text-left flex items-center justify-between gap-2 cursor-pointer ${
                                                pendingFollowUp ? 'text-ink-900 dark:text-white border-brand-300 dark:border-brand-500/40 bg-brand-50/40 dark:bg-brand-500/10' : 'text-ink-400'
                                            }`}
                                        >
                                            <span className="truncate">
                                                {pendingFollowUp
                                                    ? new Date(pendingFollowUp.appointment_date).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
                                                    : 'Select date…'}
                                            </span>
                                            {pendingFollowUp
                                                ? <CheckCircle2 size={13} className="text-accent-600 dark:text-accent-400 shrink-0" aria-hidden="true" />
                                                : <CalendarPlus size={13} className="text-ink-400 shrink-0" aria-hidden="true" />}
                                        </button>
                                        {pendingFollowUp && (
                                            <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">
                                                With <span className="font-medium text-ink-700 dark:text-ink-200">{pendingFollowUp.doctor_name}</span>.{' '}
                                                <button
                                                    type="button"
                                                    onClick={() => setIsFollowUpOpen(true)}
                                                    className="text-brand-700 dark:text-brand-300 hover:text-brand-800 dark:hover:text-brand-200 cursor-pointer underline"
                                                >
                                                    Change
                                                </button>
                                            </p>
                                        )}
                                    </div>
                                </div>

                                <label htmlFor="chargeFee" className="border border-brand-200 dark:border-brand-500/20 bg-brand-50/50 dark:bg-brand-500/10 p-4 rounded-xl flex items-center justify-between cursor-pointer hover:bg-brand-50/80 dark:hover:bg-brand-500/15 transition-colors">
                                    <div className="flex items-center gap-3">
                                        <input type="checkbox" id="chargeFee" checked={chargeConsultation} onChange={(e) => setChargeConsultation(e.target.checked)} className="size-5 text-brand-600 rounded border-brand-300 focus:ring-brand-500" />
                                        <div>
                                            <span className="text-sm font-semibold text-brand-900 dark:text-brand-200 block">Authorize consultation fee</span>
                                            <span className="text-xs text-brand-700 dark:text-brand-300">Automatically generate a consultation invoice at the cashier.</span>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <span className="text-base font-semibold text-brand-700 dark:text-brand-300 block">
                                            KES {Number(myFee?.amount ?? 1000).toLocaleString()}
                                        </span>
                                        <button
                                            type="button"
                                            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsFeeModalOpen(true); }}
                                            className="text-xs text-brand-700 dark:text-brand-300 underline hover:text-brand-800 dark:hover:text-brand-200 cursor-pointer"
                                        >
                                            Change my fee
                                        </button>
                                    </div>
                                </label>
                            </div>
                        </div>

                        {/* Footer actions */}
                        <div data-tour="clinical-submit" className="p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex flex-wrap justify-between items-center gap-3 shrink-0 z-10">
                            <div className="flex gap-2">
                                <button type="button" data-tour="clinical-save-draft" onClick={() => handleClinicalSubmit('Draft')} disabled={isSubmitting} className="btn-secondary"><Save size={15} /> Save draft</button>
                                <button type="button" onClick={() => setIsReferModalOpen(true)} className="btn-ghost"><ArrowRightLeft size={15} /> Refer patient</button>
                            </div>

                            <div className="flex gap-2">
                                <button type="button" data-tour="clinical-send-billing" onClick={() => handleClinicalSubmit('Billed')} disabled={isSubmitting} className="btn-secondary text-brand-700 dark:text-brand-300 border-brand-200 dark:border-brand-500/30 hover:bg-brand-50 dark:hover:bg-brand-500/15">
                                    <Receipt size={15} /> Send to billing
                                </button>
                                <button type="button" data-tour="clinical-forward-pharmacy" onClick={() => handleClinicalSubmit('Pharmacy')} disabled={isSubmitting} className="btn-success">
                                    <Pill size={15} /> Forward to pharmacy
                                </button>
                                <button type="button" data-tour="clinical-finalize" onClick={() => handleClinicalSubmit('Completed')} disabled={isSubmitting} className="btn bg-ink-800 dark:bg-ink-700 text-white hover:bg-ink-900 dark:hover:bg-ink-600 shadow-soft">
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

            {activePatient && isConsentOpen && (
                <ConsentModal
                    patient={activePatient}
                    draft={consentDraft}
                    setDraft={setConsentDraft}
                    submitting={consentSubmitting}
                    onClose={() => setIsConsentOpen(false)}
                    onSubmit={handleConsentSubmit}
                />
            )}

            {activePatient && isTrendsOpen && (
                <VitalsTrendsModal
                    patient={activePatient}
                    onClose={() => setIsTrendsOpen(false)}
                />
            )}

            {isReferModalOpen && activePatient && (
                <ReferralModal
                    patient={activePatient}
                    initialSummary={buildDiagnosisFields(icdCodes, clinicalNotes.diagnosis).diagnosis}
                    onClose={() => setIsReferModalOpen(false)}
                />
            )}

            {isFeeModalOpen && (
                <ConsultationFeeModal
                    current={myFee}
                    onClose={() => setIsFeeModalOpen(false)}
                    onSaved={(fee) => { setMyFee(fee); setIsFeeModalOpen(false); }}
                />
            )}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Consultation fee modal — doctor self-service pricing.                     */
/*                                                                            */
/*  PUTs /billing/consultation-fee/me, which upserts a per-doctor row in the  */
/*  master price list (service code CONSULT-DR-<id>). The charge endpoint     */
/*  resolves the fee server-side from that row, so this editor is the single  */
/*  source of truth — the client never sends an amount when charging.         */
/* ────────────────────────────────────────────────────────────────────────── */
function ConsultationFeeModal({ current, onClose, onSaved }) {
    const [amount, setAmount] = useState(current?.amount ? String(current.amount) : '');
    const [submitting, setSubmitting] = useState(false);

    const submit = async () => {
        const value = parseFloat(amount);
        if (!Number.isFinite(value) || value <= 0) {
            toast.error('Enter a fee greater than zero.');
            return;
        }
        setSubmitting(true);
        try {
            const response = await apiClient.put('/billing/consultation-fee/me', { amount: value });
            toast.success('Your consultation fee has been updated.');
            onSaved(response.data);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to update consultation fee.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-sm overflow-hidden flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="size-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-500 text-white flex items-center justify-center shadow-soft">
                            <Receipt size={17} />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">My consultation fee</h3>
                            <p className="text-xs text-ink-500 dark:text-ink-400">Billed whenever you authorize a consultation fee.</p>
                        </div>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-3">
                    <div>
                        <label htmlFor="clinic-my-consultation-fee" className="label">Fee amount (KES)</label>
                        <input
                            id="clinic-my-consultation-fee"
                            type="number"
                            min="1"
                            step="50"
                            className="input"
                            value={amount}
                            onChange={(e) => setAmount(e.target.value)}
                            placeholder="e.g. 1500"
                        />
                        <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">
                            Saved to the hospital price list under your name — admins can also
                            see and adjust it from Accounting → Config → Price list.
                        </p>
                    </div>
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2 bg-ink-50/40 dark:bg-ink-800/40">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button type="button" onClick={submit} disabled={submitting} className="btn-primary cursor-pointer">
                        {submitting
                            ? <><Activity size={14} className="animate-spin" /> Saving…</>
                            : <><Receipt size={14} /> Save fee</>}
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Consent modal — KDPA Section 30 Treatment consent.                        */
/*                                                                            */
/*  Local to ClinicalDesk so the doctor can record consent without leaving    */
/*  the encounter. POSTs /medical-history/consent with consent_type=          */
/*  'Treatment'. The server backs that with an audit-log entry, so the chain  */
/*  of custody is intact even when the consent is recorded mid-consultation.  */
/* ────────────────────────────────────────────────────────────────────────── */
const CONSENT_METHODS = ['Verbal', 'Written', 'Guardian/Next of Kin', 'Implied (Emergency)'];

function ConsentModal({ patient, draft, setDraft, submitting, onClose, onSubmit }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="size-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-500 text-white flex items-center justify-center shadow-soft">
                            <ShieldCheck size={17} />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">Record treatment consent</h3>
                            <p className="text-xs text-ink-500 dark:text-ink-400">KDPA Section 30 · {patient.patient_name}</p>
                        </div>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-4 overflow-y-auto">
                    <p className="text-sm text-ink-700 dark:text-ink-200 leading-relaxed">
                        The patient agrees to assessment, diagnosis, and treatment for this encounter.
                        Recording consent lets you save SOAP notes and forward to Pharmacy / Billing.
                    </p>

                    <div>
                        <label htmlFor="clinic-consent-method" className="label">Consent method</label>
                        <select id="clinic-consent-method"
                            className="input"
                            value={draft.consent_method}
                            onChange={(e) => setDraft({ ...draft, consent_method: e.target.value })}
                        >
                            {CONSENT_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                        <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">
                            Use <strong>Verbal</strong> for in-person consent, <strong>Written</strong> when a signed
                            form is on file, <strong>Implied</strong> only in emergencies where the patient can't
                            communicate.
                        </p>
                    </div>

                    <div>
                        <label htmlFor="clinic-notes-optional" className="label">Notes (optional)</label>
                        <textarea id="clinic-notes-optional"
                            rows="3"
                            className="input resize-none"
                            placeholder="e.g. Witnessed by Nurse Atieno; patient confirmed understanding of treatment plan."
                            value={draft.notes}
                            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
                        />
                    </div>
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2 bg-ink-50/40 dark:bg-ink-800/40">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button
                        type="button"
                        onClick={onSubmit}
                        disabled={submitting}
                        className="btn-primary cursor-pointer"
                    >
                        {submitting
                            ? <><Activity size={14} className="animate-spin" /> Recording…</>
                            : <><ShieldCheck size={14} /> Record consent</>}
                    </button>
                </div>
            </div>
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
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-elevated w-full max-w-3xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">New lab order</p>
                        <h2 id="lab-order-title" className="text-base sm:text-lg font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-100 dark:hover:bg-ink-800/50 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {/* Search */}
                    <div className="px-4 sm:px-6 py-3 border-b border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900 sticky top-0 z-10">
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                            <label htmlFor="lab-search" className="sr-only">Search tests</label>
                            <input
                                id="lab-search"
                                type="search"
                                placeholder="Search lab tests by name or specimen…"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 dark:placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                    </div>

                    {/* Catalog list */}
                    <div className="p-4 sm:p-6 space-y-1.5">
                        {isLoading ? (
                            <div className="text-center py-8 text-ink-500 dark:text-ink-400">
                                <Activity className="animate-spin inline mr-2 text-brand-600" size={18} aria-hidden="true" /> Loading catalog…
                            </div>
                        ) : filtered.length === 0 ? (
                            <p className="text-center py-8 text-ink-500 dark:text-ink-400 text-sm">No tests match your search.</p>
                        ) : filtered.map(item => {
                            const state = selection[item.catalog_id];
                            const isSelected = !!state?.selected;
                            return (
                                <div
                                    key={item.catalog_id}
                                    className={`rounded-lg border transition-colors ${
                                        isSelected
                                            ? 'bg-brand-50/60 dark:bg-brand-500/10 border-brand-200 dark:border-brand-500/20'
                                            : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:bg-ink-50 dark:hover:bg-ink-800/50'
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
                                            className="mt-0.5 size-4 accent-brand-600 cursor-pointer"
                                        />
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium text-ink-900 dark:text-white truncate">{item.test_name}</p>
                                            <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 truncate">
                                                {item.specimen_type || 'Unknown specimen'}
                                                {item.base_price !== undefined && item.base_price !== null
                                                    ? ` · KES ${Number(item.base_price).toLocaleString('en-KE')}`
                                                    : ''}
                                            </p>
                                        </div>
                                    </label>
                                    {isSelected && (
                                        <div className="px-3 pb-3 grid grid-cols-1 sm:grid-cols-3 gap-2">
                                            <label className="sm:col-span-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400">
                                                Priority
                                                <select
                                                    value={state.priority}
                                                    onChange={e => updateField(item.catalog_id, 'priority', e.target.value)}
                                                    className="mt-1 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-md px-2 py-1.5 text-xs text-ink-900 dark:text-white normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                                >
                                                    {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                                                </select>
                                            </label>
                                            <label className="sm:col-span-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400">
                                                Clinical notes (optional)
                                                <input
                                                    type="text"
                                                    value={state.clinical_notes}
                                                    onChange={e => updateField(item.catalog_id, 'clinical_notes', e.target.value)}
                                                    placeholder="e.g. fasting since 8pm yesterday"
                                                    className="mt-1 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-md px-2 py-1.5 text-xs text-ink-900 dark:text-white normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                                />
                                            </label>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex flex-col-reverse sm:flex-row sm:justify-between sm:items-center gap-2 shrink-0">
                    <p className="text-xs text-ink-600 dark:text-ink-400">
                        <span className="font-semibold text-ink-900 dark:text-white">{selectedItems.length}</span> test{selectedItems.length === 1 ? '' : 's'} selected
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
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-elevated w-full max-w-2xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">New imaging order</p>
                        <h2 id="imaging-order-title" className="text-base sm:text-lg font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-100 dark:hover:bg-ink-800/50 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
                    {/* Catalog picker */}
                    <div>
                        <label htmlFor="img-search" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">Catalogue</label>
                        <div className="relative mt-1.5">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                            <input
                                id="img-search"
                                type="search"
                                placeholder="Search by exam name or modality…"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-9 pr-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 dark:placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                        <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-ink-200 dark:border-ink-800 custom-scrollbar">
                            {isLoading ? (
                                <div className="p-4 text-center text-ink-500 dark:text-ink-400 text-sm">
                                    <Activity className="animate-spin inline mr-2 text-brand-600" size={16} aria-hidden="true" /> Loading…
                                </div>
                            ) : filtered.length === 0 ? (
                                <p className="p-4 text-center text-ink-500 dark:text-ink-400 text-sm">No exams match.</p>
                            ) : (
                                <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                                    {filtered.map(item => {
                                        const isPicked = pickedId === item.catalog_id;
                                        return (
                                            <li key={item.catalog_id}>
                                                <button
                                                    type="button"
                                                    onClick={() => { setPickedId(item.catalog_id); setCustomName(''); }}
                                                    aria-pressed={isPicked}
                                                    className={`w-full text-left px-3 py-2 transition-colors cursor-pointer ${
                                                        isPicked ? 'bg-brand-50 dark:bg-brand-500/10' : 'hover:bg-ink-50 dark:hover:bg-ink-800/50'
                                                    }`}
                                                >
                                                    <div className="flex items-center justify-between gap-2">
                                                        <span className="text-sm font-medium text-ink-900 dark:text-white truncate">{item.exam_name}</span>
                                                        {isPicked && <CheckCircle2 size={14} className="text-brand-700 shrink-0" aria-hidden="true" />}
                                                    </div>
                                                    <div className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">
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
                        <label htmlFor="img-custom" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">
                            Or custom exam (when not in catalog)
                        </label>
                        <input
                            id="img-custom"
                            type="text"
                            value={customName}
                            onChange={e => { setCustomName(e.target.value); if (e.target.value) setPickedId(null); }}
                            placeholder="e.g. X-Ray Right Wrist AP/Lat"
                            className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 dark:placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                        />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <label className="sm:col-span-1 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">
                            Priority
                            <select
                                value={priority}
                                onChange={e => setPriority(e.target.value)}
                                className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            >
                                {PRIORITIES.map(p => <option key={p}>{p}</option>)}
                            </select>
                        </label>
                        <label className="sm:col-span-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">
                            Clinical notes
                            <textarea
                                value={clinicalNotes}
                                onChange={e => setClinicalNotes(e.target.value)}
                                rows="2"
                                placeholder="Clinical question, indication, or area of interest"
                                className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white normal-case tracking-normal focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 resize-none"
                            />
                        </label>
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0">
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
    const [date, setDate] = useState(() => toDateInput(initial));
    const [time, setTime] = useState(() => {
        const pad = (n) => String(n).padStart(2, '0');
        const hours = initial.getHours() || 9;
        const minutes = Math.floor((initial.getMinutes() || 0) / 30) * 30;
        return `${pad(hours)}:${pad(minutes)}`;
    });
    const [notes, setNotes] = useState(existing?.notes || 'Follow-up consultation');
    const [bookings, setBookings] = useState([]);
    // `busy` is derived, not stored: it's true whenever the bookings we hold were
    // loaded for a different (doctor, date) than the one currently selected. This
    // avoids flipping a loading flag from inside the effect purely because a prop
    // changed (no-adjust-state-on-prop-change).
    const [loadedKey, setLoadedKey] = useState(null);
    const busy = !!(doctorId && date) && loadedKey !== `${doctorId}|${date}`;
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
        const key = `${doctorId}|${date}`;
        let cancelled = false;
        apiClient.get('/appointments/availability', { params: { doctor_id: doctorId, date } })
            .then(res => { if (!cancelled) setBookings(res.data?.bookings || []); })
            .catch(() => { if (!cancelled) setBookings([]); })
            .finally(() => { if (!cancelled) setLoadedKey(key); });
        return () => { cancelled = true; };
    }, [doctorId, date]);

    const bookingTimes = useMemo(() => new Set(
        bookings.flatMap(b => {
            if (!b.appointment_date) return [];
            const d = new Date(b.appointment_date);
            const pad = (n) => String(n).padStart(2, '0');
            return [`${pad(d.getHours())}:${pad(d.getMinutes())}`];
        })
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
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-elevated w-full max-w-xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0">
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Schedule follow-up</p>
                        <h2 id="followup-title" className="text-base sm:text-lg font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                            {patient.patient_name}
                        </h2>
                        <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-100 dark:hover:bg-ink-800/50 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200 mb-1.5">Common cadences</p>
                        <div className="flex flex-wrap gap-1.5">
                            {QUICK_PICKS.map(q => (
                                <button
                                    key={q.label}
                                    type="button"
                                    onClick={() => applyQuickPick(q.add)}
                                    className="inline-flex items-center px-2.5 py-1.5 rounded-md text-2xs font-semibold bg-brand-50 dark:bg-brand-500/10 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-500/20 hover:bg-brand-100 dark:hover:bg-brand-500/20 cursor-pointer"
                                >
                                    {q.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label htmlFor="fu-doctor" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">Doctor</label>
                        <select
                            id="fu-doctor"
                            value={doctorId}
                            onChange={e => setDoctorId(e.target.value)}
                            disabled={isLoadingDoctors}
                            className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
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
                            <label htmlFor="fu-date" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">Date</label>
                            <input
                                id="fu-date"
                                type="date"
                                value={date}
                                onChange={e => setDate(e.target.value)}
                                // react-doctor-disable-next-line react-doctor/rendering-hydration-mismatch-time
                                min={toDateInput(new Date())}
                                className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                        <div>
                            <label htmlFor="fu-time" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">Time</label>
                            <input
                                id="fu-time"
                                type="time"
                                value={time}
                                onChange={e => setTime(e.target.value)}
                                step={60 * 30}
                                className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                            />
                        </div>
                    </div>

                    <div className="rounded-lg border border-ink-200 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/40">
                        <div className="px-3 py-2 border-b border-ink-200 dark:border-ink-800 flex items-center justify-between text-2xs font-semibold uppercase tracking-[0.14em] text-ink-600 dark:text-ink-400">
                            <span>Doctor's bookings on {date || '—'}</span>
                            {busy && <Activity size={12} className="animate-spin text-brand-600" aria-hidden="true" />}
                        </div>
                        {bookings.length === 0 ? (
                            <p className="px-3 py-3 text-xs text-ink-500 dark:text-ink-400">No appointments yet for this day.</p>
                        ) : (
                            <ul className="divide-y divide-ink-100 dark:divide-ink-800 max-h-32 overflow-y-auto">
                                {bookings.map(b => {
                                    const d = b.appointment_date ? new Date(b.appointment_date) : null;
                                    const pad = (n) => String(n).padStart(2, '0');
                                    const slot = d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : '—';
                                    const isYou = b.patient_id === patient.patient_id;
                                    return (
                                        <li key={b.appointment_id} className="px-3 py-1.5 flex items-center justify-between gap-2 text-xs">
                                            <span className={`font-mono ${time === slot ? 'text-rose-700 dark:text-rose-300 font-semibold' : 'text-ink-700 dark:text-ink-200'}`}>{slot}</span>
                                            <span className={isYou ? 'text-brand-700 dark:text-brand-300 italic' : 'text-ink-500 dark:text-ink-400'}>
                                                {isYou ? 'this patient' : `patient #${b.patient_id}`} · {b.status}
                                            </span>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>

                    <div>
                        <label htmlFor="fu-notes" className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-200">Notes</label>
                        <textarea
                            id="fu-notes"
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            rows="2"
                            placeholder="What should this follow-up review?"
                            className="mt-1.5 w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg px-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 dark:placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 resize-none"
                        />
                    </div>
                </div>

                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-800/40 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0">
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