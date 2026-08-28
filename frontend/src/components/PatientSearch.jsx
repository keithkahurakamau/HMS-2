import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { apiClient } from '../api/client';

// Reusable patient typeahead. Type a name, ID, OP number or phone, the
// patients API (`GET /patients/?search=`) matches all of them, pick from the
// dropdown. Calls onSelect(patient) with the chosen row. Replaces raw
// "Patient ID" number inputs so lookup is convenient everywhere.
export default function PatientSearch({
  onSelect,
  placeholder = 'Search patient by name, ID, OP No or phone…',
  autoFocus = false,
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState(null);
  const boxRef = useRef(null);

  // Debounced search; ignore stale responses via an alive flag.
  useEffect(() => {
    const q = query.trim();
    let alive = true;
    // All state updates live inside the debounced timer, so the effect body
    // has no synchronous setState (react-hooks/set-state-in-effect).
    const t = setTimeout(() => {
      if (picked || q.length < 2) { if (alive) setResults([]); return; }
      setLoading(true);
      apiClient.get('/patients/', { params: { search: q, limit: 8 } })
        .then((r) => { if (alive) { setResults(r.data || []); setOpen(true); } })
        .catch(() => { if (alive) setResults([]); })
        .finally(() => { if (alive) setLoading(false); });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [query, picked]);

  // Close on outside click.
  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const choose = (p) => {
    setPicked(p);
    setQuery(`${p.surname}, ${p.other_names}`);
    setOpen(false);
    onSelect(p);
  };

  const clear = () => {
    setPicked(null);
    setQuery('');
    setResults([]);
    onSelect(null);
  };

  return (
    <div ref={boxRef} className="relative">
      <div className="relative">
        <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
        <input
          type="text"
          value={query}
          autoFocus={autoFocus}
          onChange={(e) => { setPicked(null); setQuery(e.target.value); }}
          onFocus={() => results.length && setOpen(true)}
          placeholder={placeholder}
          aria-label="Search patient"
          role="combobox"
          aria-expanded={open}
          aria-controls="patient-search-results"
          className="w-full rounded-lg border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900 py-2 pl-9 pr-9 text-sm text-ink-900 dark:text-white placeholder-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        />
        {(query || picked) && (
          <button type="button" onClick={clear} aria-label="Clear patient search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800/60 hover:text-ink-700 dark:hover:text-ink-200">
            <X size={14} />
          </button>
        )}
      </div>

      {open && (
        <ul id="patient-search-results" role="listbox"
            className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-ink-200 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-overlay">
          {loading && <li className="px-3 py-2 text-sm text-ink-400">Searching…</li>}
          {!loading && results.length === 0 && (
            <li className="px-3 py-2 text-sm text-ink-400">No matches.</li>
          )}
          {results.map((p) => (
            <li key={p.patient_id} role="option" aria-selected="false">
              <button type="button" onClick={() => choose(p)}
                      className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-brand-50 dark:hover:bg-brand-900/20">
                <span className="font-medium text-ink-900 dark:text-white">{p.surname}, {p.other_names}</span>
                <span className="text-xs text-ink-500 dark:text-ink-400">
                  {p.outpatient_no ? `OP ${p.outpatient_no}` : `#${p.patient_id}`}{p.sex ? ` · ${p.sex}` : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
