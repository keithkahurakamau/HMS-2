import { useState } from 'react';
import { putOperativeNote } from './api';
import { errorText } from './errors';

const TEXT = [
  ['findings', 'Findings'], ['procedure_performed', 'Procedure performed'],
  ['technique', 'Technique'], ['closure', 'Closure'], ['specimens', 'Specimens'],
  ['complications', 'Complications'],
];
const NUM = [['blood_loss_ml', 'Blood loss (mL)'], ['estimated_duration_min', 'Duration (min)']];

export default function OperativeNoteForm({ caseObj, onSaved }) {
  const note = caseObj.operative_note || {};
  const [form, setForm] = useState({
    ...Object.fromEntries(TEXT.map(([k]) => [k, note[k] || ''])),
    ...Object.fromEntries(NUM.map(([k]) => [k, note[k] != null ? String(note[k]) : ''])),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = {};
    for (const [k] of TEXT) payload[k] = form[k] || null;
    for (const [k] of NUM) payload[k] = form[k] !== '' ? Number(form[k]) : null;
    putOperativeNote(caseObj.case_id, payload)
      .then((saved) => onSaved && onSaved(saved))
      .catch((err) => setError(errorText(err, 'Failed to save operative note')))
      .finally(() => setSaving(false));
  };

  return (
    <form onSubmit={submit} className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Operative note">
      <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Operative note</h4>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      <div className="mt-3 grid grid-cols-2 gap-3">
        {NUM.map(([k, label]) => (
          <label key={k} className="block text-sm text-ink-700 dark:text-ink-300">
            {label}
            <input type="number" value={form[k]} onChange={set(k)} className="input mt-1 w-full" />
          </label>
        ))}
        {TEXT.map(([k, label]) => (
          <label key={k} className="col-span-2 block text-sm text-ink-700 dark:text-ink-300">
            {label}
            <textarea value={form[k]} onChange={set(k)} rows={2} className="input mt-1 w-full" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex justify-end">
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          {saving ? 'Saving…' : 'Save operative note'}
        </button>
      </div>
    </form>
  );
}
