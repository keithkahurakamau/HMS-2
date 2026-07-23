import { useEffect, useState } from 'react';
import { listRooms, createRoom, updateRoom } from './api';
import { errorText } from './errors';

export default function RoomsTab() {
  const [rows, setRows] = useState([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => {
    listRooms()
      .then((data) => { setRows(data || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load rooms')));
  };
  useEffect(() => { load(); }, []);

  const add = (e) => {
    e.preventDefault();
    if (!name.trim()) { setError('Name is required'); return; }
    setSaving(true);
    createRoom({ name: name.trim() })
      .then(() => { setName(''); load(); })
      .catch((err) => setError(errorText(err, 'Failed to add room')))
      .finally(() => setSaving(false));
  };

  const toggle = (r) => {
    updateRoom(r.room_id, { is_active: !r.is_active })
      .then(load)
      .catch((err) => setError(errorText(err, 'Failed to update room')));
  };

  return (
    <div className="max-w-xl">
      <form onSubmit={add} className="flex items-end gap-2 rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
        <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
          Room name
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} className="input mt-1 w-full" />
        </label>
        <button type="submit" disabled={saving}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
          Add room
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <ul className="mt-4 divide-y divide-ink-100 dark:divide-ink-800 rounded-xl border border-ink-200/70 dark:border-ink-800">
        {rows.map((r) => (
          <li key={r.room_id} className="flex items-center justify-between gap-3 px-4 py-3">
            <span className="text-sm font-medium text-ink-900 dark:text-white">{r.name}</span>
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
