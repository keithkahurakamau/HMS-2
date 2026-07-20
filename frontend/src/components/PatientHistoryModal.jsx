import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
    X, Activity, ChevronDown, ChevronRight, Lock, ExternalLink, ShieldCheck,
} from 'lucide-react';
import { apiClient } from '../api/client';
import VisitHistoryList from './VisitHistoryList';
import { ENTRY_TYPES, ENTRY_TYPE_COLOR_CLASSES, ENTRY_TYPE_TO_CHART_FIELD } from '../constants/medicalHistoryEntryTypes';

/* ──────────────────────────────────────────────────────────────────────────
 * PatientHistoryModal — Clinical Desk's inline, read-only view of a
 * patient's medical chart. Opens over the encounter form (nothing in the
 * in-progress SOAP notes is touched) instead of navigating away to
 * /app/medical-history. Fetches the same GET /medical-history/{id}/chart
 * endpoint the full Medical History page uses — no backend change, no
 * separate source of truth.
 *
 * This view never writes. A doctor who needs to add/edit/delete an entry,
 * print, or manage consents follows the "Open full record" link, which is
 * the same deep-link the old toolbar buttons used to navigate to directly.
 *
 *   patientId       required — whose chart to load
 *   initialSection  optional ENTRY_TYPES key to auto-expand + scroll to.
 *                   Omitted/null expands every section (full-chart view).
 *   onClose         required — close handler
 * ────────────────────────────────────────────────────────────────────────── */
export default function PatientHistoryModal({ patientId, initialSection = null, onClose }) {
    const navigate = useNavigate();
    const [chart, setChart] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState(false);
    const [expanded, setExpanded] = useState({});
    const sectionRefs = useRef({});

    useEffect(() => {
        let cancelled = false;
        apiClient.get(`/medical-history/${patientId}/chart`)
            .then((res) => {
                if (cancelled) return;
                setChart(res.data);
                if (initialSection) {
                    setExpanded({ [initialSection]: true });
                } else {
                    const all = {};
                    ENTRY_TYPES.forEach((t) => { all[t.key] = true; });
                    setExpanded(all);
                }
            })
            .catch((err) => {
                if (cancelled) return;
                setLoadError(true);
                toast.error(err.response?.data?.detail || 'Could not load medical history.');
            })
            .finally(() => { if (!cancelled) setIsLoading(false); });
        return () => { cancelled = true; };
    }, [patientId, initialSection]);

    // Scroll the requested section into view once the chart has rendered.
    useEffect(() => {
        if (!initialSection || !chart) return;
        const el = sectionRefs.current[initialSection];
        el?.scrollIntoView?.({ block: 'nearest' });
    }, [initialSection, chart]);

    const toggleSection = (key) => setExpanded((p) => ({ ...p, [key]: !p[key] }));

    const openFullRecord = () => {
        const params = new URLSearchParams({ patient_id: String(patientId) });
        if (initialSection) params.set('entry_type', initialSection);
        navigate(`/app/medical-history?${params.toString()}`);
        onClose();
    };

    const getEntries = (typeKey) => chart?.[ENTRY_TYPE_TO_CHART_FIELD[typeKey]] || [];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true" aria-label="Patient medical history">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight truncate">
                                {chart ? chart.patient_name : 'Medical history'}
                            </h3>
                            <span className="badge-success shrink-0"><ShieldCheck size={11} /> KDPA 2019</span>
                        </div>
                        {chart && (
                            <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
                                <span className="font-mono">{chart.opd_number}</span>
                                <span>Blood group: <span className="font-semibold text-ink-700 dark:text-ink-200">{chart.blood_group || '—'}</span></span>
                            </p>
                        )}
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full shrink-0">
                        <X size={18} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-5 space-y-3 bg-ink-50/40 dark:bg-ink-800/40 custom-scrollbar">
                    {isLoading ? (
                        <div className="text-center py-10 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} /> Loading medical history&hellip;</div>
                    ) : loadError ? (
                        <div className="text-center py-10 text-ink-400">Could not load this patient's history.</div>
                    ) : (
                        <>
                            {ENTRY_TYPES.map((type) => {
                                const entries = getEntries(type.key);
                                const isOpen = !!expanded[type.key];
                                const colorClass = ENTRY_TYPE_COLOR_CLASSES[type.color];
                                return (
                                    <div key={type.key} ref={(el) => { sectionRefs.current[type.key] = el; }} className="card overflow-hidden scroll-mt-4">
                                        <button type="button" onClick={() => toggleSection(type.key)} className="w-full flex items-center justify-between p-3.5 hover:bg-ink-50/50 dark:hover:bg-ink-800/50 transition-colors">
                                            <div className="flex items-center gap-2.5">
                                                <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${colorClass}`}>
                                                    {type.icon} {type.label}
                                                </span>
                                                <span className="badge-neutral">{entries.length}</span>
                                            </div>
                                            {isOpen ? <ChevronDown size={15} className="text-ink-400" /> : <ChevronRight size={15} className="text-ink-400" />}
                                        </button>
                                        {isOpen && (
                                            <div className="border-t border-ink-100 dark:border-ink-800 p-3.5">
                                                {entries.length === 0 ? (
                                                    <p className="text-xs text-ink-400 italic text-center py-2">No {type.label.toLowerCase()} entries recorded.</p>
                                                ) : (
                                                    <div className="space-y-2">
                                                        {entries.map((entry) => (
                                                            <div key={entry.entry_id} className={`p-3 rounded-xl border text-sm ${entry.is_sensitive ? 'border-red-200 dark:border-red-500/20 bg-red-50/50 dark:bg-red-500/10' : 'border-ink-100 dark:border-ink-800 bg-ink-50/50 dark:bg-ink-800/40'}`}>
                                                                <div className="flex flex-wrap items-center gap-2 mb-1">
                                                                    <h4 className="font-semibold text-ink-900 dark:text-white">{entry.title}</h4>
                                                                    {entry.is_sensitive && (
                                                                        <span className="flex items-center gap-1 text-2xs font-bold bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-300 px-2 py-0.5 rounded-full border border-red-200 dark:border-red-500/20">
                                                                            <Lock size={9} /> Sensitive
                                                                        </span>
                                                                    )}
                                                                    {entry.severity && entry.severity !== 'N/A' && (
                                                                        <span className="text-2xs font-bold px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300">{entry.severity}</span>
                                                                    )}
                                                                </div>
                                                                <p className="text-ink-700 dark:text-ink-200">{entry.description}</p>
                                                                {entry.event_date && <p className="text-2xs text-ink-400 mt-1">📅 {entry.event_date}</p>}
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            <VisitHistoryList visits={chart?.recent_visits || []} />
                        </>
                    )}
                </div>

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end bg-ink-50/40 dark:bg-ink-800/40 shrink-0">
                    <button type="button" onClick={openFullRecord} className="btn-secondary cursor-pointer">
                        <ExternalLink size={14} /> Open full record
                    </button>
                </div>
            </div>
        </div>
    );
}
