import { useState } from 'react';
import OrdersTab from './dialysis/OrdersTab';
import RenalProfileTab from './dialysis/RenalProfileTab';
import RosterTab from './dialysis/RosterTab';
import MachinesTab from './dialysis/MachinesTab';
import ChecklistsConfigTab from './dialysis/ChecklistsConfigTab';

const TABS = [
  { key: 'sessions', label: 'Sessions' },
  { key: 'profile', label: 'Renal Profile' },
  { key: 'roster', label: 'Roster' },
  { key: 'machines', label: 'Machines' },
  { key: 'checklists', label: 'Checklists' },
];

export default function Dialysis() {
  const [tab, setTab] = useState('sessions');
  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-semibold text-ink-900 dark:text-white">Dialysis</h1>
      <div className="mt-4 flex gap-2 border-b border-ink-200/70 dark:border-ink-800" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-md ${
              tab === t.key
                ? 'bg-white dark:bg-ink-900 border border-b-0 border-ink-200/70 dark:border-ink-800 text-blue-600 dark:text-blue-400'
                : 'text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === 'sessions' && <OrdersTab />}
        {tab === 'profile' && <RenalProfileTab />}
        {tab === 'roster' && <RosterTab />}
        {tab === 'machines' && <MachinesTab />}
        {tab === 'checklists' && <ChecklistsConfigTab />}
      </div>
    </div>
  );
}
