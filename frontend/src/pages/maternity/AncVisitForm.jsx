import { useState } from 'react';
import { createAncVisit } from './api';

const NUMBER_FIELDS = ['bp_systolic', 'bp_diastolic', 'fetal_heart_rate'];
const DECIMAL_FIELDS = ['weight_kg', 'fundal_height_cm'];
const TEXT_FIELDS = ['urine_dip', 'notes'];

export default function AncVisitForm({ episodeId, onClose, onSaved }) {
  const [form, setForm] = useState({
    visit_date: '', bp_systolic: '', bp_diastolic: '', weight_kg: '',
    fundal_height_cm: '', fetal_heart_rate: '', urine_dip: '', notes: '',
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
    for (const k of [...NUMBER_FIELDS, ...DECIMAL_FIELDS]) {
      if (form[k] !== '') payload[k] = Number(form[k]);
    }
    for (const k of TEXT_FIELDS) {
      if (form[k]) payload[k] = form[k];
    }
    try {
      await createAncVisit(episodeId, payload);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save visit');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="New ANC visit"
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">New ANC visit</h3>
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
            <input type="number" value={form.bp_systolic} onChange={set('bp_systolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            BP diastolic
            <input type="number" value={form.bp_diastolic} onChange={set('bp_diastolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Weight (kg)
            <input type="number" step="0.1" value={form.weight_kg} onChange={set('weight_kg')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Fundal height (cm)
            <input type="number" step="0.1" value={form.fundal_height_cm} onChange={set('fundal_height_cm')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Fetal heart rate
            <input type="number" value={form.fetal_heart_rate} onChange={set('fetal_heart_rate')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Urine dip
            <input type="text" value={form.urine_dip} onChange={set('urine_dip')} maxLength={40} className="input mt-1 w-full" />
          </label>
        </div>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Notes
          <textarea value={form.notes} onChange={set('notes')} rows={2} className="input mt-1 w-full" />
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
            {saving ? 'Saving…' : 'Save visit'}
          </button>
        </div>
      </form>
    </div>
  );
}
