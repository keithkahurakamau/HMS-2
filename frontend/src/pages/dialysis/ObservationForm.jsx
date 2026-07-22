import { useState } from 'react';
import { addObservation } from './api';
import { errorText } from './errors';

const INT = [
  ['bp_systolic', 'BP systolic'], ['bp_diastolic', 'BP diastolic'], ['pulse', 'Pulse'],
  ['venous_pressure', 'Venous P'], ['arterial_pressure', 'Arterial P'], ['tmp', 'TMP'],
  ['blood_flow_rate', 'Blood flow'], ['dialysate_flow_rate', 'Dialysate flow'], ['uf_volume_ml', 'UF volume (mL)'],
];
const DEC = [
  ['conductivity', 'Conductivity', '0.1'],
  ['blood_volume_processed_l', 'Blood vol (L)', '0.1'],
  ['temperature_c', 'Temp (°C)', '0.1'],
];

export default function ObservationForm({ orderId, onClose, onSaved }) {
  const [form, setForm] = useState(
    Object.fromEntries([...INT, ...DEC].map(([k]) => [k, '']).concat([['heparin_note', '']])),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    const payload = {};
    for (const [k] of [...INT, ...DEC]) if (form[k] !== '') payload[k] = Number(form[k]);
    if (form.heparin_note) payload.heparin_note = form.heparin_note;
    try {
      const saved = await addObservation(orderId, payload);
      onSaved(saved);
    } catch (err) {
      setError(errorText(err, 'Failed to record observation'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
         role="dialog" aria-modal="true" aria-label="Record observation">
      <form onSubmit={submit} className="w-full max-w-lg rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Record observation</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="mt-3 grid grid-cols-3 gap-3">
          {INT.map(([k, label]) => (
            <label key={k} className="block text-sm text-ink-700 dark:text-ink-300">
              {label}
              <input type="number" value={form[k]} onChange={set(k)} className="input mt-1 w-full" />
            </label>
          ))}
          {DEC.map(([k, label, step]) => (
            <label key={k} className="block text-sm text-ink-700 dark:text-ink-300">
              {label}
              <input type="number" step={step} value={form[k]} onChange={set(k)} className="input mt-1 w-full" />
            </label>
          ))}
        </div>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Heparin note
          <input type="text" value={form.heparin_note} onChange={set('heparin_note')} maxLength={255} className="input mt-1 w-full" />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onClose}
                  className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
            Cancel
          </button>
          <button type="submit" disabled={saving}
                  className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
            {saving ? 'Saving…' : 'Save observation'}
          </button>
        </div>
      </form>
    </div>
  );
}
