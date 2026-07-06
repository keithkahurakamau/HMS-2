import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { apiClient } from '../api/client';

const MAX_CODES = 10;

/**
 * Multi-select ICD-10 picker. Type-ahead against /clinical/icd10/search;
 * each pick becomes a removable chip. The first chip is the primary
 * diagnosis. Parent owns the list via `codes` / `onChange`.
 */
export default function IcdDiagnosisPicker({ codes, onChange }) {
    const [search, setSearch] = useState('');
    const [results, setResults] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [limitHit, setLimitHit] = useState(false);

    useEffect(() => {
        if (!showDropdown || search.trim().length < 2) {
            setResults([]);
            return;
        }
        const timer = setTimeout(async () => {
            try {
                const res = await apiClient.get('/clinical/icd10/search', { params: { q: search } });
                setResults(res.data || []);
            } catch {
                setResults([]);
            }
        }, 250);
        return () => clearTimeout(timer);
    }, [search, showDropdown]);

    const addCode = (r) => {
        setShowDropdown(false);
        setSearch('');
        if (codes.some((c) => c.code === r.code)) return;
        if (codes.length >= MAX_CODES) {
            setLimitHit(true);
            return;
        }
        setLimitHit(false);
        onChange([...codes, { code: r.code, description: r.description }]);
    };

    const removeCode = (code) => {
        setLimitHit(false);
        onChange(codes.filter((c) => c.code !== code));
    };

    return (
        <div className="relative">
            <label htmlFor="clinic-diagnoses-icd-10" className="label">Diagnoses (ICD-10)</label>
            <input
                id="clinic-diagnoses-icd-10"
                type="text"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setShowDropdown(true); }}
                onFocus={() => setShowDropdown(true)}
                className="input"
                placeholder="Type to search ICD-10 codes — add as many as apply…"
            />
            {showDropdown && search.trim().length >= 2 && (
                <div className="absolute z-30 w-full mt-1 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-xl shadow-elevated max-h-48 overflow-y-auto custom-scrollbar">
                    {results.length > 0 ? results.map((r) => (
                        <button
                            type="button"
                            key={r.code}
                            onClick={() => addCode(r)}
                            className="block w-full text-left px-4 py-2 hover:bg-brand-50 dark:hover:bg-brand-500/15 text-sm dark:text-ink-200"
                        >
                            <span className="font-mono font-semibold">{r.code}</span> — {r.description}
                        </button>
                    )) : <div className="px-4 py-3 text-sm text-ink-500 dark:text-ink-400">No codes found.</div>}
                </div>
            )}
            {limitHit && (
                <p className="text-xs text-rose-600 dark:text-rose-400 mt-1">Maximum of 10 diagnoses per visit.</p>
            )}
            {codes.length > 0 && (
                <ul className="flex flex-wrap gap-2 mt-2">
                    {codes.map((c, idx) => (
                        <li key={c.code} className="flex items-center gap-2 pl-2 pr-1 py-1 rounded-lg border border-brand-200 dark:border-brand-500/30 bg-brand-50 dark:bg-brand-500/10 text-xs text-brand-800 dark:text-brand-200 max-w-full">
                            <span className="font-mono font-semibold shrink-0">{c.code}</span>
                            <span className="truncate" title={c.description}>{c.description}</span>
                            {idx === 0 && (
                                <span className="shrink-0 px-1.5 py-0.5 rounded bg-brand-600 text-white text-2xs font-semibold uppercase tracking-wide">Primary</span>
                            )}
                            <button
                                type="button"
                                onClick={() => removeCode(c.code)}
                                aria-label={`Remove diagnosis ${c.code}`}
                                className="text-brand-400 hover:text-rose-600 shrink-0"
                            >
                                <X size={13} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
