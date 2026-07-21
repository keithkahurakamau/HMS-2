import { useState } from 'react';
import { createPncVisit } from './api';
import { errorText } from './errors';

const NUMBER_FIELDS = ['baby_weight_g', 'bp_systolic', 'bp_diastolic'];
const TEXT_FIELDS = ['involution', 'lochia', 'feeding', 'cord_status'];

export default function PncVisitForm({ episodeId, onClose, onSaved }) {
  const [form, setForm] = useState({
    visit_date: '', bp_systolic: '', bp_diastolic: '', involution: '',
    lochia: '', feeding: '', cord_status: '', baby_weight_g: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.visit_date) { setError('Visit date is required'); return; }
    setSaving(true);
    setError('');
    const payload = { visit_date: form.visit_date };
    for (const k of NUMBER_FIELDS) {
      if (form[k] !== '') payload[k] = Number(form[k]);
    }
    for (const k of TEXT_FIELDS) {
      if (form[k]) payload[k] = form[k];
    }
    try {
      await createPncVisit(episodeId, payload);
      onSaved();
    } catch (err) {
      setError(errorText(err, 'Failed to save visit'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="New PNC visit"
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">New PNC visit</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Visit date
          <input
            type="date"
            value={form.visit_date}
            onChange={set('visit_date')}
            required
            className="input mt-1 w-full"
          />
        </label>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            BP systolic
            <input type="number" min="40" max="300" value={form.bp_systolic} onChange={set('bp_systolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            BP diastolic
            <input type="number" min="20" max="200" value={form.bp_diastolic} onChange={set('bp_diastolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Baby weight (g)
            <input type="number" min="200" max="9000" value={form.baby_weight_g} onChange={set('baby_weight_g')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Involution
            <input type="text" value={form.involution} onChange={set('involution')} maxLength={40} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Lochia
            <input type="text" value={form.lochia} onChange={set('lochia')} maxLength={40} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Feeding
            <input type="text" value={form.feeding} onChange={set('feeding')} maxLength={40} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Cord status
            <input type="text" value={form.cord_status} onChange={set('cord_status')} maxLength={40} className="input mt-1 w-full" />
          </label>
        </div>
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
            {saving ? 'Saving…' : 'Save visit'}
          </button>
        </div>
      </form>
    </div>
  );
}
