import { useEffect, useState } from 'react';
import { listChecklists, createChecklist, updateChecklist } from './api';
import { errorText } from './errors';

export default function ChecklistsConfigTab() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: '', description: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => {
    listChecklists()
      .then((rows) => { setRows(rows || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load checklists')));
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    setError('');
    try {
      await createChecklist({ name: form.name.trim(), description: form.description || undefined });
      setForm({ name: '', description: '' });
      await load();
    } catch (err) {
      setError(errorText(err, 'Failed to add checklist'));
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (row) => {
    try {
      await updateChecklist(row.checklist_id, { is_active: !row.is_active });
      await load();
    } catch (err) {
      setError(errorText(err, 'Failed to update checklist'));
    }
  };

  return (
    <div className="max-w-2xl">
      <form onSubmit={add} className="flex flex-wrap items-end gap-2 rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
        <label className="block text-sm text-ink-700 dark:text-ink-300">
          Name
          <input type="text" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="input mt-1 w-48" />
        </label>
        <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
          Description
          <input type="text" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className="input mt-1 w-full" />
        </label>
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          Add checklist
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <ul className="mt-4 divide-y divide-ink-100 dark:divide-ink-800 rounded-xl border border-ink-200/70 dark:border-ink-800">
        {rows.map((r) => (
          <li key={r.checklist_id} className="flex items-center justify-between gap-3 px-4 py-3">
            <span>
              <span className="block text-sm font-medium text-ink-900 dark:text-white">{r.name}</span>
              {r.description && <span className="block text-xs text-ink-500 dark:text-ink-400">{r.description}</span>}
            </span>
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
  );
}
