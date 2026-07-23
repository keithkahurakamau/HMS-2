import { useState } from 'react';
import { putAnaesthesia } from './api';
import { errorText } from './errors';

const TYPES = ['GA', 'Spinal', 'Epidural', 'Local', 'Sedation'];
const ASA = ['', 'I', 'II', 'III', 'IV', 'V'];

export default function AnaesthesiaForm({ caseObj, onSaved }) {
  const a = caseObj.anaesthesia || {};
  const [form, setForm] = useState({
    type: a.type || 'GA', asa_grade: a.asa_grade || '',
    agents: a.agents || '', airway: a.airway || '', notes: a.notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = { type: form.type };
    if (form.asa_grade) payload.asa_grade = form.asa_grade;
    if (form.agents) payload.agents = form.agents;
    if (form.airway) payload.airway = form.airway;
    if (form.notes) payload.notes = form.notes;
    putAnaesthesia(caseObj.case_id, payload)
      .then((saved) => onSaved && onSaved(saved))
      .catch((err) => setError(errorText(err, 'Failed to save anaesthesia')))
      .finally(() => setSaving(false));
  };

  return (
    <form onSubmit={submit} className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Anaesthesia record">
      <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Anaesthesia</h4>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Type
          <select value={form.type} onChange={set('type')} className="input mt-1 w-full">
            {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          ASA grade
          <select value={form.asa_grade} onChange={set('asa_grade')} className="input mt-1 w-full">
            {ASA.map((g) => <option key={g} value={g}>{g || '—'}</option>)}
          </select>
        </label>
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Agents
          <input type="text" value={form.agents} onChange={set('agents')} className="input mt-1 w-full" />
        </label>
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Airway
          <input type="text" value={form.airway} onChange={set('airway')} className="input mt-1 w-full" />
        </label>
        <label className="col-span-2 block text-sm text-ink-700 dark:text-ink-300">
          Notes
          <textarea value={form.notes} onChange={set('notes')} rows={2} className="input mt-1 w-full" />
        </label>
      </div>
      <div className="mt-3 flex justify-end">
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          {saving ? 'Saving…' : 'Save anaesthesia'}
        </button>
      </div>
    </form>
  );
}
