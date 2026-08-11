import { useEffect, useState } from 'react';
import { listMachines, createMachine, updateMachine } from './api';
import { errorText } from './errors';

export default function MachinesTab() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: '', model: '', station: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => {
    listMachines()
      .then((data) => { setRows(data || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load machines')));
  };
  useEffect(() => { load(); }, []);

  const add = (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    createMachine({ name: form.name.trim(), model: form.model || undefined, station: form.station || undefined })
      .then(() => { setForm({ name: '', model: '', station: '' }); load(); })
      .catch((err) => setError(errorText(err, 'Failed to add machine')))
      .finally(() => setSaving(false));
  };

  const toggle = (m) => {
    updateMachine(m.machine_id, { is_active: !m.is_active })
      .then(load)
      .catch((err) => setError(errorText(err, 'Failed to update machine')));
  };

  return (
    <div className="max-w-2xl">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Name
          <input type="text" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="input mt-1 w-40" />
        </label>
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Model
          <input type="text" value={form.model} onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))} className="input mt-1 w-40" />
        </label>
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Station
          <input type="text" value={form.station} onChange={(e) => setForm((f) => ({ ...f, station: e.target.value }))} className="input mt-1 w-32" />
        </label>
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          Add machine
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <ul className="mt-4 divide-y divide-ink-100 dark:divide-ink-800 rounded-xl border border-ink-200/70 dark:border-ink-800">
        {rows.map((m) => (
          <li key={m.machine_id} className="flex items-center justify-between gap-3 px-4 py-3">
            <span>
              <span className="block text-sm font-medium text-ink-900 dark:text-white">{m.name}</span>
              <span className="block text-xs text-ink-500 dark:text-ink-400">
                {[m.model, m.station].filter(Boolean).join(' · ') || '—'}
              </span>
            </span>
            <button type="button" onClick={() => toggle(m)}
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      m.is_active
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                        : 'bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400'
                    }`}>
              {m.is_active ? 'Active' : 'Inactive'}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
