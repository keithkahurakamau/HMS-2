import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Activity, HeartPulse, Save, ArrowRight, Stethoscope, XCircle, UserMinus, Paperclip,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import { useActivePatient } from '../context/PatientContext';
import { useAuth } from '../context/AuthContext';
import useDraftSafetyNet from '../hooks/useDraftSafetyNet';
import PatientHistoryModal from '../components/PatientHistoryModal';
import PatientDetailsHeader from './clinical/PatientDetailsHeader';
import PatientHistoryTab from './clinical/PatientHistoryTab';
import ActionsMenu from './clinical/ActionsMenu';
import FilesModal from './clinical/modals/FilesModal';
import TriageTab from './triage/TriageTab';

const DISPOSITIONS = ['Consultation', 'Laboratory', 'Pharmacy', 'Radiology', 'Billing', 'Wards'];
const EMPTY_VITALS = { weight: '', height: '', bp: '', hr: '', rr: '', temp: '', spo2: '', pain: '', glucose: '' };
// Map the nurse-assessed acuity to the shared header's priority chip.
const ACUITY_TO_PRIORITY = { 1: 'Critical', 2: 'High' };

export default function Triage() {
    const navigate = useNavigate();
    const auth = useAuth();
    const perms = auth?.user?.permissions || [];
    const hasPerm = (p) => perms.includes(p);

    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [activePatient, setActivePatient] = useState(null);
    const [activeTab, setActiveTab] = useState('triage'); // 'triage' | 'history'
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [actionModal, setActionModal] = useState(null); // 'files' | null
    const [historyModal, setHistoryModal] = useState(null); // { entry_type } | null

    const [vitals, setVitals] = useState(EMPTY_VITALS);
    const [complaints, setComplaints] = useState([]);
    const [complaintInput, setComplaintInput] = useState('');
    const [triageNotes, setTriageNotes] = useState('');
    const [acuity, setAcuity] = useState(3);
    const [disposition, setDisposition] = useState('Consultation');

    // Local draft safety net for the notes field — protects a nurse's typed
    // observations from an interruption before "Save & send" is clicked. Keyed
    // by queue_id so one patient's notes can never surface on another's form.
    const triageDraftKey = activePatient?.queue_id ? `triageNotes:${activePatient.queue_id}` : null;
    const {
        hasSavedDraft: hasNotesDraft,
        savedAt: notesDraftSavedAt,
        applyDraft: applyNotesDraft,
        discardDraft: discardNotesDraft,
        clearDraft: clearNotesDraft,
    } = useDraftSafetyNet({ storageKey: triageDraftKey, value: triageNotes, enabled: !!activePatient });

    const { setActivePatient: setGlobalActivePatient } = useActivePatient();

    useEffect(() => { fetchQueue(); }, []);

    const fetchQueue = async () => {
        setIsLoadingQueue(true);
        try {
            const res = await apiClient.get('/triage/queue');
            setQueue(res.data || []);
        } catch {
            toast.error('Failed to load the triage queue.');
        } finally {
            setIsLoadingQueue(false);
        }
    };

    // Header queue rows expect triage_time / priority; map them from the triage
    // queue shape so the shared PatientDetailsHeader renders consistently.
    const headerQueue = queue.map((q) => ({
        ...q,
        triage_time: q.joined_time,
        priority: ACUITY_TO_PRIORITY[q.acuity_level] || 'Normal',
    }));

    const clearWorkspace = () => {
        setActivePatient(null);
        setGlobalActivePatient(null);
    };

    const removeFromTriage = async (item) => {
        if (!window.confirm(`Remove ${item.patient_name} from the triage queue?`)) return;
        try {
            await apiClient.patch(`/queue/${item.queue_id}/checkout`);
            toast.success('Removed from triage queue.');
            if (activePatient?.queue_id === item.queue_id) clearWorkspace();
            fetchQueue();
        } catch {
            toast.error('Could not remove from the queue.');
        }
    };

    const cancelFromTriage = async (item) => {
        const reason = window.prompt(`Cancel ${item.patient_name}? Reason (optional):`);
        if (reason === null) return; // dismissed
        try {
            await apiClient.patch(`/queue/${item.queue_id}/cancel`, { reason: reason || null });
            toast.success('Patient cancelled.');
            if (activePatient?.queue_id === item.queue_id) clearWorkspace();
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
        setActiveTab('triage');
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
        if (complaints.some((c) => c.toLowerCase() === value.toLowerCase())) { setComplaintInput(''); return; }
        setComplaints((prev) => [...prev, value]);
        setComplaintInput('');
    };
    const removeComplaint = (idx) => setComplaints((prev) => prev.filter((_, i) => i !== idx));

    const handleSubmit = async () => {
        if (!activePatient) { toast.error('Select a patient from the queue first.'); return; }
        const hasAnyVital = Object.values(vitals).some((v) => String(v).trim() !== '');
        // Fold text left unsubmitted in the input into the list so a nurse who
        // typed but didn't press Enter doesn't lose it.
        const pending = complaintInput.trim();
        const allComplaints = pending && !complaints.some((c) => c.toLowerCase() === pending.toLowerCase())
            ? [...complaints, pending] : complaints;
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
            clearNotesDraft();
            clearWorkspace();
            fetchQueue();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to save triage.');
        } finally {
            setIsSubmitting(false);
        }
    };

    // Consolidated Actions ▾ — permission-gated; empty groups disappear.
    const actionGroups = [
        { label: 'Flow', items: [
            { label: 'Cancel patient', icon: XCircle, perm: 'triage:write', onClick: () => cancelFromTriage(activePatient) },
            { label: 'Remove from queue', icon: UserMinus, perm: 'triage:write', onClick: () => removeFromTriage(activePatient) },
        ] },
        { label: 'Documents', items: [
            { label: 'Attachments', icon: Paperclip, perm: 'clinical:read', onClick: () => setActionModal('files') },
        ] },
    ];

    return (
        <div className="flex flex-col gap-3 h-full md:h-[calc(100vh-6rem)] min-h-[calc(100vh-6rem)]">
            <PageHeader
                eyebrow="Nursing"
                icon={HeartPulse}
                title="Triage"
                subtitle="Capture vitals and acuity before the consultation — the doctor's desk arrives pre-filled."
            />

            {/* TOP PANEL: patient details + triage queue */}
            <div data-tour="triage-queue" className="shrink-0 z-20">
                <PatientDetailsHeader
                    key={activePatient?.queue_id ?? 'idle'}
                    activePatient={activePatient}
                    queue={headerQueue}
                    isLoadingQueue={isLoadingQueue}
                    showSearch={false}
                    queueLabel="Triage queue"
                    onSelectPatient={(item) => { if (item?.patient_name) handlePatientSelect(item); }}
                    onRemoveFromQueue={removeFromTriage}
                    onViewAllPatients={() => navigate('/app/patients')}
                />
            </div>

            {/* BOTTOM PANEL: triage workspace */}
            <div className="flex-1 min-h-0 card overflow-hidden flex flex-col z-10 relative">
                {!activePatient ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/40">
                        <HeartPulse size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-600 dark:text-ink-400 mb-1">Triage station</h3>
                        <p className="text-sm">Select a patient from the queue to record their vitals.</p>
                    </div>
                ) : (
                    <>
                        {/* Tab bar + Actions ▾ */}
                        <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 p-3 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 z-10">
                            <div className="flex gap-1 bg-ink-100/70 dark:bg-ink-800/70 p-1 rounded-xl">
                                {[
                                    { id: 'triage', label: 'Triage' },
                                    { id: 'history', label: 'Patient History' },
                                ].map((t) => (
                                    <button type="button" key={t.id} onClick={() => setActiveTab(t.id)}
                                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${activeTab === t.id ? 'bg-white dark:bg-ink-900 text-brand-700 dark:text-brand-300 shadow-soft' : 'text-ink-500 dark:text-ink-400 hover:text-ink-800 dark:hover:text-ink-200'}`}>
                                        {t.label}
                                    </button>
                                ))}
                            </div>
                            <ActionsMenu has={hasPerm} groups={actionGroups} />
                        </div>

                        {/* Scroll body */}
                        <div className="flex-1 overflow-y-auto p-4 sm:p-6 custom-scrollbar">
                            {activeTab === 'triage' ? (
                                <TriageTab
                                    value={{ vitals, bmi: calculateBMI(), complaints, complaintInput, triageNotes, acuity, hasNotesDraft, notesDraftSavedAt }}
                                    on={{
                                        setVitals, setComplaintInput, addComplaint, removeComplaint,
                                        setTriageNotes, setAcuity,
                                        onRestoreDraft: () => setTriageNotes(applyNotesDraft() || ''),
                                        onDiscardDraft: discardNotesDraft,
                                    }}
                                />
                            ) : (
                                <PatientHistoryTab patientId={activePatient.patient_id} onOpenHistory={(t) => setHistoryModal({ entry_type: t })} />
                            )}
                        </div>

                        {/* Footer: route-to + save */}
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
                    </>
                )}
            </div>

            {activePatient && actionModal === 'files' && (
                <FilesModal patient={activePatient} recordId={null} onClose={() => setActionModal(null)} />
            )}
            {activePatient && historyModal && (
                <PatientHistoryModal
                    patientId={activePatient.patient_id}
                    initialSection={historyModal.entry_type}
                    onClose={() => setHistoryModal(null)}
                />
            )}
        </div>
    );
}
