import { useState } from 'react';
import { getRenalProfile, createVascularAccess } from './api';
import { errorText } from './errors';

const ACCESS_TYPES = ['AVF', 'AVG', 'Tunneled-cath', 'Non-tunneled-cath', 'Permcath'];

export default function RenalProfileTab() {
  const [pid, setPid] = useState('');
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [access, setAccess] = useState({ type: 'AVF', site: '' });

  const loadProfile = (id) => {
    getRenalProfile(id)
      .then((data) => { setProfile(data); setError(''); })
      .catch((err) => { setProfile(null); setError(errorText(err, 'Patient not found')); });
  };

  const lookup = (e) => {
    e.preventDefault();
    if (pid) loadProfile(pid);
  };

  const addAccess = (e) => {
    e.preventDefault();
    createVascularAccess({ patient_id: Number(pid), type: access.type, site: access.site || undefined })
      .then(() => { setAccess({ type: 'AVF', site: '' }); loadProfile(pid); })
      .catch((err) => setError(errorText(err, 'Failed to add access')));
  };

  return (
    <div className="max-w-3xl space-y-5">
      <form onSubmit={lookup} className="flex items-end gap-2">
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Patient ID
          <input type="number" value={pid} onChange={(e) => setPid(e.target.value)} className="input mt-1 w-40" />
        </label>
        <button type="submit" className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">
          Load profile
        </button>
      </form>
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {profile && (
        <>
          <h3 className="text-sm font-semibold text-ink-900 dark:text-white">{profile.patient_name}</h3>

          <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Vascular accesses">
            <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Vascular access</h4>
            <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-300">
              {profile.accesses.map((a) => (
                <li key={a.access_id}>• {a.type}{a.site ? ` — ${a.site}` : ''} <span className="text-ink-400">({a.status})</span></li>
              ))}
              {profile.accesses.length === 0 && <li className="text-ink-400">None recorded.</li>}
            </ul>
            <form onSubmit={addAccess} className="mt-3 flex flex-wrap items-end gap-2">
              <label className="block text-sm text-ink-700 dark:text-ink-300">
                Type
                <select value={access.type} onChange={(e) => setAccess((a) => ({ ...a, type: e.target.value }))} className="input mt-1">
                  {ACCESS_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
                Site
                <input type="text" value={access.site} onChange={(e) => setAccess((a) => ({ ...a, site: e.target.value }))} className="input mt-1 w-full" />
              </label>
              <button type="submit" className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700">Add access</button>
            </form>
          </section>

          <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Schedule">
            <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Schedule</h4>
            {profile.schedule ? (
              <p className="mt-1 text-sm text-ink-700 dark:text-ink-300">
                {profile.schedule.pattern}{profile.schedule.shift ? ` · ${profile.schedule.shift}` : ''}
                {profile.schedule.target_dry_weight_kg ? ` · dry weight ${profile.schedule.target_dry_weight_kg} kg` : ''}
              </p>
            ) : <p className="mt-1 text-sm text-ink-400">No active schedule.</p>}
          </section>

          <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Adequacy trend">
            <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Adequacy trend</h4>
            {profile.adequacy_trend.length ? (
              <table className="mt-2 w-full text-left text-sm">
                <thead className="text-xs uppercase text-ink-500 dark:text-ink-400">
                  <tr><th className="py-1">Session</th><th className="py-1">URR %</th><th className="py-1">Kt/V</th></tr>
                </thead>
                <tbody>
                  {profile.adequacy_trend.map((a) => (
                    <tr key={a.order_id} className="border-t border-ink-100 dark:border-ink-800">
                      <td className="py-1 text-ink-800 dark:text-ink-200">#{a.order_id}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{a.urr ?? '—'}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{a.kt_v ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="mt-1 text-sm text-ink-400">No adequacy recorded yet.</p>}
          </section>
        </>
      )}
    </div>
  );
}
