import { useEffect, useState } from 'react';
import { getRoster } from './api';
import { errorText } from './errors';

export default function RosterTab() {
  const [roster, setRoster] = useState(null);
  const [error, setError] = useState('');

  const load = () => {
    getRoster()
      .then((data) => { setRoster(data); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load roster')));
  };
  useEffect(() => { load(); }, []);

  if (error) return <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>;
  if (!roster) return <p className="text-sm text-ink-500 dark:text-ink-400">Loading roster…</p>;

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-ink-900 dark:text-white">
        Chair occupancy — {roster.weekday}, {roster.date}
      </h3>

      <section aria-label="Machines">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">Machines</h4>
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {roster.machines.map((m) => (
            <div key={m.machine_id} className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
              <div className="text-sm font-medium text-ink-900 dark:text-white">{m.name}</div>
              <div className="text-xs text-ink-500 dark:text-ink-400">{m.station || '—'}</div>
              <div className="mt-2 text-sm">
                {m.current_order ? (
                  <span className="text-brand-700 dark:text-brand-300">
                    {m.current_order.patient_name || `Patient #${m.current_order.patient_id}`} · {m.current_order.status}
                  </span>
                ) : (
                  <span className="text-ink-400">Free</span>
                )}
              </div>
            </div>
          ))}
          {roster.machines.length === 0 && <p className="text-sm text-ink-500 dark:text-ink-400">No active machines.</p>}
        </div>
      </section>

      <section aria-label="Scheduled patients">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">Scheduled today</h4>
        <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-300">
          {roster.scheduled.map((s) => (
            <li key={s.schedule_id}>• {s.patient_name || `Patient #${s.patient_id}`} — {s.pattern}{s.shift ? ` (${s.shift})` : ''}</li>
          ))}
          {roster.scheduled.length === 0 && <li className="text-ink-400">No patients scheduled today.</li>}
        </ul>
      </section>
    </div>
  );
}
