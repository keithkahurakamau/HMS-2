import { useState } from 'react';
import { appendPartograph } from './api';
import { errorText } from './errors';

const NUMBER_FIELDS = [
  'cervical_dilation_cm', 'descent_fifths', 'contractions_per_10min',
  'contraction_duration_sec', 'fetal_heart_rate', 'maternal_bp_systolic',
  'maternal_bp_diastolic', 'maternal_pulse', 'temperature_c',
];
const TEXT_FIELDS = ['liquor', 'moulding', 'drugs_note'];

const EMPTY_FORM = {
  cervical_dilation_cm: '', descent_fifths: '', contractions_per_10min: '',
  contraction_duration_sec: '', fetal_heart_rate: '', maternal_bp_systolic: '',
  maternal_bp_diastolic: '', maternal_pulse: '', temperature_c: '',
  liquor: '', moulding: '', drugs_note: '',
};

// The partograph is append-only by design: this same form both creates a
// fresh entry and — when `correctingEntry` is supplied — appends a NEW entry
// carrying `corrects_entry_id` that supersedes it. Nothing is ever mutated
// or deleted; see maternity_labor.py module docstring.
export default function PartographEntryForm({ laborId, correctingEntry = null, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    if (!correctingEntry) return EMPTY_FORM;
    const prefilled = { ...EMPTY_FORM };
    for (const k of [...NUMBER_FIELDS, ...TEXT_FIELDS]) {
      if (correctingEntry[k] != null) prefilled[k] = correctingEntry[k];
    }
    return prefilled;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = {};
    for (const k of NUMBER_FIELDS) {
      if (form[k] !== '') payload[k] = Number(form[k]);
    }
    for (const k of TEXT_FIELDS) {
      if (form[k]) payload[k] = form[k];
    }
    if (correctingEntry) payload.corrects_entry_id = correctingEntry.entry_id;
    try {
      await appendPartograph(laborId, payload);
      onSaved();
    } catch (err) {
      setError(errorText(err, 'Failed to save entry'));
    } finally {
      setSaving(false);
    }
  };

  const heading = correctingEntry
    ? `Correct entry — originally recorded ${new Date(correctingEntry.recorded_at).toLocaleString()}`
    : 'New partograph entry';

  return (
    <div
      className="print:hidden fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label={correctingEntry ? 'Correct partograph entry' : 'New partograph entry'}
    >
      <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated max-h-[90vh] overflow-y-auto">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">{heading}</h3>
        {correctingEntry && (
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            This saves a NEW entry that supersedes the one above — the original stays on the
            chart, shown struck through.
          </p>
        )}
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Cervical dilation (cm)
            <input type="number" step="0.5" min="0" max="10" value={form.cervical_dilation_cm}
                   onChange={set('cervical_dilation_cm')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Descent (fifths)
            <input type="number" min="0" max="5" value={form.descent_fifths}
                   onChange={set('descent_fifths')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Contractions / 10 min
            <input type="number" min="0" max="10" value={form.contractions_per_10min}
                   onChange={set('contractions_per_10min')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Contraction duration (sec)
            <input type="number" min="0" max="600" value={form.contraction_duration_sec}
                   onChange={set('contraction_duration_sec')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Fetal heart rate
            <input type="number" min="40" max="240" value={form.fetal_heart_rate}
                   onChange={set('fetal_heart_rate')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Liquor
            <input type="text" value={form.liquor} onChange={set('liquor')}
                   maxLength={4} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Moulding
            <input type="text" value={form.moulding} onChange={set('moulding')}
                   maxLength={4} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Maternal BP systolic
            <input type="number" min="40" max="300" value={form.maternal_bp_systolic}
                   onChange={set('maternal_bp_systolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Maternal BP diastolic
            <input type="number" min="20" max="200" value={form.maternal_bp_diastolic}
                   onChange={set('maternal_bp_diastolic')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Maternal pulse
            <input type="number" min="20" max="250" value={form.maternal_pulse}
                   onChange={set('maternal_pulse')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Temperature (°C)
            <input type="number" step="0.1" min="30" max="45" value={form.temperature_c}
                   onChange={set('temperature_c')} className="input mt-1 w-full" />
          </label>
        </div>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Drugs note
          <textarea value={form.drugs_note} onChange={set('drugs_note')} rows={2}
                    maxLength={255} className="input mt-1 w-full" />
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
            {saving ? 'Saving…' : correctingEntry ? 'Save correction' : 'Save entry'}
          </button>
        </div>
      </form>
    </div>
  );
}
