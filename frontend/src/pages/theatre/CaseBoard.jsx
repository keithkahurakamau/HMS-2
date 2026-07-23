import { useEffect, useState } from 'react';
import {
  addChecklistRun, cancelCase, completeCase, getCase, startCase, toRecovery, listChecklists,
} from './api';
import { errorText } from './errors';
import OperativeNoteForm from './OperativeNoteForm';
import AnaesthesiaForm from './AnaesthesiaForm';
import CaseExtras from './CaseExtras';

const FLOW = ['Scheduled', 'InTheatre', 'Recovery', 'Completed'];
const PHASES = [
  { key: 'SignIn', label: 'Sign In (before induction)' },
  { key: 'TimeOut', label: 'Time Out (before incision)' },
  { key: 'SignOut', label: 'Sign Out (before leaving theatre)' },
];

function Stepper({ status }) {
  const cancelled = status === 'Cancelled';
  const idx = FLOW.indexOf(status);
  return (
    <ol className="flex items-center gap-2 text-xs" aria-label="Case progress">
      {FLOW.map((s, i) => (
        <li key={s} className={`rounded-full px-2.5 py-1 font-medium ${
          !cancelled && i <= idx ? 'bg-brand-600 text-white' : 'bg-ink-100 dark:bg-ink-800 text-ink-500 dark:text-ink-400'
        }`}>{s}</li>
      ))}
      {cancelled && <li className="rounded-full bg-rose-600 px-2.5 py-1 font-medium text-white">Cancelled</li>}
    </ol>
  );
}

export default function CaseBoard({ caseObj, onChanged }) {
  const [checklists, setChecklists] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    listChecklists()
      .then((rows) => setChecklists(rows || []))
      .catch(() => setChecklists([]));
  }, []);

  const signed = (phase) => (caseObj.checklist_runs || []).some((r) => r.phase === phase && r.checked);
  const isTerminal = caseObj.status === 'Completed' || caseObj.status === 'Cancelled';

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      onChanged(await getCase(caseObj.case_id));
    } catch (err) {
      setError(errorText(err, 'Action failed'));
    } finally {
      setBusy(false);
    }
  };

  const doCancel = () => {
    const reason = window.prompt('Reason for cancelling this case?');
    if (reason) run(() => cancelCase(caseObj.case_id, { reason }));
  };

  return (
    <section className="space-y-4" aria-label="Case detail">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink-900 dark:text-white">
            {caseObj.patient_name || `Patient #${caseObj.patient_id}`} · {caseObj.procedure_name}
          </div>
          <div className="mt-1"><Stepper status={caseObj.status} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {caseObj.status === 'Scheduled' && (
            <button type="button" disabled={busy || !signed('TimeOut')} title={signed('TimeOut') ? '' : 'Complete WHO Time-Out first'}
                    onClick={() => run(() => startCase(caseObj.case_id))}
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
              Start surgery
            </button>
          )}
          {caseObj.status === 'InTheatre' && (
            <button type="button" disabled={busy} onClick={() => run(() => toRecovery(caseObj.case_id))}
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
              To recovery
            </button>
          )}
          {caseObj.status === 'Recovery' && (
            <button type="button" disabled={busy || !signed('SignOut')} title={signed('SignOut') ? '' : 'Complete WHO Sign-Out first'}
                    onClick={() => run(() => completeCase(caseObj.case_id))}
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
              Complete
            </button>
          )}
          {!isTerminal && (
            <button type="button" disabled={busy} onClick={doCancel}
                    className="rounded-lg border border-rose-300 dark:border-rose-800 px-3 py-1.5 text-sm font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20">
              Cancel
            </button>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {PHASES.map((ph) => (
          <div key={ph.key} className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-ink-900 dark:text-white">{ph.label}</h4>
              {signed(ph.key) && <span className="rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 px-2 py-0.5 text-xs font-medium">Signed</span>}
            </div>
            <ul className="mt-2 space-y-1 text-xs text-ink-600 dark:text-ink-400">
              {checklists.filter((c) => c.phase === ph.key).map((c) => <li key={c.checklist_id}>• {c.name}</li>)}
            </ul>
            {!isTerminal && !signed(ph.key) && (
              <button type="button" disabled={busy} onClick={() => run(() => addChecklistRun(caseObj.case_id, { phase: ph.key, checked: true }))}
                      className="mt-3 rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
                Sign {ph.key}
              </button>
            )}
          </div>
        ))}
      </div>

      <OperativeNoteForm caseObj={caseObj} onSaved={() => run(() => Promise.resolve())} />
      <AnaesthesiaForm caseObj={caseObj} onSaved={() => run(() => Promise.resolve())} />
      <CaseExtras caseObj={caseObj} onChanged={onChanged} />
    </section>
  );
}
