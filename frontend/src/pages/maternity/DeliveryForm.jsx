import { useRef, useState } from 'react';
import { recordDelivery } from './api';

const MODES = ['SVD', 'Assisted', 'CSection', 'Breech'];
const MOTHER_STATUSES = ['Stable', 'Referred', 'Deceased'];
const SEXES = ['Male', 'Female'];
const OUTCOMES = ['Live', 'FSB', 'MSB'];

// Each newborn row carries a stable `id` (independent of its position in the
// array) so React can key rows correctly across add/remove — using the array
// index as the key would let a row's DOM/focus state get reattached to the
// wrong newborn's data when a row in the middle is removed.
const emptyNewborn = (id) => ({ id, sex: 'Male', weight_g: '', apgar_1: '', apgar_5: '', outcome: 'Live' });

export default function DeliveryForm({ episodeId, onClose, onSaved }) {
  const [deliveredAt, setDeliveredAt] = useState('');
  const [mode, setMode] = useState('SVD');
  const [bloodLossMl, setBloodLossMl] = useState('');
  const [placentaComplete, setPlacentaComplete] = useState(false);
  const [complications, setComplications] = useState('');
  const [motherStatus, setMotherStatus] = useState('Stable');
  const nextRowIdRef = useRef(1);
  const [newborns, setNewborns] = useState([emptyNewborn(0)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const setNewbornField = (id, key) => (e) => {
    const { value } = e.target;
    setNewborns((rows) => rows.map((row) => (row.id === id ? { ...row, [key]: value } : row)));
  };
  const addTwin = () => setNewborns((rows) => [...rows, emptyNewborn(nextRowIdRef.current++)]);
  const removeNewborn = (id) => setNewborns((rows) => rows.filter((row) => row.id !== id));

  const submit = async (e) => {
    e.preventDefault();
    if (!deliveredAt) { setError('Delivered at is required'); return; }
    if (newborns.length === 0) { setError('At least one newborn record is required'); return; }
    setSaving(true);
    setError('');
    const payload = {
      delivered_at: new Date(deliveredAt).toISOString(),
      mode,
      mother_status: motherStatus,
      placenta_complete: placentaComplete,
    };
    if (bloodLossMl !== '') payload.blood_loss_ml = Number(bloodLossMl);
    if (complications) payload.complications = complications;
    payload.newborns = newborns.map((n, idx) => {
      const row = { sex: n.sex, outcome: n.outcome, birth_order: idx + 1 };
      if (n.weight_g !== '') row.weight_g = Number(n.weight_g);
      if (n.apgar_1 !== '') row.apgar_1 = Number(n.apgar_1);
      if (n.apgar_5 !== '') row.apgar_5 = Number(n.apgar_5);
      return row;
    });
    try {
      await recordDelivery(episodeId, payload);
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save delivery');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Record delivery"
    >
      <form onSubmit={submit} className="w-full max-w-lg rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated max-h-[90vh] overflow-y-auto">
        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Record delivery</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Delivered at
          <input
            type="datetime-local"
            value={deliveredAt}
            onChange={(e) => setDeliveredAt(e.target.value)}
            required
            className="input mt-1 w-full"
          />
        </label>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value)} className="input mt-1 w-full">
              {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Mother status
            <select value={motherStatus} onChange={(e) => setMotherStatus(e.target.value)} className="input mt-1 w-full">
              {MOTHER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Blood loss (ml)
            <input type="number" value={bloodLossMl} onChange={(e) => setBloodLossMl(e.target.value)} className="input mt-1 w-full" />
          </label>
          <label className="mt-6 flex items-center gap-2 text-sm text-ink-700 dark:text-ink-300">
            <input type="checkbox" checked={placentaComplete} onChange={(e) => setPlacentaComplete(e.target.checked)} />
            Placenta complete
          </label>
        </div>
        <label className="mt-3 block text-sm text-ink-700 dark:text-ink-300">
          Complications
          <textarea value={complications} onChange={(e) => setComplications(e.target.value)} rows={2} className="input mt-1 w-full" />
        </label>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Newborns</h4>
            <button
              type="button"
              onClick={addTwin}
              className="text-sm font-medium text-brand-700 dark:text-brand-300 hover:underline"
            >
              Add twin
            </button>
          </div>
          {newborns.map((n, idx) => (
            <div key={n.id} className="mt-2 rounded-lg border border-ink-200/70 dark:border-ink-800 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-ink-500 dark:text-ink-400">Newborn {idx + 1}</span>
                <button
                  type="button"
                  onClick={() => removeNewborn(n.id)}
                  className="text-xs font-medium text-rose-600 dark:text-rose-400 hover:underline"
                >
                  Remove
                </button>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3">
                <label className="block text-sm text-ink-700 dark:text-ink-300">
                  Sex
                  <select value={n.sex} onChange={setNewbornField(n.id, 'sex')} className="input mt-1 w-full">
                    {SEXES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </label>
                <label className="block text-sm text-ink-700 dark:text-ink-300">
                  Outcome
                  <select value={n.outcome} onChange={setNewbornField(n.id, 'outcome')} className="input mt-1 w-full">
                    {OUTCOMES.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                </label>
                <label className="block text-sm text-ink-700 dark:text-ink-300">
                  Weight (g)
                  <input type="number" value={n.weight_g} onChange={setNewbornField(n.id, 'weight_g')} className="input mt-1 w-full" />
                </label>
                <label className="block text-sm text-ink-700 dark:text-ink-300">
                  APGAR 1 min
                  <input type="number" min="0" max="10" value={n.apgar_1} onChange={setNewbornField(n.id, 'apgar_1')} className="input mt-1 w-full" />
                </label>
                <label className="block text-sm text-ink-700 dark:text-ink-300">
                  APGAR 5 min
                  <input type="number" min="0" max="10" value={n.apgar_5} onChange={setNewbornField(n.id, 'apgar_5')} className="input mt-1 w-full" />
                </label>
              </div>
            </div>
          ))}
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
            {saving ? 'Saving…' : 'Save delivery'}
          </button>
        </div>
      </form>
    </div>
  );
}
