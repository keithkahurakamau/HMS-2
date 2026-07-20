import {
    FileText, Users, Cigarette, Syringe, AlertCircle, Heart, Clock, Baby, Brain,
} from 'lucide-react';

// Shared between MedicalHistory.jsx (full chart, read/write) and
// PatientHistoryModal.jsx (Clinical Desk's inline read-only popup) so the two
// views can never drift out of sync on labels, icons, or colors.
export const ENTRY_TYPES = [
    { key: 'SURGICAL_HISTORY', label: 'Surgical History', icon: <FileText size={16} />, color: 'blue' },
    { key: 'FAMILY_HISTORY', label: 'Family History', icon: <Users size={16} />, color: 'purple' },
    { key: 'SOCIAL_HISTORY', label: 'Social History', icon: <Cigarette size={16} />, color: 'amber' },
    { key: 'IMMUNIZATION', label: 'Immunizations', icon: <Syringe size={16} />, color: 'green' },
    { key: 'ALLERGY', label: 'Allergies', icon: <AlertCircle size={16} />, color: 'red' },
    { key: 'CHRONIC_CONDITION', label: 'Chronic Conditions', icon: <Heart size={16} />, color: 'rose' },
    { key: 'PAST_MEDICAL_EVENT', label: 'Past Medical Events', icon: <Clock size={16} />, color: 'slate' },
    { key: 'OBSTETRIC_HISTORY', label: 'Obstetric History', icon: <Baby size={16} />, color: 'pink' },
    { key: 'MENTAL_HEALTH', label: 'Mental Health', icon: <Brain size={16} />, color: 'indigo' },
];

export const ENTRY_TYPE_COLOR_CLASSES = {
    blue: 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/20',
    purple: 'bg-purple-50 dark:bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/20',
    amber: 'bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/20',
    green: 'bg-green-50 dark:bg-green-500/10 text-green-700 dark:text-green-300 border-green-200 dark:border-green-500/20',
    red: 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-300 border-red-200 dark:border-red-500/20',
    rose: 'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/20',
    slate: 'bg-slate-100 dark:bg-ink-800/40 text-slate-700 dark:text-ink-200 border-slate-200 dark:border-ink-800',
    pink: 'bg-pink-50 dark:bg-pink-500/10 text-pink-700 dark:text-pink-300 border-pink-200 dark:border-pink-500/20',
    indigo: 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/20',
};

// Maps an ENTRY_TYPES key to the corresponding array field on
// PatientMedicalChartResponse (GET /medical-history/{patient_id}/chart).
export const ENTRY_TYPE_TO_CHART_FIELD = {
    SURGICAL_HISTORY: 'surgical_history',
    FAMILY_HISTORY: 'family_history',
    SOCIAL_HISTORY: 'social_history',
    IMMUNIZATION: 'immunizations',
    ALLERGY: 'allergies',
    CHRONIC_CONDITION: 'chronic_conditions',
    PAST_MEDICAL_EVENT: 'past_medical_events',
    OBSTETRIC_HISTORY: 'obstetric_history',
    MENTAL_HEALTH: 'mental_health',
};
