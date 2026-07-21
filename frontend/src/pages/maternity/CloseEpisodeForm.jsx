import { useState } from 'react';
import { closeEpisode } from './api';
import { errorText } from './errors';

// Mirrors the backend's VALID_CLOSE_STATUS (app/routes/maternity.py) —
// these are the only two values close_episode accepts.
const CLOSE_STATUSES = ['Closed', 'Transferred'];

export default function CloseEpisodeForm({ episodeId, patientName, onClose, onClosed }) {
  const [status, setStatus] = useState('Closed');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = { status };
    if (reason) payload.reason = reason;
    try {
      await closeEpisode(episodeId, payload);
      onClosed();
    } catch (err) {
      setError(errorText(err, 'Failed to close episode'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Close episode"
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">
          Close episode{patientName ? ` — ${patientName}` : ''}
        </h3>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          This ends the pregnancy episode. It cannot be reopened here, but the
          patient can be re-enrolled afterwards if needed.
        </p>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="input mt-1 w-full">
            {CLOSE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Reason (optional)
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className="input mt-1 w-full" />
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
            className="rounded-lg border border-rose-300 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-900/20 px-3 py-1.5 text-sm font-medium text-rose-700 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/30 disabled:opacity-60"
          >
            {saving ? 'Closing…' : 'Confirm close'}
          </button>
        </div>
      </form>
    </div>
  );
}
