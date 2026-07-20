import { useCallback, useEffect, useRef, useState } from 'react';
import { getLaborBoard, getPartograph } from './api';
import PartographChart from './PartographChart';
import PartographEntryForm from './PartographEntryForm';

const ALERT_BADGE = {
  ok: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  alert: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  action: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
};

export default function LaborBoardTab() {
  const [board, setBoard] = useState([]);
  const [selected, setSelected] = useState(null);
  const [chart, setChart] = useState(null);
  const [showEntry, setShowEntry] = useState(false);
  const [error, setError] = useState('');
  // Tracks the labor_admission_id of the most recently requested partograph so
  // that a late-resolving (out-of-order) fetch for a since-abandoned selection
  // can never overwrite the chart for whichever labor is selected now.
  const requestedLaborIdRef = useRef(null);

  const refreshBoard = useCallback(() => {
    Promise.resolve(getLaborBoard())
      .then((rows) => { setBoard(rows || []); setError(''); })
      .catch(() => setError('Failed to load labor board'));
  }, []);
  useEffect(() => { refreshBoard(); }, [refreshBoard]);

  const open = useCallback((row) => {
    setSelected(row);
    setChart(null); // clear stale chart immediately so it can never render under the new name
    requestedLaborIdRef.current = row.labor_admission_id;
    Promise.resolve(getPartograph(row.labor_admission_id))
      .then((data) => {
        // Ignore out-of-order responses: only apply if this is still the
        // latest requested labor, and the payload actually matches it.
        if (requestedLaborIdRef.current !== row.labor_admission_id) return;
        if (data && data.labor_admission_id !== row.labor_admission_id) return;
        setChart(data || null);
        setError('');
      })
      .catch(() => {
        if (requestedLaborIdRef.current !== row.labor_admission_id) return;
        setError('Failed to load partograph');
      });
  }, []);

  return (
    <div className="space-y-4">
      {error && <p className="print:hidden text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      <section aria-label="Labor board"
               className="print:hidden rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4">
        <h2 className="text-sm font-semibold text-ink-900 dark:text-white">In labor</h2>
        <ul className="mt-3 divide-y divide-ink-100 dark:divide-ink-800">
          {board.map((row) => (
            <li key={row.labor_admission_id}>
              <button
                type="button"
                onClick={() => open(row)}
                className="flex w-full items-center justify-between rounded-lg px-2 py-2 text-left hover:bg-ink-50 dark:hover:bg-ink-800/50"
              >
                <span className="font-medium text-ink-900 dark:text-white">{row.patient_name}</span>
                {row.latest && (
                  <span className={`rounded-full px-2 py-0.5 text-xs ${ALERT_BADGE[row.latest.alert_status] || ALERT_BADGE.ok}`}>
                    {row.latest.cervical_dilation_cm ?? '—'} cm · FHR {row.latest.fetal_heart_rate ?? '—'}
                  </span>
                )}
              </button>
            </li>
          ))}
          {board.length === 0 && (
            <li className="py-2 text-sm text-ink-500 dark:text-ink-400">No patients in labor.</li>
          )}
        </ul>
      </section>

      {selected && (
        <section aria-label="Partograph"
                 className="rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900 dark:text-white">
              Partograph — {selected.patient_name}
            </h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => window.print()}
                className="print:hidden rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50"
              >
                Print
              </button>
              <button
                type="button"
                onClick={() => setShowEntry(true)}
                className="print:hidden rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                New entry
              </button>
            </div>
          </div>
          {chart && chart.labor_admission_id === selected.labor_admission_id ? (
            <div className="mt-3 overflow-x-auto">
              <PartographChart entries={chart.entries} activeStart={chart.active_labor_started_at} />
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">Loading…</p>
          )}
        </section>
      )}

      {showEntry && selected && (
        <PartographEntryForm
          laborId={selected.labor_admission_id}
          onClose={() => setShowEntry(false)}
          onSaved={() => { setShowEntry(false); open(selected); refreshBoard(); }}
        />
      )}
    </div>
  );
}
