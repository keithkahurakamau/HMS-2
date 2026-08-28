import React, { useState, useEffect, useMemo } from 'react';
import { X, Search, Activity, Send, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../../api/client';

// Imaging (radiology) order modal: one exam per order from /radiology/catalog
// (or a free-text custom exam), with notes + priority, POSTed to /radiology/.
// Shared by the Clinical Desk and Triage.
const PRIORITIES = ['Routine', 'Urgent', 'STAT'];

export default function ImagingOrderModal({ patient, onClose }) {
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
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-overlay w-full max-w-2xl max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
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
