import { useState } from 'react';
import { Scissors } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import CasesTab from './theatre/CasesTab';
import RoomsTab from './theatre/RoomsTab';
import ChecklistsConfigTab from './theatre/ChecklistsConfigTab';

const TABS = [
  { key: 'cases', label: 'Cases' },
  { key: 'rooms', label: 'Rooms' },
  { key: 'checklists', label: 'Checklists' },
];

export default function Theatre() {
  const [tab, setTab] = useState('cases');
  return (
    <div className="p-4 md:p-6">
      <PageHeader
        eyebrow="Surgery"
        icon={Scissors}
        title="Theatre & Surgery"
        subtitle="Schedule cases, run the WHO safety checklist, and record operative notes, anaesthesia and billing."
      />
      <div className="flex gap-2 border-b border-ink-200/70 dark:border-ink-800" role="tablist">
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
        {tab === 'cases' && <CasesTab />}
        {tab === 'rooms' && <RoomsTab />}
        {tab === 'checklists' && <ChecklistsConfigTab />}
      </div>
    </div>
  );
}
