import React, { useState } from 'react';
import { Clock, ChevronDown, ChevronRight, Pill, TestTube, Image as ImageIcon } from 'lucide-react';
import { apiClient } from '../api/client';

const VITAL_LABELS = [
    ['blood_pressure', 'BP'], ['heart_rate', 'HR'], ['respiratory_rate', 'RR'],
    ['temperature', 'Temp °C'], ['spo2', 'SpO2 %'], ['weight_kg', 'Weight kg'],
    ['height_cm', 'Height cm'], ['calculated_bmi', 'BMI'], ['blood_glucose', 'RBS mmol/L'],
];

function Section({ title, children }) {
    return (
        <div>
            <h5 className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400 mb-1">{title}</h5>
            {children}
        </div>
    );
}

/**
 * Full clinic visit history. Summary rows come from the chart payload
 * (all visits); expanding a row lazy-loads /clinical/record/{id} once
 * and caches it for the life of the page.
 */
export default function VisitHistoryList({ visits }) {
    const [openId, setOpenId] = useState(null);
    const [details, setDetails] = useState({});   // record_id -> detail
    const [loadingId, setLoadingId] = useState(null);
    const [errorId, setErrorId] = useState(null);

    const fetchDetail = async (recordId) => {
        setLoadingId(recordId);
        setErrorId(null);
        try {
            const res = await apiClient.get(`/clinical/record/${recordId}`);
            setDetails((prev) => ({ ...prev, [recordId]: res.data }));
        } catch {
            setErrorId(recordId);
        } finally {
            setLoadingId(null);
        }
    };

    const toggle = (recordId) => {
        const next = openId === recordId ? null : recordId;
        setOpenId(next);
        if (next && !details[next]) fetchDetail(next);
    };

    return (
        <div className="bg-white dark:bg-ink-900 border border-slate-200 dark:border-ink-800 rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-100 dark:border-ink-800 bg-slate-50 dark:bg-ink-800/40">
                <h3 className="font-bold text-slate-800 dark:text-ink-200 flex items-center gap-2">
                    <Clock size={16} /> Visit History ({visits.length})
                </h3>
            </div>
            <div className="p-4 space-y-2 max-h-[32rem] overflow-y-auto custom-scrollbar">
                {visits.length === 0 ? (
                    <p className="text-sm text-slate-400 dark:text-ink-400 italic text-center py-4">No clinical visits recorded.</p>
                ) : visits.map((visit) => {
                    const isOpen = openId === visit.record_id;
                    const detail = details[visit.record_id];
                    return (
                        <div key={visit.record_id} className="rounded-xl border border-slate-100 dark:border-ink-800 overflow-hidden">
                            <button
                                type="button"
                                onClick={() => toggle(visit.record_id)}
                                aria-expanded={isOpen}
                                className="w-full flex gap-3 items-start p-3 bg-slate-50 dark:bg-ink-800/40 text-left hover:bg-slate-100 dark:hover:bg-ink-800/70"
                            >
                                {isOpen ? <ChevronDown size={15} className="mt-0.5 shrink-0" /> : <ChevronRight size={15} className="mt-0.5 shrink-0" />}
                                <span className="flex-1 min-w-0">
                                    <span className="flex justify-between items-start gap-2">
                                        <span className="font-bold text-sm text-slate-800 dark:text-ink-200 truncate">{visit.diagnosis || 'No diagnosis recorded'}</span>
                                        <span className="flex items-center gap-2 shrink-0">
                                            {visit.record_status && (
                                                <span className="px-1.5 py-0.5 rounded-md bg-slate-100 dark:bg-ink-800 border border-slate-200 dark:border-ink-700 text-2xs font-semibold uppercase tracking-wide text-slate-500 dark:text-ink-400">
                                                    {visit.record_status}
                                                </span>
                                            )}
                                            <span className="text-xs text-slate-400 dark:text-ink-400">{visit.date ? new Date(visit.date).toLocaleDateString() : '—'}</span>
                                        </span>
                                    </span>
                                    <span className="block text-xs text-slate-500 dark:text-ink-400 mt-0.5">
                                        <span className="font-medium">Complaint:</span> {visit.chief_complaint || '—'} · <span className="font-medium">Dr:</span> {visit.doctor}
                                    </span>
                                </span>
                            </button>

                            {isOpen && (
                                <div className="p-4 space-y-4 border-t border-slate-100 dark:border-ink-800">
                                    {loadingId === visit.record_id && (
                                        <p className="text-sm text-slate-400 dark:text-ink-400 italic">Loading visit details…</p>
                                    )}
                                    {errorId === visit.record_id && (
                                        <p className="text-sm text-rose-600 dark:text-rose-400">
                                            Could not load this visit.{' '}
                                            <button type="button" className="underline font-medium" onClick={() => fetchDetail(visit.record_id)}>Retry</button>
                                        </p>
                                    )}
                                    {detail && (
                                        <>
                                            <Section title="Vitals">
                                                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                                                    {VITAL_LABELS.map(([key, label]) => (
                                                        <div key={key} className="rounded-lg bg-slate-50 dark:bg-ink-800/40 p-2">
                                                            <p className="text-2xs text-slate-400 dark:text-ink-400">{label}</p>
                                                            <p className="text-sm font-semibold text-slate-800 dark:text-ink-200">{detail.vitals?.[key] ?? '—'}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            </Section>
                                            {detail.history_of_present_illness && (
                                                <Section title="History of present illness">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.history_of_present_illness}</p>
                                                </Section>
                                            )}
                                            {detail.review_of_systems && Object.keys(detail.review_of_systems).length > 0 && (
                                                <Section title="Review of systems">
                                                    <ul className="space-y-0.5">
                                                        {Object.entries(detail.review_of_systems)
                                                            .filter(([, finding]) => finding)
                                                            .map(([system, finding]) => (
                                                                <li key={system} className="text-sm text-slate-700 dark:text-ink-300">
                                                                    <span className="font-semibold">{system}:</span> {finding}
                                                                </li>
                                                            ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.physical_examination && (
                                                <Section title="Physical examination">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.physical_examination}</p>
                                                </Section>
                                            )}
                                            <Section title="Diagnoses">
                                                {detail.icd10_codes?.length ? (
                                                    <ul className="flex flex-wrap gap-1.5">
                                                        {detail.icd10_codes.map((code) => (
                                                            <li key={code} className="px-2 py-0.5 rounded-md bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/30 font-mono text-xs font-semibold text-brand-800 dark:text-brand-200">{code}</li>
                                                        ))}
                                                    </ul>
                                                ) : null}
                                                <p className="text-sm text-slate-700 dark:text-ink-300 mt-1">{detail.diagnosis || '—'}</p>
                                            </Section>
                                            {detail.prescriptions?.length > 0 && (
                                                <Section title="Prescriptions">
                                                    <ul className="space-y-1">
                                                        {detail.prescriptions.map((p, i) => (
                                                            <li key={i} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <Pill size={13} className="text-accent-600 dark:text-accent-400 shrink-0" />
                                                                <span><span className="font-semibold">{p.drug}</span> {p.formulation} — {p.dosage}, {p.frequency}, {p.duration}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                    {detail.prescription_notes && (
                                                        <p className="text-sm text-slate-500 dark:text-ink-400 italic mt-1.5">{detail.prescription_notes}</p>
                                                    )}
                                                </Section>
                                            )}
                                            {!(detail.prescriptions?.length > 0) && detail.prescription_notes && (
                                                <Section title="Prescription notes">
                                                    <p className="text-sm text-slate-500 dark:text-ink-400 italic">{detail.prescription_notes}</p>
                                                </Section>
                                            )}
                                            {detail.lab_tests?.length > 0 && (
                                                <Section title="Lab tests">
                                                    <ul className="space-y-1">
                                                        {detail.lab_tests.map((t) => (
                                                            <li key={t.test_id} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <TestTube size={13} className="text-brand-600 dark:text-brand-400 shrink-0" />
                                                                <span><span className="font-semibold">{t.test_name}</span> · {t.status}{t.result_summary ? ` — ${t.result_summary}` : ''}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.radiology?.length > 0 && (
                                                <Section title="Imaging (same day)">
                                                    <ul className="space-y-1">
                                                        {detail.radiology.map((r) => (
                                                            <li key={r.request_id} className="text-sm text-slate-700 dark:text-ink-300 flex items-center gap-2">
                                                                <ImageIcon size={13} className="text-brand-600 dark:text-brand-400 shrink-0" />
                                                                <span><span className="font-semibold">{r.exam_type}</span> · {r.status}{r.conclusion ? ` — ${r.conclusion}` : ''}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </Section>
                                            )}
                                            {detail.internal_notes && (
                                                <Section title="Internal notes">
                                                    <p className="text-sm text-slate-700 dark:text-ink-300 whitespace-pre-wrap">{detail.internal_notes}</p>
                                                </Section>
                                            )}
                                            {detail.follow_up_date && (
                                                <p className="text-xs text-slate-500 dark:text-ink-400">Follow-up: {new Date(detail.follow_up_date).toLocaleDateString()}</p>
                                            )}
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
