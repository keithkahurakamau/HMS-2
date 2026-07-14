import React, { useState, useEffect, useRef, useId } from 'react';
import { X, StickyNote, Plus } from 'lucide-react';
import { apiClient } from '../api/client';

const MAX_CODES = 10;

/**
 * Multi-select ICD-10 picker. Type-ahead against /clinical/icd10/search;
 * each pick becomes a removable chip. The first chip is the primary
 * diagnosis. Parent owns the list via `codes` / `onChange`.
 *
 * Besides catalogue codes, the typed text can always be added as a custom
 * diagnosis ({ code: null, description, custom: true }) — rendered with a
 * "Note" badge. Custom entries persist into the free-text `diagnosis`
 * column, never `icd10_code` (see utils/diagnosisMapping.js), because the
 * history endpoints parse `icd10_code` as a comma-separated code list.
 *
 * Keyboard: ArrowUp/ArrowDown highlight a row, Enter picks it (or adds the
 * typed text as custom when nothing is highlighted), Escape closes.
 */
export default function IcdDiagnosisPicker({ codes, onChange }) {
    const [search, setSearch] = useState('');
    const [results, setResults] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [limitHit, setLimitHit] = useState(false);
    // -1 = nothing highlighted; 0..results.length-1 = catalogue rows;
    // results.length = the trailing "add as custom" row.
    const [activeIdx, setActiveIdx] = useState(-1);
    const rootRef = useRef(null);
    const listboxId = useId();

    const term = search.trim();
    const open = showDropdown && term.length >= 2;

    useEffect(() => {
        if (!showDropdown || search.trim().length < 2) return undefined;
        const timer = setTimeout(async () => {
            try {
                const res = await apiClient.get('/clinical/icd10/search', { params: { q: search } });
                setResults(res.data || []);
            } catch {
                setResults([]);
            }
            setActiveIdx(-1);
        }, 250);
        return () => clearTimeout(timer);
    }, [search, showDropdown]);

    // Close when the user clicks anywhere outside the picker.
    useEffect(() => {
        if (!open) return undefined;
        const onDocMouseDown = (e) => {
            if (rootRef.current && !rootRef.current.contains(e.target)) {
                setShowDropdown(false);
            }
        };
        document.addEventListener('mousedown', onDocMouseDown);
        return () => document.removeEventListener('mousedown', onDocMouseDown);
    }, [open]);

    const closeAndClear = () => {
        setShowDropdown(false);
        setSearch('');
        setActiveIdx(-1);
    };

    const addCode = (r) => {
        closeAndClear();
        if (codes.some((c) => c.code === r.code)) return;
        if (codes.length >= MAX_CODES) {
            setLimitHit(true);
            return;
        }
        setLimitHit(false);
        onChange([...codes, { code: r.code, description: r.description }]);
    };

    const addCustom = (text) => {
        const value = text.trim();
        closeAndClear();
        if (!value) return;
        // Dedupe against existing custom texts (case-insensitive) and codes.
        const lower = value.toLowerCase();
        if (codes.some((c) => (c.custom && c.description.toLowerCase() === lower)
            || (c.code && c.code.toLowerCase() === lower))) return;
        if (codes.length >= MAX_CODES) {
            setLimitHit(true);
            return;
        }
        setLimitHit(false);
        onChange([...codes, { code: null, description: value, custom: true }]);
    };

    const removeChip = (target) => {
        setLimitHit(false);
        onChange(codes.filter((c) => c !== target));
    };

    const handleKeyDown = (e) => {
        if (!open) {
            if (e.key === 'Escape') setShowDropdown(false);
            return;
        }
        const lastIdx = results.length; // the "add as custom" row
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIdx((i) => Math.min(i + 1, lastIdx));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIdx((i) => Math.max(i - 1, -1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIdx >= 0 && activeIdx < results.length) addCode(results[activeIdx]);
            else addCustom(term);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            setShowDropdown(false);
            setActiveIdx(-1);
        }
    };

    const optionId = (idx) => `${listboxId}-opt-${idx}`;
    const optionClass = (idx) => `block w-full text-left px-4 py-2 text-sm cursor-pointer ${
        activeIdx === idx ? 'bg-brand-50 dark:bg-brand-500/15' : 'hover:bg-brand-50 dark:hover:bg-brand-500/15'
    }`;

    return (
        <div className="relative" ref={rootRef}>
            <label htmlFor="clinic-diagnoses-icd-10" className="label">Diagnoses (ICD-10)</label>
            <input
                id="clinic-diagnoses-icd-10"
                type="text"
                role="combobox"
                aria-expanded={open}
                aria-controls={listboxId}
                aria-activedescendant={activeIdx >= 0 ? optionId(activeIdx) : undefined}
                aria-autocomplete="list"
                value={search}
                onChange={(e) => {
                    const value = e.target.value;
                    setSearch(value);
                    setShowDropdown(true);
                    setActiveIdx(-1);
                    // Clear at event time (not in the effect) so a fresh search
                    // never flashes the previous term's results.
                    if (value.trim().length < 2) setResults([]);
                }}
                onFocus={() => setShowDropdown(true)}
                onKeyDown={handleKeyDown}
                className="input"
                placeholder="Type to search ICD-10 codes, or add your own wording…"
            />
            {open && (
                <div
                    id={listboxId}
                    role="listbox"
                    aria-label="Diagnosis suggestions"
                    className="absolute z-30 w-full mt-1 bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-xl shadow-elevated max-h-48 overflow-y-auto custom-scrollbar"
                >
                    {results.map((r, idx) => (
                        <button
                            type="button"
                            role="option"
                            aria-selected={activeIdx === idx}
                            id={optionId(idx)}
                            tabIndex={-1}
                            key={r.code}
                            onClick={() => addCode(r)}
                            className={`${optionClass(idx)} dark:text-ink-200`}
                        >
                            <span className="font-mono font-semibold">{r.code}</span> — {r.description}
                        </button>
                    ))}
                    {results.length === 0 && (
                        <div className="px-4 pt-3 pb-1 text-sm text-ink-500 dark:text-ink-400">No catalogue match.</div>
                    )}
                    <button
                        type="button"
                        role="option"
                        aria-selected={activeIdx === results.length}
                        id={optionId(results.length)}
                        tabIndex={-1}
                        onClick={() => addCustom(term)}
                        className={`${optionClass(results.length)} border-t border-ink-100 dark:border-ink-800 text-brand-700 dark:text-brand-300`}
                    >
                        <Plus size={13} className="inline -mt-0.5 mr-1" aria-hidden="true" />
                        Add "{term}" as custom diagnosis (saved as a note)
                    </button>
                </div>
            )}
            {limitHit && (
                <p className="text-xs text-rose-600 dark:text-rose-400 mt-1">Maximum of 10 diagnoses per visit.</p>
            )}
            {codes.length > 0 && (
                <ul className="flex flex-wrap gap-2 mt-2">
                    {codes.map((c, idx) => (
                        <li key={c.code ?? `note:${c.description}`} className="flex items-center gap-2 pl-2 pr-1 py-1 rounded-lg border border-brand-200 dark:border-brand-500/30 bg-brand-50 dark:bg-brand-500/10 text-xs text-brand-800 dark:text-brand-200 max-w-full">
                            {c.custom ? (
                                <span className="flex items-center gap-1 shrink-0 px-1.5 py-0.5 rounded bg-ink-200/70 dark:bg-ink-700 text-ink-700 dark:text-ink-200 text-2xs font-semibold uppercase tracking-wide">
                                    <StickyNote size={10} aria-hidden="true" /> Note
                                </span>
                            ) : (
                                <span className="font-mono font-semibold shrink-0">{c.code}</span>
                            )}
                            <span className="truncate" title={c.description}>{c.description}</span>
                            {idx === 0 && (
                                <span className="shrink-0 px-1.5 py-0.5 rounded bg-brand-600 text-white text-2xs font-semibold uppercase tracking-wide">Primary</span>
                            )}
                            <button
                                type="button"
                                onClick={() => removeChip(c)}
                                aria-label={`Remove diagnosis ${c.code || c.description}`}
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
