import React, { useState } from 'react';
import { X, Printer, Save, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { printReferralLetter } from '../utils/printReferral';
import DraftRecoveryBanner from './DraftRecoveryBanner';
import useDraftSafetyNet from '../hooks/useDraftSafetyNet';

const URGENCIES = ['Routine', 'Urgent', 'Emergency'];

/**
 * External referral capture + letter printing. Typed letters require the
 * referral to be saved first (the referral log stays accurate); the two
 * blank modes only print — nothing is recorded.
 */
export default function ReferralModal({ patient, recordId = null, initialSummary = '', onClose }) {
    const { user } = useAuth();
    const doctorName = user?.full_name || '';
    const [form, setForm] = useState({
        specialty: '', target_facility: '', target_clinician: '',
        urgency: 'Routine', reason: '', clinical_summary: initialSummary,
    });
    const [isSaving, setIsSaving] = useState(false);

    // Local draft safety net — the letter is only recorded on Save; closing
    // the modal early (backdrop click, Escape, a browser interruption)
    // would otherwise lose everything typed. Keyed by patient so reopening
    // this modal for the same patient later offers the letter back.
    const referralDraftKey = patient?.patient_id ? `referral:${patient.patient_id}` : null;
    const {
        hasSavedDraft: hasReferralDraft,
        savedAt: referralDraftSavedAt,
        applyDraft: applyReferralDraft,
        discardDraft: discardReferralDraft,
        clearDraft: clearReferralDraft,
    } = useDraftSafetyNet({
        storageKey: referralDraftKey,
        value: form,
        enabled: true,
    });

    const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

    const save = async () => {
        if (!form.specialty.trim() || !form.reason.trim()) {
            toast.error('Specialty and reason are required for a referral.');
            return null;
        }
        setIsSaving(true);
        try {
            const res = await apiClient.post('/referrals/', {
                patient_id: patient.patient_id,
                record_id: recordId,
                specialty: form.specialty.trim(),
                target_facility: form.target_facility.trim() || null,
                target_clinician: form.target_clinician.trim() || null,
                urgency: form.urgency,
                reason: form.reason.trim(),
                clinical_summary: form.clinical_summary.trim() || null,
            });
            toast.success('Referral recorded.');
            clearReferralDraft();
            return res.data;
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Could not save the referral.');
            return null;
        } finally {
            setIsSaving(false);
        }
    };

    const handleSaveOnly = async () => {
        const saved = await save();
        if (saved) onClose();
    };

    const handleSaveAndPrint = async () => {
        const saved = await save();
        if (!saved) return;
        printReferralLetter({ mode: 'typed', referral: saved, patient, doctorName });
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true" aria-labelledby="referral-modal-title">
            <div className="bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-lg max-h-[90vh] overflow-y-auto custom-scrollbar">
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <h3 id="referral-modal-title" className="font-bold text-ink-800 dark:text-ink-200 flex items-center gap-2">
                        <FileText size={16} /> Refer {patient.patient_name}
                    </h3>
                    <button type="button" onClick={onClose} aria-label="Close referral dialog" className="text-ink-400 hover:text-ink-600"><X size={18} /></button>
                </div>

                <div className="p-4 space-y-3">
                    {hasReferralDraft && (
                        <DraftRecoveryBanner
                            savedAt={referralDraftSavedAt}
                            label="referral letter"
                            onRestore={() => setForm((f) => ({ ...f, ...applyReferralDraft() }))}
                            onDiscard={discardReferralDraft}
                        />
                    )}
                    <div>
                        <label htmlFor="referral-specialty" className="label">Specialty *</label>
                        <input id="referral-specialty" type="text" value={form.specialty} onChange={set('specialty')} className="input" placeholder="e.g. Cardiology" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label htmlFor="referral-facility" className="label">Target facility</label>
                            <input id="referral-facility" type="text" value={form.target_facility} onChange={set('target_facility')} className="input" placeholder="Receiving hospital / clinic" />
                        </div>
                        <div>
                            <label htmlFor="referral-clinician" className="label">Target clinician</label>
                            <input id="referral-clinician" type="text" value={form.target_clinician} onChange={set('target_clinician')} className="input" placeholder="If known" />
                        </div>
                    </div>
                    <div>
                        <label htmlFor="referral-urgency" className="label">Urgency</label>
                        <select id="referral-urgency" value={form.urgency} onChange={set('urgency')} className="input">
                            {URGENCIES.map((u) => <option key={u} value={u}>{u}</option>)}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="referral-reason" className="label">Reason for referral *</label>
                        <textarea id="referral-reason" rows="3" value={form.reason} onChange={set('reason')} className="input resize-none" placeholder="Why this patient needs onward care…" />
                    </div>
                    <div>
                        <label htmlFor="referral-summary" className="label">Clinical summary</label>
                        <textarea id="referral-summary" rows="4" value={form.clinical_summary} onChange={set('clinical_summary')} className="input resize-none" placeholder="Relevant findings, treatment so far…" />
                    </div>
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 space-y-2">
                    <div className="flex gap-2">
                        <button type="button" onClick={handleSaveAndPrint} disabled={isSaving} className="btn-success flex-1">
                            <Printer size={14} /> Save &amp; print typed letter
                        </button>
                        <button type="button" onClick={handleSaveOnly} disabled={isSaving} className="btn-secondary flex-1">
                            <Save size={14} /> Save referral
                        </button>
                    </div>
                    <p className="text-2xs text-ink-500 dark:text-ink-400 pt-1">Print a letter to fill in by hand (nothing is saved):</p>
                    <div className="flex gap-2">
                        <button type="button" onClick={() => printReferralLetter({ mode: 'blank-patient', referral: {}, patient, doctorName })} className="btn-ghost flex-1 text-xs">
                            <Printer size={13} /> Blank (with patient info)
                        </button>
                        <button type="button" onClick={() => printReferralLetter({ mode: 'blank', referral: {}, patient, doctorName: '' })} className="btn-ghost flex-1 text-xs">
                            <Printer size={13} /> Fully blank
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
