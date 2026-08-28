import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    Printer, FileText, Activity, AlertTriangle, Receipt, Pill,
    TestTube, ScanLine, BedDouble, Stethoscope, RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../api/client';
import { reprintPatientDocument } from '../utils/reprintDocument';
import { SkeletonTable } from './ui/Skeleton';

/**
 * PatientDocumentsPanel: every document previously issued to a patient, with
 * a one-click reprint.
 *
 * Reprints render from the *current* record rather than a stored file, so a
 * corrected result or an amended invoice prints correctly rather than
 * reproducing a stale copy. They also pick up the tenant's letterhead like any
 * other print. The server logs each reprint as a KDPA Section 26 data access.
 */

const KIND_META = {
    invoice: { icon: Receipt, label: 'Invoices' },
    prescription: { icon: Pill, label: 'Prescriptions' },
    lab_report: { icon: TestTube, label: 'Lab reports' },
    radiology_report: { icon: ScanLine, label: 'Radiology' },
    admission: { icon: BedDouble, label: 'Admissions' },
    visit_summary: { icon: Stethoscope, label: 'Visits' },
};

const formatDate = (value) => {
    if (!value) return '-';
    const d = new Date(value);
    return Number.isNaN(d.getTime())
        ? value
        : d.toLocaleDateString('en-KE', { year: 'numeric', month: 'short', day: '2-digit' });
};

export default function PatientDocumentsPanel({ patientId }) {
    const [documents, setDocuments] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [kindFilter, setKindFilter] = useState('all');
    const [printingKey, setPrintingKey] = useState(null);

    const load = useCallback(async () => {
        if (!patientId) return;
        setIsLoading(true);
        setError(null);
        try {
            const res = await apiClient.get(`/patients/${patientId}/documents`);
            setDocuments(res.data?.documents || []);
        } catch (e) {
            setError(e.response?.data?.detail || 'Could not load this patient’s documents.');
            setDocuments([]);
        } finally {
            setIsLoading(false);
        }
    }, [patientId]);

    useEffect(() => { load(); }, [load]);

    // One chip per kind actually present, so a patient with only invoices
    // isn't shown five empty filters.
    const availableKinds = useMemo(() => {
        const counts = new Map();
        for (const d of documents) counts.set(d.kind, (counts.get(d.kind) || 0) + 1);
        return [...counts.entries()].map(([kind, count]) => ({ kind, count }));
    }, [documents]);

    const visible = useMemo(
        () => (kindFilter === 'all' ? documents : documents.filter((d) => d.kind === kindFilter)),
        [documents, kindFilter],
    );

    const handlePrint = async (doc) => {
        const key = `${doc.kind}:${doc.id}`;
        setPrintingKey(key);
        try {
            const ok = await reprintPatientDocument(apiClient, patientId, doc.kind, doc.id);
            if (!ok) toast.error(`${doc.kind} documents can’t be reprinted yet.`);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not reprint that document.');
        } finally {
            setPrintingKey(null);
        }
    };

    return (
        <section data-tour="patient-documents" className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/40 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    <span className="text-brand-600"><FileText size={16} /></span>
                    <h2 className="text-sm font-semibold text-ink-900 dark:text-white tracking-tight">
                        Documents &amp; reprints
                    </h2>
                    {!isLoading && documents.length > 0 && (
                        <span className="badge-neutral">{documents.length}</span>
                    )}
                </div>
                <button
                    type="button"
                    onClick={load}
                    disabled={isLoading}
                    aria-label="Refresh documents"
                    className="p-1.5 rounded-lg text-ink-500 hover:text-brand-700 hover:bg-brand-50 dark:hover:bg-ink-800 transition-colors cursor-pointer disabled:cursor-wait"
                >
                    <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                </button>
            </div>

            <div className="p-5 space-y-4">
                <p className="text-xs text-ink-500 dark:text-ink-400 leading-relaxed">
                    Anything already issued to this patient can be printed again. Reprints are
                    generated from the current record, so corrections are included, and each one
                    is written to the access log.
                </p>

                {error && (
                    <p className="text-xs text-rose-600 flex items-start gap-1.5">
                        <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {error}
                    </p>
                )}

                {isLoading ? (
                    <div className="flex items-center gap-2 text-sm text-ink-400 dark:text-ink-500 py-4">
                        <SkeletonTable rows={4} cols={3} label="Loading" /></div>
                ) : documents.length === 0 && !error ? (
                    <p className="text-sm text-ink-400 dark:text-ink-500 py-3">
                        No documents have been issued to this patient yet.
                    </p>
                ) : (
                    <>
                        {availableKinds.length > 1 && (
                            <div className="flex flex-wrap gap-2" role="group" aria-label="Filter documents by type">
                                <FilterChip active={kindFilter === 'all'} onClick={() => setKindFilter('all')}
                                    label="All" count={documents.length} />
                                {availableKinds.map(({ kind, count }) => (
                                    <FilterChip
                                        key={kind}
                                        active={kindFilter === kind}
                                        onClick={() => setKindFilter(kind)}
                                        label={KIND_META[kind]?.label || kind}
                                        count={count}
                                        icon={KIND_META[kind]?.icon}
                                    />
                                ))}
                            </div>
                        )}

                        <ul className="divide-y divide-ink-100 dark:divide-ink-800">
                            {visible.map((doc) => {
                                const Icon = KIND_META[doc.kind]?.icon || FileText;
                                const key = `${doc.kind}:${doc.id}`;
                                const busy = printingKey === key;
                                return (
                                    <li key={key} className="py-3 flex items-center gap-3">
                                        <span className="size-9 shrink-0 rounded-xl bg-brand-50 dark:bg-brand-500/10 text-brand-600 flex items-center justify-center">
                                            <Icon size={16} />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-semibold text-ink-900 dark:text-white truncate">
                                                {doc.title}
                                            </p>
                                            <p className="text-xs text-ink-500 dark:text-ink-400 truncate">
                                                {formatDate(doc.date)}
                                                {doc.summary ? ` · ${doc.summary}` : ''}
                                            </p>
                                        </div>
                                        {doc.status && (
                                            <span className="badge-neutral hidden sm:inline-flex shrink-0">{doc.status}</span>
                                        )}
                                        <button
                                            type="button"
                                            onClick={() => handlePrint(doc)}
                                            disabled={busy}
                                            className="btn-secondary shrink-0 cursor-pointer disabled:cursor-wait"
                                        >
                                            {busy
                                                ? <Activity size={14} className="animate-spin" />
                                                : <Printer size={14} />}
                                            <span className="hidden sm:inline">Print</span>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </>
                )}
            </div>
        </section>
    );
}

function FilterChip({ active, onClick, label, count, icon: Icon }) {
    return (
        <button
            type="button"
            onClick={onClick}
            aria-pressed={active}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-colors cursor-pointer ${
                active
                    ? 'bg-brand-600 text-white'
                    : 'bg-white dark:bg-ink-900 ring-1 ring-ink-200 dark:ring-ink-700 text-ink-600 dark:text-ink-300 hover:ring-brand-300'
            }`}
        >
            {Icon && <Icon size={12} />}
            {label}
            <span className={active ? 'text-white/70' : 'text-ink-400'}>{count}</span>
        </button>
    );
}
