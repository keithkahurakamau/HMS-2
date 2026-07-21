import { useCallback, useEffect, useRef, useState } from 'react';
import { listEpisodes, getWardBoard, linkLabor } from './api';
import { errorText } from './errors';

// The wards board (GET /wards/board) already attaches admission_id to every
// Occupied bed, but it only carries a formatted display name ("Surname,
// Other names") for the occupant — not a raw patient_id. That formatted
// name is produced the same way ep.patient_name is (see
// app/routes/maternity.py _episode_dict), so matching on it here finds the
// right admission(s) without a backend change. Ward/bed/admission-date are
// shown alongside so a rare same-name collision can still be told apart by
// the person starting labor.
function findAdmissionsForPatient(wards, patientName) {
  const matches = [];
  for (const ward of wards || []) {
    for (const bed of ward.beds || []) {
      if (bed.status === 'Occupied' && bed.admission_id && bed.patient === patientName) {
        matches.push({
          admission_id: bed.admission_id,
          ward_name: ward.name,
          bed_number: bed.number,
          admission_date: bed.admission_date,
        });
      }
    }
  }
  return matches;
}

export default function StartLaborForm({ onClose, onStarted }) {
  const [episodes, setEpisodes] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [episodeId, setEpisodeId] = useState('');
  const [admissions, setAdmissions] = useState([]);
  const [admissionsLoading, setAdmissionsLoading] = useState(false);
  const [admissionId, setAdmissionId] = useState('');
  const [activeLaborStartedAt, setActiveLaborStartedAt] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // Tracks the episode_id of the most recently requested ward-board lookup
  // so a late-resolving (out-of-order) fetch for a since-abandoned episode
  // selection can never populate the admission list under the wrong patient.
  const requestedEpisodeIdRef = useRef(null);

  useEffect(() => {
    Promise.resolve(listEpisodes({ status: 'Active' }))
      .then((rows) => { setEpisodes(rows || []); setLoadError(''); })
      .catch(() => setLoadError('Failed to load active pregnancies'));
  }, []);

  const selectEpisode = useCallback((idStr, list) => {
    setEpisodeId(idStr);
    setAdmissions([]); // clear stale admissions immediately so a stale match can never be submitted
    setAdmissionId('');
    setError('');
    const id = Number(idStr);
    if (!id) {
      requestedEpisodeIdRef.current = null;
      return;
    }
    const episode = list.find((ep) => ep.episode_id === id);
    requestedEpisodeIdRef.current = id;
    setAdmissionsLoading(true);
    Promise.resolve(getWardBoard())
      .then((wards) => {
        // Ignore out-of-order responses: only apply if this is still the
        // latest requested episode.
        if (requestedEpisodeIdRef.current !== id) return;
        const matches = findAdmissionsForPatient(wards, episode?.patient_name);
        setAdmissions(matches);
        if (matches.length === 1) setAdmissionId(String(matches[0].admission_id));
        setAdmissionsLoading(false);
      })
      .catch(() => {
        if (requestedEpisodeIdRef.current !== id) return;
        setAdmissionsLoading(false);
        setError('Failed to load ward admissions');
      });
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!episodeId) { setError('Select a pregnancy episode'); return; }
    if (!admissionId) { setError('Select an active ward admission'); return; }
    setSaving(true);
    setError('');
    const payload = { admission_id: Number(admissionId) };
    if (activeLaborStartedAt) {
      payload.active_labor_started_at = new Date(activeLaborStartedAt).toISOString();
    }
    try {
      const result = await linkLabor(Number(episodeId), payload);
      const episode = episodes.find((ep) => ep.episode_id === Number(episodeId));
      onStarted(result, episode);
    } catch (err) {
      setError(errorText(err, 'Failed to start labor'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Start labor"
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Start labor</h3>
        {(error || loadError) && (
          <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error || loadError}</p>
        )}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Pregnancy episode
          <select
            value={episodeId}
            onChange={(e) => selectEpisode(e.target.value, episodes)}
            required
            className="input mt-1 w-full"
          >
            <option value="">Select a patient…</option>
            {episodes.map((ep) => (
              <option key={ep.episode_id} value={ep.episode_id}>
                {ep.patient_name} — G{ep.gravida} P{ep.para}
              </option>
            ))}
          </select>
        </label>
        {episodeId && (
          <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
            Ward admission
            <select
              value={admissionId}
              onChange={(e) => setAdmissionId(e.target.value)}
              required
              disabled={admissionsLoading || admissions.length === 0}
              className="input mt-1 w-full"
            >
              <option value="">
                {admissionsLoading ? 'Loading…' : 'Select an admission…'}
              </option>
              {admissions.map((a) => (
                <option key={a.admission_id} value={a.admission_id}>
                  {a.ward_name} · Bed {a.bed_number} · admitted {a.admission_date || '—'}
                </option>
              ))}
            </select>
            {!admissionsLoading && admissions.length === 0 && (
              <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
                No active ward admission found for this patient — admit them to a ward first.
              </span>
            )}
          </label>
        )}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Active labor started at (optional)
          <input
            type="datetime-local"
            value={activeLaborStartedAt}
            onChange={(e) => setActiveLaborStartedAt(e.target.value)}
            className="input mt-1 w-full"
          />
          <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
            Leave blank to anchor the alert line on the first ≥4 cm entry.
          </span>
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {saving ? 'Starting…' : 'Start labor'}
          </button>
        </div>
      </form>
    </div>
  );
}
