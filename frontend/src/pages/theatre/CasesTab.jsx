import { useCallback, useEffect, useState } from 'react';
import { listCases, getCase } from './api';
import { errorText } from './errors';
import CaseForm from './CaseForm';
import CaseBoard from './CaseBoard';

const STATUSES = ['', 'Scheduled', 'InTheatre', 'Recovery', 'Completed', 'Cancelled'];

const CHIP = {
  Scheduled: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  InTheatre: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Recovery: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
  Completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  Cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

export default function CasesTab() {
  const [cases, setCases] = useState([]);
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    listCases(status ? { status } : {})
      .then((rows) => { setCases(rows || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load cases')));
  }, [status]);

  useEffect(() => { load(); }, [load]);

  const openCase = (id) => {
    getCase(id).then(setSelected).catch((err) => setError(errorText(err, 'Failed to open case')));
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="text-sm text-ink-700 dark:text-ink-300">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="input ml-2">
            {STATUSES.map((s) => <option key={s} value={s}>{s || 'All'}</option>)}
          </select>
        </label>
        <button type="button" onClick={() => setShowNew(true)}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
          New case
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <div className="overflow-hidden rounded-xl border border-ink-200/70 dark:border-ink-800">
          {cases.length === 0 ? (
            <p className="p-6 text-center text-sm text-ink-500 dark:text-ink-400">No cases.</p>
          ) : (
            <ul className="divide-y divide-ink-100 dark:divide-ink-800">
              {cases.map((c) => (
                <li key={c.case_id}>
                  <button type="button" onClick={() => openCase(c.case_id)}
                          className={`flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-ink-50 dark:hover:bg-ink-800/40 ${
                            selected?.case_id === c.case_id ? 'bg-brand-50 dark:bg-brand-900/20' : ''
                          }`}>
                    <span>
                      <span className="block text-sm font-medium text-ink-900 dark:text-white">
                        {c.patient_name || `Patient #${c.patient_id}`}
                      </span>
                      <span className="block text-xs text-ink-500 dark:text-ink-400">{c.procedure_name}</span>
                    </span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CHIP[c.status] || ''}`}>{c.status}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
          {selected ? (
            <CaseBoard caseObj={selected} onChanged={(updated) => { setSelected(updated); load(); }} />
          ) : (
            <p className="py-12 text-center text-sm text-ink-500 dark:text-ink-400">Select a case to view its board.</p>
          )}
        </div>
      </div>

      {showNew && (
        <CaseForm onClose={() => setShowNew(false)}
                  onSaved={(created) => { setShowNew(false); setSelected(created); load(); }} />
      )}
    </div>
  );
}
