import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, ShieldCheck, AlertCircle, Clock, Activity,
    Plus, X, ChevronDown, ChevronRight, FileText,
    Syringe, Users, Heart, Brain, Baby, Cigarette,
    Trash2, Edit, Save, Lock, Printer
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { printMedicalHistory } from '../utils/printTemplates';

const ENTRY_TYPES = [
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

const SEVERITY_LEVELS = ['Mild', 'Moderate', 'Severe', 'Life-threatening', 'N/A'];
const STATUSES = ['Active', 'Resolved', 'Managed', 'Remission'];
const colorMap = {
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

const defaultForm = {
    patient_id: '', entry_type: 'PAST_MEDICAL_EVENT', title: '',
    description: '', event_date: '', severity: 'N/A', status: 'Active', is_sensitive: false
};

const KDPA_BADGE = (
    <span className="badge-success">
        <ShieldCheck size={12} /> KDPA 2019
    </span>
);

export default function MedicalHistory() {
    const [searchParams] = useSearchParams();
    const [chart, setChart] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [searchInput, setSearchInput] = useState(searchParams.get('patient_id') || '');
    const [suggestions, setSuggestions] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [expandedSections, setExpandedSections] = useState({});
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [form, setForm] = useState(defaultForm);
    const [editEntry, setEditEntry] = useState(null);

    useEffect(() => {
        const urlPatientId = searchParams.get('patient_id');
        if (urlPatientId) {
            fetchChart(urlPatientId);
        }
    }, [searchParams]);

    // Deep-link target. The Clinical Desk's history toolbar passes ?entry_type=
    // so a click on "Social Hx" lands the doctor on the right section. Scroll
    // + highlight runs once the chart has rendered, hence the dependency on
    // chart + searchParams together.
    useEffect(() => {
        const targetType = searchParams.get('entry_type');
        if (!targetType || !chart) return;
        // Collapse everything except the requested section so the doctor's eye
        // lands on it immediately.
        setExpandedSections(prev => {
            const next = { ...prev };
            ENTRY_TYPES.forEach(t => { next[t.key] = (t.key === targetType); });
            return next;
        });
        // Defer the scroll so the DOM has the section rendered.
        const id = setTimeout(() => {
            const el = document.getElementById(`mh-section-${targetType}`);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 60);
        return () => clearTimeout(id);
    }, [searchParams, chart]);

    useEffect(() => {
        if (!searchInput || searchInput.trim().length === 0) {
            setSuggestions([]);
            return;
        }
        const timer = setTimeout(async () => {
            try {
                const res = await apiClient.get(`/patients/?search=${searchInput}`);
                setSuggestions(res.data);
            } catch (err) {
                setSuggestions([]);
            }
        }, 300);
        return () => clearTimeout(timer);
    }, [searchInput]);

    const fetchChart = async (patientId) => {
        if (!patientId) return;
        setIsLoading(true);
        setChart(null);
        try {
            const res = await apiClient.get(`/medical-history/${patientId}/chart`);
            setChart(res.data);
            const expanded = {};
            ENTRY_TYPES.forEach(t => { expanded[t.key] = true; });
            setExpandedSections(expanded);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Patient not found or access denied.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleSearch = (e) => {
        e.preventDefault();
        if (suggestions.length > 0) {
            setSearchInput(`${suggestions[0].surname} ${suggestions[0].other_names}`);
            setShowSuggestions(false);
            fetchChart(suggestions[0].patient_id);
        } else if (!isNaN(parseInt(searchInput))) {
            fetchChart(searchInput.trim());
        }
    };

    const handleAddEntry = async (e) => {
        e.preventDefault();
        if (!chart) return;
        setIsSubmitting(true);
        try {
            const payload = { ...form, patient_id: chart.patient_id };
            if (editEntry) {
                await apiClient.put(`/medical-history/entries/${editEntry.entry_id}`, payload);
                toast.success('Entry updated successfully.');
            } else {
                await apiClient.post('/medical-history/entries', payload);
                toast.success('History entry added successfully.');
            }
            setIsAddModalOpen(false);
            setEditEntry(null);
            setForm(defaultForm);
            fetchChart(chart.patient_id);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to save entry.');
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleDelete = async (entryId) => {
        if (!window.confirm('Permanently remove this entry? Audit trail will be preserved.')) return;
        try {
            await apiClient.delete(`/medical-history/entries/${entryId}`);
            toast.success('Entry removed. Audit trail preserved per KDPA.');
            fetchChart(chart.patient_id);
        } catch (err) {
            toast.error('Failed to delete entry.');
        }
    };

    const openEditModal = (entry) => {
        setEditEntry(entry);
        setForm({
            patient_id: entry.patient_id, entry_type: entry.entry_type, title: entry.title,
            description: entry.description, event_date: entry.event_date || '',
            severity: entry.severity || 'N/A', status: entry.status, is_sensitive: entry.is_sensitive
        });
        setIsAddModalOpen(true);
    };

    const openAddModal = () => {
        setEditEntry(null);
        setForm(defaultForm);
        setIsAddModalOpen(true);
    };

    const toggleSection = (key) => setExpandedSections(p => ({ ...p, [key]: !p[key] }));

    const getEntriesForType = (typeKey) => {
        const map = {
            SURGICAL_HISTORY: 'surgical_history', FAMILY_HISTORY: 'family_history',
            SOCIAL_HISTORY: 'social_history', IMMUNIZATION: 'immunizations',
            ALLERGY: 'allergies', CHRONIC_CONDITION: 'chronic_conditions',
            PAST_MEDICAL_EVENT: 'past_medical_events', OBSTETRIC_HISTORY: 'obstetric_history',
            MENTAL_HEALTH: 'mental_health',
        };
        return chart?.[map[typeKey]] || [];
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Patient chart"
                icon={FileText}
                title="Medical History"
                subtitle="Full patient medical chart — KDPA 2019 compliant."
                meta={KDPA_BADGE}
            />

            {/* Patient Search */}
            <div data-tour="mh-search" className="card p-4 shrink-0 overflow-visible relative z-20">
                <form onSubmit={handleSearch} className="flex gap-2 relative flex-wrap">
                    <div className="relative flex-1 min-w-[16rem]">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input aria-label="Search patient by name, ID, or phone to load their medical chart…"
                            type="text" placeholder="Search patient by name, ID, or phone to load their medical chart…"
                            value={searchInput}
                            onChange={e => { setSearchInput(e.target.value); setShowSuggestions(true); }}
                            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                            className="input pl-10"
                        />
                        {showSuggestions && suggestions.length > 0 && (
                            <div className="absolute z-30 w-full mt-1 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-xl shadow-elevated max-h-64 overflow-y-auto top-full left-0 custom-scrollbar">
                                {suggestions.map(patient => (
                                    <button type="button" key={patient.patient_id}
                                        onMouseDown={() => {
                                            setSearchInput(`${patient.surname} ${patient.other_names}`);
                                            setShowSuggestions(false);
                                            fetchChart(patient.patient_id);
                                        }}
                                        className="w-full text-left px-4 py-3 hover:bg-brand-50 dark:hover:bg-brand-900/20 border-b border-ink-100 dark:border-ink-800 last:border-0 transition-colors"
                                    >
                                        <div className="font-semibold text-ink-900 dark:text-white">{patient.surname}, {patient.other_names}</div>
                                        <div className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">OPD: <span className="font-mono">{patient.outpatient_no}</span> &middot; Phone: {patient.telephone_1}</div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <button type="submit" className="btn-primary">Search chart</button>
                    {chart && (
                        <button type="button" data-tour="mh-add-entry" onClick={openAddModal} className="btn-success">
                            <Plus size={15} /> Add entry
                        </button>
                    )}
                </form>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-y-auto space-y-4 custom-scrollbar">
                {isLoading && (
                    <div className="card p-12 flex flex-col items-center justify-center text-ink-400">
                        <Activity className="animate-spin mb-3 text-brand-500" size={26} />
                        <p className="font-medium">Loading patient chart… Access is being logged.</p>
                    </div>
                )}

                {!isLoading && !chart && (
                    <div className="card p-16 flex flex-col items-center justify-center text-ink-400 border-dashed">
                        <FileText size={48} className="mb-4 text-ink-200 dark:text-ink-700" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-500 dark:text-ink-400">No chart loaded</h3>
                        <p className="text-sm mt-1">Search for a patient above to view their complete medical history.</p>
                    </div>
                )}

                {chart && (
                    <>
                        {/* Patient Header Card */}
                        <div className="bg-brand-gradient rounded-2xl p-5 sm:p-6 text-white shadow-elevated relative overflow-hidden">
                            <div className="absolute inset-0 bg-aurora opacity-30 pointer-events-none" />
                            <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div>
                                    <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-brand-100">Patient chart</span>
                                    <h2 className="text-xl sm:text-2xl font-semibold mt-1 tracking-tight">{chart.patient_name}</h2>
                                    <p className="text-brand-100/90 text-sm mt-1 font-mono">{chart.opd_number}</p>
                                    <button type="button"
                                        onClick={() => printMedicalHistory({
                                            patient: { full_name: chart.patient_name, outpatient_no: chart.opd_number, date_of_birth: chart.date_of_birth, sex: chart.sex },
                                            entries: chart.entries || [],
                                            consents: chart.consents || [],
                                        })}
                                        data-tour="mh-print"
                                        className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 bg-white/10 hover:bg-white/15 ring-1 ring-white/15 rounded-lg text-xs font-semibold transition-colors"
                                    >
                                        <Printer size={13} /> Print summary
                                    </button>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    <div className="bg-white/10 backdrop-blur-sm ring-1 ring-white/15 rounded-xl px-4 py-2 text-center">
                                        <p className="text-2xs text-brand-100 uppercase font-semibold tracking-[0.14em]">Blood group</p>
                                        <p className="text-base font-semibold text-white mt-1">{chart.blood_group || '—'}</p>
                                    </div>
                                    <div className="bg-rose-500/20 ring-1 ring-rose-300/30 rounded-xl px-4 py-2 max-w-xs">
                                        <p className="text-2xs text-rose-100 uppercase font-semibold tracking-[0.14em] mb-1">Allergies</p>
                                        <p className="text-xs text-rose-50 font-medium leading-snug">{chart.baseline_allergies || 'None on record'}</p>
                                    </div>
                                    <div className="bg-white/10 ring-1 ring-white/15 rounded-xl px-4 py-2 max-w-xs">
                                        <p className="text-2xs text-brand-100 uppercase font-semibold tracking-[0.14em] mb-1">Chronic conditions</p>
                                        <p className="text-xs text-white font-medium leading-snug">{chart.baseline_conditions || 'None on record'}</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* KDPA Compliance Notice */}
                        <div className="bg-amber-50 dark:bg-amber-500/10 ring-1 ring-amber-100 dark:ring-amber-500/20 rounded-xl p-4 flex items-start gap-3">
                            <Lock size={16} className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                            <div className="text-sm">
                                <p className="font-semibold text-amber-800 dark:text-amber-300">KDPA 2019 compliance active</p>
                                <p className="text-amber-700 dark:text-amber-200 mt-0.5 leading-relaxed text-xs">Your access to this chart has been logged per Section 26 of the Kenya Data Protection Act. Sensitive records (mental health, obstetric) are redacted based on your role. All modifications are permanently recorded in the audit trail.</p>
                            </div>
                        </div>

                        {/* Consents on file (KDPA Section 30) */}
                        <ConsentCard
                            patientId={chart.patient_id}
                            consents={chart.consents || []}
                            onRecorded={() => fetchChart(chart.patient_id)}
                        />

                        {/* History Sections */}
                        {ENTRY_TYPES.map(type => {
                            const entries = getEntriesForType(type.key);
                            const isOpen = expandedSections[type.key];
                            const colorClass = colorMap[type.color];
                            return (
                                <div key={type.key} id={`mh-section-${type.key}`} data-tour={type.key === ENTRY_TYPES[0].key ? 'mh-entry-section' : undefined} className="card overflow-hidden scroll-mt-20">
                                    <button type="button"
                                        onClick={() => toggleSection(type.key)}
                                        className="w-full flex items-center justify-between p-4 hover:bg-ink-50/50 dark:hover:bg-ink-800/50 transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold ${colorClass}`}>
                                                {type.icon} {type.label}
                                            </span>
                                            <span className="badge-neutral">{entries.length}</span>
                                        </div>
                                        {isOpen ? <ChevronDown size={16} className="text-ink-400" /> : <ChevronRight size={16} className="text-ink-400" />}
                                    </button>

                                    {isOpen && (
                                        <div className="border-t border-slate-100 dark:border-ink-800 p-4">
                                            {entries.length === 0 ? (
                                                <p className="text-sm text-slate-400 dark:text-ink-400 italic text-center py-4">No {type.label.toLowerCase()} entries recorded.</p>
                                            ) : (
                                                <div className="space-y-3">
                                                    {entries.map(entry => (
                                                        <div key={entry.entry_id} className={`p-4 rounded-xl border ${entry.is_sensitive ? 'border-red-200 dark:border-red-500/20 bg-red-50/50 dark:bg-red-500/10' : 'border-slate-100 dark:border-ink-800 bg-slate-50/50 dark:bg-ink-800/40'} relative`}>
                                                            <div className="flex items-start justify-between gap-4">
                                                                <div className="flex-1">
                                                                    <div className="flex flex-wrap items-center gap-2 mb-2">
                                                                        <h4 className="font-bold text-slate-900 dark:text-white">{entry.title}</h4>
                                                                        {entry.is_sensitive && (
                                                                            <span className="flex items-center gap-1 text-[10px] font-bold bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-0.5 rounded-full border border-red-200 dark:border-red-500/20">
                                                                                <Lock size={9} /> Sensitive
                                                                            </span>
                                                                        )}
                                                                        {entry.severity && entry.severity !== 'N/A' && (
                                                                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${entry.severity === 'Severe' || entry.severity === 'Life-threatening' ? 'bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300' : entry.severity === 'Moderate' ? 'bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300' : 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-300'}`}>
                                                                                {entry.severity}
                                                                            </span>
                                                                        )}
                                                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${entry.status === 'Active' ? 'bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300' : entry.status === 'Resolved' ? 'bg-green-100 dark:bg-green-500/10 text-green-700 dark:text-green-300' : 'bg-slate-100 dark:bg-ink-800/40 text-slate-600 dark:text-ink-400'}`}>
                                                                            {entry.status}
                                                                        </span>
                                                                    </div>
                                                                    <p className="text-sm text-slate-700 dark:text-ink-200">{entry.description}</p>
                                                                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-400 dark:text-ink-400">
                                                                        {entry.event_date && <span>📅 {entry.event_date}</span>}
                                                                        <span>Recorded: {new Date(entry.created_at).toLocaleDateString()}</span>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-1 shrink-0">
                                                                    <button type="button" onClick={() => openEditModal(entry)} className="p-1.5 text-slate-400 dark:text-ink-400 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-900/20 rounded-lg transition-colors">
                                                                        <Edit size={14} />
                                                                    </button>
                                                                    <button type="button" onClick={() => handleDelete(entry.entry_id)} className="p-1.5 text-slate-500 dark:text-ink-300 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors">
                                                                        <Trash2 size={14} />
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}

                        {/* Recent Clinical Visits */}
                        <div className="bg-white dark:bg-ink-900 border border-slate-200 dark:border-ink-800 rounded-xl shadow-sm overflow-hidden">
                            <div className="p-4 border-b border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40">
                                <h3 className="font-bold text-slate-800 dark:text-ink-200 flex items-center gap-2"><Clock size={16} /> Recent Clinical Visits</h3>
                            </div>
                            <div className="p-4 space-y-3">
                                {(chart.recent_visits || []).length === 0 ? (
                                    <p className="text-sm text-slate-400 dark:text-ink-400 italic text-center py-4">No clinical visits recorded.</p>
                                ) : chart.recent_visits.map(visit => (
                                    <div key={visit.record_id} className="flex gap-4 p-3 bg-slate-50 dark:bg-ink-800/40 rounded-xl border border-slate-100 dark:border-ink-800">
                                        <div className="w-1 rounded-full bg-brand-500 shrink-0" />
                                        <div className="flex-1">
                                            <div className="flex justify-between items-start">
                                                <p className="font-bold text-sm text-slate-800 dark:text-ink-200">{visit.diagnosis || 'No diagnosis recorded'}</p>
                                                <span className="text-xs text-slate-400 dark:text-ink-400">{visit.date ? new Date(visit.date).toLocaleDateString() : '—'}</span>
                                            </div>
                                            <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5"><span className="font-medium">Complaint:</span> {visit.chief_complaint || '—'}</p>
                                            <p className="text-xs text-slate-500 dark:text-ink-400"><span className="font-medium">Dr:</span> {visit.doctor}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Add / Edit Entry Modal */}
            {isAddModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsAddModalOpen(false)} />
                    <div className="relative w-full max-w-lg bg-white dark:bg-ink-900 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-slide-up max-h-[90vh]">
                        <div className="p-5 border-b border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40 flex justify-between items-center shrink-0">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900 dark:text-white">{editEntry ? 'Edit History Entry' : 'Add History Entry'}</h2>
                                <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5">All entries are audit-logged per KDPA 2019.</p>
                            </div>
                            <button type="button" onClick={() => setIsAddModalOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 rounded-lg hover:bg-ink-100 cursor-pointer"><X size={20} aria-hidden="true" /></button>
                        </div>

                        <form id="historyForm" onSubmit={handleAddEntry} className="p-5 space-y-4 overflow-y-auto">
                            <div>
                                <label htmlFor="medica-entry-type" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Entry Type <span className="text-red-500">*</span></label>
                                <select id="medica-entry-type" value={form.entry_type} onChange={e => setForm({ ...form, entry_type: e.target.value })} className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm font-medium focus:ring-2 focus:ring-brand-500 outline-none bg-white dark:bg-ink-900 dark:text-white">
                                    {ENTRY_TYPES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                                </select>
                            </div>

                            <div>
                                <label htmlFor="medica-title" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Title <span className="text-red-500">*</span></label>
                                <input id="medica-title" required type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Appendectomy, Penicillin Allergy" className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none dark:bg-ink-900 dark:text-white" />
                            </div>

                            <div>
                                <label htmlFor="medica-detailed-description" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Detailed Description <span className="text-red-500">*</span></label>
                                <textarea id="medica-detailed-description" required rows="3" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Full clinical description of the event..." className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none dark:bg-ink-900 dark:text-white" />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label htmlFor="medica-approximate-date" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Approximate Date</label>
                                    <input id="medica-approximate-date" type="text" value={form.event_date} onChange={e => setForm({ ...form, event_date: e.target.value })} placeholder="e.g. March 2019, 2015" className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none dark:bg-ink-900 dark:text-white" />
                                </div>
                                <div>
                                    <label htmlFor="medica-severity" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Severity</label>
                                    <select id="medica-severity" value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })} className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white dark:bg-ink-900 dark:text-white">
                                        {SEVERITY_LEVELS.map(s => <option key={s}>{s}</option>)}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label htmlFor="medica-status" className="block text-xs font-bold text-slate-700 dark:text-ink-200 mb-1.5">Status</label>
                                <select id="medica-status" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full px-3 py-2 border border-slate-200 dark:border-ink-800 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white dark:bg-ink-900 dark:text-white">
                                    {STATUSES.map(s => <option key={s}>{s}</option>)}
                                </select>
                            </div>

                            <label className={`flex items-start gap-3 p-4 border rounded-xl cursor-pointer transition-colors ${form.is_sensitive ? 'border-red-300 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10' : 'border-slate-200 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40 hover:bg-slate-100 dark:hover:bg-ink-800/50'}`}>
                                <input type="checkbox" checked={form.is_sensitive} onChange={e => setForm({ ...form, is_sensitive: e.target.checked })} className="mt-0.5 size-4 text-red-600 rounded border-slate-300 dark:border-ink-700" />
                                <div>
                                    <p className="text-sm font-bold text-slate-800 dark:text-ink-200 flex items-center gap-2"><Lock size={13} className="text-red-600 dark:text-red-400" /> Mark as Sensitive</p>
                                    <p className="text-xs text-slate-500 dark:text-ink-400 mt-0.5">KDPA: Restricts access to Doctors and Nurses only. Use for Mental Health, HIV, and Obstetric records.</p>
                                </div>
                            </label>
                        </form>

                        <div className="p-4 border-t border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40 flex justify-end gap-3 shrink-0">
                            <button type="button" onClick={() => setIsAddModalOpen(false)} className="px-4 py-2 text-sm font-bold text-slate-600 dark:text-ink-300 hover:bg-slate-200 dark:hover:bg-ink-800/50 rounded-lg">Cancel</button>
                            <button type="submit" form="historyForm" disabled={isSubmitting} className="flex items-center gap-2 px-5 py-2 bg-brand-600 text-white text-sm font-bold rounded-lg hover:bg-brand-700 disabled:opacity-50">
                                {isSubmitting ? <Activity className="animate-spin" size={15} /> : <Save size={15} />}
                                {editEntry ? 'Save Changes' : 'Add to Chart'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}


// Valid consent_type values mirror VALID_CONSENT_TYPES in
// backend/app/schemas/medical_history.py. Treatment is the only one the
// Section 30 gate currently checks; the rest are surfaced for completeness
// (the Privacy Officer may need them on file for KDPA audits even though
// they don't block writes).
const CONSENT_TYPES = ['Treatment', 'Data Sharing', 'Research', 'Telehealth', 'Photography'];
const CONSENT_METHODS = ['Verbal', 'Written', 'Electronic'];

/**
 * ConsentCard — view + record patient consents (KDPA Section 30).
 *
 *  Lists every consent_record currently on file for the patient and
 *  surfaces an inline form so the clinician can capture a new one without
 *  leaving the chart. POSTs /api/medical-history/consent then triggers a
 *  chart refetch so the new row appears in the list (and downstream
 *  clinical writes pass the consent gate).
 */
function ConsentCard({ patientId, consents, onRecorded }) {
    const [open, setOpen] = useState(false);
    const [busy, setBusy] = useState(false);
    const [form, setForm] = useState({
        consent_type: 'Treatment',
        consent_method: 'Verbal',
        notes: '',
        consent_expires_at: '',
    });

    // Active Treatment consent is the one that gates clinical writes.
    const activeTreatment = useMemo(() => {
        const now = Date.now();
        return (consents || [])
            .filter(c => c.consent_type === 'Treatment' && c.consent_given
                && (!c.consent_expires_at || new Date(c.consent_expires_at).getTime() > now))
            .reduce((latest, c) =>
                (!latest || new Date(c.consented_at).getTime() > new Date(latest.consented_at).getTime()) ? c : latest,
                null);
    }, [consents]);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const payload = {
                patient_id: patientId,
                consent_type: form.consent_type,
                consent_given: true,
                consent_method: form.consent_method,
            };
            if (form.notes.trim()) payload.notes = form.notes.trim();
            if (form.consent_expires_at) {
                // Schema expects ISO; <input type="date"> gives YYYY-MM-DD,
                // append end-of-day UTC so a same-day expiry isn't already
                // stale by the time the request lands.
                payload.consent_expires_at = `${form.consent_expires_at}T23:59:59Z`;
            }
            await apiClient.post('/medical-history/consent', payload);
            toast.success(`${form.consent_type} consent recorded.`);
            setForm(f => ({ ...f, notes: '', consent_expires_at: '' }));
            setOpen(false);
            await onRecorded();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to record consent');
        } finally {
            setBusy(false);
        }
    };

    const handle = (e) => setForm(f => ({ ...f, [e.target.name]: e.target.value }));

    return (
        <div data-tour="consent-card" className="card overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/20">
                        <ShieldCheck size={14} /> Consents (KDPA Section 30)
                    </span>
                    <span className="badge-neutral">{(consents || []).length}</span>
                    {activeTreatment ? (
                        <span className="text-xs text-emerald-700 dark:text-emerald-300">Treatment consent active</span>
                    ) : (
                        <span className="text-xs text-rose-700 dark:text-rose-300 font-medium">No active Treatment consent — clinical writes will be blocked</span>
                    )}
                </div>
                <button
                    type="button"
                    onClick={() => setOpen(o => !o)}
                    className="btn-primary text-xs py-1.5 px-3"
                >
                    <Plus size={13} /> Record consent
                </button>
            </div>

            {/* Existing consents */}
            {(consents || []).length > 0 && (
                <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                    {consents.map((c) => (
                        <li key={c.consent_id} className="px-4 py-3 flex items-center justify-between text-sm">
                            <div>
                                <div className="font-medium text-ink-900 dark:text-white">
                                    {c.consent_type}
                                    <span className="ml-2 text-xs text-ink-500 dark:text-ink-400">({c.consent_method})</span>
                                    {c.consent_given ? (
                                        <span className="ml-2 inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300 text-xs"><ShieldCheck size={11} /> Granted</span>
                                    ) : (
                                        <span className="ml-2 inline-flex items-center gap-1 text-rose-700 dark:text-rose-300 text-xs"><X size={11} /> Withheld</span>
                                    )}
                                </div>
                                <div className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">
                                    Recorded {new Date(c.consented_at).toLocaleString()}
                                    {c.consent_expires_at && ` · expires ${new Date(c.consent_expires_at).toLocaleDateString()}`}
                                </div>
                                {c.notes && <div className="text-xs text-ink-600 dark:text-ink-400 mt-1 italic">"{c.notes}"</div>}
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            {/* Inline record form */}
            {open && (
                <form onSubmit={submit} className="p-4 border-t border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/40 space-y-3">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                            <label htmlFor="medica-consent-type" className="label">Consent type</label>
                            <select id="medica-consent-type" name="consent_type" value={form.consent_type} onChange={handle} className="input">
                                {CONSENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>
                        <div>
                            <label htmlFor="medica-method" className="label">Method</label>
                            <select id="medica-method" name="consent_method" value={form.consent_method} onChange={handle} className="input">
                                {CONSENT_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                            </select>
                        </div>
                        <div>
                            <label htmlFor="medica-expires-optional" className="label">Expires (optional)</label>
                            <input id="medica-expires-optional" type="date" name="consent_expires_at" value={form.consent_expires_at} onChange={handle} className="input" />
                        </div>
                    </div>
                    <div>
                        <label htmlFor="medica-notes-optional" className="label">Notes (optional)</label>
                        <textarea id="medica-notes-optional" name="notes" value={form.notes} onChange={handle} rows="2" className="input" placeholder="e.g., Patient consented verbally during admission" />
                    </div>
                    <div className="flex gap-2 justify-end">
                        <button type="button" onClick={() => setOpen(false)} className="btn-secondary text-xs">Cancel</button>
                        <button type="submit" disabled={busy} className="btn-primary text-xs">
                            {busy ? (<><Activity className="animate-spin" size={13} /> Recording…</>) : (<><Save size={13} /> Record consent</>)}
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
}
