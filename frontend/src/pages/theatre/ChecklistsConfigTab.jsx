import { useEffect, useState } from 'react';
import { listChecklists, createChecklist, updateChecklist } from './api';
import { errorText } from './errors';

const PHASES = ['SignIn', 'TimeOut', 'SignOut'];

export default function ChecklistsConfigTab() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ phase: 'SignIn', name: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => {
    listChecklists()
      .then((data) => { setRows(data || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load checklists')));
  };
  useEffect(() => { load(); }, []);

  const add = (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    createChecklist({ phase: form.phase, name: form.name.trim() })
      .then(() => { setForm({ phase: 'SignIn', name: '' }); load(); })
      .catch((err) => setError(errorText(err, 'Failed to add item')))
      .finally(() => setSaving(false));
  };

  const toggle = (r) => {
    updateChecklist(r.checklist_id, { is_active: !r.is_active })
      .then(load)
      .catch((err) => setError(errorText(err, 'Failed to update item')));
  };

  return (
    <div className="max-w-3xl">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Phase
          <select value={form.phase} onChange={(e) => setForm((f) => ({ ...f, phase: e.target.value }))} className="input mt-1">
            {PHASES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
          Item
          <input type="text" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="input mt-1 w-full" />
        </label>
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          Add item
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {PHASES.map((phase) => (
        <div key={phase} className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">{phase}</h4>
          <ul className="mt-2 divide-y divide-ink-100 dark:divide-ink-800 rounded-xl border border-ink-200/70 dark:border-ink-800">
            {rows.filter((r) => r.phase === phase).map((r) => (
              <li key={r.checklist_id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="text-sm text-ink-800 dark:text-ink-200">{r.name}</span>
                <button type="button" onClick={() => toggle(r)}
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          r.is_active
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                            : 'bg-ink-100 text-ink-500 dark:bg-ink-800 dark:text-ink-400'
                        }`}>
                  {r.is_active ? 'Active' : 'Inactive'}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
