import { useState } from 'react';
import { recordAdequacy } from './api';
import { errorText } from './errors';

const REQUIRED = [
  ['pre_urea', 'Pre-urea'], ['post_urea', 'Post-urea'],
  ['session_duration_min', 'Duration (min)'], ['ultrafiltration_actual_ml', 'Actual UF (mL)'],
  ['post_weight_kg', 'Post-weight (kg)'],
];
const OPTIONAL = [
  ['pre_creatinine', 'Pre-creat'], ['post_creatinine', 'Post-creat'],
  ['pre_potassium', 'Pre-K+'], ['post_potassium', 'Post-K+'], ['pre_hb', 'Pre-Hb'],
];

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-brand-50 dark:bg-brand-900/20 px-3 py-2 text-center">
      <div className="text-xs text-ink-500 dark:text-ink-400">{label}</div>
      <div className="text-lg font-semibold text-brand-700 dark:text-brand-300">{value ?? '—'}</div>
    </div>
  );
}

export default function AdequacyPanel({ order, onSaved }) {
  const [result, setResult] = useState(order?.adequacy || null);
  const [form, setForm] = useState(
    Object.fromEntries([...REQUIRED, ...OPTIONAL].map(([k]) => [k, ''])),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    for (const [k, label] of REQUIRED) {
      if (form[k] === '') { setError(`${label} is required`); return; }
    }
    setSaving(true);
    setError('');
    const payload = {};
    for (const [k] of [...REQUIRED, ...OPTIONAL]) if (form[k] !== '') payload[k] = Number(form[k]);
    try {
      const saved = await recordAdequacy(order.order_id, payload);
      setResult(saved);
      if (onSaved) onSaved(saved);
    } catch (err) {
      setError(errorText(err, 'Failed to record adequacy'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Dialysis adequacy">
      <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Adequacy</h4>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Metric label="URR %" value={result?.urr} />
        <Metric label="Kt/V" value={result?.kt_v} />
      </div>
      <form onSubmit={submit} className="mt-4">
        {error && <p className="mb-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {[...REQUIRED, ...OPTIONAL].map(([k, label]) => (
            <label key={k} className="block text-sm text-ink-700 dark:text-ink-300">
              {label}
              <input type="number" step="0.01" value={form[k]} onChange={set(k)} className="input mt-1 w-full" />
            </label>
          ))}
        </div>
        <div className="mt-3 flex justify-end">
          <button type="submit" disabled={saving}
                  className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
            {saving ? 'Computing…' : 'Compute adequacy'}
          </button>
        </div>
      </form>
    </section>
  );
}
