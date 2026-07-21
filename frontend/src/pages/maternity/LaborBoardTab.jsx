import { useCallback, useEffect, useRef, useState } from 'react';
import { getLaborBoard, getPartograph } from './api';
import PartographChart from './PartographChart';
import PartographEntryForm from './PartographEntryForm';
import StartLaborForm from './StartLaborForm';

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
  // The entry being corrected (prefills PartographEntryForm and sets
  // corrects_entry_id on submit); null means the plain "New entry" path.
  const [correctingEntry, setCorrectingEntry] = useState(null);
  const [showStartLabor, setShowStartLabor] = useState(false);
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

  // Fires after StartLaborForm's linkLabor() call succeeds: refresh the
  // board and immediately select the newly-started labor so the midwife
  // lands straight on its (still-empty) partograph rather than back on the
  // bare board list.
  const handleStarted = useCallback((result, episode) => {
    setShowStartLabor(false);
    refreshBoard();
    open({ labor_admission_id: result.labor_admission_id, patient_name: episode?.patient_name || '' });
  }, [refreshBoard, open]);

  return (
    <div className="space-y-4">
      {error && <p className="print:hidden text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      <section aria-label="Labor board"
               className="print:hidden rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-900 dark:text-white">In labor</h2>
          <button
            type="button"
            data-tour="mat-start-labor"
            onClick={() => setShowStartLabor(true)}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Start labor
          </button>
        </div>
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
        <section aria-label="Partograph" data-tour="mat-partograph"
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
                onClick={() => { setCorrectingEntry(null); setShowEntry(true); }}
                className="print:hidden rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                New entry
              </button>
            </div>
          </div>
          {chart && chart.labor_admission_id === selected.labor_admission_id ? (
            <>
              <div className="mt-3 overflow-x-auto">
                <PartographChart entries={chart.entries} activeStart={chart.active_labor_started_at} />
              </div>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-ink-500 dark:text-ink-400">
                      <th className="py-1 pr-2 font-medium">Time</th>
                      <th className="py-1 pr-2 font-medium">Dilation</th>
                      <th className="py-1 pr-2 font-medium">Descent</th>
                      <th className="py-1 pr-2 font-medium">Contractions</th>
                      <th className="py-1 pr-2 font-medium">FHR</th>
                      <th className="py-1 pr-2 font-medium">Liquor</th>
                      <th className="py-1 pr-2 font-medium">BP</th>
                      <th className="py-1 pr-2 font-medium">Pulse</th>
                      <th className="py-1 pr-2 font-medium">Temp</th>
                      <th className="print:hidden py-1 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(chart.entries || []).map((e) => (
                      <tr
                        key={e.entry_id}
                        className={`border-t border-ink-100 dark:border-ink-800 ${
                          e.superseded
                            ? 'line-through text-ink-400 dark:text-ink-600'
                            : 'text-ink-900 dark:text-white'
                        }`}
                      >
                        <td className="py-1 pr-2">
                          {new Date(e.recorded_at).toLocaleString()}
                          {e.superseded && (
                            <span className="no-underline ml-2 inline-block rounded-full bg-ink-100 dark:bg-ink-800 px-1.5 py-0.5 text-[10px] font-medium text-ink-600 dark:text-ink-400">
                              Superseded
                            </span>
                          )}
                        </td>
                        <td className="py-1 pr-2">{e.cervical_dilation_cm ?? '—'}</td>
                        <td className="py-1 pr-2">{e.descent_fifths ?? '—'}</td>
                        <td className="py-1 pr-2">{e.contractions_per_10min ?? '—'}</td>
                        <td className="py-1 pr-2">{e.fetal_heart_rate ?? '—'}</td>
                        <td className="py-1 pr-2">{e.liquor ?? '—'}</td>
                        <td className="py-1 pr-2">
                          {e.maternal_bp_systolic != null ? `${e.maternal_bp_systolic}/${e.maternal_bp_diastolic ?? '—'}` : '—'}
                        </td>
                        <td className="py-1 pr-2">{e.maternal_pulse ?? '—'}</td>
                        <td className="py-1 pr-2">{e.temperature_c ?? '—'}</td>
                        <td className="print:hidden py-1">
                          {!e.superseded && (
                            <button
                              type="button"
                              className="no-underline rounded-lg border border-ink-200 dark:border-ink-800 px-2 py-1 text-xs font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50"
                              onClick={() => { setCorrectingEntry(e); setShowEntry(true); }}
                            >
                              Correct
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {(chart.entries || []).length === 0 && (
                      <tr>
                        <td colSpan={10} className="py-2 text-ink-500 dark:text-ink-400">No entries recorded yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">Loading…</p>
          )}
        </section>
      )}

      {showEntry && selected && (
        <PartographEntryForm
          laborId={selected.labor_admission_id}
          correctingEntry={correctingEntry}
          onClose={() => { setShowEntry(false); setCorrectingEntry(null); }}
          onSaved={() => { setShowEntry(false); setCorrectingEntry(null); open(selected); refreshBoard(); }}
        />
      )}

      {showStartLabor && (
        <StartLaborForm
          onClose={() => setShowStartLabor(false)}
          onStarted={handleStarted}
        />
      )}
    </div>
  );
}
