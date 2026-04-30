import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, ShieldCheck, AlertCircle, Clock, Activity,
    Plus, X, ChevronDown, ChevronRight, FileText,
    Syringe, Users, Heart, Brain, Baby, Cigarette,
    Trash2, Edit, Save, Lock
} from 'lucide-react';

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
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    rose: 'bg-rose-50 text-rose-700 border-rose-200',
    slate: 'bg-slate-100 text-slate-700 border-slate-200',
    pink: 'bg-pink-50 text-pink-700 border-pink-200',
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200',
};

const defaultForm = {
    patient_id: '', entry_type: 'PAST_MEDICAL_EVENT', title: '',
    description: '', event_date: '', severity: 'N/A', status: 'Active', is_sensitive: false
};

export default function MedicalHistory() {
    const [searchParams] = useSearchParams();
    const [searchQuery, setSearchQuery] = useState('');
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
        <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
            {/* Header */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm shrink-0">
                <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-brand-50 text-brand-600 rounded-lg flex items-center justify-center border border-brand-100">
                            <FileText size={22} />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-slate-900">Medical History</h1>
                            <p className="text-sm text-slate-500">Full patient medical chart · KDPA 2019 Compliant</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full text-xs font-bold text-green-700">
                        <ShieldCheck size={14} /> Kenya Data Protection Act 2019
                    </div>
                </div>
            </div>

            {/* Patient Search */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm shrink-0 overflow-visible relative z-20">
                <form onSubmit={handleSearch} className="flex gap-3 relative">
                    <div className="relative flex-1">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input
                            type="text" placeholder="Search Patient by Name, ID, or Phone to load their Medical Chart..."
                            value={searchInput} 
                            onChange={e => { setSearchInput(e.target.value); setShowSuggestions(true); }}
                            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                            className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                        />
                        {/* Autocomplete Dropdown */}
                        {showSuggestions && suggestions.length > 0 && (
                            <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-xl max-h-64 overflow-y-auto top-full left-0">
                                {suggestions.map(patient => (
                                    <div 
                                        key={patient.patient_id}
                                        onMouseDown={() => {
                                            setSearchInput(`${patient.surname} ${patient.other_names}`);
                                            setShowSuggestions(false);
                                            fetchChart(patient.patient_id);
                                        }}
                                        className="px-4 py-3 hover:bg-brand-50 cursor-pointer border-b border-slate-100 last:border-0 transition-colors"
                                    >
                                        <div className="font-bold text-slate-900">{patient.surname}, {patient.other_names}</div>
                                        <div className="text-xs text-slate-500 mt-0.5">OPD: {patient.outpatient_no} • Phone: {patient.telephone_1}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <button type="submit" className="px-5 py-2.5 bg-brand-600 text-white text-sm font-bold rounded-lg hover:bg-brand-700 shadow-sm">
                        Search Chart
                    </button>
                    {chart && (
                        <button type="button" onClick={openAddModal} className="flex items-center gap-2 px-5 py-2.5 bg-accent-600 text-white text-sm font-bold rounded-lg hover:bg-accent-700 shadow-sm">
                            <Plus size={16} /> Add Entry
                        </button>
                    )}
                </form>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-y-auto space-y-4 custom-scrollbar">
                {isLoading && (
                    <div className="bg-white rounded-xl border border-slate-200 p-12 flex flex-col items-center justify-center text-slate-400">
                        <Activity className="animate-spin mb-3 text-brand-500" size={28} />
                        <p className="font-medium">Loading patient chart... Access is being logged.</p>
                    </div>
                )}

                {!isLoading && !chart && (
                    <div className="bg-white rounded-xl border border-slate-200 p-16 flex flex-col items-center justify-center text-slate-400">
                        <FileText size={56} className="mb-4 text-slate-200" strokeWidth={1.5} />
                        <h3 className="text-lg font-semibold text-slate-500">No Chart Loaded</h3>
                        <p className="text-sm mt-1">Enter a Patient ID above to view their complete medical history.</p>
                    </div>
                )}

                {chart && (
                    <>
                        {/* Patient Header Card */}
                        <div className="bg-gradient-to-r from-brand-600 to-brand-700 rounded-xl p-5 text-white shadow-md">
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div>
                                    <p className="text-brand-200 text-xs font-bold uppercase tracking-wider mb-1">Patient Chart</p>
                                    <h2 className="text-2xl font-black">{chart.patient_name}</h2>
                                    <p className="text-brand-200 text-sm mt-1">{chart.opd_number}</p>
                                </div>
                                <div className="flex flex-wrap gap-3">
                                    <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-lg px-4 py-2 text-center">
                                        <p className="text-[10px] text-brand-200 uppercase font-bold">Blood Group</p>
                                        <p className="text-lg font-black text-white">{chart.blood_group || '—'}</p>
                                    </div>
                                    <div className="bg-red-500/20 border border-red-300/30 rounded-lg px-4 py-2">
                                        <p className="text-[10px] text-red-200 uppercase font-bold mb-1">Allergies</p>
                                        <p className="text-xs text-red-100 font-semibold">{chart.baseline_allergies || 'None on record'}</p>
                                    </div>
                                    <div className="bg-white/10 border border-white/20 rounded-lg px-4 py-2">
                                        <p className="text-[10px] text-brand-200 uppercase font-bold mb-1">Chronic Conditions</p>
                                        <p className="text-xs text-white font-semibold">{chart.baseline_conditions || 'None on record'}</p>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* KDPA Compliance Notice */}
                        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
                            <Lock size={18} className="text-amber-600 shrink-0 mt-0.5" />
                            <div className="text-sm">
                                <p className="font-bold text-amber-800">KDPA 2019 Compliance Active</p>
                                <p className="text-amber-700 mt-0.5">Your access to this chart has been logged per Section 26 of the Kenya Data Protection Act. Sensitive records (Mental Health, Obstetric) are redacted based on your role. All modifications are permanently recorded in the audit trail.</p>
                            </div>
                        </div>

                        {/* History Sections */}
                        {ENTRY_TYPES.map(type => {
                            const entries = getEntriesForType(type.key);
                            const isOpen = expandedSections[type.key];
                            const colorClass = colorMap[type.color];
                            return (
                                <div key={type.key} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                                    <button
                                        onClick={() => toggleSection(type.key)}
                                        className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold ${colorClass}`}>
                                                {type.icon} {type.label}
                                            </span>
                                            <span className="text-xs font-bold text-slate-400 bg-slate-100 px-2 py-1 rounded-full">
                                                {entries.length}
                                            </span>
                                        </div>
                                        {isOpen ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}
                                    </button>

                                    {isOpen && (
                                        <div className="border-t border-slate-100 p-4">
                                            {entries.length === 0 ? (
                                                <p className="text-sm text-slate-400 italic text-center py-4">No {type.label.toLowerCase()} entries recorded.</p>
                                            ) : (
                                                <div className="space-y-3">
                                                    {entries.map(entry => (
                                                        <div key={entry.entry_id} className={`p-4 rounded-xl border ${entry.is_sensitive ? 'border-red-200 bg-red-50/50' : 'border-slate-100 bg-slate-50/50'} relative`}>
                                                            <div className="flex items-start justify-between gap-4">
                                                                <div className="flex-1">
                                                                    <div className="flex flex-wrap items-center gap-2 mb-2">
                                                                        <h4 className="font-bold text-slate-900">{entry.title}</h4>
                                                                        {entry.is_sensitive && (
                                                                            <span className="flex items-center gap-1 text-[10px] font-bold bg-red-100 text-red-700 px-2 py-0.5 rounded-full border border-red-200">
                                                                                <Lock size={9} /> Sensitive
                                                                            </span>
                                                                        )}
                                                                        {entry.severity && entry.severity !== 'N/A' && (
                                                                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${entry.severity === 'Severe' || entry.severity === 'Life-threatening' ? 'bg-red-100 text-red-700' : entry.severity === 'Moderate' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>
                                                                                {entry.severity}
                                                                            </span>
                                                                        )}
                                                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${entry.status === 'Active' ? 'bg-blue-100 text-blue-700' : entry.status === 'Resolved' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                                                                            {entry.status}
                                                                        </span>
                                                                    </div>
                                                                    <p className="text-sm text-slate-700">{entry.description}</p>
                                                                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                                                                        {entry.event_date && <span>📅 {entry.event_date}</span>}
                                                                        <span>Recorded: {new Date(entry.created_at).toLocaleDateString()}</span>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center gap-1 shrink-0">
                                                                    <button onClick={() => openEditModal(entry)} className="p-1.5 text-slate-400 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-colors">
                                                                        <Edit size={14} />
                                                                    </button>
                                                                    <button onClick={() => handleDelete(entry.entry_id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
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
                        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                            <div className="p-4 border-b border-slate-100 bg-slate-50">
                                <h3 className="font-bold text-slate-800 flex items-center gap-2"><Clock size={16} /> Recent Clinical Visits</h3>
                            </div>
                            <div className="p-4 space-y-3">
                                {(chart.recent_visits || []).length === 0 ? (
                                    <p className="text-sm text-slate-400 italic text-center py-4">No clinical visits recorded.</p>
                                ) : chart.recent_visits.map(visit => (
                                    <div key={visit.record_id} className="flex gap-4 p-3 bg-slate-50 rounded-xl border border-slate-100">
                                        <div className="w-1 rounded-full bg-brand-500 shrink-0" />
                                        <div className="flex-1">
                                            <div className="flex justify-between items-start">
                                                <p className="font-bold text-sm text-slate-800">{visit.diagnosis || 'No diagnosis recorded'}</p>
                                                <span className="text-xs text-slate-400">{visit.date ? new Date(visit.date).toLocaleDateString() : '—'}</span>
                                            </div>
                                            <p className="text-xs text-slate-500 mt-0.5"><span className="font-medium">Complaint:</span> {visit.chief_complaint || '—'}</p>
                                            <p className="text-xs text-slate-500"><span className="font-medium">Dr:</span> {visit.doctor}</p>
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
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsAddModalOpen(false)} />
                    <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 max-h-[90vh]">
                        <div className="p-5 border-b border-slate-100 bg-slate-50 flex justify-between items-center shrink-0">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900">{editEntry ? 'Edit History Entry' : 'Add History Entry'}</h2>
                                <p className="text-xs text-slate-500 mt-0.5">All entries are audit-logged per KDPA 2019.</p>
                            </div>
                            <button onClick={() => setIsAddModalOpen(false)} className="text-slate-400 hover:text-slate-700 p-1"><X size={20} /></button>
                        </div>

                        <form id="historyForm" onSubmit={handleAddEntry} className="p-5 space-y-4 overflow-y-auto">
                            <div>
                                <label className="block text-xs font-bold text-slate-700 mb-1.5">Entry Type <span className="text-red-500">*</span></label>
                                <select value={form.entry_type} onChange={e => setForm({ ...form, entry_type: e.target.value })} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm font-medium focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                    {ENTRY_TYPES.map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
                                </select>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-700 mb-1.5">Title <span className="text-red-500">*</span></label>
                                <input required type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Appendectomy, Penicillin Allergy" className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-700 mb-1.5">Detailed Description <span className="text-red-500">*</span></label>
                                <textarea required rows="3" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Full clinical description of the event..." className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none resize-none" />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Approximate Date</label>
                                    <input type="text" value={form.event_date} onChange={e => setForm({ ...form, event_date: e.target.value })} placeholder="e.g. March 2019, 2015" className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Severity</label>
                                    <select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                        {SEVERITY_LEVELS.map(s => <option key={s}>{s}</option>)}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-slate-700 mb-1.5">Status</label>
                                <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                    {STATUSES.map(s => <option key={s}>{s}</option>)}
                                </select>
                            </div>

                            <label className={`flex items-start gap-3 p-4 border rounded-xl cursor-pointer transition-colors ${form.is_sensitive ? 'border-red-300 bg-red-50' : 'border-slate-200 bg-slate-50 hover:bg-slate-100'}`}>
                                <input type="checkbox" checked={form.is_sensitive} onChange={e => setForm({ ...form, is_sensitive: e.target.checked })} className="mt-0.5 w-4 h-4 text-red-600 rounded border-slate-300" />
                                <div>
                                    <p className="text-sm font-bold text-slate-800 flex items-center gap-2"><Lock size={13} className="text-red-600" /> Mark as Sensitive</p>
                                    <p className="text-xs text-slate-500 mt-0.5">KDPA: Restricts access to Doctors and Nurses only. Use for Mental Health, HIV, and Obstetric records.</p>
                                </div>
                            </label>
                        </form>

                        <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3 shrink-0">
                            <button type="button" onClick={() => setIsAddModalOpen(false)} className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-lg">Cancel</button>
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
