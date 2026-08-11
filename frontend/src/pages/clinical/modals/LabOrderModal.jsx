import React, { useState, useEffect, useMemo } from 'react';
import { X, Search, Activity, Send } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../../api/client';

// Lab order modal — fetches /laboratory/catalog (active tests), lets the
// clinician pick one or more with per-test notes + priority, and submits via
// /laboratory/orders. Shared by the Clinical Desk and Triage.
const PRIORITIES = ['Routine', 'Urgent', 'STAT'];

export default function LabOrderModal({ patient, onClose }) {
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
