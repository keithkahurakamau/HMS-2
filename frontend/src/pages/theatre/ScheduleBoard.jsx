import { useEffect, useState } from 'react';
import { getBoard } from './api';
import { errorText } from './errors';

const CHIP = {
  Scheduled: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  InTheatre: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Recovery: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
  Completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  Cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

function CaseRow({ c }) {
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <span className="text-ink-800 dark:text-ink-200">
        {c.patient_name || `Patient #${c.case_id}`} <span className="text-ink-400">· {c.procedure_name}</span>
      </span>
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${CHIP[c.status] || ''}`}>{c.status}</span>
    </li>
  );
}

export default function ScheduleBoard() {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState('');

  const load = () => {
    getBoard()
      .then((data) => { setBoard(data); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load board')));
  };
  useEffect(() => { load(); }, []);

  if (error) return <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>;
  if (!board) return <p className="text-sm text-ink-500 dark:text-ink-400">Loading board…</p>;

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Theatre schedule — {board.date}</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {board.rooms.map((r) => (
          <div key={r.room_id} className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
            <div className="text-sm font-semibold text-ink-900 dark:text-white">{r.name}</div>
            <ul className="mt-2 space-y-1">
              {r.cases.map((c) => <CaseRow key={c.case_id} c={c} />)}
              {r.cases.length === 0 && <li className="text-sm text-ink-400">No cases.</li>}
            </ul>
          </div>
        ))}
      </div>
      {board.unassigned.length > 0 && (
        <section aria-label="Unassigned cases">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">Unassigned</h4>
          <ul className="mt-2 space-y-1">
            {board.unassigned.map((c) => <CaseRow key={c.case_id} c={c} />)}
          </ul>
        </section>
      )}
    </div>
  );
}
