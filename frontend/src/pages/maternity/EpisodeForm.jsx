import { useState } from 'react';
import { createEpisode } from './api';

export default function EpisodeForm({ initialPatientId, onClose, onSaved }) {
  const [form, setForm] = useState({
    patient_id: initialPatientId ? String(initialPatientId) : '',
    gravida: '1', para: '0', lmp: '', blood_group: '', rhesus: '', risk_flags: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.patient_id) { setError('Patient is required'); return; }
    setSaving(true);
    setError('');
    const payload = {
      patient_id: Number(form.patient_id),
      gravida: Number(form.gravida || 1),
      para: Number(form.para || 0),
    };
    if (form.lmp) payload.lmp = form.lmp;
    if (form.blood_group) payload.blood_group = form.blood_group;
    if (form.rhesus) payload.rhesus = form.rhesus;
    if (form.risk_flags) payload.risk_flags = form.risk_flags;
    try {
      await createEpisode(payload);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to enroll patient');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Enroll patient"
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Enroll patient</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Patient ID
          <input
            type="number"
            value={form.patient_id}
            onChange={set('patient_id')}
            required
            className="input mt-1 w-full"
          />
        </label>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Gravida
            <input type="number" min="1" max="30" value={form.gravida} onChange={set('gravida')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Para
            <input type="number" min="0" max="30" value={form.para} onChange={set('para')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            LMP
            <input type="date" value={form.lmp} onChange={set('lmp')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Blood group
            <input type="text" value={form.blood_group} onChange={set('blood_group')} maxLength={8} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Rhesus
            <input type="text" value={form.rhesus} onChange={set('rhesus')} maxLength={4} className="input mt-1 w-full" />
          </label>
        </div>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Risk flags
          <textarea value={form.risk_flags} onChange={set('risk_flags')} rows={2} className="input mt-1 w-full" />
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
            {saving ? 'Saving…' : 'Enroll'}
          </button>
        </div>
      </form>
    </div>
  );
}
