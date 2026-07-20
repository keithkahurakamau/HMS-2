import { useCallback, useEffect, useState } from 'react';
import { listEpisodes, getEpisode, getMaternityQueue } from './api';
import EpisodeForm from './EpisodeForm';
import AncVisitForm from './AncVisitForm';

export default function AncClinicTab() {
  const [episodes, setEpisodes] = useState([]);
  const [queue, setQueue] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showEnroll, setShowEnroll] = useState(null);
  const [showVisit, setShowVisit] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    Promise.resolve(listEpisodes({ status: 'Active' }))
      .then((rows) => setEpisodes(rows || []))
      .catch(() => setError('Failed to load episodes'));
    Promise.resolve(getMaternityQueue())
      .then((rows) => setQueue(rows || []))
      .catch(() => setQueue([]));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const openEpisode = (id) =>
    Promise.resolve(getEpisode(id))
      .then((ep) => setSelected(ep || null))
      .catch(() => setError('Failed to load episode'));

  const ancVisits = selected?.anc_visits || [];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {queue.length > 0 && (
        <div className="md:col-span-2 rounded-2xl bg-brand-50 dark:bg-brand-500/10 p-3">
          <h3 className="text-sm font-medium text-brand-800 dark:text-brand-300">Routed to Maternity</h3>
          <ul className="mt-1 space-y-1">
            {queue.map((q) => (
              <li key={q.queue_id} className="flex items-center justify-between text-sm text-ink-900 dark:text-white">
                <span>{q.patient_name}</span>
                <button
                  type="button"
                  onClick={() => setShowEnroll({ patientId: q.patient_id })}
                  className="text-brand-700 dark:text-brand-300 hover:underline"
                >
                  Enroll / open
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <section
        aria-label="Active pregnancies"
        className="rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-900 dark:text-white">Active pregnancies</h2>
          <button
            type="button"
            onClick={() => setShowEnroll({})}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Enroll patient
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <ul className="mt-3 divide-y divide-ink-100 dark:divide-ink-800">
          {episodes.map((ep) => (
            <li key={ep.episode_id}>
              <button
                type="button"
                onClick={() => openEpisode(ep.episode_id)}
                className="w-full rounded-lg px-2 py-2 text-left hover:bg-ink-50 dark:hover:bg-ink-800/50"
              >
                <span className="font-medium text-ink-900 dark:text-white">{ep.patient_name}</span>
                <span className="ml-2 text-sm text-ink-500 dark:text-ink-400">
                  G{ep.gravida} P{ep.para}{ep.edd ? ` · EDD ${ep.edd}` : ''}
                </span>
              </button>
            </li>
          ))}
          {episodes.length === 0 && (
            <li className="py-2 text-sm text-ink-500 dark:text-ink-400">No active pregnancies.</li>
          )}
        </ul>
      </section>

      <section
        aria-label="Episode detail"
        className="rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4"
      >
        {!selected ? (
          <p className="text-sm text-ink-500 dark:text-ink-400">Select an episode to view visits.</p>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink-900 dark:text-white">{selected.patient_name}</h2>
              <button
                type="button"
                onClick={() => setShowVisit(true)}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                New ANC visit
              </button>
            </div>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-ink-500 dark:text-ink-400">
                  <th className="py-1 pr-2 font-medium">#</th>
                  <th className="py-1 pr-2 font-medium">Date</th>
                  <th className="py-1 pr-2 font-medium">GA (wk)</th>
                  <th className="py-1 pr-2 font-medium">BP</th>
                  <th className="py-1 font-medium">FHR</th>
                </tr>
              </thead>
              <tbody className="text-ink-900 dark:text-white">
                {ancVisits.map((v) => (
                  <tr key={v.visit_id} className="border-t border-ink-100 dark:border-ink-800">
                    <td className="py-1 pr-2">{v.visit_number}</td>
                    <td className="py-1 pr-2">{v.visit_date}</td>
                    <td className="py-1 pr-2">{v.gestation_weeks ?? '—'}</td>
                    <td className="py-1 pr-2">{v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic}` : '—'}</td>
                    <td className="py-1">{v.fetal_heart_rate ?? '—'}</td>
                  </tr>
                ))}
                {ancVisits.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-2 text-ink-500 dark:text-ink-400">No ANC visits recorded yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </section>

      {showEnroll && (
        <EpisodeForm
          initialPatientId={showEnroll.patientId}
          onClose={() => setShowEnroll(null)}
          onSaved={() => { setShowEnroll(null); refresh(); }}
        />
      )}
      {showVisit && selected && (
        <AncVisitForm
          episodeId={selected.episode_id}
          onClose={() => setShowVisit(false)}
          onSaved={() => { setShowVisit(false); openEpisode(selected.episode_id); }}
        />
      )}
    </div>
  );
}
